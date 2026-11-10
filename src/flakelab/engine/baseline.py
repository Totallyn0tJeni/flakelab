"""The baseline experiment: how often does the test fail when nothing is changed?

Every later experiment is a comparison against this number, so it is measured
first and stored like any other experiment.
"""

from __future__ import annotations

import random
import subprocess
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from flakelab.engine.stats import FailureRate, failure_rate
from flakelab.runner.process import FAILING, PASSING, RunRequest, RunResult, run_once
from flakelab.store.db import Store, timestamp


@dataclass(frozen=True)
class BaselineConfig:
    repo: Path
    target: str
    suite: tuple[str, ...]
    """Paths handed to pytest. Empty means the target runs on its own."""
    runs: int
    jobs: int
    timeout_s: float
    seed: int


@dataclass(frozen=True)
class BaselineSummary:
    session_id: int
    experiment_id: int
    counts: Counter[str]
    rate: FailureRate | None
    """None when no run produced a pass or a fail."""
    top_failure_message: str | None
    problem: str | None
    """Why the test did not run, when at least one run could not execute it."""

    @property
    def failures(self) -> int:
        return sum(n for outcome, n in self.counts.items() if outcome in FAILING)

    @property
    def passes(self) -> int:
        return sum(n for outcome, n in self.counts.items() if outcome in PASSING)

    @property
    def excluded(self) -> int:
        return sum(self.counts.values()) - self.failures - self.passes


def normalize_target(target: str) -> str:
    """Use forward slashes in the file part, as pytest does on every platform."""
    path, separator, rest = target.partition("::")
    return path.replace("\\", "/") + separator + rest


def run_baseline(
    config: BaselineConfig,
    store: Store,
    on_result: Callable[[RunResult], None] | None = None,
) -> BaselineSummary:
    # One seeded generator produces every run's hash seed, so the whole session
    # can be replayed from the session seed alone.
    rng = random.Random(config.seed)
    session_id = store.create_session(
        repo=config.repo,
        target=config.target,
        seed=config.seed,
        config={
            "runs": config.runs,
            "jobs": config.jobs,
            "timeout_s": config.timeout_s,
            "suite": list(config.suite),
        },
        commit_sha=_commit_sha(config.repo),
    )
    experiment_id = store.create_experiment(session_id, "baseline", {"suite": list(config.suite)})
    log_dir = store.log_dir(session_id)
    requests = [
        RunRequest(
            repo=config.repo,
            target=config.target,
            pytest_args=config.suite or (config.target,),
            log_path=log_dir / f"run-{index:04d}.log",
            hash_seed=rng.randrange(1, 2**32),
            timeout_s=config.timeout_s,
        )
        for index in range(1, config.runs + 1)
    ]

    results: list[RunResult] = []
    status = "aborted"
    try:
        with ThreadPoolExecutor(max_workers=config.jobs) as pool:
            futures = [pool.submit(_timed_run, request) for request in requests]
            try:
                for future in as_completed(futures):
                    started_at, result = future.result()
                    # Only this thread touches the database.
                    store.record_run(experiment_id, "baseline", result, started_at)
                    results.append(result)
                    if on_result is not None:
                        on_result(result)
            except BaseException:
                # Ctrl-C or an internal error: do not start the runs still queued.
                pool.shutdown(wait=False, cancel_futures=True)
                raise
        status = "finished"
    finally:
        store.finish_experiment(experiment_id, status)
        store.finish_session(session_id, status)

    counts = store.outcome_counts(experiment_id)
    failures = sum(n for outcome, n in counts.items() if outcome in FAILING)
    passes = sum(n for outcome, n in counts.items() if outcome in PASSING)
    messages = Counter(r.message for r in results if r.outcome in FAILING and r.message)
    problems = [r.message for r in results if r.outcome == "not_run" and r.message]
    return BaselineSummary(
        session_id=session_id,
        experiment_id=experiment_id,
        counts=counts,
        rate=failure_rate(failures, failures + passes) if failures + passes else None,
        top_failure_message=messages.most_common(1)[0][0] if messages else None,
        problem=problems[0] if problems else None,
    )


def _timed_run(request: RunRequest) -> tuple[str, RunResult]:
    started_at = timestamp()
    return started_at, run_once(request)


def _commit_sha(repo: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout.strip() or None if completed.returncode == 0 else None
