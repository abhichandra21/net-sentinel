from diagnostics import calculate_jitter


def test_calculate_jitter_returns_stdev():
    # stdev of [10, 12, 14] == 2.0
    assert calculate_jitter([10, 12, 14]) == 2.0


def test_calculate_jitter_too_few_samples_returns_none():
    assert calculate_jitter([10]) is None
