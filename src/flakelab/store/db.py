"""SQLite persistence for sessions, experiments and runs.

All data lives in ``<repo>/.flakelab/``: one database file plus a folder of
run logs. SQLite is used because the tool runs on a single machine, the data
is relational, and one file is easy to attach to a CI run.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any

from flakelab.runner.process import RunResult

SCHEMA_VERSION = 1
DATA_DIR_NAME = ".flakelab"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        # Keeps Flakelab's files out of the user's commits without asking them
        # to edit their own .gitignore.
        ignore = data_dir / ".gitignore"
        if not ignore.exists():
            ignore.write_text("*\n", encoding="utf-8")

        self._db = sqlite3.connect(data_dir / "flakelab.db")
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    @classmethod
    def for_repo(cls, repo: Path) -> Store:
        return cls(repo / DATA_DIR_NAME)

    def close(self) -> None:
        self._db.close()

    def _migrate(self) -> None:
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            schema = resources.files("flakelab.store").joinpath("schema.sql").read_text("utf-8")
            self._db.executescript(schema)
            self._db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._db.commit()
        elif version != SCHEMA_VERSION:
            raise RuntimeError(
                f"{self.data_dir} was written by a different Flakelab version "
                f"(schema {version}, expected {SCHEMA_VERSION})"
            )

    # -- sessions ---------------------------------------------------------

    def create_session(
        self,
        *,
        repo: Path,
        target: str,
        seed: int,
        config: dict[str, Any],
        commit_sha: str | None,
    ) -> int:
        cursor = self._db.execute(
            "INSERT INTO sessions (repo_path, commit_sha, target_test, seed, config_json,"
            " status, started_at) VALUES (?, ?, ?, ?, ?, 'running', ?)",
            (str(repo), commit_sha, target, seed, json.dumps(config), _now()),
        )
        self._db.commit()
        return _row_id(cursor)

    def finish_session(self, session_id: int, status: str = "finished") -> None:
        self._db.execute(
            "UPDATE sessions SET status = ?, finished_at = ? WHERE id = ?",
            (status, _now(), session_id),
        )
        self._db.commit()

    def session(self, session_id: int) -> sqlite3.Row:
        row = self._db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise KeyError(f"no session {session_id}")
        return row  # type: ignore[no-any-return]

    def log_dir(self, session_id: int) -> Path:
        return self.data_dir / "logs" / f"session-{session_id:04d}"

    # -- experiments ------------------------------------------------------

    def create_experiment(self, session_id: int, kind: str, params: dict[str, Any]) -> int:
        cursor = self._db.execute(
            "INSERT INTO experiments (session_id, kind, params_json, status)"
            " VALUES (?, ?, ?, 'running')",
            (session_id, kind, json.dumps(params)),
        )
        self._db.commit()
        return _row_id(cursor)

    def finish_experiment(self, experiment_id: int, status: str = "finished") -> None:
        self._db.execute("UPDATE experiments SET status = ? WHERE id = ?", (status, experiment_id))
        self._db.commit()

    # -- runs -------------------------------------------------------------

    def record_run(self, experiment_id: int, arm: str, result: RunResult, started_at: str) -> int:
        order_json = json.dumps(list(result.order))
        order_hash = hashlib.sha256(order_json.encode()).hexdigest()[:16]
        self._db.execute(
            "INSERT OR IGNORE INTO orders (hash, test_ids_json) VALUES (?, ?)",
            (order_hash, order_json),
        )
        cursor = self._db.execute(
            "INSERT INTO runs (experiment_id, arm, hash_seed, order_hash, outcome, message,"
            " duration_ms, exit_code, log_path, started_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                experiment_id,
                arm,
                result.hash_seed,
                order_hash,
                result.outcome,
                result.message,
                result.duration_ms,
                result.exit_code,
                str(result.log_path),
                started_at,
            ),
        )
        self._db.commit()
        return _row_id(cursor)

    def runs(self, experiment_id: int) -> list[sqlite3.Row]:
        return self._db.execute(
            "SELECT * FROM runs WHERE experiment_id = ? ORDER BY id", (experiment_id,)
        ).fetchall()

    def outcome_counts(self, experiment_id: int) -> Counter[str]:
        rows = self._db.execute(
            "SELECT outcome, COUNT(*) AS n FROM runs WHERE experiment_id = ? GROUP BY outcome",
            (experiment_id,),
        ).fetchall()
        return Counter({row["outcome"]: row["n"] for row in rows})

    def order(self, order_hash: str) -> list[str]:
        row = self._db.execute(
            "SELECT test_ids_json FROM orders WHERE hash = ?", (order_hash,)
        ).fetchone()
        if row is None:
            raise KeyError(f"no order {order_hash}")
        return list(json.loads(row["test_ids_json"]))


def _row_id(cursor: sqlite3.Cursor) -> int:
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def timestamp() -> str:
    """The current time in the format the store uses."""
    return _now()
