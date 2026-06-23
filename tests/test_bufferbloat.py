import diagnostics


def _fake_load(url, stop_event, ready_event, failed_event):
    ready_event.set()
    stop_event.wait(timeout=1)


def test_bufferbloat_reports_latency_delta_and_zero_loss(monkeypatch):
    seq = iter([10.0, 10.0, 10.0, 210.0, 210.0, 210.0])
    monkeypatch.setattr(diagnostics, "check_ping", lambda host, timeout=2: next(seq))
    monkeypatch.setattr(diagnostics, "_download_load", _fake_load)

    result = diagnostics.measure_bufferbloat(
        "100.64.0.1", idle_samples=3, load_samples=3,
    )
    assert result["idle_ms"] == 10.0
    assert result["loaded_ms"] == 210.0
    assert result["bloat_ms"] == 200.0
    assert result["loaded_loss_pct"] == 0.0


def test_total_loaded_loss_is_not_reported_as_zero_bloat(monkeypatch):
    seq = iter([10.0, 10.0, 10.0, None, None, None])
    monkeypatch.setattr(diagnostics, "check_ping", lambda host, timeout=2: next(seq))
    monkeypatch.setattr(diagnostics, "_download_load", _fake_load)

    result = diagnostics.measure_bufferbloat(
        "100.64.0.1", idle_samples=3, load_samples=3,
    )
    assert result["loaded_ms"] is None
    assert result["bloat_ms"] is None
    assert result["loaded_loss_pct"] == 100.0


def test_failed_load_generator_returns_none(monkeypatch):
    monkeypatch.setattr(diagnostics, "check_ping", lambda host, timeout=2: 10.0)

    def failed_load(url, stop_event, ready_event, failed_event):
        failed_event.set()
        ready_event.set()

    monkeypatch.setattr(diagnostics, "_download_load", failed_load)
    assert diagnostics.measure_bufferbloat("100.64.0.1") is None
