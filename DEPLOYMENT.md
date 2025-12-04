# Internet Monitor - Deployment Guide

## Network Topology

```
┌─────────────────────────────────────────────────────────────┐
│ Home Network (192.168.1.0/24)                               │
│                                                              │
│  ┌──────────────────┐                                       │
│  │ Router/Gateway   │                                       │
│  │ 192.168.1.1      │                                       │
│  └────────┬─────────┘                                       │
│           │                                                  │
│           ├──────────────┬──────────────┐                  │
│           │              │              │                   │
│  ┌────────▼────────┐ ┌──▼────────────┐ │                  │
│  │ Home Assistant  │ │ Docker Host   │ │                  │
│  │ 192.168.1.50    │ │ 192.168.1.3   │ │                  │
│  │                 │ │               │ │                   │
│  │ - MQTT Broker   │ │ - Monitor     │ │                  │
│  │ - Webhooks      │ │ - Container   │ │                  │
│  └─────────────────┘ └───────────────┘ │                  │
└─────────────────────────────────────────┼──────────────────┘
                                          │
                                    Internet
                                          │
                            ┌─────────────▼──────────────┐
                            │ VPS Cloud Probe            │
                            │ ssh-day1.abhichandra.com   │
                            │                            │
                            │ - Pings home from outside  │
                            │ - Reports to HA webhook    │
                            └────────────────────────────┘
```

## Component 1: Local Monitor (Docker on 192.168.1.3)

**Purpose:** Monitor internet from inside your network, detect faults

**Deployment:**

SSH to Docker host:
```bash
# Passwordless access (assumes SSH key already configured)
ssh 192.168.1.3
```

Clone/copy the repository:
```bash
cd ~
git clone <your-repo-url> internet-monitor
cd internet-monitor
```

Verify configuration in `config/config.yaml`:
```yaml
monitoring:
  interval_seconds: 30
  targets:
    router: "192.168.1.1"        # Your router
    isp_gateway: null

mqtt:
  broker: "192.168.1.50"         # Home Assistant IP
  port: 1883
  username: "abhishek"
  password: "Al211hama!"
```

Start with Docker:
```bash
docker-compose up -d

# Check logs
docker-compose logs -f sentinel
```

**Expected output:**
```
INFO - Network Sentinel Started.
INFO - ✓ Healthy - DNS: 12.5ms, HTTP: 45.3ms, Jitter: 8.2ms
```

**Verify MQTT is publishing:**
```bash
# From any machine that can reach HA
mosquitto_sub -h 192.168.1.50 -u abhishek -P 'Al211hama!' -t 'home/network/sentinel/#' -v
```

## Component 2: Cloud Probe (VPS)

**Purpose:** Monitor home internet from outside, detect if your home is reachable

**Deployment:**

SSH to VPS:
```bash
ssh -i ~/.ssh/aws.pub ubuntu@ssh-day1.abhichandra.com
```

Install dependencies:
```bash
sudo apt update
sudo apt install python3 python3-pip
pip3 install requests ping3
```

Copy cloud probe code:
```bash
mkdir -p ~/cloud-probe
cd ~/cloud-probe
# Upload main.py here (use scp or copy-paste)
```

**Get your home public IP or DDNS:**
```bash
# From home network
curl ifconfig.me
```

**Create systemd service:**
```bash
sudo nano /etc/systemd/system/cloud-probe.service
```

```ini
[Unit]
Description=Internet Monitor Cloud Probe
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/cloud-probe
ExecStart=/usr/bin/python3 /home/ubuntu/cloud-probe/main.py \
    --target <YOUR_HOME_PUBLIC_IP_OR_DDNS> \
    --webhook http://192.168.1.50:8123/api/webhook/net-sentinel-cloud-probe-2025 \
    --interval 60
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Replace `<YOUR_HOME_PUBLIC_IP_OR_DDNS>` with your actual home IP or DDNS hostname.**

**Start the service:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable cloud-probe
sudo systemctl start cloud-probe

# Check status
sudo systemctl status cloud-probe

# View logs
sudo journalctl -u cloud-probe -f
```

**Note about webhook URL:**
If accessing Home Assistant from outside, you may need:
- Port forwarding (8123) on your router, OR
- Nabu Casa Cloud URL, OR
- Tailscale/VPN connection

For security, consider using Tailscale:
```bash
# On VPS
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Then use Tailscale IP instead
--webhook http://<HA_TAILSCALE_IP>:8123/api/webhook/...
```

## Component 3: Home Assistant (192.168.1.50)

**Add MQTT sensors:**

Edit `configuration.yaml` or create `config/packages/internet_monitor.yaml`:

```yaml
mqtt:
  sensor:
    - name: "Internet Status"
      state_topic: "home/network/sentinel/status"
      icon: mdi:network

    - name: "Internet Fault Blame"
      state_topic: "home/network/sentinel/blame"
      icon: mdi:alert-circle

    - name: "Internet Fault Detail"
      state_topic: "home/network/sentinel/fault_detail"

    - name: "Router Latency"
      state_topic: "home/network/sentinel/router_latency"
      unit_of_measurement: "ms"

    - name: "DNS Latency"
      state_topic: "home/network/sentinel/dns_latency"
      unit_of_measurement: "ms"

    - name: "HTTP Latency"
      state_topic: "home/network/sentinel/http_latency"
      unit_of_measurement: "ms"

    - name: "Jitter"
      state_topic: "home/network/sentinel/jitter"
      unit_of_measurement: "ms"

    - name: "Download Speed"
      state_topic: "home/network/sentinel/download_speed"
      unit_of_measurement: "Mbps"
```

**Restart Home Assistant**

**Add dashboard cards** from `ha_comprehensive_setup.yaml`

## Verification Checklist

### Local Monitor (192.168.1.3)
- [ ] Docker container running: `docker ps`
- [ ] Logs show healthy checks: `docker-compose logs sentinel`
- [ ] MQTT publishing: `mosquitto_sub -h 192.168.1.50 ...`

### Cloud Probe (VPS)
- [ ] Service running: `sudo systemctl status cloud-probe`
- [ ] Logs show successful pings: `sudo journalctl -u cloud-probe -f`
- [ ] Webhook reaching HA (check HA logs)

### Home Assistant (192.168.1.50)
- [ ] MQTT sensors appear in Developer Tools > States
- [ ] Sensors show current values
- [ ] Dashboard displays all cards
- [ ] Helpers exist: `input_boolean.cloud_probe_status`

## Troubleshooting

**Local Monitor can't connect to MQTT:**
```bash
# From Docker host (192.168.1.3)
telnet 192.168.1.50 1883

# Test MQTT credentials
mosquitto_pub -h 192.168.1.50 -u abhishek -P 'Al211hama!' -t 'test' -m 'hello'
```

**Cloud Probe can't reach webhook:**
```bash
# Test from VPS
curl -X POST http://192.168.1.50:8123/api/webhook/net-sentinel-cloud-probe-2025 \
  -H "Content-Type: application/json" \
  -d '{"status":"online","latency":50}'
```

If this fails, you need port forwarding or VPN.

**Sensors not appearing in HA:**
- Check `configuration.yaml` syntax
- Restart HA
- Check HA logs: Settings > System > Logs

## Maintenance

**Update local monitor:**
```bash
ssh 192.168.1.3
cd ~/internet-monitor
git pull
docker-compose up -d --build
```

**Update cloud probe:**
```bash
ssh -i ~/.ssh/aws.pub ubuntu@ssh-day1.abhichandra.com
cd ~/cloud-probe
# Update main.py
sudo systemctl restart cloud-probe
```

**View all logs:**
```bash
# Local monitor
ssh 192.168.1.3
docker-compose logs -f sentinel

# Cloud probe
ssh -i ~/.ssh/aws.pub ubuntu@ssh-day1.abhichandra.com
sudo journalctl -u cloud-probe -f

# Home Assistant
# Via HA UI: Settings > System > Logs
```
