# P03: verifier aggregation reproduction

Run with Python 3.11+ and the standard library:

```sh
python -S -B reproduce.py --out results/fresh.json
```

The output must be absent. Exact Apache-2.0 upstream source and a public benchmark task are pinned under `vendor/`. The script verifies their Git blob identities and SHA256 before executing only `_run_verifiers` extracted by AST. Configuration/transport objects are replaced; the task SQL is unchanged and runs in a constructed SQLite database. No network, LLM, MCP handshake or complete gym is run.

Eight constructed combinations/orderings retain two false successes in the pinned main method; the actual PR24 method and the stable-index illustration retain zero. This is known issue23/PR24, not a new discovery or field failure rate. PR24 is the strong comparator and is credited. A correct aggregator does not establish that the SQL expresses an independently approved business policy. No advantage over PR24 or production validity is claimed.

Vendor source/task: Apache-2.0, see `vendor/LICENSE_APACHE_2_0`, `NOTICE` and `UPSTREAM.json`. Original local driver: MIT, see the local `LICENSE`, with modifications recorded in SOURCES.json. Expected baseline counterexamples are retained; do not call them a safe production engine.

## Targeted post-publication correction

The published eight-case result is retained: main 2 false successes, PR24 0,
and the stable-index illustration 0. These counts are a synthetic fixture,
not an agent score, a field rate, or an advantage over PR24.

The local driver now hashes the raw vendor bytes before UTF-8 decoding, so a
CRLF-only conversion is rejected if it differs from the pinned Git blob.
A case with no obligations, incomplete execution, or a non-boolean `passed`
value raises `ValueError` instead of treating an executed-only or empty
conjunction as success. This is a refusal at the reproducer boundary; it does
not change the upstream methods, implement a general verifier engine, or
establish the business authority of a SQL query. Retained-result cardinality
is deliberately allowed to differ in the main branch so its known key-loss
counterexample remains observable.

SQLite closes in `finally`, including execution or diagnostic errors.
Fixture and summary checks use explicit conditions rather than assertions.
The historical `evidence/verification_20261101.json` refers to the original
published driver hash; it is not evidence of execution of this corrected
version. New review evidence is under `evidence/hardening/`. The review counterexamples
are synthetic and do not constitute a new independent benchmark population.

## Reproduce the targeted checks

From this directory, using a base Python 3.11+ installation (no packages needed):

```sh
python -S -B review/check_boundaries.py --out results/boundaries.json
```

The output must be absent. The probe verifies the exact reviewed driver hash.
It makes three temporary vendor copies for identity checks and stops each CLI
preflight before method extraction or database construction. It then exercises
eight new synthetic `run_case` boundary states across the three methods (24
observations), including a positive control, a genuinely false prerequisite
that was skipped, malformed `UNKNOWN` values, and a real SQLite error. It
checks eight artificial summary shapes under compilation modes 0 and 1 (16
observations). This last check extracts only the summary block: it is not an
optimized full-CLI execution. Probe-owned cleanup is excluded from the
connection state measured immediately after `run_case` returns or raises.

`boundaries_before.json` preserves the original published behavior; its PASS
means the adverse observations matched expectations, including unsafe success
and an open retained connection after a SQL exception. `boundaries_after.json`
records the corrected behavior. Both ran on Windows with Python 3.11.9 and
`-S -B`, using the same probe bytes. `cli_execution.json` and
`cli_eight_cases.json` separately record one actual corrected CLI run of the
eight original fixture combinations: main 2, stable-index 0, PR24 0 false
successes. No Linux execution or full CLI under `-O` is claimed by these new
artifacts. All original vendor files and the old verification receipt remain
unchanged.

Coverage validation counts observed queries in this fixed fixture; it does not
prove arbitrary obligation identity or execution multiplicity. Non-boolean
verdicts are injected boundary cases: the unmodified SQLite adapter returns
booleans. Cleanup is tested after successful fixture construction, not for an
exception inside its constructor. There is no new advantage over PR24.
