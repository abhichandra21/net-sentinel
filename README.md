# Internet Sentinel: Advanced Network Monitoring & Diagnostics

## Architecture
This solution employs a dual-probe architecture to triangulate network issues:

1.  **Local Probe (Net-Sentinel)**: A Docker container running on your local network (Raspberry Pi/Server).
    *   **Function**: Continuously monitors local router, ISP gateway, and public internet health.
    *   **Diagnostics**: Automatically triggers traceroutes and specific interface checks when outages occur.
    *   **Reporting**: Pushes real-time state to Home Assistant via MQTT and logs events to a local CSV.
    *   **Bandwidth**: Performs scheduled speed tests (default: every 6 hours).

2.  **Cloud Probe (Optional)**: A lightweight Python script running on an external VPS (AWS Free Tier / GCP / Azure).
    *   **Function**: Pings your home public IP (or DDNS hostname) from the "outside".
    *   **Purpose**: Distinguishes between "Modem is down" (Local Probe sees failure) and "Routing issue" (Cloud Probe can't reach you).

## Prerequisites
*   Docker & Docker Compose installed on a local server (e.g., Raspberry Pi).
*   Home Assistant with MQTT Broker (Mosquitto) configured.
*   (Optional) Python 3 installed on a cloud VPS.

## Deployment Steps

### 1. Local Probe (Sentinel)

1.  **Configure**: Edit `config/config.yaml`.
    *   `router`: Your local router IP (e.g., 192.168.1.1).
    *   `isp_gateway`: Your ISP's next hop. Run `traceroute 8.8.8.8` and pick the second IP address (the one after your router).
    *   `mqtt`: Enter your Home Assistant MQTT broker details.

2.  **Run**:
    ```bash
    docker-compose up -d --build
    ```

3.  **Home Assistant Integration**:
    *   The system uses **MQTT Auto Discovery**.
    *   Once running, go to Home Assistant > Settings > Devices & Services > MQTT.
    *   You will see a new device "Network Sentinel" with sensors:
        *   `Network Status` (Online, Diagnosing, LOCAL_FAILURE, ISP_FAILURE, etc.)
        *   `Router Latency` & `Internet Latency`
        *   `Download/Upload Speed`
        *   `Last Outage Reason`

### 2. Cloud Probe (Optional)

1.  **Setup**: Upload `cloud_probe/main.py` and `requirements.txt` (create one with `ping3`, `requests`) to your VPS.
2.  **Run**:
    ```bash
    pip install ping3 requests
    python3 cloud_probe/main.py --target <YOUR_DDNS_HOSTNAME> --webhook <HA_WEBHOOK_URL>
    ```
    *   *Note*: Create a Webhook automation in HA to receive this data.

## Dashboard & Alerts (Home Assistant)

### Dashboard Card (YAML)
```yaml
type: vertical-stack
cards:
  - type: entities
    title: Network Status
    entities:
      - entity: sensor.netsentinel_network_status
      - entity: sensor.netsentinel_last_outage_reason
      - entity: sensor.netsentinel_router_latency
      - entity: sensor.netsentinel_internet_latency
  - type: history-graph
    entities:
      - sensor.netsentinel_internet_latency
    hours_to_show: 24
```

### Automation Example (Alert on Outage)
```yaml
alias: "Notify: Internet Outage"
trigger:
  - platform: state
    entity_id: sensor.netsentinel_network_status
    to: "ISP_FAILURE"
  - platform: state
    entity_id: sensor.netsentinel_network_status
    to: "INTERNET_FAILURE"
action:
  - service: notify.mobile_app_your_phone
    data:
      message: "Internet Down! Reason: {{ states('sensor.netsentinel_last_outage_reason') }}"
```

## Troubleshooting

*   **"Router Latency is unavailable"**: Ensure Docker container has network access. `network_mode: "host"` is used in docker-compose to ensure ICMP works correctly.
*   **Permission Denied (Ping)**: If running on a strict OS, you might need to add `cap_add: [NET_ADMIN]` to docker-compose, though the provided config runs as root which usually bypasses this.
*   **No MQTT Sensors**: Check `docker logs net-sentinel`. Verify MQTT IP and credentials in `config.yaml`.
