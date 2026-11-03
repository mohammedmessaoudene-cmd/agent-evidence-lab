# P04: execution completion is not billing finality

A focused candidate for [Open Evidence Lab #352](https://github.com/probityai/agent-evidence-vectors/issues/352), by Mohammed Messaoudene, prepared and checked with AI assistance. **Proposal only: not accepted or integrated upstream.**

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

This is a same-team, AI-assisted local experiment, not independent validation. Normal reopening is not abrupt-crash, power-loss or distributed durability testing. The original full P04 suite, Windows, real billing/effect providers, P06, ZTI-MCP and the Probity CLI were **not** run in this candidate. P04's own historical results retain their original scope.

A successful fixture does not prove invoice authenticity, an external business effect, global exactly-once execution, a production cost ceiling or upstream acceptance. See [SOURCE_PIN.json](SOURCE_PIN.json), [NOTICE.md](NOTICE.md) and the scoped [MANIFEST.json](MANIFEST.json). The manifest checks bytes, not authenticity or scientific validity.

This proposal lives on a separate branch. The root historical publication manifest is unchanged and does not certify this added subtree; use this directory's manifest. Related P06 and ZTI-MCP ideas are listed separately in [FOLLOWUPS.md](FOLLOWUPS.md), not presented as integrations.
