# Memory snapshots across DBOS recovery

A 169-line illustrative regression test for [Pydantic AI issue #11191](https://github.com/pydantic/pydantic-ai/issues/11191). It adds one test file and changes no production code. It is prepared for maintainer discussion; no upstream acceptance or assignment is claimed.

The test uses a real SQLite DBOS journal and a deterministic `FunctionModel`. It interrupts a workflow after its first recorded model response, changes the memory store from A to B, and resumes the same workflow ID. Three subsequent `SlidingWindowCompaction` calls remove the snapshot. Each later model request must receive exactly the original A snapshot, with one runtime store read after the counter reset. A separate setup read obtains the original version before `reads.clear()`; the passing run makes two store reads in total.

The public DBOS journal API additionally verifies that the returned initial prefix remains unchanged, the one recorded `memory.load_snapshot` result contains the original `MemoryFile`, and the workflow finishes with `SUCCESS`. The interruption remains a `BaseException` in the same process: no OS process kill, fresh worker PID, host failure or cross-machine recovery is tested.

## Candidate and prior work

- Upstream base: [`d44704ec72744e4fc0bd5a3d5dd877462a24da5b`](https://github.com/pydantic/pydantic-ai/commit/d44704ec72744e4fc0bd5a3d5dd877462a24da5b).
- Candidate: `test_dbos_recovery.py`, also supplied as `P01_DBOS_MEMORY_MINIMAL.patch` for `tests/harness/memory/test_dbos_recovery.py`.
- Candidate SHA256: `30d4f25cf6ccb617499b2a848a2ad1bc87be4d051612ce6d194d6351b4dc4ac1`.
- Local candidate commit: `0434aa7514f766e5c739f7f3ce00377a164645a9`; this is not an upstream submission.
- [PR #10903](https://github.com/pydantic/pydantic-ai/pull/10903) already added the Temporal memory replay case. Existing Memory tests cover dispatch through a recording fake, and DBOS `DetectLoops` tests provide the in-process interruption pattern.

This revision responds to a separate AI-assisted review of the original 153-line candidate. Only the optional `dbos` import is guarded; an integration import defect propagates. A ten-second `anyio.fail_after` bounds the cooperative resume/result awaits, not initial workflow execution or the whole process. After successful construction, fixture cleanup covers launch failure and logging detachment is attempted even when DBOS destruction raises. Partial-constructor cleanup is not established. No private DBOS API is added.

`SOURCES.json` records the current and previous candidate hashes. The original file and patch are retained under `history/`; their results remain under `evidence/`. Current results are under `evidence/hardening/`.

## Install into an isolated checkout

Requirements: Git, Python 3.11 or newer, and `uv`. The current recorded run used Python 3.11.9 on Windows. These commands access the network only when you explicitly run them; the package contains no installer or automatic network action.

```text
git clone https://github.com/pydantic/pydantic-ai.git pydantic-ai-p01
cd pydantic-ai-p01
git checkout --detach d44704ec72744e4fc0bd5a3d5dd877462a24da5b
git rev-parse HEAD
uv sync --frozen --package pydantic-ai-harness --extra dbos --extra anthropic --extra logfire --group dev --group lint
```

The selected extras include the OpenTelemetry SDK needed during test collection. A predecessor CI installation without the `logfire` extra failed before collecting tests because `opentelemetry.sdk` was absent. That installation limitation remains in the earlier receipt. The revised frozen installation subsequently passed the two exact selected tests with zero skips/errors in [hosted Ubuntu CI at fa7e467](https://github.com/mohammedmessaoudene-cmd/agent-evidence-lab/actions/runs/41327039712). This result applies to that public commit and the unchanged candidate hash. No unlocked dependency version is introduced. The pinned upstream lock includes DBOS 2.29.0.

The recorded local execution reused an existing dependency environment with isolated DBOS and OpenTelemetry packages. `requirements-observed.txt` lists selected observed versions, not a complete independent lockfile. Editable Pydantic distribution labels remained older release labels; actual imports came from the pinned source checkout.

Substitute this package's location for `PATH_TO_P01`:

```text
git apply --check PATH_TO_P01/P01_DBOS_MEMORY_MINIMAL.patch
git apply PATH_TO_P01/P01_DBOS_MEMORY_MINIMAL.patch
```

Set `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `PYTEST_ADDOPTS=` and `PYTEST_PLUGINS=` in the shell, then run:

```text
uv run --no-sync python -m pytest -p no:cacheprovider -p anyio.pytest_plugin -p cassetter.pytest_plugin -p inline_snapshot.pytest_plugin -p pytest_mock -p xdist.plugin tests/harness/memory/test_dbos_recovery.py tests/harness/memory/test_memory.py::test_snapshot_load_dispatches_as_durable_operation --junitxml=p01-baseline.xml
```

Expected result: exactly two passed tests and no skips or errors. No model API key or provider call is needed. A skipped DBOS test is not a successful reproduction.

The optional failure-path probe exercises the exact candidate AST using simulated imports, DBOS lifecycle calls and a stalled handle. It checks three import paths, three fixture cleanup paths and cancellation. The ten-second deadline is injected as zero for this probe, so it does not wait ten seconds or start a real workflow:

```text
uv run --no-sync python PATH_TO_P01/review/check_failure_paths.py --candidate tests/harness/memory/test_dbos_recovery.py --previous PATH_TO_P01/history/test_dbos_recovery_153.py.txt --conftest tests/conftest.py --out p01-failure-paths.json
```

## Current observations

| Check on the 169-line source | Result |
|---|---|
| Windows, Python 3.11.9, DBOS 2.29.0 | Native case and existing recording-dispatch case: 2 passed, no failures/errors/skips |
| Same environment with capability journaling bypassed | Native case fails on B replacing A; selected dispatch fake passes |
| Failure-path probes | Original source: 3/7 expectations; corrected source: 7/7 |
| Candidate Pyright 1.1.414 | 0 errors, 0 warnings |
| Candidate Ruff 0.17.1 | Check and format pass |
| Repository Ruff | 2254 files formatted; 3 pre-existing import-order errors in unchanged files |
| Hosted Ubuntu, frozen DBOS 2.29 profile at fa7e467 | Native and selected dispatch cases: 2 passed, zero skips/errors; separate hosted receipt |
| Additional received Linux/Python 3.12.14/DBOS 3.4 report, unchanged 169 lines | Baseline 2 passed; controlled native mutant fails on B, dispatch case passes; strict typing retains one DBOSConfig error |
| Additional received Linux/Python 3.12.14/frozen DBOS 2.29 profile | Bootstrap and Ruff/format/Pyright pass; static-only qualification, no extra native run |
| macOS or fresh-process recovery | Not executed by these receipts |

The final comparison used the same base interpreter with `-S`, explicit import paths, environment and 37 registered pytest modules in both arms. The deliberate mutant changes only capability dispatch to call the handler directly instead of its DBOS step. `evidence/mutation.patch` preserves that mutation; the backend was restored exactly afterwards. The final tested bytes were subsequently committed without modification. See `evidence/hardening/summary.json` and its JUnit/log files.

The earlier Linux/Python 3.12.14/DBOS 3.4 report concerned the 153-line candidate and remains attached to that history. A later, separately received report verifies the exact current 169-line hash on Linux/DBOS 3.4; it does not relabel the older run. Its structured native extracts show five A snapshots and one runtime read in the control, then A followed by four B snapshots and two runtime reads in the mutant. Both workflow rows finish SUCCESS, so workflow status alone is insufficient. DBOS 3.4 retains one Pyright error because `run_admin_server` is absent from `DBOSConfig`; runtime success is not a strict-typing pass. The frozen upstream DBOS 2.29 profile remains the supported quality target.

`evidence/final_cloud_review.json` separates those profiles and the additional seven fault-path checks, eight rejected journal corruptions, three positive controls and three demonstrated limits. These use extracted source bodies and synthetic collaborators, not 21 native executions. The initial Memory/model entries were observed in the reported native run, but the source does not assert that `initial_steps` is nonempty: an artificial empty prefix is accepted. Raw cloud trace/JUnit/database files and the observer plugin were not delivered; their reported hashes accompany structured extracts in the retained private packet.

The cloud review corrected its own JUnit helper after a wrong-classname falsifier. This repository's existing gate already requires two exact class/name identities and consistent zero-skip/error/failure counters. It rejects that falsifier and accepts the archived hosted-CI report; no native workflow was rerun for these read-only XML checks.

The scope/id metadata are not compared by the snapshot oracle. The mutant proves a difference from the selected recording-dispatch fake; it does not prove superiority over every native DBOS test or isolate the added value of compaction. Prefect, a new production defect, cross-process recovery and adoption remain outside the evidence.

## Preserved history and license

The original `evidence/summary.json`, `controlled_comparison.json`, baseline/mutant logs and initial teardown error remain unchanged. They refer to the 153-line source. The earliest mutation comparison had different automatically loaded plugins; its later controlled addendum addressed that difference. The initial missing-SDK teardown failure and intermediate typecheck failures are not erased by later passing results. The hardening record also retains the relevant intermediate qualification limits.

Logs and JUnit are redacted publication copies; `evidence/hardening/redactions.json` records their original and published hashes. These are AI-assisted engineering records, not institutional attestation or production certification.

A [single scope proposal](https://github.com/pydantic/pydantic-ai/issues/11191#issuecomment-6560812372) has already been posted and read back. The next external evidence is a maintainer response; this received review does not call for a duplicate comment. The [contributing guide at the pinned commit](https://github.com/pydantic/pydantic-ai/blob/d44704ec72744e4fc0bd5a3d5dd877462a24da5b/docs/contributing.md) asks for approach agreement and assignment before a non-trivial PR.

The candidate derives from Pydantic AI test patterns under MIT; the upstream notice remains in `LICENSE`. Preparation, implementation and review used AI assistance. No upstream adoption, full-suite coverage gain or production reliability is claimed.
