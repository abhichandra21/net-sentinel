# Net Sentinel 🛡️

**Net Sentinel** is a dual-probe network monitoring solution designed to diagnose intermittent internet connectivity issues. It triangulates problems by monitoring your connection from both **inside** (your local network) and **outside** (a cloud VPS).

## 🏗 Architecture

The system consists of two independent components that report to **Home Assistant**:

1.  **Local Sentinel (Docker)**:
    *   Runs on your home network (Raspberry Pi, NAS, Server).
    *   Monitors: Router -> ISP Gateway -> Public DNS -> Website Reachability.
    *   Checks: Ping latency, DNS resolution, periodic Speedtests.
    *   Reporting: **MQTT** (Auto-Discovery).
    *   *Diagnoses if the issue is your Router, Modem, or ISP.*

2.  **Cloud Probe (Python)**:
    *   Runs on an external VPS (AWS, GCP, DigitalOcean).
    *   Monitors: Your Home Public IP / DDNS Hostname.
    *   Reporting: **Home Assistant Webhook** (via public internet).
    *   *Diagnoses if your home is reachable from the outside (Routing/Public IP issues).*

---

## 🚀 Part 1: Local Sentinel Setup

### Prerequisites
*   Docker & Docker Compose.
*   Home Assistant with an MQTT Broker (e.g., Mosquitto) running.

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
        isp_gateway: "100.64.0.1"  # Your ISP Gateway (Find via 'traceroute 8.8.8.8', usually hop #2)
        public_dns_1: "8.8.8.8"
    
mqtt:
      broker: "192.168.1.10"       # Your Home Assistant / MQTT Broker IP
      username: "mqtt_user"
      password: "mqtt_password"
    ```

3.  **Start the container**:
    ```bash
    docker-compose up -d --build
    ```

### Integration
Net Sentinel uses **MQTT Discovery**. Once running, go to HA Settings > **Devices & Services** > **MQTT**. You will see a new device named **"Network Sentinel"** containing:
*   `router_latency`, `internet_latency`
*   `download_speed`, `upload_speed`
*   `network_status` (Online, Diagnosing, LOCAL_FAILURE, ISP_FAILURE, etc.)

---

## ☁️ Part 2: Cloud Probe Setup (Remote)

Since your Home Assistant is exposed to the internet, the Cloud Probe sends data directly via a Webhook.

### 1. Prepare Home Assistant
We need "Helpers" to store the Cloud Probe data and an Automation to receive the Webhook.

1.  **Create Helpers** (Settings > Devices > Helpers):
    *   **Toggle** (Input Boolean): Name: `Cloud Probe Status`, Entity ID: `input_boolean.cloud_probe_status`
    *   **Number** (Input Number): Name: `Cloud Probe Latency`, Entity ID: `input_number.cloud_probe_latency` (0 to 2000, step 1).

2.  **Create Automation**:
    Create a new automation, switch to **YAML Mode**, and paste this:
    ```yaml
    alias: "System: Update Cloud Probe"
    description: "Receives heartbeat from external VPS"
    trigger:
      - platform: webhook
        webhook_id: "my-secure-probe-token-123"  # <--- CHANGE THIS to a random string
        local_only: false
    condition: []
    action:
      - service: input_boolean.turn_{{ trigger.json.status == 'online' | iif('on', 'off') }}
        target:
          entity_id: input_boolean.cloud_probe_status
      - service: input_number.set_value
        target:
          entity_id: input_number.cloud_probe_latency
        data:
          value: "{{ trigger.json.latency | default(0) }}"
    mode: single
    ```

### 2. Deploy on VPS
1.  **Copy Files**: Upload `cloud_probe/main.py` and `sentinel/requirements.txt` to your VPS.
2.  **Install Dependencies**:
    ```bash
    pip3 install ping3 requests
    ```
3.  **Test Run**:
    ```bash
    python3 cloud_probe/main.py \
      --target <YOUR_HOME_DDNS_OR_IP> \
      --webhook https://<YOUR_HA_DOMAIN>/api/webhook/my-secure-probe-token-123
    ```

### 3. Run as a Service (Systemd)
To keep it running in the background:

1.  Create `/etc/systemd/system/cloud-probe.service`:
    ```ini
    [Unit]
    Description=Net Sentinel Cloud Probe
    After=network.target

    [Service]
    User=root
    WorkingDirectory=/root/net-sentinel
    ExecStart=/usr/bin/python3 cloud_probe/main.py --target myhome.duckdns.org --webhook https://myha.com/api/webhook/token
    Restart=always
    RestartSec=10

    [Install]
    WantedBy=multi-user.target
    ```
2.  Enable it: `systemctl enable --now cloud-probe`

---

## 📊 Dashboard Example

Add this YAML to your Lovelace dashboard to visualize the stack:

```yaml
type: vertical-stack
cards:
  - type: entities
    title: Network Health
    entities:
      - entity: sensor.netsentinel_network_status
        name: Local Status
      - entity: input_boolean.cloud_probe_status
        name: Cloud Reachability
      - entity: sensor.netsentinel_last_outage_reason
  - type: grid
    columns: 2
    cards:
      - type: gauge
        entity: sensor.netsentinel_internet_latency
        name: Ping (Out)
        severity:
          green: 0
          yellow: 50
          red: 100
      - type: gauge
        entity: input_number.cloud_probe_latency
        name: Ping (In)
        severity:
          green: 0
          yellow: 50
          red: 100
  - type: history-graph
    hours_to_show: 24
    entities:
      - entity: sensor.netsentinel_download_speed
      - entity: sensor.netsentinel_upload_speed
```

## 🛠 Troubleshooting

*   **Local Probe**:
    *   *Logs*: `docker logs -f net-sentinel`
    *   *Permission Denied*: The container runs as root to allow ICMP/Ping. If you have strict security policies, you may need to adjust `cap_add`.
*   **Cloud Probe**:
    *   *404 Error*: Check your Webhook URL and ensure `local_only: false` is set in the HA Automation.
    *   *Ping Failures*: Ensure your home router allows ICMP Echo Requests from the WAN side (check Firewall settings).