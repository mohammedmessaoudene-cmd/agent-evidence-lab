# P03: verifier aggregation reproduction

Run with Python 3.11+ and the standard library:

```sh
python -B reproduce.py --out results/fresh.json
```

The output must be absent. Exact Apache-2.0 upstream source and a public benchmark task are pinned under `vendor/`. The script verifies their Git blob identities and SHA256 before executing only `_run_verifiers` extracted by AST. Configuration/transport objects are replaced; the task SQL is unchanged and runs in a constructed SQLite database. No network, LLM, MCP handshake or complete gym is run.

Eight constructed combinations/orderings retain two false successes in the pinned main method; the actual PR24 method and the stable-index illustration retain zero. This is known issue23/PR24, not a new discovery or field failure rate. PR24 is the strong comparator and is credited. A correct aggregator does not establish that the SQL expresses an independently approved business policy. No advantage over PR24 or production validity is claimed.

Vendor source/task: Apache-2.0, see `vendor/LICENSE_APACHE_2_0`, `NOTICE` and `UPSTREAM.json`. Original local driver: repository MIT, with modifications recorded in SOURCES.json. Expected baseline counterexamples are retained; do not call them a safe production engine.
