# Flakelab

Flakelab diagnoses **why** a pytest test is flaky. It reruns a suspect test
under controlled conditions (test order, clock, random seeds, CPU load,
network), works out which condition changes the outcome, and prints the
shortest command that reproduces the failure.

> **Status: early development.** Flakelab can currently measure how often a
> test fails. Working out the cause comes next. See the roadmap below.

## Usage

```bash
flakelab diagnose zoo/network/test_nw_fetch_status.py::test_status_endpoint_replies_ok --runs 40
```

Real output from this repository's own zoo test, which calls a service that
drops a quarter of its connections:

```text
flakelab baseline: zoo/network/test_nw_fetch_status.py::test_status_endpoint_replies_ok
40 runs, on its own, seed 1528171295
40 runs: 7 failed, 33 passed
Failure rate 17.5% (95% interval: 8.7% to 31.9%)

Flaky: failed 7 of 40 runs.
Most common failure: AssertionError: assert b'' == b'ok'
```

Each run is a fresh Python process, so nothing leaks between runs. Useful
options:

| Option | Meaning |
| --- | --- |
| `--runs N` | How many times to run the test (default 30) |
| `--suite PATH` | Run the test inside a larger set of tests instead of alone; repeatable |
| `--jobs N` | Runs to execute at once (default 1; more is faster but adds load) |
| `--timeout S` | Kill a run after this many seconds (default 300) |
| `--seed N` | Replay the per-run hash seeds of an earlier session |

Results and logs are stored in `.flakelab/` inside your project, which ignores
itself in git.

## Why

Existing tools tell you *that* a test is flaky, usually by spotting a pass
after a retry. Working out the cause is still done by hand. Flakelab automates
that step with controlled experiments and statistics.

## The flaky zoo

`zoo/` holds small, deliberately flaky tests, one per root cause, each with a
known answer recorded in `zoo/manifest.json`. They are how we know whether
Flakelab's verdicts are right. See [zoo/README.md](zoo/README.md).

## Development

Requires Python 3.10 or newer.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run the checks:

```bash
python -m pytest        # tests, including verification of the zoo
ruff check .            # lint
ruff format --check .   # formatting
mypy                    # type checking
```

A plain `pytest` never collects `zoo/` directly, because those tests fail on
purpose. `tests/test_zoo_is_flaky.py` runs them in separate processes instead.

## Roadmap

| Phase | Outcome | Status |
| --- | --- | --- |
| 0 | Foundation, CI and the flaky zoo | Done |
| 1 | Runner and baseline failure rate | Done |
| 2 | Perturbation experiments and verdicts | Next |
| 3 | Polluter search with delta debugging | Planned |
| 4 | Report viewer | Planned |
| 5 | Evaluation on real projects, GitHub Action | Planned |
| 6 | Release | Planned |

## License

MIT
