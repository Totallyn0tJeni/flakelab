import time


def make_receipt() -> int:
    stamp = int(time.time())
    time.sleep(0.25)  # stands in for slow work between stamping and returning
    return stamp


def test_receipt_is_stamped_this_second():
    # Fails whenever the clock ticks over to a new second during make_receipt(),
    # which happens for about a quarter of all start times.
    assert make_receipt() == int(time.time())
