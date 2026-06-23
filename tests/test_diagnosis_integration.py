import monitor


class FakeNotifier:
    def __init__(self):
        self.states = {}
        self.events = []

    def update_state(self, key, value):
        self.states[key] = value

    def log_event(self, *args):
        self.events.append(args)


def test_lastmile_classifier_preempts_legacy_gateway_label(monkeypatch):
    monkeypatch.setattr(monitor, "run_traceroute", lambda *a, **k: "trace")
    notifier = FakeNotifier()
    results = {
        "router": 1.0,
        "router_health": {"health_score": 100},
        "isp_gateway_configured": True,
        "isp_gateway": None,
        "dns": {"all_succeeded": False},
        "http": {"all_succeeded": False},
        "anchor": (False, None),
        "jitter": 1.0,
    }
    blame = monitor.diagnose_issue(
        {"router": "192.168.1.1", "isp_gateway": "100.64.0.1"},
        results,
        notifier,
    )
    assert blame == "LASTMILE_RF_SUSPECT"
    assert notifier.states["blame"] == "LASTMILE_RF_SUSPECT"
