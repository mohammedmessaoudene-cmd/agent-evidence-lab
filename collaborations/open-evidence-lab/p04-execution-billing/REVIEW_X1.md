# X1 review and source-preserving follow-up

The case and three dispatch-guard mutations are credited to
[piiiico's report](https://github.com/probityai/agent-evidence-vectors/issues/352#issuecomment-6601133451).
The question is tracked in [Probity #435](https://github.com/probityai/agent-evidence-vectors/issues/435).
This is a local candidate, not an upstream conformance or adoption claim.

## Decision

An invoice for an existing reserved attempt may precede any dispatch recorded by
this ledger. A missing local dispatch entry is not authoritative proof of no
external effect. The implementation already preserves UNKNOWN execution and
blocks the subsequent dispatch. No production-source correction is needed for X1.
The input contract now states this ordering and its rejected-input boundaries.

## Local execution

The new `evidence/x1_summary.json` identifies Python, SQLite, source and runner
hashes. Nineteen distinct scenarios are evaluated against the original and five
variants: 114 matrix observations, not 114 independent experiments. The unchanged
eighteen-case generator retains SHA256
`38b7a100b029232449463b4d31c8eb2ec0ffe96ce71a23a879f882bb1d3e1929`.

| Variant | Old cases rejected | X1 dispatch allowed |
| --- | --- | --- |
| Original | none | false |
| M1: entire guard removed | F03, F04, F08, F09 | true |
| M2: FINAL bypasses guard | F04, F08, F09 | true |
| M3: billing clause removed | none | false |
| M4: invoice POSSIBLE write removed | none | false |
| M5: M3 and M4 combined | none | true |

M3 survives and is equivalent for public-API-reachable states of the unchanged
source; it is not counted as a detected defect. M4 changes internal dispatch
state and is not globally equivalent, though the chosen gate observations do
not reject it. X1 detects M5, which the old eighteen scenarios miss.
The original source passes all nineteen. Operational errors do not count as kills.

The separate existing adapter and strict judge also accept X1. Two malformed
outputs (unsafe permission and integer zero instead of boolean false) are
rejected. Four additional controls cover ordinary first dispatch, unknown
attempt, wrong invoice role, and contradiction of fenced non-dispatch. They
are separately labelled controls, not additional corpus cases.

## What is preserved

`upstream/exposure_ledger.py` remains Git blob
`3b9599c4fa1063156b28aea0588634f9ca04cefe`, SHA256
`c321eab3e1adfa2169164f63238597f1a1c2a7868d339540a3da574f09c82d0f`.
The old generated cases and all original `evidence/*.json` are unchanged.
The root manifest now includes the candidate's tracked files instead of leaving
an unlisted subtree. Its exact-path verification remains enabled and unchanged.
Only the current manifest is updated; previous commits retain their inventories.

The ordinary runner's `not_run` metadata now says "other operating systems in
this execution" instead of unconditionally saying Windows, so a future Windows
CI run cannot mislabel itself. Its execution logic and historical records are
not changed. CI results must be read from actual runs; the workflow is not proof
of a pass.

## Limits

Same-team, AI-assisted local Linux checks; no independent human validation,
real invoice, remote business effect, payment, production recovery, power loss,
full P04 historical suite, or Probity CLI execution. Fresh-process reopening is
not an abrupt-crash test. A scoped input contract is not a universal billing rule.
No P06 or ZTI-MCP integration is claimed by this follow-up.
