# Flakelab

Flakelab diagnoses **why** a pytest test is flaky. It reruns a suspect test
under controlled conditions (test order, clock, random seeds, CPU load,
network), works out which condition changes the outcome, and prints the
shortest command that reproduces the failure.

> **Status: early development.** The repository currently contains the project
> foundation and the "flaky zoo" used as ground truth. The diagnosis engine is
> not implemented yet. See the roadmap below.

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
| 1 | Runner and baseline failure rate | Next |
| 2 | Perturbation experiments and verdicts | Planned |
| 3 | Polluter search with delta debugging | Planned |
| 4 | Report viewer | Planned |
| 5 | Evaluation on real projects, GitHub Action | Planned |
| 6 | Release | Planned |

## License

MIT
