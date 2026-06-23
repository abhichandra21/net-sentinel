from notifier import Notifier

# Keys the monitor publishes after Task 4.
PUBLISHED_KEYS = {
    "status", "blame", "fault_detail", "router_latency",
    "router_health_score", "router_packet_loss", "router_jitter_internal",
    "dns_latency", "dns_success_rate", "http_latency", "http_success_rate",
    "jitter", "download_speed", "upload_speed", "idle_latency", "last_outage",
    "isp_gateway_latency",
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
