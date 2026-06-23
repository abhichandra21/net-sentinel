import monitor


def _stub_health_checks(monkeypatch):
    monitor.latency_history.clear()
    monkeypatch.setattr(
        monitor, "check_router_health", lambda ip: {"health_score": 100}
    )
    monkeypatch.setattr(
        monitor,
        "check_multi_dns",
        lambda dns_servers=None, timeout=2.0: {
            "avg_latency": 5.0,
            "all_succeeded": True,
            "total": 2,
            "success_count": 2,
        },
    )
    monkeypatch.setattr(
        monitor,
        "check_multi_http",
        lambda endpoints=None, timeout=10.0: {
            "avg_latency": 30.0,
            "all_succeeded": True,
            "total": 2,
            "success_count": 2,
        },
    )


def test_health_check_measures_configured_modem(monkeypatch):
    _stub_health_checks(monkeypatch)
    calls = []

    def ping(host, timeout=2.0):
        calls.append(host)
        return {"192.168.1.1": 1.0, "192.168.100.1": 1.5}[host]

    monkeypatch.setattr(monitor, "check_ping", ping)
    results = monitor.perform_health_check({
        "router": "192.168.1.1",
        "modem": "192.168.100.1",
    })

    assert results["modem_configured"] is True
    assert results["modem"] == 1.5
    assert "192.168.100.1" in calls


def test_health_check_ignores_unconfigured_modem(monkeypatch):
    _stub_health_checks(monkeypatch)
    calls = []

    def ping(host, timeout=2.0):
        calls.append(host)
        return 1.0

    monkeypatch.setattr(monitor, "check_ping", ping)
    results = monitor.perform_health_check({"router": "192.168.1.1"})

    assert results["modem_configured"] is False
    assert results["modem"] is None
    assert calls == ["192.168.1.1"]


class FakeNotifier:
    def __init__(self):
        self.states = []
        self.availability = []

    def update_state(self, key, value):
        self.states.append((key, value))

    def update_availability(self, key, available):
        self.availability.append((key, available))


def test_reachable_modem_publishes_status_latency_and_availability():
    notifier = FakeNotifier()

    monitor.publish_path_metrics(notifier, {
        "isp_gateway": None,
        "modem_configured": True,
        "modem": 1.5,
    })

    assert ("modem_status", "REACHABLE") in notifier.states
    assert ("modem_latency", 1.5) in notifier.states
    assert notifier.availability == [("modem_latency", True)]


def test_unreachable_modem_publishes_status_and_unavailable_latency():
    notifier = FakeNotifier()

    monitor.publish_path_metrics(notifier, {
        "isp_gateway": None,
        "modem_configured": True,
        "modem": None,
    })

    assert ("modem_status", "UNREACHABLE") in notifier.states
    assert not any(key == "modem_latency" for key, _ in notifier.states)
    assert notifier.availability == [("modem_latency", False)]


def test_unconfigured_modem_is_explicitly_reported():
    notifier = FakeNotifier()

    monitor.publish_path_metrics(notifier, {
        "isp_gateway": None,
        "modem_configured": False,
        "modem": None,
    })

    assert ("modem_status", "NOT_CONFIGURED") in notifier.states
    assert notifier.availability == [("modem_latency", False)]
