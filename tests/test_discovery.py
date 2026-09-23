from notifier import Notifier

# Keys the monitor publishes after Task 4.
PUBLISHED_KEYS = {
    "status", "blame", "fault_detail", "router_latency",
    "router_health_score", "router_packet_loss", "router_jitter_internal",
    "dns_latency", "dns_success_rate", "http_latency", "http_success_rate",
    "jitter", "last_outage", "isp_gateway_latency", "modem_status",
    "modem_latency",
    "modem_wan_state", "modem_fiber_state", "modem_wan_ip",
    "modem_rx_power_uw", "modem_tx_power_uw", "modem_temp_c",
    "modem_last_change", "modem_probe_status",
}


def test_every_published_key_has_discovery_entry():
    missing = PUBLISHED_KEYS - set(Notifier.DISCOVERY_SENSORS.keys())
    assert not missing, f"states published without discovery config: {missing}"


def test_no_phantom_discovery_keys():
    # Discovery must not declare sensors nothing ever feeds.
    phantom = set(Notifier.DISCOVERY_SENSORS.keys()) - PUBLISHED_KEYS
    assert not phantom, f"discovery declares unfed sensors: {phantom}"


def test_unknown_state_key_warns_only_once(caplog):
    notifier = Notifier.__new__(Notifier)
    notifier.connected = False
    notifier._warned_unknown_state_keys = set()
    notifier.update_state("typo_key", 1)
    notifier.update_state("typo_key", 2)
    messages = [r.message for r in caplog.records if "typo_key" in r.message]
    assert len(messages) == 1


def test_retired_discovery_topics_are_deleted():
    published = []

    class Client:
        def publish(self, topic, payload, retain=False):
            published.append((topic, payload, retain))

    notifier = Notifier.__new__(Notifier)
    notifier.connected = True
    notifier.config = {"mqtt": {"topic_prefix": "home/network/sentinel"}}
    notifier.mqtt_client = Client()
    notifier._publish_discovery()

    assert (
        "homeassistant/sensor/netsentinel_internet_latency/config",
        "",
        True,
    ) in published
    assert (
        "homeassistant/sensor/netsentinel_modem_last_change_seconds/config",
        "",
        True,
    ) in published
    # Throughput and load-quality sensors were retired with the Pi-side
    # speedtest; HA must be told to delete them, not left showing stale values.
    for key in (
        "download_speed", "upload_speed", "idle_latency",
        "bufferbloat_ms", "loaded_loss_pct",
        "load_quality_status", "load_fault_detail",
    ):
        assert (
            f"homeassistant/sensor/netsentinel_{key}/config", "", True,
        ) in published, f"{key} discovery not deleted"


def test_modem_latency_discovery_has_availability_topic():
    import json
    published = []

    class Client:
        def publish(self, topic, payload, retain=False):
            published.append((topic, payload, retain))

    notifier = Notifier.__new__(Notifier)
    notifier.connected = True
    notifier.config = {"mqtt": {"topic_prefix": "home/network/sentinel"}}
    notifier.mqtt_client = Client()
    notifier._publish_discovery()

    topic = "homeassistant/sensor/netsentinel_modem_latency/config"
    payload = next(json.loads(body) for sent_topic, body, _ in published
                   if sent_topic == topic)
    assert payload["availability_topic"] == (
        "home/network/sentinel/modem_latency/availability"
    )
    assert payload["payload_available"] == "online"
    assert payload["payload_not_available"] == "offline"


def test_gateway_last_change_discovery_is_a_timestamp():
    import json
    published = []

    class Client:
        def publish(self, topic, payload, retain=False):
            published.append((topic, payload, retain))

    notifier = Notifier.__new__(Notifier)
    notifier.connected = True
    notifier.config = {"mqtt": {"topic_prefix": "home/network/sentinel"}}
    notifier.mqtt_client = Client()
    notifier._publish_discovery()

    topic = "homeassistant/sensor/netsentinel_modem_last_change/config"
    payload = next(json.loads(body) for sent_topic, body, _ in published
                   if sent_topic == topic)
    assert payload["device_class"] == "timestamp"
    assert "unit_of_measurement" not in payload
    assert "state_class" not in payload


def test_update_availability_publishes_retained_state():
    published = []

    class Client:
        def publish(self, topic, payload, retain=False):
            published.append((topic, payload, retain))

    notifier = Notifier.__new__(Notifier)
    notifier.connected = True
    notifier.config = {"mqtt": {"topic_prefix": "home/network/sentinel"}}
    notifier.mqtt_client = Client()

    notifier.update_availability("modem_latency", True)
    notifier.update_availability("modem_latency", False)

    assert published == [
        ("home/network/sentinel/modem_latency/availability", "online", True),
        ("home/network/sentinel/modem_latency/availability", "offline", True),
    ]


def test_last_outage_discovery_has_attributes_topic():
    import json
    published = []

    class Client:
        def publish(self, topic, payload, retain=False):
            published.append((topic, payload, retain))

    notifier = Notifier.__new__(Notifier)
    notifier.connected = True
    notifier.config = {"mqtt": {"topic_prefix": "home/network/sentinel"}}
    notifier.mqtt_client = Client()
    notifier._publish_discovery()

    topic = "homeassistant/sensor/netsentinel_last_outage/config"
    payload = next(json.loads(body) for sent_topic, body, _ in published
                   if sent_topic == topic)
    assert payload["json_attributes_topic"] == (
        "home/network/sentinel/last_outage/attributes"
    )


def test_long_outage_reason_fits_state_limit_and_keeps_full_text(tmp_path):
    # Home Assistant rejects sensor states over 255 characters, and outage
    # details carry a traceroute, so the full text has to ride in attributes.
    import json
    published = []

    class Client:
        def publish(self, topic, payload, retain=False):
            published.append((topic, payload, retain))

    notifier = Notifier.__new__(Notifier)
    notifier.connected = True
    notifier._warned_unknown_state_keys = set()
    notifier.config = {
        "mqtt": {"topic_prefix": "home/network/sentinel"},
        "logging": {"file_path": str(tmp_path / "events.csv")},
    }
    notifier.mqtt_client = Client()

    details = "ISP first hop is unreachable. Trace: " + "x" * 400
    notifier.log_event("OUTAGE", "ISP", details, "CRITICAL")

    state = next(body for topic, body, _ in published
                 if topic == "home/network/sentinel/last_outage/state")
    attributes = next(json.loads(body) for topic, body, _ in published
                      if topic == "home/network/sentinel/last_outage/attributes")
    assert len(state) <= 255
    assert state.startswith("OUTAGE: ISP first hop is unreachable.")
    assert attributes["detail"] == f"OUTAGE: {details}"
    assert attributes["target"] == "ISP"
