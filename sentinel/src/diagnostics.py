import subprocess
import logging
import requests
import dns.resolver
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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

def check_dns(hostname="google.com", dns_server="8.8.8.8", timeout=2.0):
    """
    Tries to resolve a hostname using a specific DNS server.
    Returns (success: bool, latency_ms: float) tuple.
    """
    resolver = dns.resolver.Resolver()
    resolver.nameservers = [dns_server]
    try:
        start = time.time()
        resolver.resolve(hostname, 'A', lifetime=timeout)
        latency = (time.time() - start) * 1000  # Convert to ms
        return (True, round(latency, 2))
    except Exception as e:
        logger.warning(f"DNS check failed for {hostname} via {dns_server}: {e}")
        return (False, None)

def check_http(url, timeout=10.0):
    """
    Returns (success: bool, latency_ms: float) tuple.
    """
    try:
        start = time.time()
        r = requests.get(url, timeout=timeout)
        latency = (time.time() - start) * 1000  # Convert to ms
        success = r.status_code >= 200 and r.status_code < 300
        return (success, round(latency, 2) if success else None)
    except Exception as e:
        logger.warning(f"HTTP check failed for {url}: {e}")
        return (False, None)

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

def check_multi_dns(domains=None, dns_servers=None, timeout=2.0):
    """
    Check DNS resolution for multiple domains across one or more DNS servers.
    A domain is considered successful if at least one DNS server resolves it.
    All checks run in parallel for speed.
    Returns dict with success count, failed domains, and average latency.
    """
    if domains is None:
        domains = ["google.com", "cloudflare.com", "amazon.com", "github.com"]

    # Default to a well known public resolver if no servers are provided.
    if not dns_servers:
        dns_servers = ["8.8.8.8"]

    # Create all DNS check tasks (domain, dns_server pairs)
    tasks = [(domain, dns_server) for domain in domains for dns_server in dns_servers]

    # Run all checks in parallel
    results_by_domain = {domain: [] for domain in domains}

    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        future_to_task = {
            executor.submit(check_dns, domain, dns_server, timeout): (domain, dns_server)
            for domain, dns_server in tasks
        }

        for future in as_completed(future_to_task):
            domain, dns_server = future_to_task[future]
            try:
                success, latency_ms = future.result()
                if success and latency_ms is not None:
                    results_by_domain[domain].append(latency_ms)
            except Exception as e:
                logger.error(f"DNS check exception for {domain} via {dns_server}: {e}")

    # Aggregate results
    latencies_ms = []
    failed_domains = []

    for domain in domains:
        if results_by_domain[domain]:
            latencies_ms.extend(results_by_domain[domain])
        else:
            failed_domains.append(domain)

    success_count = len(domains) - len(failed_domains)

    return {
        'success_count': success_count,
        'total': len(domains),
        'failed_domains': failed_domains,
        'avg_latency': round(statistics.mean(latencies_ms), 2) if latencies_ms else None,
        'all_succeeded': success_count == len(domains)
    }

def check_multi_http(endpoints=None, timeout=10.0):
    """
    Check HTTP connectivity to multiple reliable endpoints.
    All checks run in parallel for speed.
    Returns dict with success count, failed endpoints, and average latency.
    """
    if endpoints is None:
        endpoints = [
            "http://captive.apple.com/hotspot-detect.html",  # Apple connectivity check
            "https://www.cloudflare.com/cdn-cgi/trace",      # Cloudflare trace
            "http://www.google.com/generate_204",            # Google no-content
            "https://www.github.com"                          # GitHub
        ]

    results = []
    failed = []

    # Run all HTTP checks in parallel
    with ThreadPoolExecutor(max_workers=len(endpoints)) as executor:
        future_to_url = {
            executor.submit(check_http, url, timeout): url
            for url in endpoints
        }

        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                success, latency = future.result()
                if success:
                    results.append(latency)
                else:
                    failed.append(url)
            except Exception as e:
                logger.error(f"HTTP check exception for {url}: {e}")
                failed.append(url)

    return {
        'success_count': len(results),
        'total': len(endpoints),
        'failed_endpoints': failed,
        'avg_latency': round(statistics.mean(results), 2) if results else None,
        'all_succeeded': len(failed) == 0
    }

def calculate_jitter(latency_samples):
    """
    Calculate jitter (standard deviation of latency) from samples.
    latency_samples should be a list of latency values in ms.
    """
    if not latency_samples or len(latency_samples) < 2:
        return None

    try:
        return round(statistics.stdev(latency_samples), 2)
    except Exception as e:
        logger.warning(f"Failed to calculate jitter: {e}")
        return None

def check_router_health(router_ip="192.168.1.1", samples=5):
    """
    Check router health with multiple metrics:
    - Packet loss rate
    - Average latency
    - Latency consistency (jitter to router)
    Returns dict with health assessment.
    """
    latencies = []
    failures = 0

    for i in range(samples):
        latency = check_ping(router_ip, timeout=1)
        if latency is None:
            failures += 1
        else:
            latencies.append(latency)
        time.sleep(0.1)  # Small delay between pings

    return {
        'packet_loss_rate': round((failures / samples) * 100, 1),
        'avg_latency': round(statistics.mean(latencies), 2) if latencies else None,
        'jitter': calculate_jitter(latencies) if len(latencies) >= 2 else None,
        'health_score': calculate_router_health_score(latencies, failures, samples)
    }

def calculate_router_health_score(latencies, failures, total_samples):
    """
    Score router health 0-100 (100 = perfect)
    Based on: packet loss, latency, jitter
    """
    if not latencies and failures == total_samples:
        return 0  # Completely unresponsive

    # Start with 100 points
    score = 100

    # Deduct for packet loss (10 points per 20% loss)
    loss_rate = failures / total_samples
    score -= (loss_rate * 50)

    # Deduct for high latency (1 point per ms over 5ms)
    if latencies:
        avg_latency = statistics.mean(latencies)
        if avg_latency > 5:
            score -= (avg_latency - 5)

    # Deduct for high jitter (2 points per ms jitter)
    if len(latencies) >= 2:
        jitter = statistics.stdev(latencies)
        score -= (jitter * 2)

    return max(0, min(100, round(score)))

def run_cloudflare_speedtest():
    """
    Run Cloudflare speed test using their API.
    Returns dict with download/upload speeds in Mbps.
    """
    try:
        # Cloudflare speed test endpoint
        # Using a simple download test
        test_url = "https://speed.cloudflare.com/__down?bytes=25000000"  # 25MB download

        start = time.time()
        response = requests.get(test_url, timeout=30)
        duration = time.time() - start

        if response.status_code == 200:
            bytes_downloaded = len(response.content)
            # Convert to Mbps: (bytes * 8) / (duration * 1000000)
            download_mbps = round((bytes_downloaded * 8) / (duration * 1000000), 2)

            return {
                'download_mbps': download_mbps,
                'latency_ms': round(duration * 1000, 2)
            }
        else:
            logger.error(f"Cloudflare speedtest failed with status {response.status_code}")
            return None

    except Exception as e:
        logger.error(f"Cloudflare speedtest failed: {e}")
        return None
