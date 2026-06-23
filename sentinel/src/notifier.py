import json
import time
import csv
import os
import paho.mqtt.client as mqtt
import logging

logger = logging.getLogger("Notifier")

class Notifier:
    DISCOVERY_SENSORS = {
        "status": {"name": "Network Status", "icon": "mdi:web"},
        "blame": {"name": "Fault Attribution", "icon": "mdi:gavel"},
        "fault_detail": {"name": "Fault Detail", "icon": "mdi:information"},
        "router_latency": {"name": "Router Latency", "unit_of_measurement": "ms", "icon": "mdi:router-wireless"},
        "router_health_score": {"name": "Router Health Score", "unit_of_measurement": "/100", "icon": "mdi:heart-pulse"},
        "router_packet_loss": {"name": "Router Packet Loss", "unit_of_measurement": "%", "icon": "mdi:close-network"},
        "router_jitter_internal": {"name": "Router Jitter", "unit_of_measurement": "ms", "icon": "mdi:sine-wave"},
        "dns_latency": {"name": "DNS Latency", "unit_of_measurement": "ms", "icon": "mdi:dns"},
        "dns_success_rate": {"name": "DNS Success Rate", "icon": "mdi:dns"},
        "http_latency": {"name": "HTTP Latency", "unit_of_measurement": "ms", "icon": "mdi:web-clock"},
        "http_success_rate": {"name": "HTTP Success Rate", "icon": "mdi:web-check"},
        "jitter": {"name": "Connection Jitter", "unit_of_measurement": "ms", "icon": "mdi:sine-wave"},
        "download_speed": {"name": "Download Speed", "unit_of_measurement": "Mbps", "icon": "mdi:download"},
        "upload_speed": {"name": "Upload Speed", "unit_of_measurement": "Mbps", "icon": "mdi:upload"},
        "bufferbloat_ms": {"name": "Bufferbloat", "unit_of_measurement": "ms", "icon": "mdi:water"},
        "loaded_loss_pct": {"name": "Loaded Packet Loss", "unit_of_measurement": "%", "icon": "mdi:close-network"},
        "load_quality_status": {"name": "Load Quality Status", "icon": "mdi:speedometer-slow"},
        "load_fault_detail": {"name": "Load Quality Detail", "icon": "mdi:information"},
        "idle_latency": {"name": "Idle Latency", "unit_of_measurement": "ms", "icon": "mdi:speedometer"},
        "isp_gateway_latency": {
            "name": "ISP First-Hop Latency",
            "unit_of_measurement": "ms",
            "icon": "mdi:transit-connection-variant",
        },
        "last_outage": {"name": "Last Outage Reason", "icon": "mdi:alert-circle"},
    }

    RETIRED_DISCOVERY_KEYS = {"internet_latency", "speedtest_latency"}

    def __init__(self, config):
        self.config = config
        self.mqtt_client = None
        self.connected = False
        self._warned_unknown_state_keys = set()
        self._setup_mqtt()
        self._setup_logging()

    def _setup_logging(self):
        log_path = self.config['logging']['file_path']
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        if not os.path.exists(log_path):
            with open(log_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "event_type", "target", "details", "status"])

    def _setup_mqtt(self):
        broker = self.config['mqtt']['broker']
        if not broker or broker == "192.168.1.10":
            logger.warning("MQTT broker not configured properly. Skipping MQTT setup.")
            return

        logger.info(f"Setting up MQTT connection to {broker}:{self.config['mqtt']['port']}")
        self.mqtt_client = mqtt.Client("NetSentinel")
        
        if self.config['mqtt'].get('username'):
            logger.info(f"Using MQTT username: {self.config['mqtt']['username']}")
            self.mqtt_client.username_pw_set(
                self.config['mqtt']['username'],
                self.config['mqtt']['password']
            )

        try:
            logger.info("Attempting MQTT connection...")
            self.mqtt_client.connect(broker, self.config['mqtt']['port'], 10)  # Reduced timeout
            logger.info("MQTT connection successful, starting loop...")
            self.mqtt_client.loop_start()
            self.connected = True
            logger.info("Publishing discovery messages...")
            self._publish_discovery()
            logger.info("MQTT setup complete!")
        except Exception as e:
            logger.error(f"Failed to connect to MQTT: {e}")
            logger.info("Continuing without MQTT functionality")

    def _publish_discovery(self):
        """Publish Home Assistant Auto-Discovery Config"""
        if not self.connected: return

        prefix = self.config['mqtt']['topic_prefix']
        
        # Define sensors to create
        sensors = self.DISCOVERY_SENSORS

        for key, data in sensors.items():
            config_payload = {
                "name": f"NetSentinel {data['name']}",
                "unique_id": f"netsentinel_{key}",
                "state_topic": f"{prefix}/{key}/state",
                "icon": data.get("icon"),
                "device": {
                    "identifiers": ["netsentinel_local"],
                    "name": "Network Sentinel",
                    "model": "Docker Container",
                    "manufacturer": "Custom"
                }
            }
            if "unit_of_measurement" in data:
                config_payload["unit_of_measurement"] = data["unit_of_measurement"]

            topic = f"homeassistant/sensor/netsentinel_{key}/config"
            self.mqtt_client.publish(topic, json.dumps(config_payload), retain=True)

        for key in self.RETIRED_DISCOVERY_KEYS - set(sensors):
            topic = f"homeassistant/sensor/netsentinel_{key}/config"
            self.mqtt_client.publish(topic, "", retain=True)

    def update_state(self, key, value):
        """Publish state to MQTT"""
        if key not in self.DISCOVERY_SENSORS and key not in getattr(self, '_warned_unknown_state_keys', set()):
            logger.warning(f"Publishing state without discovery config: {key}")
            if hasattr(self, '_warned_unknown_state_keys'):
                self._warned_unknown_state_keys.add(key)
        if not self.connected: return
        prefix = self.config['mqtt']['topic_prefix']
        self.mqtt_client.publish(f"{prefix}/{key}/state", str(value), retain=True)

    def log_event(self, event_type, target, details, status):
        """Log to CSV and optionally MQTT"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        
        # File Logging
        try:
            with open(self.config['logging']['file_path'], 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([timestamp, event_type, target, details, status])
        except Exception as e:
            logger.error(f"Failed to write to log file: {e}")

        # MQTT Alert if critical
        if status == "CRITICAL":
            self.update_state("last_outage", f"{event_type}: {details}")
            
