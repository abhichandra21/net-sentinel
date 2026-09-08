# Net Sentinel 🛡️

**Net Sentinel** is a dual-probe network monitoring solution designed to diagnose intermittent internet connectivity issues with **clear fault attribution**. It tells you **WHO IS TO BLAME** - your router, your ISP, or network degradation.

## 🏗 Architecture

The system consists of two independent components that report to **Home Assistant**:

1.  **Local Sentinel (Docker)**:
    *   Runs on your home network (Raspberry Pi, NAS, Server).
    *   Monitors: Router Health → BGW620 Fiber Gateway (optional) → ISP Gateway → Public DNS → Website Reachability.
    *   Checks: Ping latency, packet loss, jitter, DNS resolution, HTTP reachability.
    *   Reporting: **MQTT** with Auto-Discovery.
    *   *Diagnoses if the issue is your Router, Modem, or ISP with detailed health scoring.*

2.  **Cloud Probe (Python)**:
    *   Runs on an external VPS (AWS, GCP, DigitalOcean).
    *   Monitors: Your Home Public IP / DDNS Hostname from outside.
    *   Reporting: **Home Assistant Webhook** (via public internet).
    *   *Diagnoses if your home is reachable from the outside (Routing/Public IP issues).*

---

## 🚨 Fault Attribution System

Net Sentinel provides **clear fault codes** so you know exactly who to call:

| Fault Code          | Meaning                      | Action Required                        |
|---------------------|------------------------------|----------------------------------------|
| `NONE`              | All systems healthy          | ✓ No action needed                     |
| `ROUTER_CRITICAL`   | Router health < 30/100       | 🔧 **Reboot router or replace**        |
| `ROUTER_DEGRADED`   | Router health 30-60/100      | 🔧 **Check router load/performance**   |
| `ROUTER_DOWN`       | Router not responding        | 🔧 **Check power and cables**          |
| `MODEM_DOWN` | Router is up, while the configured modem, ISP first hop, DNS, and HTTP checks all fail | 🔧 Check gateway power and fiber cable; then contact ISP |
| `LASTMILE_FIBER_SUSPECT` | ISP first hop and public checks fail, but direct gateway evidence does not prove the gateway is down | 📞 Capture evidence and contact ISP |
| `ISP_INGRESS_CONGEST` | ISP first hop is reachable but abnormally slow | 📞 Contact ISP with first-hop latency |
| `ISP_CORE_ROUTING` | First hop works but DNS, HTTP, and anchor corroborate upstream failure | 📞 Contact ISP with trace evidence |
| `ISP_DNS`           | ISP DNS servers failing      | 📞 **Call ISP - DNS issue**            |
| `ISP_ROUTING`       | ISP routing problem          | 📞 **Call ISP - routing issue**        |
| `DEGRADED_DNS`      | Partial DNS failures         | ⏳ Monitor - may auto-resolve          |
| `DEGRADED_INTERNET` | Partial connectivity loss    | ⏳ Monitor - may auto-resolve          |
| `DEGRADED_QUALITY`  | High jitter (>50ms)          | ⏳ Monitor connection quality          |
| `TRANSIENT`         | Temporary glitch resolved    | ✓ Issue was temporary                  |

---

## 📊 Sensors Available

### Router Health Sensors (NEW)
- **`sensor.router_health_score`**: 0-100 health score
  - ≥80 = Healthy (green)
  - 60-79 = Degraded (yellow)
  - <60 = Critical (red)
  - Based on: packet loss, latency, jitter

- **`sensor.router_packet_loss`**: Percentage of packets lost (should be 0%)
- **`sensor.router_jitter_internal`**: Latency variance to router (should be <2ms)

### Status Sensors
- **`sensor.internet_status`**: Overall status (HEALTHY, OUTAGE_*, DEGRADED_*)
- **`sensor.internet_fault_blame`**: WHO TO BLAME fault code
- **`sensor.internet_fault_detail`**: Human-readable explanation

### Latency Metrics
- **`sensor.internet_router_latency`**: Ping to local router
- **`sensor.netsentinel_modem_status`**: `REACHABLE`, `UNREACHABLE`, or `NOT_CONFIGURED`
- **`sensor.netsentinel_modem_latency`**: Direct ICMP RTT to the configured modem; unavailable when it does not answer
- **`sensor.internet_dns_latency`**: DNS resolution time
- **`sensor.internet_http_latency`**: HTTP request time
- **`sensor.internet_jitter`**: Connection stability (low = good)

### Reliability Metrics
- **`sensor.internet_dns_success_rate`**: Format "4/4" (successful/total)
- **`sensor.internet_http_success_rate`**: Format "4/4" (successful/total)

### Throughput

The sentinel does not measure throughput. It runs on a Raspberry Pi 4, which
has no AES hardware acceleration, so a single TLS stream is capped near
250 Mbps by software crypto: its old speedtest reported ~213 Mbps on a line
that delivers 690 down and 904 up. It was measuring the Pi, not the internet.

Throughput comes from the Cloudflare Speed Test integration running on Home
Assistant itself, and the dashboard reads
`sensor.cloudflare_speed_test_90th_percentile_down` / `_up`.

The load classifier was dropped for the same reason: bufferbloat was measured
by generating load from the Pi, and a host that caps near 345 Mbps cannot
saturate a 700 Mbps uplink, so `DEGRADED_UNDER_LOAD` could never fire
honestly.

### Cloud Probe
- **`input_boolean.cloud_probe_status`**: Is HA reachable from internet?
- **`input_number.cloud_probe_latency`**: Latency from VPS to HA

---

## 🚀 Part 1: Local Sentinel Setup

### Prerequisites
*   Docker & Docker Compose
*   Home Assistant with MQTT Broker (e.g., Mosquitto)

### Installation
1.  **Clone the repository**:
    ```bash
    git clone https://github.com/abhichandra21/net-sentinel.git
    cd net-sentinel
    ```

2.  **Configure**:
    Create the local configuration from the committed template, then edit the
    non-secret network and MQTT settings:
    ```bash
    cp config/config.example.yaml config/config.yaml
    ```

    `config/config.yaml` should retain the environment token for the password:
    ```yaml
    monitoring:
      targets:
        router: "192.168.1.1"       # Your local router IP
        modem: null                  # Set to your BGW620 LAN address: "192.168.10.254"
        isp_gateway: "100.64.0.1"   # ISP Gateway (find via 'traceroute 8.8.8.8')
        public_dns_1: "8.8.8.8"     # Primary DNS resolver to test
        public_dns_2: "1.1.1.1"     # Optional secondary DNS resolver

      # Optional: override default HTTP endpoints used for connectivity checks.
      # If omitted, a sensible default set of endpoints is used.
      http_endpoints:
        - "http://captive.apple.com/hotspot-detect.html"
        - "https://www.cloudflare.com/cdn-cgi/trace"
        - "http://www.google.com/generate_204"
        - "https://www.github.com"

    mqtt:
      broker: "192.168.1.10"        # Your Home Assistant IP
      username: "mqtt_user"
      password: "${MQTT_PASSWORD}"
    ```

    A failed modem ping is always published as telemetry, but does not by
    itself declare an outage. `MODEM_DOWN` requires the router to remain up
    while the modem, ISP first hop, DNS, and HTTP checks corroborate the same
    failure. Remove or null the `modem` target if the device stops answering
    ICMP.

    Create an untracked `.env` file for Docker Compose:
    ```dotenv
    MQTT_PASSWORD=replace-with-your-broker-password
    ```

3.  **Start the container**:
    ```bash
    docker-compose up -d --build
    ```

### Home Assistant Integration

#### Option 1: Quick Setup (Copy/Paste)
See `ha_comprehensive_setup.yaml` for a ready-to-use configuration.

#### Option 2: Manual Setup

1. **Add MQTT Sensors**
   Create or edit `mqtt.yaml` in your HA config directory (see `ha_comprehensive_setup.yaml` for full config).

2. **Add Dashboard**
   Run `homeassistant/deploy_dashboard.py all`. See "Dashboard" below.

3. **Restart Home Assistant**
   ```bash
   ha core restart
   ```

After restart, all sensors will auto-discover via MQTT. Go to **Settings > Devices & Services > MQTT** to see the "Network Sentinel" device.

---

## ☁️ Part 2: Cloud Probe Setup (Optional)

The Cloud Probe monitors your home from **outside**, detecting issues with public IP routing or incoming connectivity.

### 1. Prepare Home Assistant

1.  **Create Helpers** (Settings > Devices > Helpers):
    *   **Toggle**: `Cloud Probe Status` (Entity: `input_boolean.cloud_probe_status`)
    *   **Number**: `Cloud Probe Latency` (Entity: `input_number.cloud_probe_latency`, 0-2000, step 1)

2.  **Create Automation**:
    See `ha_complete_setup.yaml` for the webhook automation config.

### 2. Deploy on VPS

1.  **Upload files** to your VPS:
    ```bash
    scp -r cloud_probe/ user@your-vps.com:/root/net-sentinel/
    ```

2.  **Install dependencies**:
    ```bash
    pip3 install ping3 requests
    ```

3.  **Test run**:
    ```bash
    python3 cloud_probe/main.py \
      --target your-home.duckdns.org \
      --webhook https://your-ha.com/api/webhook/net-sentinel-cloud-probe-2025
    ```

4.  **Run as a service**:
    See `deploy_cloud_probe.sh` for systemd service setup.

---

## 📊 Dashboard

The dashboard lives here, under `homeassistant/`:

```
homeassistant/
  dashboards/net_sentinel.yaml   the dashboard (source of truth)
  themes/net-sentinel.yaml       the colours it styles itself with
  deploy_dashboard.py            pushes both to Home Assistant
```

Deploy it:

```bash
export HA_TOKEN=...                        # long-lived access token
homeassistant/deploy_dashboard.py all      # theme + dashboard
homeassistant/deploy_dashboard.py get live.yaml   # pull the live config back
```

**Editing the YAML alone changes nothing.** `/net-sentinel` is a *storage-mode*
dashboard, so Home Assistant reads `.storage/lovelace.net_sentinel` and never
reads a YAML file. The deploy script pushes the config over the
`lovelace/config/save` websocket command, which takes effect immediately and
needs no restart. The theme is different: it is a real file HA does read, so it
is scp'd into `<config>/themes/` and the frontend is told to reload.

Because HA owns the live copy, someone can edit the dashboard in the UI and
diverge from this file. `deploy_dashboard.py get` is how you check.

This repo previously carried two *other* dashboard YAMLs that nothing read and
that drifted for months. They are gone, and a test keeps them from returning:
there is one source now.

Three views:

1. **Live** - the verdict and remedy, the hop-by-hop path readout, BGW620 fiber
   plant (optical power, link state, WAN IP), router health, quality under load,
   throughput, and 24 h trends on a log axis
2. **Diagnostics** - every published entity, grouped
3. **Runbook** - what each fault code means and what to do about it

---

## 🛠 Troubleshooting

### Local Sentinel
*   **Check logs**: `docker logs -f net-sentinel`
*   **MQTT not connecting**: Verify broker IP and username in `config/config.yaml`, and the password in the untracked `.env` file
*   **No sensors in HA**: Restart HA after first run, check MQTT integration

### Cloud Probe
*   **404 webhook error**: Ensure automation has `local_only: false`
*   **Ping failures**: Check home firewall allows ICMP from WAN
*   **Probe shows offline**: Verify VPS can reach your public IP/DDNS

### Router Health Always Low
*   **Check router**: May be overloaded or failing
*   **Verify IP**: Ensure `router:` in config is your actual gateway
*   **Network congestion**: High local traffic can cause packet loss

---

## 📝 Updates in This Version

- ✅ **Router Health Scoring**: 0-100 score with packet loss & jitter metrics
- ✅ **Enhanced Fault Codes**: New ROUTER_CRITICAL, ROUTER_DEGRADED codes
- ✅ **Conditional Dashboard**: Router details only show when health < 80
- ✅ **Fault Attribution UI**: Clear "Who's Responsible?" section with actions
- ✅ **Cloud Probe Integration**: External monitoring via webhook
- ✅ **Modern Mushroom Cards**: Clean, minimal dashboard design

---

## 📄 License

MIT License - See LICENSE file for details.

## 🤝 Contributing

Issues and pull requests welcome! Please test thoroughly before submitting.
