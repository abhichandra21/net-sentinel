import os
import time
import logging
import requests
import argparse
from ping3 import ping

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("CloudProbe")

def check_home_connectivity(hostname):
    """
    Pings the home public IP/Hostname.
    """
    try:
        latency = ping(hostname, timeout=4, unit='ms')
        if latency is None:
            return False, None
        return True, latency
    except Exception as e:
        logger.error(f"Ping failed: {e}")
        return False, None

def notify_home_assistant(webhook_url, status, latency):
    """
    Sends data to Home Assistant via Webhook trigger.
    """
    payload = {
        "source": "cloud_probe",
        "status": "online" if status else "offline",
        "latency": latency
    }
    try:
        requests.post(webhook_url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"Failed to notify Home Assistant: {e}")

def main():
    parser = argparse.ArgumentParser(description='Cloud Probe for Home Network')
    parser.add_argument('--target', required=True, help='Home DDNS Hostname or Static IP')
    parser.add_argument('--webhook', required=True, help='Home Assistant Webhook URL')
    parser.add_argument('--interval', type=int, default=60, help='Check interval in seconds')
    args = parser.parse_args()

    logger.info(f"Starting Cloud Probe targeting {args.target}")

    while True:
        is_up, latency = check_home_connectivity(args.target)
        
        if is_up:
            logger.info(f"Home is UP. Latency: {latency}ms")
        else:
            logger.warning("Home is DOWN.")

        # Always notify (or notify on change - keeping it simple here)
        notify_home_assistant(args.webhook, is_up, latency)
        
        time.sleep(args.interval)

if __name__ == "__main__":
    main()
