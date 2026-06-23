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
        # Use GET request for better compatibility (some servers don't handle HEAD well)
        response = requests.get(url, timeout=5, allow_redirects=True, stream=True)
        # Read just the first byte to ensure connection is established
        response.raw.read(1)
        latency_ms = (time.time() - start) * 1000

        # Any 2xx or 3xx status code means it's reachable
        if response.status_code < 400:
            # Ensure we return a valid number
            latency_value = round(float(latency_ms), 2)
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

def update_debounce(state, is_up, latency, threshold):
    """
    Debounce flapping observations. Returns (new_state, changed).
    Status flips only after `threshold` consecutive same-direction reads.
    """
    desired = "online" if is_up else "offline"
    if desired == state["status"]:
        stable_latency = latency if desired == "online" else None
        return {
            "status": state["status"],
            "streak": 0,
            "latency": stable_latency,
        }, False
    streak = state["streak"] + 1
    if streak >= threshold:
        stable_latency = latency if desired == "online" else None
        return {
            "status": desired,
            "streak": 0,
            "latency": stable_latency,
        }, True
    return {
        "status": state["status"],
        "streak": streak,
        "latency": state.get("latency"),
    }, False

def notification_for_state(state):
    """Return webhook arguments for a confirmed status, else None."""
    if state["status"] is None:
        return None
    return (state["status"] == "online", state.get("latency"))

def main():
    parser = argparse.ArgumentParser(description='Cloud Probe for Home Network')
    parser.add_argument('--target', required=True, help='Home URL to check (e.g., https://homeassistant.abhichandra.com)')
    parser.add_argument('--webhook', required=True, help='Home Assistant Webhook URL')
    parser.add_argument('--interval', type=int, default=60, help='Check interval in seconds')
    args = parser.parse_args()

    logger.info(f"Starting Cloud Probe targeting {args.target}")

    state = {"status": None, "streak": 0, "latency": None}
    threshold = 3
    while True:
        is_up, latency = check_home_connectivity(args.target)
        state, changed = update_debounce(state, is_up, latency, threshold)
        if changed:
            logger.info(f"State change -> {state['status']}")
        notification = notification_for_state(state)
        if notification is not None:
            notify_home_assistant(args.webhook, *notification)
        time.sleep(args.interval)

if __name__ == "__main__":
    main()
