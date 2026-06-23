import subprocess
import diagnostics


def test_traceroute_returns_message_on_timeout(monkeypatch):
    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="traceroute", timeout=20)
    monkeypatch.setattr(diagnostics.subprocess, "run", boom)
    out = diagnostics.run_traceroute("8.8.8.8", timeout=20)
    assert out.startswith("Traceroute timed out")


def test_traceroute_passes_timeout_to_subprocess(monkeypatch):
    captured = {}

    class _Result:
        stdout = "ok"

    def fake_run(cmd, capture_output, text, timeout):
        captured["timeout"] = timeout
        return _Result()

    monkeypatch.setattr(diagnostics.subprocess, "run", fake_run)
    diagnostics.run_traceroute("8.8.8.8", timeout=7)
    assert captured["timeout"] == 7
