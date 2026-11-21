# A stale receipt can carry the right decision

The existing P02 Node peer reads a correction to input C and recalculates decision D3. D3 compares the integer mean of A and C with 28. The fixture holds A at 10. At the second correction, the old and current decisions are both true. The old signed receipt still refers to the previous revision of C.

| C revision | C value | D3 score | D3 decision |
|---:|---:|---:|---|
| 0 | 30 | 20 | false |
| 1 | 48 | 29 | true |
| 2 | 50 | 30 | true |

After setting up the public P02 Python dependencies and Node as described in the [project README](../../README.md), run this command from the repository root with that same Python interpreter.

```sh
python -I -B -S projects/P02_corrections/examples/stale-receipt-same-decision/run.py
```

For each correction, the example requests a signed receipt from the Node peer before delivering the update. The Python engine rejects the old dependency versions and keeps the obligation pending. The peer then applies the correction to its own store and issues a fresh receipt. Python accepts it after local replay. A SQLite query checks the score, decision and input versions using the same fixture and signed corrections. The stores use a temporary directory under the project's `.local` folder.

This synthetic example measures a local software decision. Receipt withdrawal, alternative evidence, a business action and production trust are outside its scope. It exercises the public [peer](../../src/node_peer.mjs), [fixture](../../src/p02/fixtures.py) and [receipt API](../../src/p02/engine.py) used by the existing [interoperability test](../../tests/test_recovery_interop.py). Copyright 2026 Mohammed Messaoudene. [MIT license](../../LICENSE).
