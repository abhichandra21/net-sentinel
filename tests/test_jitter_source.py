import monitor


def test_health_check_feeds_router_rtt_into_jitter(monkeypatch):
    monitor.latency_history.clear()
    # Stub every diagnostic so only the jitter-source wiring is under test.
    monkeypatch.setattr(monitor, "check_router_health", lambda ip: {"health_score": 100})
    monkeypatch.setattr(monitor, "check_ping", lambda host, timeout=2.0: 11.0)
    monkeypatch.setattr(monitor, "check_multi_dns",
                        lambda dns_servers=None, timeout=2.0: {"avg_latency": 5.0, "all_succeeded": True, "total": 4, "success_count": 4})
    monkeypatch.setattr(monitor, "check_multi_http",
                        lambda endpoints=None, timeout=10.0: {"avg_latency": 300.0, "all_succeeded": True, "total": 4, "success_count": 4})

    targets = {"router": "192.168.1.1", "public_dns_1": "8.8.8.8", "public_dns_2": "1.1.1.1"}
    monitor.perform_health_check(targets)

    # Router RTT (11.0), not HTTP avg (300.0), must be the jitter sample.
    assert list(monitor.latency_history)[-1] == 11.0
