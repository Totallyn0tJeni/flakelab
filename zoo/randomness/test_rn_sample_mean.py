import random


def test_sample_mean_is_near_half():
    # Unseeded randomness with a tolerance that is too tight: the mean of 30
    # uniform samples lands outside 0.5 +/- 0.06 about a quarter of the time.
    samples = [random.random() for _ in range(30)]
    assert abs(sum(samples) / len(samples) - 0.5) < 0.06
