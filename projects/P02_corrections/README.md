# P02 — correction obligations and evidence limits

This research package tracks corrections to declared inputs, reopens affected decision obligations, and audits the receipts that claim to close them. It includes a SQLite engine, a deliberately restricted signed JSON profile, synthetic fixtures, a Node peer, and adversarial tests.

The central counterexample is preserved: an already registered consumer can close its declared obligation while another decision it owns stays stale. A supplied read trace can reveal that omission; the declared graph alone cannot establish real decision coverage. A valid signature also does not prove that a consumer recomputed its result or performed a business action.

## Contract

- `src/p02/engine.py` uses one local SQLite store and a fixed declared graph/participant epoch. A later correction invalidates an old receipt frontier. It does not discover undeclared applications or dependencies.
- `src/p02/audit.py` reads the store and reports separate signature, local replay, declared semantic consistency, and coverage states. Missing semantic expectations and coherent false declarations remain unresolved.
- `src/p02/wire.py` accepts ASCII JSON and safe integers, rejects ambiguous or unsupported values, and uses deterministic Ed25519 **test identities derived from public labels**. These keys are intentionally reproducible, not credentials. This is not a general JCS, COSE, SCITT, or production trust implementation.
- `src/node_peer.mjs` uses Node's standard library and assumes one writer per store. It synchronizes the file and renames it. On Windows, directory-sync `EPERM` produces `UNSUPPORTED_EPERM_WIN32` and `power_loss_durability: NOT_ESTABLISHED`; other I/O errors propagate.
- The `classic_sql` and `portable_graph` modes share engine, wire and evaluator code. Their agreement is not independent algorithmic validation or evidence of superiority.

No network, provider, LLM, enrolled organization, business side effect, dataset, or human-time measurement is part of these tests. OpenLineage SDK/schema integration is outside this minimal package. Its historical results are not claimed as results of this copy.

## Reproduce

Use a direct base CPython 3.11 or 3.12 executable. The recorded run used CPython 3.11.9 and Node 20.15.1 on Windows. Node must be available as `node` on `PATH`. The test launchers use `-S` and explicit source/dependency directories, avoiding global and user site packages. Do not run these assertion-based tests with `-O`.

From this project directory, replace the example interpreter path with your actual base interpreter:

```powershell
$python = 'C:\Path\To\Python311\python.exe'
& $python -I -m pip --isolated --disable-pip-version-check install --only-binary=:all: --no-compile --target .local/deps -r requirements.txt
& $python -S -B run_tests.py
```

On Linux/macOS, the equivalent commands are:

```sh
python3.11 -I -m pip --isolated --disable-pip-version-check install --only-binary=:all: --no-compile --target .local/deps -r requirements.txt
python3.11 -S -B run_tests.py
```

Installation is an explicit preparation step; the test runner never installs or downloads anything. It creates a new ignored `.local/runs/<timestamp>/` directory for every run. To write an additional sanitized summary, pass `--summary path/to/summary.json`. That option intentionally writes the selected destination.

The runner checks three expected cardinalities and returns nonzero for incomplete or failed suites:

| Suite | Cases | Purpose |
| --- | ---: | --- |
| Scope and semantics | 18 | Nine synthetic cases in each of two shared-engine modes |
| Receipt records | 12 | Six corruption/evidence-state probes in each mode |
| Recovery and interop | 8 | Six actual child-process exits/restarts and two Python/Node exchanges |

The historical scope specification and its byte hash are retained under `protocol/`. Its original local timestamp is not an independent timestamp or a new preregistration. This is a fresh execution of selected public copies, not a replay of the historical random-graph or NASA campaigns. The total of 38 checks is not 38 independent real-world experiments.

## Evidence and provenance

`evidence/verification_20261101.json` records the fresh author execution, source hashes, actual runtime versions, all case outcomes and selected negative observations. It contains no absolute personal paths or private conversation links. The detailed local artifacts are intentionally excluded from publication. This is the preserved author snapshot; separate internal AI technical and strategic reviews examine the publication copy. These reviews are not independent external attestation, maintainer acceptance or deployment validation.

`SOURCES.json` maps copied files to their historical origin hashes and records every public-copy modification. Core engine, wire, auditor, synthetic fixtures, worker and the corrected Node peer are exact copies. The scope driver only changes child interpreter isolation and explicit dependency-path propagation. The recovery/interop driver is a smaller new selection of the historical synthetic checks, with explicit durability-receipt assertions.

## Licenses

The original code and documentation are MIT, copyright 2026 Mohammed Messaoudene, prepared with AI assistance. The unpublished Apache-2.0 proposal in the private campaign is superseded for this original public subset by the author's authorized MIT choice. No third-party source or dataset is vendored here.

Installed dependencies retain their own licenses: [cryptography 50.0.2](https://pypi.org/project/cryptography/50.0.2/) is `Apache-2.0 OR BSD-3-Clause`, [cffi 2.1.1](https://pypi.org/project/cffi/2.1.1/) is `MIT-0`, and [pycparser 3.12](https://pypi.org/project/pycparser/3.12/) is `BSD-3-Clause`. `DEPENDENCIES.json` records these declarations, official project links and the exact Windows wheels used for the recorded run. Those wheel hashes identify that environment, not every supported platform. Python and Node are separately installed runtimes, not redistributed in this package.
