"""Run pytest once, in its own process, and report what happened to one test.

Why a fresh process for every run:

* Some conditions can only be set before Python starts, such as the hash seed.
* Nothing can leak from one run into the next. Leaked state is exactly the
  kind of bug Flakelab hunts, so the tool must not create it.
* A test that hangs or crashes the interpreter cannot take Flakelab down.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from flakelab.runner.plugin import RESULT_ENV

Outcome = Literal["passed", "failed", "error", "skipped", "timeout", "crashed", "not_run"]

# Outcomes that count as the test failing, and as the test passing. Everything
# else ("skipped", "not_run") says nothing about flakiness and is excluded.
FAILING: frozenset[str] = frozenset({"failed", "error", "timeout", "crashed"})
PASSING: frozenset[str] = frozenset({"passed"})


@dataclass(frozen=True)
class RunRequest:
    repo: Path
    """Directory pytest is started from."""
    target: str
    """Node id of the test under diagnosis, e.g. ``tests/test_a.py::test_x``."""
    pytest_args: tuple[str, ...]
    """What pytest should collect: the target itself, or the suite around it."""
    log_path: Path
    hash_seed: int
    timeout_s: float
    extra_env: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RunResult:
    outcome: Outcome
    duration_ms: int
    exit_code: int | None
    """pytest's exit code; None when the run was killed for timing out."""
    order: tuple[str, ...]
    """Node ids in the order they started."""
    message: str | None
    log_path: Path
    hash_seed: int


def run_once(request: RunRequest) -> RunResult:
    request.log_path.parent.mkdir(parents=True, exist_ok=True)
    events_path = request.log_path.with_suffix(".events.jsonl")
    env = {
        **os.environ,
        **request.extra_env,
        RESULT_ENV: str(events_path),
        "PYTHONHASHSEED": str(request.hash_seed),
    }
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "flakelab.runner.plugin",
        # The cache plugin writes files that parallel runs would fight over.
        "-p",
        "no:cacheprovider",
        *request.pytest_args,
    ]

    started = time.monotonic()
    # Output goes straight to a file, not through a pipe: a test that prints
    # megabytes cannot fill a buffer and stall, and nothing is held in memory.
    with open(request.log_path, "wb") as log:
        process = _spawn(command, cwd=request.repo, env=env, log=log)
        try:
            exit_code: int | None = process.wait(timeout=request.timeout_s)
        except subprocess.TimeoutExpired:
            _kill_tree(process)
            process.wait()
            exit_code = None
    duration_ms = round((time.monotonic() - started) * 1000)

    events = _read_events(events_path)
    events_path.unlink(missing_ok=True)
    outcome, message = interpret(events, request.target, exit_code)
    return RunResult(
        outcome=outcome,
        duration_ms=duration_ms,
        exit_code=exit_code,
        order=tuple(e["nodeid"] for e in events if e["event"] == "start"),
        message=message,
        log_path=request.log_path,
        hash_seed=request.hash_seed,
    )


def interpret(
    events: list[dict[str, Any]], target: str, exit_code: int | None
) -> tuple[Outcome, str | None]:
    """Decide the target test's outcome from the events of one run.

    ``exit_code`` is None when the run was killed for exceeding its timeout.
    """
    timed_out = exit_code is None
    started = any(e["event"] == "start" and e["nodeid"] == target for e in events)
    reports = [e for e in events if e["event"] == "report" and e["nodeid"] == target]
    session_finished = any(e["event"] == "finish" for e in events)

    failed = [r for r in reports if r["outcome"] == "failed"]
    if failed:
        # A failure in the test body is "failed"; one in a fixture's setup or
        # teardown is "error". The body wins if both happened.
        in_body = [r for r in failed if r["when"] == "call"]
        chosen = in_body[0] if in_body else failed[0]
        return ("failed" if in_body else "error"), chosen["message"]

    # pytest always reports a teardown phase, so its presence means the test
    # ran to completion.
    completed = any(r["when"] == "teardown" for r in reports)
    if completed:
        if any(r["outcome"] == "skipped" for r in reports):
            return "skipped", None
        return "passed", None

    if started:
        if timed_out:
            return "timeout", "the test was still running when the time limit was reached"
        return "crashed", f"the test process exited with code {exit_code} mid-test"

    if timed_out:
        return "not_run", "the time limit was reached before the test started"
    if not session_finished:
        return "not_run", f"pytest exited with code {exit_code} before the test started"
    return "not_run", "pytest did not select this test; check the test id"


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            # A process killed mid-write can leave a partial last line.
            break
    return events


def _spawn(
    command: list[str], *, cwd: Path, env: dict[str, str], log: Any
) -> subprocess.Popen[bytes]:
    # The child gets its own process group so that a timeout can kill it
    # together with any processes the tests started.
    if sys.platform == "win32":
        return subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    return subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def _kill_tree(process: subprocess.Popen[bytes]) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )
        if process.poll() is None:
            process.kill()
    else:
        import signal

        # The process may have exited on its own between the timeout and here.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
