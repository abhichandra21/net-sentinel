# Net Sentinel 🛡️

**Net Sentinel** is a dual-probe network monitoring solution designed to diagnose intermittent internet connectivity issues with **clear fault attribution**. It tells you **WHO IS TO BLAME** - your router, your ISP, or network degradation.

## 🏗 Architecture

The system consists of two independent components that report to **Home Assistant**:

1.  **Local Sentinel (Docker)**:
    *   Runs on your home network (Raspberry Pi, NAS, Server).
    *   Monitors: Router Health → ISP Gateway → Public DNS → Website Reachability.
    *   Checks: Ping latency, packet loss, jitter, DNS resolution, periodic Speedtests.
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
| `ISP_EQUIPMENT`     | ISP gateway unreachable      | 📞 **Call ISP - their equipment down** |
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
- **`sensor.internet_dns_latency`**: DNS resolution time
- **`sensor.internet_http_latency`**: HTTP request time
- **`sensor.internet_jitter`**: Connection stability (low = good)

### Reliability Metrics
- **`sensor.internet_dns_success_rate`**: Format "4/4" (successful/total)
- **`sensor.internet_http_success_rate`**: Format "4/4" (successful/total)

### Speed Test
- **`sensor.internet_download_speed`**: Download bandwidth in Mbit/s
- **`sensor.internet_speedtest_latency`**: Latency during speed test

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
    Edit `config/config.yaml`:
    ```yaml
    monitoring:
      targets:
        router: "192.168.1.1"      # Your local router IP
        isp_gateway: "100.64.0.1"  # ISP Gateway (find via 'traceroute 8.8.8.8')
        public_dns_1: "8.8.8.8"
    
    mqtt:
      broker: "192.168.1.10"       # Your Home Assistant IP
      username: "mqtt_user"
      password: "mqtt_password"
    ```

3.  **Start the container**:
    ```bash
    docker-compose up -d --build
    ```

### Home Assistant Integration

#### Option 1: Quick Setup (Copy/Paste)
See `ha_complete_setup.yaml` for a ready-to-use configuration.

#### Option 2: Manual Setup

1. **Add MQTT Sensors**
   Create or edit `mqtt.yaml` in your HA config directory (see `ha_comprehensive_setup.yaml` for full config).

2. **Add Dashboard**
   Copy the contents of `ha_dashboard.yaml` to a new Lovelace dashboard.

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

## 📊 Dashboard Overview

The included dashboard (`ha_dashboard.yaml`) provides:

1. **Critical Status** - Immediate health indicator
2. **Router Health** - Gauge showing 0-100 health score with conditional packet loss/jitter details
3. **Fault Attribution** - Shows WHO TO BLAME with recommended actions
4. **Performance** - Download speed and ping metrics
5. **Connection Quality** - DNS, HTTP latency, and jitter
6. **Reliability** - Success rates for DNS/HTTP requests + cloud probe status
7. **Advanced Diagnostics** - Detailed view of all metrics
8. **Historical Trends** - 24-hour graphs

---

## 🛠 Troubleshooting

### Local Sentinel
*   **Check logs**: `docker logs -f net-sentinel`
*   **MQTT not connecting**: Verify broker IP, username, password in `config/config.yaml`
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
