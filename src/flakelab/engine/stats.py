"""Statistics for pass/fail data.

Everything here uses only the standard library, and every function is small
enough to check by hand.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist


@dataclass(frozen=True)
class FailureRate:
    failures: int
    total: int
    low: float
    high: float
    confidence: float

    @property
    def rate(self) -> float:
        return self.failures / self.total


def wilson_interval(failures: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    """Confidence interval for a failure rate, using the Wilson score method.

    If a test failed 3 times in 30 runs, its true failure rate is probably not
    exactly 10%. The interval gives the range of rates that are consistent with
    what we saw.

    Why Wilson and not the textbook formula (rate +/- z * standard error): the
    textbook one collapses to a width of zero when there are no failures, which
    would claim certainty that a test never fails. Wilson stays honest at 0 and
    at 100%, and with small samples, which are exactly the cases we care about.
    """
    if total <= 0:
        raise ValueError("total must be positive")
    if not 0 <= failures <= total:
        raise ValueError("failures must be between 0 and total")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")

    # z is how many standard deviations cover the middle `confidence` share of
    # a normal distribution: about 1.96 for 95%.
    z = NormalDist().inv_cdf(1 - (1 - confidence) / 2)
    p = failures / total
    denominator = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denominator
    half_width = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denominator
    # At the two extremes the bound is exactly 0 or 1; computing it would leave
    # floating-point dust such as 2.8e-17.
    low = 0.0 if failures == 0 else max(0.0, centre - half_width)
    high = 1.0 if failures == total else min(1.0, centre + half_width)
    return low, high


def failure_rate(failures: int, total: int, confidence: float = 0.95) -> FailureRate:
    low, high = wilson_interval(failures, total, confidence)
    return FailureRate(failures=failures, total=total, low=low, high=high, confidence=confidence)
