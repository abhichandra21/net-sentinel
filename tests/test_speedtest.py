import diagnostics


class _Resp:
    status_code = 200
    content = b"x" * 25_000_000  # 25 MB


def test_cloudflare_speedtest_latency_is_ping_not_download_duration(monkeypatch):
    # Download takes a "long" time; latency must come from ping, not duration.
    def fake_get(url, timeout=30):
        import time
        time.sleep(0.01)
        return _Resp()
    monkeypatch.setattr(diagnostics.requests, "get", fake_get)
    monkeypatch.setattr(diagnostics, "check_ping", lambda host, timeout=2: 14.5)

    result = diagnostics.run_cloudflare_speedtest()
    assert result["latency_ms"] == 14.5
    assert result["download_mbps"] > 0
