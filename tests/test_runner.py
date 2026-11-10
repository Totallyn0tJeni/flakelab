"""Integration tests: real pytest processes run against a throwaway project."""

from __future__ import annotations

from pathlib import Path

import pytest

from flakelab.runner.process import RunRequest, RunResult, run_once

SAMPLE = """
import os
import time

import pytest


def test_passes():
    pass


def test_fails():
    assert 1 + 1 == 3


@pytest.fixture
def broken():
    raise RuntimeError("fixture exploded")


def test_setup_error(broken):
    pass


@pytest.mark.skip(reason="not today")
def test_skipped():
    pass


def test_hangs():
    time.sleep(600)


def test_crashes():
    os._exit(7)


def test_noisy():
    print("x" * 5_000_000)
    assert False


def test_hash_seed():
    assert os.environ["PYTHONHASHSEED"] == "12345"
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "test_sample.py").write_text(SAMPLE, encoding="utf-8")
    return tmp_path


def run(project: Path, test: str, *also: str, timeout_s: float = 60, seed: int = 1) -> RunResult:
    """Run `also` (if given) followed by `test`; `test` is the target."""
    ids = tuple(f"test_sample.py::{name}" for name in (*also, test))
    return run_once(
        RunRequest(
            repo=project,
            target=ids[-1],
            pytest_args=ids,
            log_path=project / "logs" / "run.log",
            hash_seed=seed,
            timeout_s=timeout_s,
        )
    )


def test_pass(project: Path) -> None:
    result = run(project, "test_passes")
    assert result.outcome == "passed"
    assert result.exit_code == 0
    assert result.message is None
    assert result.duration_ms > 0


def test_fail_carries_the_assertion_message(project: Path) -> None:
    result = run(project, "test_fails")
    assert result.outcome == "failed"
    assert result.exit_code == 1
    assert result.message is not None and "assert" in result.message


def test_fixture_failure_is_an_error(project: Path) -> None:
    result = run(project, "test_setup_error")
    assert result.outcome == "error"
    assert result.message is not None and "fixture exploded" in result.message


def test_skip(project: Path) -> None:
    assert run(project, "test_skipped").outcome == "skipped"


def test_unknown_test_id(project: Path) -> None:
    assert run(project, "test_does_not_exist").outcome == "not_run"


def test_hang_is_killed_at_the_time_limit(project: Path) -> None:
    result = run(project, "test_hangs", timeout_s=3)
    assert result.outcome == "timeout"
    assert result.exit_code is None
    assert result.duration_ms < 30_000


def test_hang_in_an_earlier_test_is_not_blamed_on_the_target(project: Path) -> None:
    result = run(project, "test_passes", "test_hangs", timeout_s=3)
    assert result.outcome == "not_run"


def test_interpreter_crash(project: Path) -> None:
    result = run(project, "test_crashes")
    assert result.outcome == "crashed"
    assert result.exit_code == 7


def test_megabytes_of_output_go_to_the_log(project: Path) -> None:
    result = run(project, "test_noisy")
    assert result.outcome == "failed"
    assert result.log_path.stat().st_size > 5_000_000


def test_order_is_recorded(project: Path) -> None:
    result = run(project, "test_passes", "test_fails")
    assert result.order == ("test_sample.py::test_fails", "test_sample.py::test_passes")
    assert result.outcome == "passed"


def test_hash_seed_reaches_the_test_process(project: Path) -> None:
    assert run(project, "test_hash_seed", seed=12345).outcome == "passed"
    assert run(project, "test_hash_seed", seed=54321).outcome == "failed"


def test_event_file_is_cleaned_up(project: Path) -> None:
    result = run(project, "test_passes")
    assert [p.name for p in result.log_path.parent.iterdir()] == ["run.log"]
