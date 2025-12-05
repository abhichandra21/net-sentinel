# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Net Sentinel is a dual-probe network monitoring system for diagnosing intermittent internet connectivity issues with clear fault attribution. The system determines WHO IS TO BLAME: your router, your ISP, or network degradation.

**Key Components:**
1. **Local Sentinel** (Docker) - Runs on home network, monitors router → ISP → DNS → HTTP connectivity
2. **Cloud Probe** (Python VPS service) - Monitors home reachability from external internet
3. **Home Assistant Integration** - Central hub via MQTT + webhooks for dashboards and alerts

## Development Commands

### Docker Container (Local Sentinel)

```bash
# Build and start container
docker-compose up -d --build

# View logs
docker logs -f net-sentinel

# Stop container
docker-compose down

# Rebuild after code changes
docker-compose up -d --build --force-recreate
```

### Cloud Probe Deployment

```bash
# Deploy to VPS
./deploy_cloud_probe.sh <your-home-ddns-or-ip>

# View VPS logs
ssh -i ~/.ssh/aws.pub ubuntu@ssh-day1.abhichandra.com 'sudo journalctl -u cloud-probe -f'

# Restart cloud probe service
ssh -i ~/.ssh/aws.pub ubuntu@ssh-day1.abhichandra.com 'sudo systemctl restart cloud-probe'
```

### Testing Python Code Locally

```bash
# Install dependencies
pip3 install -r sentinel/requirements.txt

# Run sentinel directly (requires config/config.yaml)
cd sentinel/src
python3 monitor.py

# Test diagnostics individually
python3 -c "from diagnostics import check_ping; print(check_ping('192.168.1.1'))"
```

## Architecture

### System Flow

```
Local Sentinel Container (sentinel/src/monitor.py)
  ├─ Every 30s: perform_health_check()
  │   ├─ check_router_health() → 5 pings, packet loss, jitter, health score
  │   ├─ check_ping(router) → basic reachability
  │   ├─ check_ping(isp_gateway) → ISP first hop
  │   ├─ check_multi_dns() → test google.com, cloudflare.com, amazon.com, github.com
  │   ├─ check_multi_http() → test Apple, Cloudflare, Google, GitHub endpoints
  │   └─ calculate_jitter() → latency variance from last 10 samples
  │
  ├─ Every 6h: perform_speedtest()
  │   └─ Cloudflare speedtest (primary) or speedtest-cli (fallback)
  │
  ├─ On failure (3 consecutive): diagnose_issue()
  │   └─ Returns fault code: ROUTER_*, ISP_*, DEGRADED_*, TRANSIENT
  │
  └─ Publish to MQTT (notifier.py)
      └─ Topic: home/network/sentinel/<sensor>

Cloud Probe (cloud_probe/main.py)
  ├─ Every 60s: check_home_connectivity()
  │   └─ HTTP GET to home public IP/DDNS
  │
  └─ POST to Home Assistant webhook
      └─ Payload: {source, status, latency}

Home Assistant
  ├─ MQTT Broker: receives Local Sentinel data
  ├─ Webhook: receives Cloud Probe data
  └─ Dashboard: displays all metrics + fault attribution
```

### Fault Attribution Logic (monitor.py:diagnose_issue)

The system performs layered diagnostics in this order:

1. **Router Health** - Detailed metrics (packet loss, jitter, health score)
   - Critical: score < 30 → `ROUTER_CRITICAL`
   - Degraded: score < 60 → `ROUTER_DEGRADED`

2. **Router Reachability** - Basic ping
   - Unreachable → `ROUTER_DOWN`

3. **ISP Gateway** - First hop beyond router
   - Unreachable → `ISP_EQUIPMENT`

4. **DNS Resolution** - Multiple domains across configured DNS servers
   - All failed + HTTP failed → `ISP_ROUTING`
   - All DNS failed only → `ISP_DNS`
   - Partial failure → `DEGRADED_DNS`

5. **HTTP Connectivity** - Multiple public endpoints
   - All failed → `ISP_ROUTING`
   - Partial failure → `DEGRADED_INTERNET`

6. **Connection Quality** - Jitter measurement
   - Jitter > 50ms → `DEGRADED_QUALITY`

7. **Transient** - Issue resolved → `TRANSIENT`

### Configuration Structure (config/config.yaml)

```yaml
monitoring:
  interval_seconds: 30
  targets:
    router: "192.168.1.1"
    isp_gateway: null  # Optional ISP first hop
    public_dns_1: "8.8.8.8"
    public_dns_2: "1.1.1.1"
  http_endpoints:  # Optional override
    - "http://captive.apple.com/hotspot-detect.html"
    - "https://www.cloudflare.com/cdn-cgi/trace"
  speedtest:
    use_cloudflare: true
    interval_hours: 6

mqtt:
  broker: "192.168.1.50"
  port: 1883
  username: "username"
  password: "password"
  topic_prefix: "home/network/sentinel"

logging:
  file_path: "/data/network_events.csv"
```

### Core Modules

**sentinel/src/monitor.py** (393 lines)
- Main orchestration loop
- Calls diagnostics functions every interval
- Determines fault attribution
- Publishes to MQTT via notifier

**sentinel/src/diagnostics.py** (265 lines)
- `check_ping(host)` - ICMP ping via ping3
- `check_dns(hostname, dns_server)` - DNS resolution timing
- `check_http(url)` - HTTP request timing
- `check_multi_dns(domains, dns_servers)` - Test multiple domains/servers
- `check_multi_http(endpoints)` - Test multiple HTTP endpoints
- `check_router_health(router_ip, samples=5)` - Detailed router metrics
- `calculate_router_health_score()` - 0-100 scoring algorithm
- `run_cloudflare_speedtest()` - Fast speed test via Cloudflare API
- `run_speedtest()` - Fallback via speedtest-cli
- `calculate_jitter(latency_samples)` - Standard deviation of latency

**sentinel/src/notifier.py** (112 lines)
- MQTT client wrapper (paho-mqtt)
- Auto-discovery for Home Assistant
- `update_state(key, value)` - Publish sensor updates
- `log_event(event_type, target, details, severity)` - CSV logging

**cloud_probe/main.py** (78 lines)
- Standalone HTTP connectivity checker
- Runs on external VPS as systemd service
- POSTs results to Home Assistant webhook

## Important Implementation Details

### DNS Configuration Override

The `check_multi_dns()` function allows overriding DNS servers from config to test the actual resolvers in use:

```python
dns_servers = [
    dns_ip for dns_ip in (
        targets.get('public_dns_1'),
        targets.get('public_dns_2')
    ) if dns_ip
]
if dns_servers:
    dns_results = check_multi_dns(dns_servers=dns_servers)
else:
    dns_results = check_multi_dns()  # Uses default 8.8.8.8
```

### HTTP Endpoint Override

Similarly, HTTP endpoints can be overridden in config to test specific services:

```python
if http_endpoints:
    http_results = check_multi_http(endpoints=http_endpoints)
else:
    http_results = check_multi_http()  # Uses default endpoints
```

### Router Health Scoring Algorithm

Router health score (0-100) is calculated from:
- **Packet loss**: -50 points for 100% loss, -25 for 50% loss, etc.
- **Latency**: -1 point per ms over 5ms baseline
- **Jitter**: -2 points per ms of standard deviation

Code location: `diagnostics.py:calculate_router_health_score`

### Consecutive Failure Threshold

The system waits for 3 consecutive failures before triggering fault diagnosis to avoid false positives from transient network glitches:

```python
if consecutive_failures >= 3:
    notifier.update_state("status", "DIAGNOSING")
    blame = diagnose_issue(targets, results, notifier)
```

### Docker Network Configuration

The container uses `network_mode: "host"` and `privileged: true` for:
- Accurate ICMP ping from the host network perspective
- Local network discovery (router at 192.168.1.1)
- Traceroute functionality

## File Locations

### Configuration & Data
- `config/config.yaml` - Main configuration (mounted to `/app/config` in container)
- `data/network_events.csv` - Event log (mounted to `/data` in container)

### Python Source
- `sentinel/src/monitor.py` - Main monitoring loop
- `sentinel/src/diagnostics.py` - Network diagnostic utilities
- `sentinel/src/notifier.py` - MQTT publisher and CSV logger
- `cloud_probe/main.py` - External VPS probe

### Deployment
- `docker-compose.yml` - Container orchestration
- `sentinel/Dockerfile` - Container build definition
- `sentinel/requirements.txt` - Python dependencies
- `deploy_cloud_probe.sh` - Cloud probe deployment script

### Home Assistant
- `ha_complete_setup.yaml` - Full HA configuration (helpers, automation, dashboard)
- `ha_comprehensive_setup.yaml` - Extended MQTT sensor definitions
- `ha_dashboard.yaml` - Lovelace dashboard cards

## Known Configuration Details

**VPS Details:**
- Host: `ssh-day1.abhichandra.com`
- User: `ubuntu`
- SSH Key: `~/.ssh/aws.pub`
- Service: `cloud-probe.service`

**Home Network:**
- Router: `192.168.1.1`
- Home Assistant: `192.168.1.50`
- Docker Host: `192.168.1.3`
- MQTT Port: `1883`

**Home Assistant Webhook:**
- ID: `net-sentinel-cloud-probe-2025`
- URL: `http://192.168.1.50:8123/api/webhook/net-sentinel-cloud-probe-2025`

## Modifying Behavior

### Adding New Diagnostic Checks

1. Add check function to `diagnostics.py`
2. Call from `perform_health_check()` in `monitor.py`
3. Add result handling in main loop
4. Publish new metric via `notifier.update_state()`

### Adding New Fault Codes

1. Add detection logic in `diagnose_issue()` function in `monitor.py`
2. Return new fault code string
3. Update `ha_dashboard.yaml` to display new code
4. Document in README.md fault attribution table

### Changing Monitoring Intervals

Edit `config/config.yaml`:
- `monitoring.interval_seconds` - Main health check frequency
- `monitoring.speedtest.interval_hours` - Speed test frequency

Speedtest scheduling uses `schedule` library in `monitor.py:main()`:
```python
schedule.every(6).hours.do(perform_speedtest, notifier=notifier)
```

### Adding New MQTT Sensors

1. Publish from `monitor.py` via `notifier.update_state(key, value)`
2. Add sensor definition to `ha_comprehensive_setup.yaml`
3. Add to dashboard in `ha_dashboard.yaml`

Auto-discovery handles sensor registration automatically via MQTT discovery protocol.
