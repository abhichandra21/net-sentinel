import time
import yaml
import logging
import sys
import os
import schedule
from collections import deque
from diagnostics import (
    check_ping, check_dns, check_http, check_multi_dns, check_multi_http,
    run_traceroute, check_interface_status, run_speedtest,
    run_cloudflare_speedtest, calculate_jitter, check_router_health
)
from notifier import Notifier

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("Sentinel")

# Global latency tracking for jitter calculation (last 10 samples)
latency_history = deque(maxlen=10)

def load_config():
    config_path = os.environ.get('CONFIG_PATH', 'config/config.yaml')
    if not os.path.exists(config_path):
        config_path = '../../config/config.yaml'

    if not os.path.exists(config_path):
        logger.error(f"Config file not found. Tried: config/config.yaml and ../../config/config.yaml")
        logger.error(f"Current directory: {os.getcwd()}")
        logger.error(f"Set CONFIG_PATH environment variable or run from project root")
        sys.exit(1)

    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def perform_health_check(targets, http_endpoints=None):
    """
    Comprehensive health check across multiple layers.
    Returns dict with results from each check.
    """
    results = {}

    # Layer 0: Router health (detailed metrics)
    results['router_health'] = check_router_health(targets['router'])

    # Layer 1: Local network (your router) - basic ping
    results['router'] = check_ping(targets['router'])

    # Layer 2: ISP gateway (if configured)
    if targets.get('isp_gateway'):
        results['isp_gateway'] = check_ping(targets['isp_gateway'])

    # Layer 3: DNS resolution across multiple domains.
    # Prefer DNS servers from configuration if provided so DNS failures
    # reflect the actual resolvers in use rather than a hard coded default.
    dns_servers = [
        dns_ip for dns_ip in (
            targets.get('public_dns_1'),
            targets.get('public_dns_2')
        ) if dns_ip
    ]
    if dns_servers:
        dns_results = check_multi_dns(dns_servers=dns_servers)
    else:
        dns_results = check_multi_dns()
    results['dns'] = dns_results

    # Layer 4: HTTP connectivity across multiple endpoints.
    # Allow overriding default endpoints from configuration when provided.
    if http_endpoints:
        http_results = check_multi_http(endpoints=http_endpoints)
    else:
        http_results = check_multi_http()
    results['http'] = http_results

    # Track latency for jitter calculation
    if http_results['avg_latency']:
        latency_history.append(http_results['avg_latency'])

    # Calculate current jitter
    results['jitter'] = calculate_jitter(list(latency_history))

    return results

def perform_speedtest(notifier, use_cloudflare=True):
    """
    Run speed test and report results.
    Tries Cloudflare first (faster), falls back to speedtest-cli.
    """
    logger.info("Running scheduled speedtest...")

    if use_cloudflare:
        cf_result = run_cloudflare_speedtest()
        if cf_result:
            logger.info(f"Cloudflare Speedtest - Down: {cf_result['download_mbps']} Mbps")
            notifier.update_state("download_speed", cf_result['download_mbps'])
            notifier.update_state("speedtest_latency", cf_result['latency_ms'])
            return

    # Fallback to speedtest-cli
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

def diagnose_issue(targets, results, notifier):
    """
    Fault isolation: determine if it's YOUR equipment or the ISP.
    Returns clear blame attribution.
    """
    logger.info("Issue detected. Starting fault isolation...")

    # Layer 0: ROUTER HEALTH (detailed check)
    router_health = results.get('router_health', {})
    if router_health:
        health_score = router_health.get('health_score', 100)
        packet_loss = router_health.get('packet_loss_rate', 0)

        # Check if router is critically unhealthy
        if health_score < 30:
            blame = "ROUTER_CRITICAL"
            logger.error(f"⚠️  FAULT: ROUTER CRITICAL - Health score {health_score}/100")
            logger.error(f"  Packet loss: {packet_loss}%, Latency: {router_health.get('avg_latency')}ms, Jitter: {router_health.get('jitter')}ms")
            notifier.log_event("OUTAGE", "Router", f"Router health critical ({health_score}/100) - hardware issue", "CRITICAL")
            notifier.update_state("blame", "ROUTER_CRITICAL")
            notifier.update_state("fault_detail", f"Router health critical (score: {health_score}/100, packet loss: {packet_loss}%) - possible hardware failure or overload")
            return blame

        # Check if router is degraded
        elif health_score < 60:
            # Router is struggling, check if ISP also has issues
            dns_check = results.get('dns', {})
            http_check = results.get('http', {})

            if dns_check.get('all_succeeded', True) and http_check.get('all_succeeded', True):
                # Only router is degraded, ISP seems fine
                blame = "ROUTER_DEGRADED"
                logger.warning(f"⚠️  DEGRADED: Router performance degraded (score: {health_score}/100)")
                notifier.log_event("DEGRADED", "Router", f"Router performance degraded (score: {health_score}/100)", "WARNING")
                notifier.update_state("blame", "ROUTER_DEGRADED")
                notifier.update_state("fault_detail", f"Router degraded (score: {health_score}/100) - high latency or packet loss")
                return blame
            # If ISP also has issues, continue to ISP diagnosis
            logger.warning(f"Router degraded (score: {health_score}/100) but ISP also has issues - checking ISP...")

    # Layer 1: YOUR ROUTER/MODEM - Basic reachability
    if results['router'] is None:
        blame = "ROUTER_DOWN"
        logger.error("⚠️  FAULT: ROUTER DOWN - Router is unreachable")
        notifier.log_event("OUTAGE", "Router", "Router is not responding to ping", "CRITICAL")
        notifier.update_state("blame", "ROUTER_DOWN")
        notifier.update_state("fault_detail", "Router not responding to ping - check power and cables")
        return blame

    # Layer 2: ISP GATEWAY/EQUIPMENT
    if targets.get('isp_gateway') and results.get('isp_gateway') is None:
        blame = "ISP_EQUIPMENT"
        logger.error("⚠️  FAULT: ISP EQUIPMENT - ISP gateway unreachable")
        trace = run_traceroute(targets['isp_gateway'])
        notifier.log_event("OUTAGE", "ISP", f"ISP gateway unreachable. Trace: {trace[-200:]}", "CRITICAL")
        notifier.update_state("blame", "ISP_EQUIPMENT")
        notifier.update_state("fault_detail", "ISP gateway down - contact your ISP")
        return blame

    # Layer 3: DNS FAILURES (likely resolver or upstream DNS issues)
    dns_check = results.get('dns', {})
    if not dns_check.get('all_succeeded', True):
        failed_count = len(dns_check.get('failed_domains', []))
        total = dns_check.get('total', 0)

        if failed_count == total:
            # Complete DNS failure across all tested resolvers.
            # If HTTP checks also show a complete failure, treat this as a
            # broader upstream connectivity or routing problem rather than a
            # pure DNS issue.
            http_snapshot = results.get('http', {})
            http_failed_total = False
            if not http_snapshot.get('all_succeeded', True):
                http_failed_count = len(http_snapshot.get('failed_endpoints', []))
                http_total = http_snapshot.get('total', 0)
                if http_total and http_failed_count == http_total:
                    http_failed_total = True

            if http_failed_total:
                blame = "ISP_ROUTING"
                logger.error("FAULT: ISP ROUTING - DNS and HTTP checks both failed")
                trace = run_traceroute("8.8.8.8")
                notifier.log_event(
                    "OUTAGE",
                    "ISP",
                    f"DNS and HTTP checks failed. Trace: {trace[-200:]}",
                    "CRITICAL",
                )
                notifier.update_state("blame", "ISP_ROUTING")
                notifier.update_state(
                    "fault_detail",
                    "DNS and HTTP failed - likely upstream connectivity or routing issue",
                )
            else:
                blame = "ISP_DNS"
                logger.error("FAULT: ISP DNS - All DNS lookups failed")
                notifier.log_event(
                    "OUTAGE",
                    "ISP_DNS",
                    "All DNS resolution failed - DNS servers down or unreachable",
                    "CRITICAL",
                )
                notifier.update_state("blame", "ISP_DNS")
                notifier.update_state(
                    "fault_detail",
                    "DNS completely failed - DNS resolver issue",
                )
        else:
            # Partial DNS failure
            blame = "DEGRADED_DNS"
            logger.warning(
                f"DEGRADED: DNS - {failed_count}/{total} DNS lookups failed"
            )
            notifier.log_event(
                "DEGRADED",
                "DNS",
                f"{failed_count}/{total} DNS failed: {dns_check.get('failed_domains')}",
                "WARNING",
            )
            notifier.update_state("blame", "DEGRADED_DNS")
            notifier.update_state(
                "fault_detail",
                "Partial DNS failure - some domains unreachable",
            )

        return blame

    # Layer 4: HTTP CONNECTIVITY (ISP routing/firewall)
    http_check = results.get('http', {})
    if not http_check.get('all_succeeded', True):
        failed_count = len(http_check.get('failed_endpoints', []))
        total = http_check.get('total', 0)

        if failed_count == total:
            # Complete internet failure
            blame = "ISP_ROUTING"
            logger.error(f"⚠️  FAULT: ISP ROUTING - All internet connectivity failed")
            trace = run_traceroute("8.8.8.8")
            notifier.log_event("OUTAGE", "ISP", f"Internet completely unreachable. Trace: {trace[-200:]}", "CRITICAL")
            notifier.update_state("blame", "ISP_ROUTING")
            notifier.update_state("fault_detail", "Internet unreachable - ISP routing/connection issue")
        else:
            # Partial internet failure
            blame = "DEGRADED_INTERNET"
            logger.warning(f"⚠️  DEGRADED: Internet - {failed_count}/{total} endpoints unreachable")
            notifier.log_event("DEGRADED", "Internet", f"{failed_count}/{total} endpoints failed", "WARNING")
            notifier.update_state("blame", "DEGRADED_INTERNET")
            notifier.update_state("fault_detail", f"Partial internet failure - some services unreachable")

        return blame

    # Layer 5: HIGH JITTER (degraded connection quality)
    jitter = results.get('jitter')
    if jitter and jitter > 50:  # >50ms jitter is bad
        blame = "DEGRADED_QUALITY"
        logger.warning(f"⚠️  DEGRADED: High jitter detected ({jitter}ms) - poor connection quality")
        notifier.log_event("DEGRADED", "Quality", f"High jitter: {jitter}ms - connection unstable", "WARNING")
        notifier.update_state("blame", "DEGRADED_QUALITY")
        notifier.update_state("fault_detail", f"High jitter ({jitter}ms) - unstable connection")
        return blame

    # If we got here, issue was transient
    logger.info("Issue appears transient - all checks now passing")
    notifier.update_state("blame", "TRANSIENT")
    notifier.update_state("fault_detail", "Issue resolved - was temporary")
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
    http_endpoints = config['monitoring'].get('http_endpoints')
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
            results = perform_health_check(targets, http_endpoints=http_endpoints)

            # Determine health status
            dns_healthy = results.get('dns', {}).get('all_succeeded', False)
            http_healthy = results.get('http', {}).get('all_succeeded', False)
            router_healthy = results['router'] is not None

            is_healthy = router_healthy and dns_healthy and http_healthy

            if is_healthy:
                consecutive_failures = 0
                notifier.update_state("status", "HEALTHY")
                notifier.update_state("blame", "NONE")

                # Report metrics
                notifier.update_state("router_latency", results['router'])

                # Report router health metrics
                router_health = results.get('router_health', {})
                if router_health:
                    notifier.update_state("router_health_score", router_health.get('health_score'))
                    notifier.update_state("router_packet_loss", router_health.get('packet_loss_rate'))
                    notifier.update_state("router_jitter_internal", router_health.get('jitter'))

                dns_data = results.get('dns', {})
                notifier.update_state("dns_latency", dns_data.get('avg_latency'))
                notifier.update_state("dns_success_rate", f"{dns_data.get('success_count', 0)}/{dns_data.get('total', 0)}")

                http_data = results.get('http', {})
                notifier.update_state("http_latency", http_data.get('avg_latency'))
                notifier.update_state("http_success_rate", f"{http_data.get('success_count', 0)}/{http_data.get('total', 0)}")

                # Jitter tracking
                if results.get('jitter'):
                    notifier.update_state("jitter", results['jitter'])
                router_health_str = f", Router Health: {router_health.get('health_score')}/100" if router_health else ""
                logger.info(f"✓ Healthy - DNS: {dns_data.get('avg_latency')}ms, HTTP: {http_data.get('avg_latency')}ms, Jitter: {results.get('jitter')}ms{router_health_str}")

            else:
                consecutive_failures += 1
                logger.warning(f"Health Check Failed. Consecutive: {consecutive_failures}")

                if consecutive_failures >= 3:  # Wait for 3 cycles to confirm
                    notifier.update_state("status", "DIAGNOSING")
                    blame = diagnose_issue(targets, results, notifier)
                    notifier.update_state("status", f"OUTAGE_{blame}")

                    # Log detailed failure info
                    logger.error(f"OUTAGE CONFIRMED - Blame: {blame}")
                    if not dns_healthy:
                        logger.error(f"  DNS: {results.get('dns', {}).get('failed_domains')}")
                    if not http_healthy:
                        logger.error(f"  HTTP: {results.get('http', {}).get('failed_endpoints')}")

            time.sleep(interval)

        except KeyboardInterrupt:
            logger.info("Stopping.")
            break
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
            time.sleep(interval)

if __name__ == "__main__":
    main()
