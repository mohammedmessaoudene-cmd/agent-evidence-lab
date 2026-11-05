# P05 pilot collection: declared costs and documentary prerequisites

This standard-library tool checks a passive test-dossier pilot form, reads the
referenced file bytes, and computes comparable declared costs. It keeps missing
costs unknown and never authorizes release of hardware or a batch.

Python 3.11 or later is sufficient; no package installation, agent, instrument or
model API is used. From this directory, run:

```sh
python -B pilot_collect.py --input tests/complete_pair.json --artifact-root .
python -B tests/run_regressions.py --out p05-regression-evidence
```

The first command evaluates one supplied **synthetic pair**. Its displayed costs
and percentage are arithmetic examples, not measured savings. The second runs
eight bounded CLI checks: one positive declaration control and seven invalid
fragments covering missing source/contract/approval, a template, invalid operator
keys, an invalid first method and an invalid currency. It exercises corrections
TECH001/TECH002 already identified during internal AI review.

The regression generator fabricates 16 jobs and 32 records to avoid a refusal
caused only by an incomplete population. It deliberately uses the
`OBSERVED_DECLARATIONS` tag on synthetic copies to test that branch. These are
**not human observations, 16 field missions, approvals or an economic study**.
No record from a customer or physical instrument is included. The calculator's
acceptance means declarations are complete enough for human signoff; it cannot
authenticate a coherent forgery or establish that the declared people worked.

## Preparing an actual pilot

Start from `collection.template.json`, keep the evidence in an approved private
directory, and follow `COLLECTION_CONTRACT.md` and `PILOT_PROTOCOL_R2.txt`. The
plan has four development jobs and twelve reserved jobs from at least three
families, two operators with balanced assignments, and a separate arbiter.
Authorization, data rights, inputs, contracts, method versions, observations,
assistance and costs must be supplied and checked by the responsible people.
The template itself is not an observation or permission to start.

All registered attempts, including rejected or abandoned work, contribute cost.
Human active time, machine time and calendar delay stay separate. Missing
categories, assistance or evidence prevent a complete comparison. A zero or
unknown control cost prevents division; negative declared savings stay negative.
A complete measured FAIL can be received as a dossier. Critical findings stop
the comparison. `material_release_authorized` is always false and
`twenty_percent_claim` remains `NOT_ESTABLISHED`.

The eight checks do not establish exhaustive malformed-input handling,
authenticity, calibration, rights, commercial demand, an agent advantage or
population-level statistics. The field pilot remains **PREPARED_NOT_RUN**.
The controlled subprocess timeout is 10 seconds; output size is checked after
capture on these finite inputs, not enforced by a hostile-process sandbox.

This is preparation dated 5 November 2026, **PREEXISTING** for the later Swarm
sprint. It introduces no new protocol and reports no LLM behavioral experiment.
Original code is MIT licensed. See `NOTICE.md` and `SOURCE_IDENTITIES.json`.
