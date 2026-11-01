# P04 — known spend and unsettled exposure

This research package is a one-account SQLite ledger for distinguishing known costs from money that may still be owed after uncertain execution. It retains a reservation after a lost response or unconfirmed cancellation. A final invoice or a fenced pre-dispatch non-dispatch proof can release the remainder.

It is not a superior budget optimizer, a payment system, or a provider billing integration. The historical SWE-bench observations and admission-policy experiment are not included or rerun.

## Contract

- Money is expressed as nonnegative integer micro-USD, within SQLite's signed 64-bit bound. Invalid types, negative amounts and inconsistent account configuration are rejected.
- `Evidence` carries a semantic kind, source role, reference and attempt ID. These are trusted adapter assertions, not cryptographic authentication or proof that a provider invoice is real.
- A cost observation is a cumulative lower bound, not a final invoice. A successful execution outcome does not establish billing finality.
- An unbounded outstanding liability blocks new admissions. A caller's authorized maximum is not automatically an enforced provider cost ceiling; a distinct ceiling-evidence field is required.
- SQLite transactions serialize cooperative writers using the same local file. Conflicting evidence can freeze the account. There is no automatic unfreeze or refund mechanism.
- Schema 1 is rejected without automatically migrating business data. The tests preserve its sentinel values and explicitly close both inspection connections.

`src/exposure_ledger.py` exposes the ledger and typed evidence/errors. `tests/test_exposure_ledger.py` contains all 23 selected ledger methods, including concurrent writers, lost responses, invoice replay, process termination, conflicting evidence and schema rejection. No pickle input, external provider, paid call, network service or historical dataset is used.

## Reproduce

No pip installation is needed: this package uses only Python's standard library. Use a direct base CPython 3.11 or 3.12 executable; the recorded run used CPython 3.11.9 on Windows. On Windows, use the actual base executable rather than a virtual-environment launcher so process termination targets the worker directly. Do not use `-O`.

From this project directory:

```powershell
$python = 'C:\Path\To\Python311\python.exe'
& $python -S -B run_tests.py
```

Or on Linux/macOS:

```sh
python3.11 -S -B run_tests.py
```

The launcher and every Python child use `-S`, with only this package's source directory explicitly added. It does not import user/global site packages. Temporary databases and process markers use fresh temporary directories; raw execution reports are written under ignored `.local/runs/<timestamp>/`. An optional `--summary path/to/summary.json` writes a sanitized summary to the selected destination. The runner requires exactly 23 test methods, zero failures/errors/skips, and a successful process exit.

## Evidence and limits

`evidence/verification_20261101.json` preserves the initial public candidate's fresh 23-method run, including its exact source hashes. A subsequent technical review found two cleanup gaps in its concurrency test helper: a later process launch could fail before entering the cleanup block, and already-exited children were not always collected. Only that helper was corrected. `evidence/cleanup_delta_20261101.json` records all five affected concurrency methods passing on the corrected source; it does not relabel the earlier 23-method run as a full run of the final test file.

The separate AI-assisted review's [before](evidence/reviewer_cleanup_before.json) and [after](evidence/reviewer_cleanup_after.json) receipts preserve two fault-injection failures followed by two passes. Those probes used simulated children and exercised cleanup ownership only: no real process or ledger operation was performed by the probes. The five author regressions did use real child processes. These complementary checks are not institutional or independent attestation.

The historical campaign additionally had 22 passing methods and one old-schema fixture-cleanup error; only its affected method was rerun at that time. Neither the public-copy runs nor the new helper correction rewrites that history.

Actual local child-process termination and concurrent access are exercised. Power loss, network filesystems, multi-host operation, real enforced provider ceilings, authentic bills and end-to-end exactly-once external effects remain untested. The execution records preserve their author-stage state; separate internal AI technical and strategic reviews examine the final publication copy and cleanup correction. They are not independent external attestation.

`SOURCES.json` records exact historical source hashes and the small test-driver changes. The production ledger is copied unchanged. The corrected test already closes its old-schema connections; the public copy additionally uses `-S` for child interpreters, reports Windows execution according to the actual measured platform, and owns child cleanup from the first successful launch through collection of every child.

The original code and documentation are MIT, copyright 2026 Mohammed Messaoudene, prepared with AI assistance. No third-party code or dataset is vendored. Python is a separately installed runtime; `requirements.txt` intentionally contains no third-party requirements.
