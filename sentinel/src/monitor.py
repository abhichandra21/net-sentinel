import time
import yaml
import logging
import sys
import os
import schedule
from diagnostics import check_ping, check_dns, check_http, run_traceroute, check_interface_status, run_speedtest
from notifier import Notifier

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("Sentinel")

def load_config():
    config_path = os.environ.get('CONFIG_PATH', 'config/config.yaml')
    if not os.path.exists(config_path):
        config_path = '../config/config.yaml'
    
    if not os.path.exists(config_path):
        logger.error(f"Config file not found at {config_path}")
        sys.exit(1)

    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def perform_health_check(targets):
    results = {}
    results['router'] = check_ping(targets['router'])
    if targets.get('isp_gateway'):
        results['isp'] = check_ping(targets['isp_gateway'])
    results['internet_ping'] = check_ping(targets['public_dns_1'])
    results['dns_resolution'] = check_dns("google.com", targets['public_dns_1'])
    return results

def perform_speedtest(notifier):
    logger.info("Running scheduled speedtest...")
    # speedtest-cli --simple returns:
    # Ping: X ms
    # Download: Y Mbit/s
    # Upload: Z Mbit/s
    output = run_speedtest()
    if output:
        try:
            lines = output.splitlines()
            download = lines[1].split(' ')[1]
            upload = lines[2].split(' ')[1]
            logger.info(f"Speedtest Result - Down: {download} Mbps, Up: {upload} Mbps")
            notifier.update_state("download_speed", download)
            notifier.update_state("upload_speed", upload)
        except Exception as e:
            logger.error(f"Failed to parse speedtest output: {e}")
            logger.debug(f"Output was: {output}")

def diagnose_issue(targets, quick_results, notifier):
    logger.info("Issue detected. Starting deep diagnostics...")
    
    if quick_results['router'] is None:
        logger.error("Router Unreachable")
        notifier.log_event("OUTAGE", "Router", "Router Unreachable", "CRITICAL")
        return "LOCAL_FAILURE"

    if targets.get('isp_gateway') and quick_results.get('isp') is None:
        logger.error("ISP Gateway Unreachable")
        notifier.log_event("OUTAGE", "ISP", "ISP Gateway Unreachable", "CRITICAL")
        return "ISP_FAILURE"

    if quick_results['internet_ping'] is None:
        logger.error("Internet Unreachable")
        trace = run_traceroute(targets['public_dns_1'])
        notifier.log_event("OUTAGE", "Internet", f"Public IP Unreachable. Trace: {trace[-100:]}", "CRITICAL")
        return "INTERNET_FAILURE"

    if not quick_results['dns_resolution']:
        logger.warning("DNS Resolution Failed")
        notifier.log_event("DEGRADED", "DNS", "DNS Resolution Failed", "WARNING")
        return "DNS_FAILURE"

    return "TRANSIENT"

def main():
    config = load_config()
    logger.info("Loading configuration...")
    
    # Create notifier with error handling
    try:
        logger.info("Creating MQTT notifier...")
        notifier = Notifier(config)
        logger.info(f"Notifier created. MQTT connected: {notifier.connected}")
    except Exception as e:
        logger.error(f"Failed to create notifier: {e}")
        logger.info("Continuing without MQTT...")
        # Create a dummy notifier for testing
        class DummyNotifier:
            def __init__(self): pass
            def update_state(self, key, value): 
                logger.info(f"Would update {key} to {value}")
            def log_event(self, *args): pass
            @property
            def connected(self): return False
        notifier = DummyNotifier()
    
    targets = config['monitoring']['targets']
    interval = config['monitoring']['interval_seconds']

    logger.info("Network Sentinel Started.")
    if notifier.connected:
        notifier.update_state("status", "Online")
    else:
        logger.info("MQTT not available, running in offline mode")

    # Schedule Speedtest every 6 hours
    schedule.every(6).hours.do(perform_speedtest, notifier=notifier)

    consecutive_failures = 0

    while True:
        try:
            # Run scheduled tasks (Speedtest)
            schedule.run_pending()

            # Main Health Check
            results = perform_health_check(targets)
            
            is_healthy = (
                results['router'] is not None and 
                results['internet_ping'] is not None and
                results['dns_resolution']
            )

            if is_healthy:
                consecutive_failures = 0
                notifier.update_state("status", "Online")
                notifier.update_state("router_latency", results['router'])
                notifier.update_state("internet_latency", results['internet_ping'])
            else:
                consecutive_failures += 1
                logger.warning(f"Health Check Failed. Consecutive: {consecutive_failures}")
                
                if consecutive_failures >= 3: # Wait for 3 cycles (e.g. 90s) to confirm
                    notifier.update_state("status", "Diagnosing")
                    diag_result = diagnose_issue(targets, results, notifier)
                    notifier.update_state("status", diag_result)
            
            time.sleep(interval)

        except KeyboardInterrupt:
            logger.info("Stopping.")
            break
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
            time.sleep(interval)

if __name__ == "__main__":
    main()