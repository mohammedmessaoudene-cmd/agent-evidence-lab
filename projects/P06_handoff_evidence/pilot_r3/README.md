# P06: bounded handoff preparation

**PREEXISTING, 5 November 2026. LLM campaign: NOT_RUN.** This is a deterministic
development harness and an offline scorer for a proposed handoff experiment.
It is not a completed multiagent LLM study, a new protocol, or evidence of
superiority over a conventional controller.

Run with Python 3.11+ and its standard library, using an absent output folder:

```sh
python -B verify.py --out results/new_run
```

The finite protocol is copied into the result directory before the first case.
Verification runs 48 positive scripted episodes (four interface configurations,
two capability profiles, three fault schedules, one or three handoffs), followed
by deliberate adverse and integrity controls. No network or model call occurs.
Every arm uses the same classical decision policy in this verification. Counts
are fixture checks, not independent tasks, agents, production incidents, or
measurements of model behavior.

## What changes from the earlier P06 kit

The historical opaque worker stops the whole mission after unresolved delivery.
Here C0 retains UNKNOWN for the uncertain obligation and completes the separately
authorized independent obligation. A real serialized envelope is decoded into
a separate receiver state at each handoff. The receiver policy consumes that
state. A paired omitted-task control therefore loses useful completion while
the canonical mission ledger still retains the missing obligation as PENDING.
Message omission and ledger deletion are different outcomes; this fixture tests
the former. It does not simulate every kind of ownership loss.

The hidden SQL oracle distinguishes no dispatch/no effect from committed effect
without a confirmation. With opaque capabilities, these histories have identical
actor-visible traces, including the independent task's receipt. UNKNOWN is a
knowledge state, not an event timestamp. Sequential global receipt IDs initially
leaked the primary outcome through the independent task; the negative result
was retained and identifiers were corrected to be local to each obligation.

C0 and all other configurations receive the same facts, stable obligation and
operation identities, authority epochs, effects, action limit, and provider
capabilities. Recoverable lookup is explicitly mission-wide for this trusted
fixture. It is **not** inherited permission to inspect another ZTI principal's
operation. A completed fence rejects a stale epoch in the normal provider.
An intentionally broken provider can violate it; a fence acknowledgement alone
does not establish enforcement. Receipt records here are trusted fixture data,
not signatures or hostile-provider attestations.

## Interpretation of the four interface configurations

- C0: competent deterministic controller with durable intent snapshots, lookup
  and idempotency where available; opaque uncertainty is retained without retry.
- L1: the same scripted policy with generated labeled-text handoff facts.
- L2: the same scripted policy with structured JSON handoff facts.
- L3: L2 plus a deterministic gate rejecting opaque retries and unsupported DONE.

L1 is lossless generated text, not an LLM-authored natural-language summary.
The actual text is decoded and compared with the receiver view. No representation
advantage is measured. A future LLM campaign must use real isolated contexts,
freeze prompts and actual model identity/settings, and verify semantic information
parity. L3 refusals measure infrastructure behavior, not improved agent reasoning.
The gate trusts provider replies; a lying provider is outside its guarantee.

## Evidence and negative controls

Authority, admission, effect, delivered response, agent claim and settlement are
separate records. The offline scorer does not import runtime code. It compares
SQL effects with ordered events and ties observed responses to allowed actions.
It checks executed handoff depth, transported payloads, state transitions and
final ledger. Hashes only check byte consistency; a malicious actor rewriting all
logs coherently is outside this trusted laboratory threat model.

Controls exercise unsupported DONE even when a hidden effect exists, blind retry
duplicates, omitted obligations, unnecessary whole-mission abstention, stale
epochs, a fabricated success with no effect, and gated unsafe proposals. Unsafe
observations remain unsafe when their detection check passes. Corrupt evidence
is invalid and rejected, not counted as a safe episode. Reviewer probes exposed
missing depth enforcement, a forged settlement response, and missing admission
checks; those findings were retained and converted to regression controls.

Metrics separate duplicate effects, post-fence effects, unsupported claims,
unsupported durable settlement, factually false DONE, omitted mentions, gate refusals, legitimate
UNKNOWN, and useful completion among safely resolvable obligations. Effects are
counted by business obligation, not merely operation ID. No statistical estimate
of deployment prevalence is justified by these authored fixtures.

DONE means exactly one correctly bound effect. No observed proof with one hidden
effect is an unjustified but factually true DONE. A received faulty provider ACK
with no effect is factually false even when the actor reasonably trusted that
reply. Two effects also invalidate DONE. These counters are evaluated against
the causal point of the assertion; later evidence does not justify an earlier
claim. Utility requires both a matching observed receipt and exactly one effect.

## Boundaries and next experimental gate

SQLite commits are real local writes. Faults are scripted in-process schedules;
there are no real transport failures, subprocess crashes, remote business effects,
physical devices, adversarial identities or OS sandbox. Files provide evidence
snapshots, not a verified restart/recovery implementation. No arbitrary agent code
is executed. An LLM runner with isolation, wall-time/token limits and an authorized
non-separately-billed runtime is absent: campaign NOT_RUN.

The public development cases are not a hidden evaluation reserve. The earlier
64-execution LLM design is a proposal and requires a fresh preregistration,
disjoint held-out fixtures, equal capabilities and fixed finite budgets. Reject
oracle leakage, broken positive controls and post-hoc reserve changes. Retain
ties and adverse results. There is no autonomous future execution or submission.

This preparation precedes the official 6–8 November event. Only work actually
performed during the sprint may be presented as its new contribution, under
the [organizer's prior-work rules](https://apartresearch.com/sprints/swarm-alignment-2026).

## Sources and rights

Original code in this folder: MIT, copyright Mohammed Messaoudene, AI-assisted.
No ZTI, AOR or third-party implementation is copied. References describe limits,
not implemented integrations or independent validation:

- [Historical P06 source](https://github.com/mohammedmessaoudene-cmd/agent-evidence-lab/tree/c21bbbc0f9b087d5f1ed2e2cf4fbf4944b6b0e01/projects/P06_handoff_evidence)
- [AOR](https://github.com/mohammedmessaoudene-cmd/action-outcome-recovery): UNKNOWN can be recorded before dispatch; its classic recoverable baseline is competent.
- [ZTI R6](https://github.com/mohammedmessaoudene-cmd/zti-mcp/tree/1697a9ec4da11de3318d55099d696a814152bc75/successor/r6): RESERVED is not an effect, COMMITTED is local atomic state, and cross-principal lookup requires explicit rights. No full R6 equivalence is claimed.
- [HSC-Bench](https://arxiv.org/abs/2610.36523): prior handoff/continuation evaluation includes action histories; this harness establishes no global novelty.

Cross-project contracts are consumed separately with exact local read receipts.
They constrain interpretation; they are not copied into this public MIT package.
Two same-team AI reviews are not independent human or institutional validation.
