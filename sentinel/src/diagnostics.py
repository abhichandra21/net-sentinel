import subprocess
import logging
import requests
import dns.resolver
from ping3 import ping

logger = logging.getLogger("Diagnostics")

def check_ping(host, count=1, timeout=2):
    """
    Returns average latency in ms or None if failed.
    """
    try:
        # ping3 returns seconds. Return ms.
        r = ping(host, timeout=timeout, unit='ms')
        if r is None:
            return None
        return round(r, 2)
    except Exception as e:
        logger.error(f"Ping error for {host}: {e}")
        return None

def check_dns(hostname="google.com", dns_server="8.8.8.8"):
    """
    Tries to resolve a hostname using a specific DNS server.
    Returns True if successful.
    """
    resolver = dns.resolver.Resolver()
    resolver.nameservers = [dns_server]
    try:
        resolver.resolve(hostname, 'A', lifetime=3)
        return True
    except Exception as e:
        logger.warning(f"DNS check failed for {hostname} via {dns_server}: {e}")
        return False

def check_http(url):
    """
    Returns True if HTTP GET status is 200-299.
    """
    try:
        r = requests.get(url, timeout=5)
        return r.status_code >= 200 and r.status_code < 300
    except Exception as e:
        logger.warning(f"HTTP check failed for {url}: {e}")
        return False

def run_traceroute(target="8.8.8.8"):
    """
    Runs a system traceroute and returns the output as a string.
    Useful for logs.
    """
    try:
        # -n: Do not resolve IP addresses to their domain names
        # -m 10: Max 10 hops (for speed)
        # -w 2: Wait max 2 seconds
        cmd = ["traceroute", "-n", "-m", "10", "-w", "2", target]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.stdout
    except Exception as e:
        return f"Traceroute failed: {e}"

def check_interface_status():
    """
    Simple check of local IP routing/interface.
    """
    try:
        result = subprocess.run(["ip", "route"], capture_output=True, text=True)
        return result.stdout
    except Exception:
        return "Could not determine interface status."

def run_speedtest():
    """
    Runs a speedtest and returns download/upload in Mbps.
    """
    try:
        # Using speedtest-cli via subprocess to avoid blocking the main thread indefinitely 
        # if we were using the library in-process without threading.
        # Also, simple JSON output is easy to parse.
        cmd = ["speedtest-cli", "--simple"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return result.stdout
    except Exception as e:
        logger.error(f"Speedtest failed: {e}")
        return None
