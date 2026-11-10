-- Flakelab schema, version 1.
-- A session is one diagnosis of one test. It has experiments; an experiment
-- has runs. Timestamps are ISO 8601 strings in UTC.

CREATE TABLE sessions (
    id           INTEGER PRIMARY KEY,
    repo_path    TEXT NOT NULL,
    commit_sha   TEXT,
    target_test  TEXT NOT NULL,
    seed         INTEGER NOT NULL,
    config_json  TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('running', 'finished', 'aborted')),
    started_at   TEXT NOT NULL,
    finished_at  TEXT
);

CREATE TABLE experiments (
    id           INTEGER PRIMARY KEY,
    session_id   INTEGER NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    kind         TEXT NOT NULL,
    params_json  TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('running', 'finished', 'aborted'))
);

-- Each distinct test order is stored once and referenced by its hash, because
-- hundreds of runs usually share a handful of orders.
CREATE TABLE orders (
    hash           TEXT PRIMARY KEY,
    test_ids_json  TEXT NOT NULL
);

CREATE TABLE runs (
    id             INTEGER PRIMARY KEY,
    experiment_id  INTEGER NOT NULL REFERENCES experiments (id) ON DELETE CASCADE,
    arm            TEXT NOT NULL,
    hash_seed      INTEGER NOT NULL,
    order_hash     TEXT NOT NULL REFERENCES orders (hash),
    outcome        TEXT NOT NULL,
    message        TEXT,
    duration_ms    INTEGER NOT NULL,
    exit_code      INTEGER,
    log_path       TEXT NOT NULL,
    started_at     TEXT NOT NULL
);

CREATE INDEX runs_by_experiment ON runs (experiment_id);
CREATE INDEX experiments_by_session ON experiments (session_id);
