"""End-to-end tests of `flakelab diagnose` against the flaky zoo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from flakelab.cli import app
from flakelab.engine.baseline import BaselineConfig, normalize_target, run_baseline
from flakelab.engine.stats import wilson_interval
from flakelab.store.db import Store

ROOT = Path(__file__).resolve().parent.parent
CASES: dict[str, dict[str, Any]] = {
    case["id"]: case
    for case in json.loads((ROOT / "zoo" / "manifest.json").read_text("utf-8"))["cases"]
}


def baseline(
    store: Store, case_id: str, runs: int, suite: tuple[str, ...] = (), seed: int = 1
) -> BaselineConfig:
    return BaselineConfig(
        repo=ROOT,
        target=CASES[case_id]["test"],
        suite=suite,
        runs=runs,
        jobs=4,
        timeout_s=120,
        seed=seed,
    )


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "data")


@pytest.mark.parametrize(
    ("case_id", "built_in_rate"),
    [
        ("network-fetch-status", 0.25),  # DROP_RATE in zoo/network/flaky_service.py
        ("random-sample-mean", 0.255),  # P(|mean of 30 uniforms - 0.5| >= 0.06)
    ],
)
def test_measured_rate_matches_the_rate_built_into_the_zoo(
    store: Store, case_id: str, built_in_rate: float
) -> None:
    summary = run_baseline(baseline(store, case_id, runs=60), store)
    assert summary.rate is not None and summary.rate.total == 60
    # A 99.9% interval, so this check itself fails about once in 1000 runs
    # rather than once in 20.
    low, high = wilson_interval(summary.failures, 60, confidence=0.999)
    assert low <= built_in_rate <= high


def test_victim_fails_every_time_inside_its_suite(store: Store) -> None:
    summary = run_baseline(baseline(store, "order-victim", 4, suite=("zoo/order_victim",)), store)
    assert (summary.failures, summary.passes) == (4, 0)
    assert summary.top_failure_message is not None and "csv" in summary.top_failure_message

    # The stored order shows the polluter ran first.
    row = store.runs(summary.experiment_id)[0]
    assert store.order(row["order_hash"]) == [
        CASES["order-victim"]["polluters"][0],
        CASES["order-victim"]["test"],
    ]


def test_victim_passes_every_time_alone(store: Store) -> None:
    summary = run_baseline(baseline(store, "order-victim", 4), store)
    assert (summary.failures, summary.passes) == (0, 4)


def test_same_seed_replays_the_same_hash_seeds(store: Store) -> None:
    first = run_baseline(baseline(store, "random-hash-order", 8, seed=99), store)
    second = run_baseline(baseline(store, "random-hash-order", 8, seed=99), store)

    def by_seed(experiment_id: int) -> dict[int, str]:
        return {row["hash_seed"]: row["outcome"] for row in store.runs(experiment_id)}

    assert by_seed(first.experiment_id) == by_seed(second.experiment_id)


def test_session_is_marked_finished(store: Store) -> None:
    summary = run_baseline(baseline(store, "stable-pass", 2), store)
    session = store.session(summary.session_id)
    assert session["status"] == "finished"
    assert json.loads(session["config_json"])["runs"] == 2


def test_windows_style_paths_are_normalised() -> None:
    assert normalize_target(r"tests\unit\test_a.py::test_x") == "tests/unit/test_a.py::test_x"
    assert normalize_target("tests/test_a.py::test_x[a\\b]") == "tests/test_a.py::test_x[a\\b]"


# -- the command line ---------------------------------------------------------


def invoke(tmp_path: Path, *args: str) -> tuple[int, str]:
    result = CliRunner().invoke(
        app, ["diagnose", *args, "--repo", str(ROOT), "--data-dir", str(tmp_path / "data")]
    )
    return result.exit_code, result.output


def test_cli_reports_a_stable_test_without_claiming_certainty(tmp_path: Path) -> None:
    code, output = invoke(tmp_path, CASES["stable-pass"]["test"], "-n", "5", "-j", "4")
    assert code == 0
    assert "5 passed" in output
    assert "Never failed" in output
    assert "does not prove" in output


def test_cli_reports_a_consistent_failure(tmp_path: Path) -> None:
    code, output = invoke(tmp_path, CASES["stable-fail"]["test"], "-n", "5", "-j", "4")
    assert code == 0
    assert "Failed every time" in output


def test_cli_reports_flakiness(tmp_path: Path) -> None:
    code, output = invoke(tmp_path, CASES["network-fetch-status"]["test"], "-n", "40", "-j", "4")
    assert code == 0
    assert "Flaky" in output


def test_cli_exits_2_when_the_test_does_not_exist(tmp_path: Path) -> None:
    code, output = invoke(tmp_path, "zoo/stable/test_st_controls.py::test_nope", "-n", "2")
    assert code == 2
    assert "never produced" in output


def test_cli_runs_inside_a_suite(tmp_path: Path) -> None:
    code, output = invoke(
        tmp_path, CASES["order-brittle"]["test"], "-n", "3", "--suite", "zoo/order_brittle"
    )
    assert code == 0
    assert "3 passed" in output
