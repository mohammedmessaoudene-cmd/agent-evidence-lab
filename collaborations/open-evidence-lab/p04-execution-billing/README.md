# P04: execution completion is not billing finality

A focused candidate for [Open Evidence Lab #352](https://github.com/probityai/agent-evidence-vectors/issues/352), by Mohammed Messaoudene, prepared and checked with AI assistance. **Accepted in discussion as a Lab example; not merged into an upstream corpus.**

## The case

An execution outcome, final billing, and permission to dispatch an attempt are different facts:

- **F01:** execution reports success but billing is not final. The remaining liability stays reserved.
- **F04:** a final invoice follows a lost response. Billing becomes final while execution remains UNKNOWN. After normal process reopening, the same attempt cannot be dispatched again; a different affordable attempt can be admitted.
- **F08:** a zero invoice still does not establish that no external effect happened.

These are tiny synthetic accounting amounts, not payments. Typed evidence roles and provider ceilings are trusted fixture assertions, not authenticated provider facts. The ledger itself is copied unchanged from [P04 at c21bbbc](https://github.com/mohammedmessaoudene-cmd/agent-evidence-lab/tree/c21bbbc0f9b087d5f1ed2e2cf4fbf4944b6b0e01/projects/P04_cost_exposure).

Probity's `uncertain-effect/v1` already addresses uncertain effects, unsafe retries and held reservations. This candidate does **not** reinterpret that contract, modify its reason codes, or claim a defect in Probity. The proposed boundary is specified in [INPUT_CONTRACT.md](INPUT_CONTRACT.md).

## Reproduce offline

Use a fresh checkout and a base Python interpreter. No pip installation, LLM, network service, provider account or paid API is used. From this directory:

```sh
python -S -B verify_kit.py
python -S -B generate_cases.py
python -S -B generate_cases.py --check
python -S -B run_review.py --out results/native1
python -S -B run_adapter_contract.py --out results/adapter1
python -S -B check_adapter_reader.py --out results/reader-probes.json
```

Output paths must not already exist. The final command reads the preceding `results/adapter1/report.json`; retain that path. The generator emits both the input files and separate expectations without importing the ledger. The adapter never reads the expected verdicts. Generated files and runtime reports are ignored by Git; the generator, frozen digests and published observations remain versioned.

## Recorded local checks

The source was rerun on **2026-11-03, Linux, Python 3.13.5, SQLite 3.46.1**:

| Check | Observation | Record |
| --- | --- | --- |
| Targeted ledger scenarios | 18/18 matched | [Native summary](evidence/native_summary.json) |
| Normal fresh-process reopening | 18/18 snapshots matched | Same native run, not additional scenarios |
| Deliberately defective variants | 5/5 detected | Witness case IDs in the native summary |
| Separate adapter and judge | Same 18 cases matched | [Adapter summary](evidence/adapter_summary.json) |
| Malformed adapter outputs | 8/8 rejected; positive control accepted | [Reader probes](evidence/reader_probes.json) |

[Case observations](evidence/case_observations.json) are a compact projection of the native run. Reproduction writes the full observations and mutant reports. Counts are finite-case observations, not security percentages; two executions of the same cases are not independent experiments. The original private preparation included an earlier reader weakness that was corrected before publication; the published reader probes qualify the corrected code only.

## Limits and provenance

This is a same-team, AI-assisted local experiment, not independent validation. Normal reopening is not abrupt-crash, power-loss or distributed durability testing. The original 3 November candidate run did **not** exercise the full P04 suite, Windows, real billing/effect providers, P06, ZTI-MCP or the Probity CLI. Later hosted Ubuntu/Windows checks have their own commit-specific receipts; they do not rewrite that historical run. P04's own historical results retain their original scope.

A successful fixture does not prove invoice authenticity, an external business effect, global exactly-once execution, a production cost ceiling or upstream acceptance. See [SOURCE_PIN.json](SOURCE_PIN.json), [NOTICE.md](NOTICE.md) and the scoped [MANIFEST.json](MANIFEST.json). The manifest checks bytes, not authenticity or scientific validity.

This proposal was developed on a separate branch; merging it in this author repository is not upstream adoption. The root publication manifest now inventories this subtree as well as the original files. The historical manifest and reports remain available at the pinned parent commits; this directory's manifest also checks the candidate in isolation. Related P06 and ZTI-MCP ideas are listed separately in [FOLLOWUPS.md](FOLLOWUPS.md), not presented as integrations.

## X1 follow-up

The clarification in `INPUT_CONTRACT.md` admits an invoice before any **locally
recorded** dispatch for an already reserved attempt. It does not infer a real
external action from that invoice. Credit for X1 and the dispatch-guard mutation
challenge belongs to piiiico in Open Evidence Lab #352.

After the commands above, run:

```sh
python -S -B run_x1_review.py --out results/x1
```

This separately evaluates the eighteen unchanged historical cases plus X1, the
three proposed guard mutations, an isolated invoice-state mutation and their
combined mutation. A mutation that is equivalent on reachable public-API states
is retained as a surviving control, not reported as a kill. The X1 adapter run,
two malformed-output checks and four boundary controls are reported separately.
See [REVIEW_X1.md](REVIEW_X1.md) and [the new local record](evidence/x1_summary.json).
Historical evidence files above are not rewritten to claim these new checks.

## M4 follow-up: required public state, not a ledger repair

The state-aware **v0.2 proposal** makes dispatch_state=POSSIBLE normative after
X1's accepted pre-dispatch invoice, through normal reopening, refused dispatch,
invoice replay and a later equal cost observation. This does not claim an external
effect. Credit: [piiiico's M4 witness](https://github.com/probityai/agent-evidence-vectors/issues/435#issuecomment-6626271127).
The ledger, generator, original eighteen inputs and earlier results are unchanged.
The old seven-field v0.1 reader remains a historical/baseline control; it cannot
qualify the additional output requirement.

After the existing commands, run:

```sh
python -S -B run_m4_review.py --out results/m4
```

The command freezes its expectations before executing an observer in separate
processes. The original and M3 meet the new contract; M1, M2, M4 and M5 do not.
It checks missing/incorrect state outputs, exact boolean types, unsupported effect
claims and an ordinary-dispatch positive control. The [local summary](evidence/m4_summary.json)
records actual versions and source hashes. `results/m4` contains the full observations
and isolated mutation sources; reruns require a new output path.

This extension tightens a test contract, not the P04 implementation. Its repeated
stages and mutation observations are not additional independent scenarios.
Historical `evidence/x1_summary.json` describes the earlier seven-field judgment,
including the formerly surviving M4; it has not been rewritten. Current hosted
CI results must be read from the actual run on the corresponding commit.
