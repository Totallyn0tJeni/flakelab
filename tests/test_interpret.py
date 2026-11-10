"""Unit tests for turning a run's events into one outcome for the target test."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flakelab.runner.process import _read_events, interpret

T = "tests/test_a.py::test_target"


def start(nodeid: str = T) -> dict[str, Any]:
    return {"event": "start", "nodeid": nodeid}


def report(when: str, outcome: str, message: str | None = None) -> dict[str, Any]:
    return {"event": "report", "nodeid": T, "when": when, "outcome": outcome, "message": message}


FINISH: dict[str, Any] = {"event": "finish", "exitstatus": 0}
PASSED_PHASES = [report("setup", "passed"), report("call", "passed"), report("teardown", "passed")]


def test_passed() -> None:
    assert interpret([start(), *PASSED_PHASES, FINISH], T, 0) == ("passed", None)


def test_failure_in_the_test_body() -> None:
    events = [
        start(),
        report("setup", "passed"),
        report("call", "failed", "assert 1 == 2"),
        report("teardown", "passed"),
        FINISH,
    ]
    assert interpret(events, T, 1) == ("failed", "assert 1 == 2")


def test_failure_in_setup_is_an_error() -> None:
    events = [start(), report("setup", "failed", "boom"), report("teardown", "passed"), FINISH]
    assert interpret(events, T, 1) == ("error", "boom")


def test_body_failure_wins_over_teardown_failure() -> None:
    events = [
        start(),
        report("setup", "passed"),
        report("call", "failed", "body"),
        report("teardown", "failed", "cleanup"),
        FINISH,
    ]
    assert interpret(events, T, 1) == ("failed", "body")


def test_skipped() -> None:
    events = [start(), report("setup", "skipped"), report("teardown", "passed"), FINISH]
    assert interpret(events, T, 0) == ("skipped", None)


def test_timeout_while_the_target_was_running() -> None:
    outcome, message = interpret([start(), report("setup", "passed")], T, None)
    assert outcome == "timeout"
    assert message is not None


def test_timeout_before_the_target_started_is_not_the_targets_fault() -> None:
    outcome, _ = interpret([start("tests/test_a.py::test_other")], T, None)
    assert outcome == "not_run"


def test_target_that_passed_before_a_later_hang_still_passed() -> None:
    events = [start(), *PASSED_PHASES, start("tests/test_a.py::test_hangs")]
    assert interpret(events, T, None) == ("passed", None)


def test_crash_mid_test() -> None:
    outcome, message = interpret([start(), report("setup", "passed")], T, -11)
    assert outcome == "crashed"
    assert message is not None and "-11" in message


def test_not_selected() -> None:
    outcome, message = interpret([FINISH], T, 4)
    assert outcome == "not_run"
    assert message is not None and "test id" in message


def test_no_events_at_all() -> None:
    outcome, _ = interpret([], T, 2)
    assert outcome == "not_run"


def test_partial_last_line_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text('{"event": "start", "nodeid": "a"}\n{"event": "rep', encoding="utf-8")
    assert _read_events(path) == [{"event": "start", "nodeid": "a"}]
