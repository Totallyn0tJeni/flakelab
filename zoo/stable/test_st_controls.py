"""Controls: tests that are not flaky. Flakelab must not invent a cause for them."""


def test_always_passes():
    assert sorted([3, 1, 2]) == [1, 2, 3]


def test_always_fails():
    # A consistent failure is a real bug, not flakiness.
    assert sorted([3, 1, 2]) == [3, 2, 1]
