# P01 R3: a narrow DBOS compatibility proposal

This supplement removes the retired `run_admin_server` option from the Memory
recovery test at Pydantic AI `d44704ec72744e4fc0bd5a3d5dd877462a24da5b`.
The complete proposed module is168lines/6400bytes, SHA256
`742edc61b5e5a4107a6807ec06520b34e496c47f5e8df07a0540f093f46e576f`.
It is separate from the historical169-line candidate and the frozen research release.
Relative to that candidate the only code change is one deleted configuration line;
assertions, recovery semantics and cleanup remain unchanged.

DBOS deliberately removed the admin server in[PR853](https://github.com/dbos-inc/dbos-transact-py/pull/853),
merged as`8e8ef5200898bf23c621aa3f327cec2f05545b5a`for3.0. DBOS3.4 therefore rejects
this option under strict typing. This is known API evolution, not a new production bug.
DBOS2.29 defaults the server off in local mode. **Only local nonCloud execution
is qualified. Set `DBOS__CLOUD=false` before importing DBOS.** Cloud can override
other settings as well; neither this deletion nor the old explicitFalse qualifies it.

## Observed qualification

| Execution | SDKs | Targeted static checks | Normal pair per SDK | Causal mutant pair per SDK |
|---|---|---|---|---|
| Received Linux,Python3.12.14,SQLite3.53.1 |2.29.0;3.4.0|Ruff check/format and strictPyright0|2PASS|Native assertion fails onB; dispatch comparator passes|
| Actual Windows,Python3.11.9,SQLite3.45.1 |2.29.0;3.4.0|Ruff0.17.2 check/format and Pyright1.1.414 strict0|2PASS|Native assertion fails onB; dispatch comparator passes|

Each OS used four pytest processes, reusing the same two selected test identities.
There were no skipped tests or test errors. In normal execution five model callbacks
containA after three compactions; the capability-step-bypass mutation yieldsA then
fourB callbacks. The native assertion catches that change; the selected unchanged
recording-dispatch comparator passes. Backends were restored exactly after each run.
This differentiates those two tests, not the whole upstream suite.

One setup store read occurs before the counter is cleared. After clearing, normal
execution reads once and the mutant reads twice. Workflow SUCCESS in the mutant
coexists with a failing property assertion. The initial journal is observed nonempty
but the test does not assert nonemptiness. Recovery is in-process, with synthetic
FunctionModel and store inputs. No provider or paid-model call is used.

The[compact report](evidence/compatibility_summary.json) separates receivedLinux
evidence, actualWindows execution, source identities and limitations. The complete
received79textfiles and Windows raw outputs are retained privately; this report
does not claim they are publicly downloadable or independently authenticated.
Setup/collector errors are preserved: CRLF mutation-preimage refusal beforepytest,
missing rootproject metadata, and a local compaction-list reader error after a
successful native pair. Correcting the last one reused its existing evidence;
it did not rerun that native pair. Received reproduction-path collisions were
corrected separately without adding a native experiment.

## Targeted reproduction

Use separate clean source and virtualenv directories for each SDK. These commands
show the qualified Windows route; use `.venv/bin/python` on Linux. Registry
availability and future dependency changes remain separate from the recorded run.
The frozen lock and the declared3.4 override are not a claim about arbitrary SDKs.
Keep this kit in an absolute `$P01Kit` path and choose an empty checkout directory.

```powershell
git -c core.autocrlf=false -c core.longpaths=true clone --no-checkout https://github.com/pydantic/pydantic-ai.git p01-compat-229
Set-Location p01-compat-229
git config core.autocrlf false
git config core.longpaths true
git checkout --detach d44704ec72744e4fc0bd5a3d5dd877462a24da5b
uv sync --frozen --package pydantic-ai-harness --extra dbos --extra logfire --group dev --group lint --python 3.11
uv pip install --python .venv/Scripts/python.exe --no-deps --editable . --offline
$env:DBOS__CLOUD = 'false'
Copy-Item -LiteralPath (Join-Path $P01Kit 'candidate/test_dbos_recovery.py') -Destination tests/harness/memory/test_dbos_recovery.py
.venv/Scripts/python.exe -m ruff check tests/harness/memory/test_dbos_recovery.py
.venv/Scripts/python.exe -m ruff format --check tests/harness/memory/test_dbos_recovery.py
.venv/Scripts/python.exe -m pyright --project pyproject.toml --outputjson tests/harness/memory/test_dbos_recovery.py
.venv/Scripts/python.exe -m pytest tests/harness/memory/test_dbos_recovery.py::TestMemoryDBOSRecovery::test_recovery_restores_snapshot_after_compaction tests/harness/memory/test_memory.py::test_snapshot_load_dispatches_as_durable_operation -q -rA --junitxml=.p01-r3-output/normal.junit.xml --basetemp=.p01-r3-output/normal-temp
```

Repeat in another checkout for3.4.0. After the frozen sync, upgrade only that
checkout's environment, before its checks:

```powershell
uv pip install --python .venv/Scripts/python.exe --reinstall-package dbos --exclude-newer-package dbos=2026-11-01 dbos==3.4.0
```

Invoke the venv interpreter directly; an automatic frozen sync would restore the
lockedSDK. For the mutation, save the backend's original bytes in that disposable
checkout, apply `candidate/capability_step_bypass.patch`, and run the same two
identities into distinct`mutant`output paths. Restore and rehash the backend in
`finally`. Expect one native assertion failure and the comparatorPASS, no skip or
error. A process timeout is infrastructure protection, not a recovery experiment.
The optional removal patch applies to the historical169module; a clean upstream
checkout instead receives the complete168module shown above.

## Rights and remaining gates

Original work uses the includedMIT licence. The Pydantic-derived test and small
backend mutation retain the[upstreamMIT notice](UPSTREAM_MIT_NOTICE.txt).
DBOS sources are referenced, not redistributed or relicensed. The legacy169module
and release are unchanged. This is a compatibility supplement, not an upstreamPR,
maintainer acceptance or additional global test coverage. The existing issue
[11191](https://github.com/pydantic/pydantic-ai/issues/11191) still requires a
maintainer's agreement and assignment before a non-trivial contribution.

Cooperative10second waits cover resume/result, not the whole test, synchronous
construction or cleanup. Partial constructor failure remains outside its cleanup
guarantee. No OS-kill/new-interpreter recovery, Cloud, physical qualification,
economic gain, independent human validation, adoption or protocol novelty is claimed.
