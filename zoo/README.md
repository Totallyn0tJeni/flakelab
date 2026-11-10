# The flaky zoo

Every test here is flaky on purpose, for exactly one known reason. The zoo is
Flakelab's ground truth: a diagnosis is correct when it matches
`manifest.json`.

| Case | Category | Behaviour |
| --- | --- | --- |
| `order-victim` | Order-dependent (victim) | Passes alone; fails after the polluter has run |
| `order-brittle` | Order-dependent (brittle) | Fails alone; passes after the state-setter has run |
| `time-same-second` | Time-dependent | Fails when the clock crosses a second boundary mid-test |
| `time-timezone` | Time-dependent | Passes only when the local time zone matches UTC |
| `random-sample-mean` | Randomness | Unseeded sampling against a tolerance that is too tight |
| `random-hash-order` | Randomness | Depends on set ordering, which changes with Python's hash seed |
| `concurrency-wait-race` | Timing and concurrency | A fixed sleep used instead of waiting for a thread |
| `network-fetch-status` | Network | Calls a local service that drops a quarter of connections |
| `stable-pass`, `stable-fail` | Not flaky | Controls that always pass or always fail |

## Rules for adding a case

1. One cause per test. A test with two causes cannot be ground truth.
2. No real internet access. Simulate external services locally.
3. Give test files and helper modules names that are unique across the zoo.
4. Add the case to `manifest.json` and a check to `tests/test_zoo_is_flaky.py`.
