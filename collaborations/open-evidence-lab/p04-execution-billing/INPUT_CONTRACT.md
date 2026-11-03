# Execution/billing finality — proposed input and observation contract

Identifier: `execution-billing-finality/v0.1-proposal`.
Status: local proposal; not a Probity predicate, conformance claim, or adopted standard.

## Why a separate example

An execution result and a final bill answer different questions. A successful or failed execution can leave billing unsettled. A final invoice, including an invoice for zero, does not establish whether an external business effect happened. Availability of money for a *different* attempt is not permission to redispatch the same attempt.

Probity's `uncertain-effect/v1` already tests unknown effects, unsafe retries and retained reservations. This example does not redefine those semantics or add monetary assumptions to them. It exposes P04's existing execution/billing distinction through portable, generated scenarios.

## State and trust

P04's `outcome` becomes `execution_outcome` without being converted into a business-effect verdict. Valid execution values are UNKNOWN, SUCCEEDED, FAILED, NOT_DISPATCHED. Billing values are UNKNOWN, FINAL, CONFLICT. Money is nonnegative integer micro-USD; bool and float are not money. Fixtures use tiny synthetic amounts, not real transactions.

The adapter submits typed `Evidence` with a kind, source role, reference and attempt ID. These are trusted fixture assertions. No signature verifier, real invoice or externally enforced ceiling is present. `external_effect` MUST remain `NOT_EVALUATED`. An unchanged SQLite row is not proof of external reality.

A maximum authorized cost is not itself an enforced provider ceiling. Dispatch in these scenarios supplies a separate, explicit, synthetic ceiling assertion. Without it the admission gate must not manufacture one.

## Inputs

`fixtures/inputs/Fxx.json` contains exactly id, budget, steps and probes. Initial setup reserves attempt A for two units. The allowed commands are reserve, dispatch, unknown, outcome, invoice, cost and non_dispatch. The generator documents their concrete arguments in the JSON files. Inputs contain no expected verdicts, expected exceptions or expected return values.

The adapter runs the main steps against a fresh persistent SQLite account, obtains a snapshot, then starts another interpreter. That interpreter reopens the same database, reports its initial snapshot and executes the probes. This tests normal process reopening; it does not simulate host loss or an abrupt crash.

`fixtures/expected.json` is kept on the judge's side. It records the expected state projection, exceptions and selected return fields. The runtime adapter never opens that file. Both sides and their expectations were prepared in this session, so this is still not an independently authored reader experiment.

## Adapter interface

Run `<adapter command> <scenario.json> --json`. A completed observation exits 0 and prints one JSON object on the last stdout line. A setup, transport, decoding or unexpected operational failure exits nonzero. Exceptions expected from a tested ledger action are reported as data, not hidden.

The result includes contract, case, observed, fresh_process_snapshot_equal, steps, probes, external_effect, source_sha256, and must_not_claim. Each step/probe exposes an exception name or null, plus relevant boolean return fields. A false value is not the integer zero.

`source_sha256` binds the local P04 source used by the supplied adapter. Other adapters must identify their own source; merely reporting a digest does not authenticate that implementation. The judge checks shape and compares reported observations. A dishonest adapter can lie; no independent instrumentation of such an adapter is supplied.

## Judge order

1. Validate object shape and required observation keys.
2. Validate exact money and boolean types and ranges.
3. Require a syntactically valid source digest.
4. Require a list of unique claim-boundary labels.
5. Match contract and case identity.
6. Compare execution/billing/account projection to the frozen expectation.
7. Require exact snapshot agreement after normal process reopening.
8. Require external_effect = NOT_EVALUATED and all claim boundaries.
9. Compare steps and probes, including exact types of expected return flags.

This reader is a finite research test, not a hardened parser for arbitrary hostile JSON. Input size, duplicate JSON keys, nesting limits and full resource-exhaustion defenses are not comprehensively tested here. Those belong in a later integration review before exposing the interface to untrusted sources.

## Claims that MUST NOT follow from a pass

- external_effect_established
- invoice_authenticity
- production_durability
- upstream_acceptance

A normal reopen is not a power-loss test. A passing same-team adapter is not independent implementation agreement. A wrong-role refusal validates a semantic role check, not cryptographic identity. Same-attempt redispatch suppression is not a proof of global exactly-once behavior under different attempt IDs.

## A discriminating example

F04 reserves two of three units, records dispatch and a lost response, then accepts a final invoice for one unit. The correct view is execution UNKNOWN, billing FINAL, known cost one, outstanding reservation zero, available two. After reopening in a fresh process, a second dispatch of A is not allowed, while a new distinct attempt B for two units can be reserved.

F01 is the other direction: observed SUCCEEDED without an invoice leaves billing UNKNOWN, a reservation of two, and only one unit available. A variant which frees the reservation merely because execution succeeded fails F01.

## Route to Probity

Start as a Lab example or scoped discussion. Do not change `uncertain-effect/v1`, its reason codes or existing expectations. A future sibling corpus would require a proposal-labeled pinned specification, generated fixtures, derived manifests/counts, condition registration where required, appropriate release wiring, upstream tests and maintainer review. No such integration is claimed by this kit.
