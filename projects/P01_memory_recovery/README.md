# Memory snapshots across DBOS recovery

A 153-line illustrative regression test for [Pydantic AI issue #11191](https://github.com/pydantic/pydantic-ai/issues/11191). It adds one test file and changes no production code. It is prepared for maintainer discussion; no upstream acceptance or assignment is claimed.

The test uses the real SQLite DBOS journal and a deterministic `FunctionModel`. It interrupts a workflow after its first recorded model response, changes the memory store from A to B, and resumes the same workflow ID. Three subsequent `SlidingWindowCompaction` calls remove the snapshot. Each later model request must receive exactly the original A snapshot, with no fresh store read.

The interruption is a `BaseException` in the same process. This covers journal replay after an interrupted workflow, not an OS process kill, a new worker PID, host failure, or cross-machine recovery.

## Candidate and prior work

- Upstream base: [`d44704ec72744e4fc0bd5a3d5dd877462a24da5b`](https://github.com/pydantic/pydantic-ai/commit/d44704ec72744e4fc0bd5a3d5dd877462a24da5b).
- Candidate: `test_dbos_recovery.py`, also supplied as `P01_DBOS_MEMORY_MINIMAL.patch` for `tests/harness/memory/test_dbos_recovery.py`.
- Candidate file SHA256: `23000a86179287de8ce2d292e9d19b9ac33a72fa5f75598328bc5f009a456075`.
- [PR #10903](https://github.com/pydantic/pydantic-ai/pull/10903) already added the Temporal memory replay case. The existing Memory test checks dispatch through a recording fake. The existing DBOS `DetectLoops` test provides the in-process recovery pattern used here.

`SOURCES.json` records exact source commits and content hashes. This is a test-coverage proposal, not a newly discovered production bug. It covers only the DBOS Memory item; Prefect and the other items in #11191 remain outside its scope.

## Install into an isolated checkout

Requirements: Git, Python 3.11 or newer, and `uv`. The recorded run used Python 3.11.9 on Windows. Use an existing compatible Pydantic AI development environment, or create a separate checkout with the explicit commands below. Cloning and installation access the network when you run them. This package includes no installer or automatic network action.

```text
git clone https://github.com/pydantic/pydantic-ai.git pydantic-ai-p01
cd pydantic-ai-p01
git checkout --detach d44704ec72744e4fc0bd5a3d5dd877462a24da5b
git rev-parse HEAD
uv sync --locked --all-packages --all-extras --no-extra mcp-tasks --group lint --reinstall-package griffelib
```

The `uv sync` command follows the upstream development setup and can install a large set of optional dependencies. It uses the `uv.lock` at the pinned commit, including DBOS 2.29.0. No global Git or Python configuration change is needed. A fresh installation of that complete lock was not executed for the supplied evidence: the observed run reused an existing dependency environment and added isolated DBOS and OpenTelemetry packages. `requirements-observed.txt` records relevant observed versions; it is not a complete independent lockfile.

From the new checkout, substitute the location of this package for `PATH_TO_P01`:

```text
git apply --check PATH_TO_P01/P01_DBOS_MEMORY_MINIMAL.patch
git apply PATH_TO_P01/P01_DBOS_MEMORY_MINIMAL.patch
uv run --no-sync python -m pytest -p no:cacheprovider tests/harness/memory/test_dbos_recovery.py tests/harness/memory/test_memory.py::test_snapshot_load_dispatches_as_durable_operation --junitxml=p01-baseline.xml
```

Expected result: two passed tests and zero skipped tests. A skipped DBOS test is not a successful reproduction. The test itself uses SQLite and `FunctionModel`; it needs no model API key or provider call.

## What was observed

| Check | Recorded result |
|---|---|
| Windows, Python 3.11.9, DBOS 2.29.0, controlled plugin configuration | New test plus existing recording-dispatch test: 2 passed, 0 failures, 0 errors, 0 skips |
| Same environment with deliberately broken DBOS capability dispatch | New test fails because B replaces A; existing recording-dispatch test passes |
| Pyright 1.1.414, candidate file | 0 errors, 0 warnings |
| Ruff 0.17.1, candidate file | Check and format passed |
| Repository-wide Ruff format | 2254 files already formatted |
| Repository-wide Ruff check | 3 pre-existing import-order errors in unchanged files; retained in evidence |
| Linux, macOS, full upstream suite, hosted CI | Not run |

The counter-test changes only the DBOS capability dispatcher from calling its durable step to calling its handler directly. It retains the Memory declaration and the model steps. `evidence/mutation.patch` contains that intentionally broken change. The production file was restored byte for byte afterwards. This distinguishes the new test from the selected Memory dispatch fake; it does not establish that the mutant escapes every other native DBOS test.

The first mutant child auto-loaded additional global pytest plugins (`zarr`, `jaxtyping`, `asyncio`, and `cov`), whereas its baseline used the isolated virtual environment. That initial comparison remains in `evidence/baseline.*` and `evidence/mutant.*` with its limitation preserved.

A subsequent targeted comparison resolved that difference. Both arms used the same base Python interpreter with `-S`, the same explicit import paths and environment, and `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`. Both loaded only the same five explicit third-party plugins: `anyio.pytest_plugin`, `cassetter.pytest_plugin`, `inline_snapshot.pytest_plugin`, `pytest_mock`, and `xdist.plugin`. The two tests passed on the unchanged backend; after the single intentional dispatch mutation, the new test failed on B versus A and the existing fake passed. No test was skipped or errored. The candidate remained byte-identical and the backend was restored exactly. See `evidence/controlled_comparison.json`, `controlled_baseline.*`, and `controlled_mutant.*`; the logs retain `--trace-config` records of the loaded plugin modules. This resolves the plugin-environment concern for these four targeted outcomes only.

An earlier attempt passed the functional assertions but failed during teardown because `opentelemetry.sdk` was missing from the reused environment. That error is preserved in `evidence/initial_teardown_error.xml` and `.log`; it was resolved by adding the dependency in the isolated environment. Other initial typecheck and import-path failures remain summarized in `evidence/summary.json`. A preliminary DBOS 3.4.0 run also passed, but the final candidate's stated qualification is the locked DBOS 2.29.0 run.

The supplied logs and JUnit files are redacted copies: private absolute paths and machine identifiers were replaced, while assertions, outcomes and platform labels were kept. `evidence/redactions.json` records original and published hashes. These are locally generated, AI-assisted test records, not an independent reproduction or external attestation.

## Maintainer discussion and license

The proposed next step is a short comment on #11191 with the scenario and evidence, asking whether this in-process recovery test fits the desired scope. The [contributing guide at the pinned commit](https://github.com/pydantic/pydantic-ai/blob/d44704ec72744e4fc0bd5a3d5dd877462a24da5b/docs/contributing.md) asks for agreement on the approach and assignment before a non-trivial PR.

The candidate derives from Pydantic AI test patterns under the MIT license. The upstream MIT notice is included as `LICENSE`. Preparation and local tests used AI assistance. No adoption, model quality, composed memory/effect guarantee, or production reliability claim is made.
