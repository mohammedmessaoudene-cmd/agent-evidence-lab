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

## Invoice before a locally recorded dispatch (X1 clarification, 2026-11-04)

Yes: a valid final-invoice observation for an **already registered and reserved
attempt** is an admitted input even when this ledger has not recorded a dispatch
for that attempt. The fixture does not require a prior `dispatch` or `unknown`
command before `invoice`. This clarifies the existing implementation; it does
not assert a real provider event or authorize bypassing a dispatch gate.

"No dispatch recorded here" is not a verified claim that no external action
occurred. A valid invoice settles the billing axis only: the execution outcome
remains UNKNOWN, `external_effect` remains NOT_EVALUATED, and the same attempt
must not gain permission to dispatch. The implementation conservatively stores
`dispatch_state=POSSIBLE`; that marker is not evidence of a real dispatch.
These restrictions must survive normal process reopening.

This is not unconditional acceptance of every invoice. An invoice for an
unregistered attempt is rejected. Wrong evidence role or attempt binding is
rejected. Contradiction of established finality, including prior fenced
non-dispatch, remains a conflict; it does not reopen the gate. Real invoice
authentication and reliable association with an attempt remain outside the fixture.

X1 reserves A for two units under budget three, accepts an invoice for one unit,
then probes dispatch in a fresh process. Expected: execution UNKNOWN, billing
FINAL, known cost one, held zero, available two, and dispatch_allowed=false.
The original eighteen generated cases and historical reports remain unchanged.
`run_x1_review.py` freezes X1 separately and evaluates that nineteen-case extension.
The scenario and three dispatch-guard mutations were proposed by
[piiiico](https://github.com/probityai/agent-evidence-vectors/issues/352#issuecomment-6601133451).
A surviving equivalent mutation is not counted as a detected defect.

## Required dispatch-state output (v0.2 proposal, 2026-11-04)

Decision in response to [Pico's M4 witness](https://github.com/probityai/agent-evidence-vectors/issues/435#issuecomment-6626271127):
`dispatch_state` is a required observable output in the **state-aware extension**,
not an internal detail. Its identifier is `execution-billing-finality/v0.2-proposal`.
The eighteen v0.1 fixtures, their seven-field reader, and their historical evidence
remain unchanged. The v0.2 observer/reader are `p04_state_adapter.py` and
`run_m4_review.py`; a v0.1 pass alone does not establish this additional requirement.

For X1's existing reserved attempt and accepted trusted final invoice, the required
projection is execution UNKNOWN, billing FINAL, known cost 1, held cost 0,
available 2, unbounded false, frozen false, and **dispatch_state POSSIBLE**.
POSSIBLE is conservative local bookkeeping: no absence of external execution has
been established. It is neither proof that a dispatch occurred nor an external
effect verdict. `external_effect` must remain NOT_EVALUATED. RESERVED is likewise
not general-purpose evidence that an external action never occurred.

The required projection must be visible immediately after the invoice, after
normal fresh-process reopening, after the refused same-attempt dispatch, after
replaying the identical invoice event, and after a later equal cost observation.
The identical invoice replay must be non-new/non-finalizing. The equal cost
observation must not repair a previously RESERVED attempt or report a change to
its attempt-state projection. `state_changed` describes that projection, not the
append-only events table. This is a source-specific proposed profile, not a
universal billing protocol.

The v0.2 adapter takes `scenario.json --json`, optionally `--source PATH` for
isolated mutation testing. Input contains exactly contract, id, budget, steps
and probes; no oracle fields. It reports contract, case, source_sha256, initial,
steps, observed, reopened, probes, end, end_reopened, external_effect and
must_not_claim. Every observed projection includes dispatch_state. Each action
record carries exception, return and observed. Probes execute in a new interpreter;
end_reopened is an additional ledger instance in that interpreter, not another
host or crash test. A successful observation exits 0; operational failures exit 2.

The reader checks identity and claim boundaries, exact projected keys/types,
initial state, post-invoice/reopened/end state, action counts, each action's
state and exception, and selected exact-boolean returns. Missing, null, wrong-type
or RESERVED dispatch_state must fail. A correct first-dispatch positive control
prevents an always-refuse implementation from being endorsed. The original
parser/resource-limit exclusions continue to apply.

M4 is now a distinguishable contract defect: the unchanged source satisfies this
output, whereas deleting the invoice's POSSIBLE write violates it. M3 remains a
surviving control under the unchanged source's reachable-state invariant. M5
remains detected. No claim of unsafe execution in the original source follows.
Credit for the public-API witness and this contract question remains with piiiico.
