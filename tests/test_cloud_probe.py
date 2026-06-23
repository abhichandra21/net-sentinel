import importlib.util, pathlib

spec = importlib.util.spec_from_file_location(
    "cloud_probe_main",
    pathlib.Path(__file__).resolve().parent.parent / "cloud_probe" / "main.py",
)
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)


def test_single_failure_does_not_flip_to_offline():
    state = {"status": "online", "streak": 0, "latency": 12.5}
    state, changed = cp.update_debounce(
        state, is_up=False, latency=None, threshold=3,
    )
    assert state["status"] == "online"
    assert state["latency"] == 12.5
    assert changed is False


def test_three_failures_flip_to_offline():
    state = {"status": "online", "streak": 0, "latency": 12.5}
    for _ in range(3):
        state, changed = cp.update_debounce(
            state, is_up=False, latency=None, threshold=3,
        )
    assert state["status"] == "offline"
    assert state["latency"] is None
    assert changed is True


def test_recovery_resets_streak():
    state = {"status": "online", "streak": 2, "latency": 15.0}
    state, changed = cp.update_debounce(
        state, is_up=True, latency=11.0, threshold=3,
    )
    assert state["status"] == "online"
    assert state["streak"] == 0
    assert state["latency"] == 11.0


def test_stable_state_still_builds_heartbeat_payload():
    state = {"status": "online", "streak": 0, "latency": 12.5}
    assert cp.notification_for_state(state) == (True, 12.5)
