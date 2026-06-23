import monitor
from classify import classify_load


class FakeNotifier:
    def __init__(self):
        self.states = {}
        self.events = []

    def update_state(self, key, value):
        self.states[key] = value

    def log_event(self, *args):
        self.events.append(args)


def test_loaded_loss_is_classified_as_degraded():
    code, confidence = classify_load({
        "idle_ms": 10.0,
        "loaded_ms": None,
        "bloat_ms": None,
        "idle_loss_pct": 0.0,
        "loaded_loss_pct": 100.0,
    })
    assert code == "DEGRADED_UNDER_LOAD"
    assert confidence >= 0.7


def test_cloudflare_success_does_not_skip_load_test(monkeypatch):
    notifier = FakeNotifier()
    calls = []
    monkeypatch.setattr(
        monitor,
        "run_cloudflare_speedtest",
        lambda: {"download_mbps": 100.0, "latency_ms": 12.0},
    )
    monkeypatch.setattr(monitor, "run_speedtest", lambda: None)

    def fake_bloat(host):
        calls.append(host)
        return {
            "idle_ms": 10.0,
            "loaded_ms": 90.0,
            "bloat_ms": 80.0,
            "idle_loss_pct": 0.0,
            "loaded_loss_pct": 0.0,
        }

    monkeypatch.setattr(monitor, "measure_bufferbloat", fake_bloat)
    monitor.perform_speedtest(
        notifier,
        {"isp_gateway": "100.64.0.1"},
        {"use_cloudflare": True},
        {"bufferbloat_ms": 50, "loaded_loss_pct": 5},
    )

    assert calls == ["100.64.0.1"]
    assert notifier.states["load_quality_status"] == "DEGRADED_UNDER_LOAD"
    assert notifier.states["bufferbloat_ms"] == 80.0


def test_unavailable_load_test_is_not_reported_healthy(monkeypatch):
    notifier = FakeNotifier()
    monkeypatch.setattr(
        monitor,
        "run_cloudflare_speedtest",
        lambda: {"download_mbps": 100.0, "latency_ms": 12.0},
    )
    monkeypatch.setattr(monitor, "measure_bufferbloat", lambda host: None)
    monitor.perform_speedtest(notifier, {}, {"use_cloudflare": True}, {})
    assert notifier.states["load_quality_status"] == "UNAVAILABLE"
