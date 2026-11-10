"""Verify that every zoo test behaves the way zoo/manifest.json says it does.

The zoo is the ground truth for Flakelab's verdicts, so it has to be checked
itself: a "flaky" test that never fails would make every later result wrong.

Each zoo test runs in a fresh Python process. That matters because some
causes, such as the hash seed, are fixed for the lifetime of a process.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
MANIFEST: dict[str, Any] = json.loads((ROOT / "zoo" / "manifest.json").read_text("utf-8"))
CASES: dict[str, dict[str, Any]] = {case["id"]: case for case in MANIFEST["cases"]}

# With a failure rate near 25%, 40 runs miss every failure about once in
# 100,000 attempts, so these checks are not themselves meaningfully flaky.
RERUNS = 40


def run_pytest(*args: str, env: dict[str, str] | None = None) -> bool:
    """Run pytest in a new process. Return True if every selected test passed."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
        cwd=ROOT,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        timeout=120,
    )
    # 0 = all passed, 1 = some failed. Anything else means pytest itself broke.
    if result.returncode not in (0, 1):
        raise RuntimeError(
            f"pytest exited with {result.returncode}:\n{result.stdout}\n{result.stderr}"
        )
    return result.returncode == 0


def rerun(test: str, times: int = RERUNS) -> list[bool]:
    """Run one test `times` times, each in its own process, a few at a time."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda _: run_pytest(test), range(times)))


def test_every_manifest_test_exists() -> None:
    tests = [case["test"] for case in CASES.values()]
    assert run_pytest("--collect-only", *tests)


def test_victim_passes_alone_and_fails_after_polluter() -> None:
    case = CASES["order-victim"]
    victim, polluter = case["test"], case["polluters"][0]
    assert run_pytest(victim)
    assert run_pytest(polluter)
    assert not run_pytest(polluter, victim)


def test_brittle_fails_alone_and_passes_after_setter() -> None:
    case = CASES["order-brittle"]
    brittle, setter = case["test"], case["state_setters"][0]
    assert not run_pytest(brittle)
    assert run_pytest(setter, brittle)


@pytest.mark.parametrize(
    "case_id",
    ["time-same-second", "random-sample-mean", "concurrency-wait-race", "network-fetch-status"],
)
def test_intermittent_case_both_passes_and_fails(case_id: str) -> None:
    outcomes = rerun(CASES[case_id]["test"])
    assert True in outcomes, f"{case_id} never passed in {RERUNS} runs"
    assert False in outcomes, f"{case_id} never failed in {RERUNS} runs"


def test_hash_order_depends_only_on_the_hash_seed() -> None:
    test = CASES["random-hash-order"]["test"]

    def with_seed(seed: int) -> bool:
        return run_pytest(test, env={"PYTHONHASHSEED": str(seed)})

    with ThreadPoolExecutor(max_workers=4) as pool:
        first = list(pool.map(with_seed, range(RERUNS)))
        again = list(pool.map(with_seed, range(8)))

    assert True in first and False in first
    # The same seed must always give the same outcome.
    assert again == first[:8]


@pytest.mark.skipif(sys.platform == "win32", reason="the TZ variable works differently on Windows")
def test_timezone_case_passes_in_utc_and_fails_elsewhere() -> None:
    test = CASES["time-timezone"]["test"]
    assert run_pytest(test, env={"TZ": "UTC"})
    assert not run_pytest(test, env={"TZ": "Asia/Tokyo"})


def test_controls_are_not_flaky() -> None:
    assert all(rerun(CASES["stable-pass"]["test"], times=10))
    assert not any(rerun(CASES["stable-fail"]["test"], times=10))
