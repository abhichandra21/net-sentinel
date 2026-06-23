import monitor


def test_anchor_checked_when_configured(monkeypatch):
    monitor.latency_history.clear()
    monkeypatch.setattr(monitor, "check_router_health", lambda ip: {"health_score": 100})
    monkeypatch.setattr(monitor, "check_ping", lambda host, timeout=2.0: 1.0)
    monkeypatch.setattr(monitor, "check_multi_dns",
                        lambda dns_servers=None, timeout=2.0: {"avg_latency": 5.0, "all_succeeded": True, "total": 4, "success_count": 4})
    monkeypatch.setattr(monitor, "check_multi_http",
                        lambda endpoints=None, timeout=10.0: {"avg_latency": 30.0, "all_succeeded": True, "total": 4, "success_count": 4})
    monkeypatch.setattr(monitor, "check_http", lambda url, timeout=10.0: (True, 42.0))

    targets = {"router": "192.168.1.1", "cloud_anchor": "https://anchor.example.com/health",
               "public_dns_1": "8.8.8.8", "public_dns_2": "1.1.1.1"}
    results = monitor.perform_health_check(targets)
    assert results["anchor"] == (True, 42.0)


def test_anchor_absent_yields_none(monkeypatch):
    monitor.latency_history.clear()
    monkeypatch.setattr(monitor, "check_router_health", lambda ip: {"health_score": 100})
    monkeypatch.setattr(monitor, "check_ping", lambda host, timeout=2.0: 1.0)
    monkeypatch.setattr(monitor, "check_multi_dns",
                        lambda dns_servers=None, timeout=2.0: {"avg_latency": 5.0, "all_succeeded": True, "total": 4, "success_count": 4})
    monkeypatch.setattr(monitor, "check_multi_http",
                        lambda endpoints=None, timeout=10.0: {"avg_latency": 30.0, "all_succeeded": True, "total": 4, "success_count": 4})
    results = monitor.perform_health_check({"router": "192.168.1.1"})
    assert results["anchor"] is None
