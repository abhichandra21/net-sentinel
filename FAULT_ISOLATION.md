# Internet Monitor - Fault Isolation System

## Purpose

Answer two critical questions when internet issues occur:
1. **Did the internet go down?**
2. **Who's to blame - my equipment or the ISP?**

## How It Works

The monitor tests your connection at multiple layers to isolate where the problem is:

```
┌─────────────────────────────────────────────────────────┐
│ Layer 1: YOUR ROUTER                                    │
│ - Ping to 192.168.1.1                                   │
│ - If fails → YOUR_ROUTER (check power/cables)          │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ Layer 2: ISP GATEWAY                                    │
│ - Ping to ISP's first hop                               │
│ - If fails → ISP_EQUIPMENT (call ISP)                  │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ Layer 3: DNS RESOLUTION                                 │
│ - Resolve google.com, cloudflare.com, amazon.com, etc  │
│ - If all fail → ISP_DNS (ISP DNS servers down)         │
│ - If some fail → DEGRADED_DNS (partial issues)         │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ Layer 4: HTTP CONNECTIVITY                              │
│ - GET requests to multiple reliable endpoints:          │
│   * captive.apple.com/hotspot-detect.html              │
│   * cloudflare.com/cdn-cgi/trace                        │
│   * google.com/generate_204                             │
│   * github.com                                          │
│ - If all fail → ISP_ROUTING (ISP routing issue)        │
│ - If some fail → DEGRADED_INTERNET (partial)           │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│ Layer 5: CONNECTION QUALITY                             │
│ - Track latency over last 10 checks                     │
│ - Calculate jitter (variance in latency)                │
│ - If jitter >50ms → DEGRADED_QUALITY (unstable)        │
└─────────────────────────────────────────────────────────┘
```

## Fault Attribution Values

The monitor publishes a `blame` MQTT topic with these values:

| Blame Value | Meaning | Action |
|------------|---------|--------|
| `NONE` | Everything healthy | Nothing to do |
| `YOUR_ROUTER` | Your router/modem is down | Check router power, reboot device |
| `ISP_EQUIPMENT` | ISP's gateway is unreachable | Call ISP support |
| `ISP_DNS` | All DNS resolution failed | ISP DNS servers down - call ISP |
| `ISP_ROUTING` | Internet completely unreachable | ISP routing/connection issue - call ISP |
| `DEGRADED_DNS` | Some DNS lookups failing | Monitor - may be temporary |
| `DEGRADED_INTERNET` | Some endpoints unreachable | Monitor - may be specific services |
| `DEGRADED_QUALITY` | High jitter detected | Poor connection quality - call ISP |
| `TRANSIENT` | Issue resolved itself | Was temporary glitch |

## Metrics Tracked

### Latency Measurements
- **Router Latency**: Ping time to your local router (should be <10ms)
- **DNS Latency**: Time to resolve domain names (should be <50ms)
- **HTTP Latency**: Time to GET a web page (should be <200ms)
- **Jitter**: Variance in latency over last 10 checks (should be <20ms)

### Success Rates
- **DNS Success Rate**: e.g., "4/4" means all 4 DNS checks passed
- **HTTP Success Rate**: e.g., "4/4" means all 4 HTTP checks passed

### Speed Tests
- **Download Speed**: Measured via Cloudflare (every 6 hours by default)
- **Speedtest Latency**: Round-trip time during speed test

## Checking Frequency

- **Health Checks**: Every 30 seconds (configurable)
- **Speed Tests**: Every 6 hours (configurable)
- **Confirmation**: 3 consecutive failures before declaring outage

## Using in Home Assistant

The monitor publishes all metrics via MQTT to Home Assistant:

```
home/network/sentinel/status          → HEALTHY or OUTAGE_*
home/network/sentinel/blame           → WHO TO BLAME
home/network/sentinel/fault_detail    → Human-readable explanation
home/network/sentinel/router_latency  → Ping to router (ms)
home/network/sentinel/dns_latency     → DNS resolution time (ms)
home/network/sentinel/http_latency    → HTTP request time (ms)
home/network/sentinel/jitter          → Connection stability (ms)
home/network/sentinel/dns_success_rate → e.g., "4/4"
home/network/sentinel/http_success_rate → e.g., "4/4"
home/network/sentinel/download_speed   → Mbps
```

## Example Scenarios

### Scenario 1: Router Reboots
```
Status: HEALTHY → OUTAGE_YOUR_ROUTER
Blame: YOUR_ROUTER
Detail: "Router unreachable - check if router is powered on"
```

### Scenario 2: ISP DNS Failure
```
Status: HEALTHY → OUTAGE_ISP_DNS
Blame: ISP_DNS
Detail: "DNS completely failed - ISP DNS issue"
DNS Success Rate: 0/4
HTTP Success Rate: 0/4 (fails because DNS failed first)
```

### Scenario 3: Partial Internet Issues
```
Status: HEALTHY → OUTAGE_DEGRADED_INTERNET
Blame: DEGRADED_INTERNET
Detail: "Partial internet failure - some services unreachable"
HTTP Success Rate: 2/4
```

### Scenario 4: Poor Connection Quality
```
Status: HEALTHY → OUTAGE_DEGRADED_QUALITY
Blame: DEGRADED_QUALITY
Detail: "High jitter (65ms) - unstable connection"
Jitter: 65ms
```

## Benefits

1. **Clear Attribution**: Know immediately if it's your fault or ISP's fault
2. **Evidence for ISP**: Detailed logs and timestamps when calling support
3. **Multiple Checks**: Not reliant on single endpoint (more reliable than just pinging 8.8.8.8)
4. **Quality Monitoring**: Track not just "up/down" but connection quality
5. **Automation Ready**: Home Assistant can auto-alert based on fault type

## Technical Details

### Why Multiple Endpoints?

Testing multiple endpoints (Google, Cloudflare, Apple, GitHub) ensures:
- Not fooled by single service outage
- More reliable detection (if all fail, it's really down)
- Can distinguish between "internet down" vs "Google down"

### Why DNS + HTTP?

- **DNS only**: Could resolve but HTTP blocked
- **HTTP only**: Could connect but DNS broken
- **Both**: Comprehensive connectivity check

### Why Jitter Matters?

Low jitter = stable connection
High jitter = packet loss, congestion, quality issues

High jitter causes:
- Video call stuttering
- Gaming lag
- VPN instability
- General poor experience

## Configuration

Edit `config/config.yaml`:

```yaml
monitoring:
  interval_seconds: 30          # How often to check
  targets:
    router: "192.168.1.1"       # Your router IP
    isp_gateway: null            # ISP first hop (or null)

  speedtest:
    use_cloudflare: true         # Use Cloudflare (faster)
    interval_hours: 6            # Speed test frequency
```

## Logs Example

```
2025-12-03 20:15:30 - Sentinel - INFO - ✓ Healthy - DNS: 12.5ms, HTTP: 45.3ms, Jitter: 8.2ms
2025-12-03 20:16:00 - Sentinel - WARNING - Health Check Failed. Consecutive: 1
2025-12-03 20:16:30 - Sentinel - WARNING - Health Check Failed. Consecutive: 2
2025-12-03 20:17:00 - Sentinel - WARNING - Health Check Failed. Consecutive: 3
2025-12-03 20:17:00 - Sentinel - INFO - Issue detected. Starting fault isolation...
2025-12-03 20:17:05 - Sentinel - ERROR - ⚠️  FAULT: ISP DNS - All DNS lookups failed
2025-12-03 20:17:05 - Sentinel - ERROR - OUTAGE CONFIRMED - Blame: ISP_DNS
2025-12-03 20:17:05 - Sentinel - ERROR -   DNS: ['google.com', 'cloudflare.com', 'amazon.com', 'github.com']
```
