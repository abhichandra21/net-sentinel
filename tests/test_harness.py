import threading
from concurrent.futures import wait

import diagnostics
from diagnostics import calculate_jitter


def test_calculate_jitter_returns_stdev():
    # stdev of [10, 12, 14] == 2.0
    assert calculate_jitter([10, 12, 14]) == 2.0


def test_calculate_jitter_too_few_samples_returns_none():
    assert calculate_jitter([10]) is None


def test_http_check_fails_futures_not_consumed_before_deadline(monkeypatch):
    endpoints = ["https://one.example", "https://two.example"]
    monkeypatch.setattr(
        diagnostics, "check_http", lambda url, timeout: (True, 10.0)
    )

    def omit_completed_futures(futures, timeout):
        wait(futures)
        return iter(())

    monkeypatch.setattr(diagnostics, "as_completed", omit_completed_futures)

    result = diagnostics.check_multi_http(endpoints=endpoints, timeout=0)

    assert result["success_count"] == 0
    assert result["failed_endpoints"] == endpoints
    assert result["all_succeeded"] is False


def test_http_check_does_not_start_another_batch_while_workers_are_blocked(
        monkeypatch):
    endpoints = [f"https://{index}.example" for index in range(4)]
    release = threading.Event()
    all_started = threading.Event()
    started = []

    def blocked_http(url, timeout):
        started.append(url)
        if len(started) == len(endpoints):
            all_started.set()
        release.wait(timeout=5)
        return True, 10.0

    monkeypatch.setattr(diagnostics, "check_http", blocked_http)

    try:
        first = diagnostics.check_multi_http(endpoints=endpoints, timeout=-0.95)
        assert all_started.is_set()

        second = diagnostics.check_multi_http(endpoints=endpoints, timeout=-0.95)

        assert len(started) == len(endpoints)
        assert first["failed_endpoints"] == endpoints
        assert second["failed_endpoints"] == endpoints
    finally:
        release.set()
