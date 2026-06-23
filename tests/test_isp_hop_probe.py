import monitor


def _stub_checks(monkeypatch):
    monitor.latency_history.clear()
    monkeypatch.setattr(monitor, "check_router_health", lambda ip: {"health_score": 100})
    monkeypatch.setattr(
        monitor,
        "check_multi_dns",
        lambda dns_servers=None, timeout=2.0: {
            "avg_latency": 5.0, "all_succeeded": True,
            "total": 4, "success_count": 4,
        },
    )
    monkeypatch.setattr(
        monitor,
        "check_multi_http",
        lambda endpoints=None, timeout=10.0: {
            "avg_latency": 30.0, "all_succeeded": True,
            "total": 4, "success_count": 4,
        },
    )


def test_health_check_marks_configured_gateway(monkeypatch):
    _stub_checks(monkeypatch)
    monkeypatch.setattr(
        monitor, "check_ping",
        lambda host, timeout=2.0: 9.0 if host == "100.64.0.1" else 1.0,
    )
    results = monitor.perform_health_check({
        "router": "192.168.1.1",
        "isp_gateway": "100.64.0.1",
    })
    assert results["isp_gateway_configured"] is True
    assert results["isp_gateway"] == 9.0


def test_health_check_marks_unobserved_gateway(monkeypatch):
    _stub_checks(monkeypatch)
    monkeypatch.setattr(monitor, "check_ping", lambda host, timeout=2.0: 1.0)
    results = monitor.perform_health_check({"router": "192.168.1.1"})
    assert results["isp_gateway_configured"] is False
    assert results["isp_gateway"] is None


def test_publish_path_metrics_publishes_reachable_gateway():
    calls = []

    class FakeNotifier:
        def update_state(self, key, value):
            calls.append((key, value))

        def update_availability(self, key, available):
            calls.append((f"{key}_availability", available))

    monitor.publish_path_metrics(
        FakeNotifier(),
        {"isp_gateway_configured": True, "isp_gateway": 9.0},
    )
    assert ("isp_gateway_latency", 9.0) in calls
