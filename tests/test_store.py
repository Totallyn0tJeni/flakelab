from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from flakelab.runner.process import Outcome, RunResult
from flakelab.store.db import Store, timestamp


def result(outcome: Outcome, order: tuple[str, ...] = ("a::t1", "a::t2")) -> RunResult:
    return RunResult(
        outcome=outcome,
        duration_ms=12,
        exit_code=0 if outcome == "passed" else 1,
        order=order,
        message=None if outcome == "passed" else "assert False",
        log_path=Path("logs/run.log"),
        hash_seed=42,
    )


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "data")


def new_experiment(store: Store) -> int:
    session_id = store.create_session(
        repo=Path("/repo"), target="a::t2", seed=7, config={"runs": 3}, commit_sha=None
    )
    return store.create_experiment(session_id, "baseline", {"suite": []})


def test_session_round_trip(store: Store) -> None:
    session_id = store.create_session(
        repo=Path("/repo"), target="a::t2", seed=7, config={"runs": 3}, commit_sha="abc123"
    )
    row = store.session(session_id)
    assert (row["target_test"], row["seed"], row["commit_sha"]) == ("a::t2", 7, "abc123")
    assert row["status"] == "running" and row["finished_at"] is None

    store.finish_session(session_id)
    row = store.session(session_id)
    assert row["status"] == "finished" and row["finished_at"] is not None


def test_runs_and_counts(store: Store) -> None:
    experiment_id = new_experiment(store)
    for outcome in ("passed", "failed", "passed"):
        store.record_run(experiment_id, "baseline", result(outcome), timestamp())

    assert store.outcome_counts(experiment_id) == {"passed": 2, "failed": 1}
    rows = store.runs(experiment_id)
    assert [row["outcome"] for row in rows] == ["passed", "failed", "passed"]
    assert rows[1]["message"] == "assert False"
    assert rows[0]["hash_seed"] == 42


def test_identical_orders_are_stored_once(store: Store) -> None:
    experiment_id = new_experiment(store)
    store.record_run(experiment_id, "baseline", result("passed"), timestamp())
    store.record_run(experiment_id, "baseline", result("passed"), timestamp())
    store.record_run(experiment_id, "baseline", result("passed", order=("a::t2",)), timestamp())

    hashes = [row["order_hash"] for row in store.runs(experiment_id)]
    assert hashes[0] == hashes[1] != hashes[2]
    assert store.order(hashes[0]) == ["a::t1", "a::t2"]
    assert store.order(hashes[2]) == ["a::t2"]


def test_data_survives_reopening(tmp_path: Path) -> None:
    first = Store(tmp_path / "data")
    experiment_id = new_experiment(first)
    first.record_run(experiment_id, "baseline", result("failed"), timestamp())
    first.close()

    second = Store(tmp_path / "data")
    assert second.outcome_counts(experiment_id) == {"failed": 1}


def test_data_dir_ignores_itself_in_git(store: Store) -> None:
    assert (store.data_dir / ".gitignore").read_text(encoding="utf-8") == "*\n"


def test_refuses_a_database_from_another_schema_version(tmp_path: Path) -> None:
    Store(tmp_path / "data").close()
    db = sqlite3.connect(tmp_path / "data" / "flakelab.db")
    db.execute("PRAGMA user_version = 99")
    db.close()
    with pytest.raises(RuntimeError, match="schema 99"):
        Store(tmp_path / "data")


def test_runs_must_belong_to_an_experiment(store: Store) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        store.record_run(9999, "baseline", result("passed"), timestamp())
