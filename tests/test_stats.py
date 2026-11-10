import pytest

from flakelab.engine.stats import failure_rate, wilson_interval


def test_matches_hand_computed_values() -> None:
    # 5 failures in 10 runs at 95%: worked by hand from the formula.
    low, high = wilson_interval(5, 10)
    assert low == pytest.approx(0.2366, abs=1e-4)
    assert high == pytest.approx(0.7634, abs=1e-4)


def test_zero_failures_still_leaves_room_for_doubt() -> None:
    # With no failures the upper bound is z^2 / (n + z^2), not zero.
    low, high = wilson_interval(0, 10)
    assert low == 0.0
    assert high == pytest.approx(3.8415 / 13.8415, abs=1e-4)


def test_all_failures_mirrors_zero_failures() -> None:
    low, high = wilson_interval(10, 10)
    assert high == 1.0
    assert low == pytest.approx(1 - wilson_interval(0, 10)[1])


def test_interval_contains_the_observed_rate() -> None:
    for failures in range(31):
        low, high = wilson_interval(failures, 30)
        assert 0.0 <= low <= failures / 30 <= high <= 1.0


def test_more_runs_narrow_the_interval() -> None:
    widths = [high - low for low, high in (wilson_interval(n // 4, n) for n in (20, 80, 320))]
    assert widths == sorted(widths, reverse=True)


def test_higher_confidence_widens_the_interval() -> None:
    low95, high95 = wilson_interval(3, 30, confidence=0.95)
    low99, high99 = wilson_interval(3, 30, confidence=0.99)
    assert low99 < low95 and high99 > high95


@pytest.mark.parametrize(
    ("failures", "total", "confidence"),
    [(0, 0, 0.95), (-1, 10, 0.95), (11, 10, 0.95), (1, 10, 0.0), (1, 10, 1.0)],
)
def test_rejects_impossible_inputs(failures: int, total: int, confidence: float) -> None:
    with pytest.raises(ValueError):
        wilson_interval(failures, total, confidence)


def test_failure_rate_bundles_the_numbers() -> None:
    rate = failure_rate(3, 30)
    assert rate.rate == pytest.approx(0.1)
    assert (rate.low, rate.high) == wilson_interval(3, 30)
