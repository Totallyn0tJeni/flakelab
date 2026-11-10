"""The pytest plugin that runs inside the test process.

Flakelab starts pytest with ``-p flakelab.runner.plugin``. The plugin writes
one JSON line per event to the file named by ``FLAKELAB_RESULT_FILE``:

    {"event": "start", "nodeid": ...}
    {"event": "report", "nodeid": ..., "when": "call", "outcome": "failed", ...}
    {"event": "finish", "exitstatus": 1}

Events are written as they happen, not at the end, so that a run which hangs
or crashes still tells us which test was executing when it died.

This module must stay small and depend only on pytest: it is imported into
other people's test processes.
"""

from __future__ import annotations

import json
import os
from typing import IO, Any

import pytest

RESULT_ENV = "FLAKELAB_RESULT_FILE"
MESSAGE_LIMIT = 300


class EventRecorder:
    def __init__(self, stream: IO[str]) -> None:
        self._stream = stream

    def _emit(self, **event: Any) -> None:
        self._stream.write(json.dumps(event) + "\n")
        self._stream.flush()

    def pytest_runtest_logstart(self, nodeid: str) -> None:
        self._emit(event="start", nodeid=nodeid)

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        self._emit(
            event="report",
            nodeid=report.nodeid,
            when=report.when,
            outcome=report.outcome,
            duration=report.duration,
            message=_failure_message(report) if report.failed else None,
        )

    def pytest_sessionfinish(self, exitstatus: int) -> None:
        self._emit(event="finish", exitstatus=int(exitstatus))
        self._stream.close()


def _failure_message(report: pytest.TestReport) -> str:
    """The one-line reason for a failure, e.g. ``assert 3 == 4``."""
    crash = getattr(report.longrepr, "reprcrash", None)
    text = crash.message if crash is not None else str(report.longrepr)
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    return first_line[:MESSAGE_LIMIT]


def pytest_configure(config: pytest.Config) -> None:
    path = os.environ.get(RESULT_ENV)
    # pytest-xdist workers forward their reports to the controller process, so
    # only the controller records.
    if not path or hasattr(config, "workerinput"):
        return
    stream = open(path, "w", encoding="utf-8")  # noqa: SIM115 - closed at session finish
    config.pluginmanager.register(EventRecorder(stream), "flakelab-recorder")
