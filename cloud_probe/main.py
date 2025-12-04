import os
import time
import logging
import requests
import argparse

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("CloudProbe")

def check_home_connectivity(url):
    """
    Check if home is reachable via HTTP/HTTPS.
    Returns: (is_reachable: bool, latency_ms: float)
    """
    try:
        start = time.time()
        # Use HEAD request to minimize data transfer
        response = requests.head(url, timeout=5, allow_redirects=True)
        latency_ms = (time.time() - start) * 1000

        # Any 2xx or 3xx status code means it's reachable
        if response.status_code < 400:
            # Ensure we return a valid number
            latency_value = round(float(latency_ms), 2) if latency_ms is not None else None
            return True, latency_value
        else:
            logger.warning(f"HTTP check returned status {response.status_code}")
            return False, None
    except requests.exceptions.RequestException as e:
        logger.debug(f"HTTP check failed for {url}: {e}")
        return False, None
    except Exception as e:
        logger.error(f"Unexpected error checking {url}: {e}")
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
    parser.add_argument('--target', required=True, help='Home URL to check (e.g., https://homeassistant.abhichandra.com)')
    parser.add_argument('--webhook', required=True, help='Home Assistant Webhook URL')
    parser.add_argument('--interval', type=int, default=60, help='Check interval in seconds')
    args = parser.parse_args()

    logger.info(f"Starting Cloud Probe targeting {args.target}")

    while True:
        is_up, latency = check_home_connectivity(args.target)

        if is_up:
            latency_str = f"{latency:.2f}" if latency is not None else "unknown"
            logger.info(f"Home is UP. Latency: {latency_str}ms")
        else:
            logger.warning("Home is DOWN.")

        # Always notify (or notify on change - keeping it simple here)
        notify_home_assistant(args.webhook, is_up, latency)

        time.sleep(args.interval)

if __name__ == "__main__":
    main()
