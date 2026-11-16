# Can a second reservation proceed after the final invoice?

The Python reader at pull request #553 accepted all ten runtime scenarios with a deliberately altered P04 ledger that keeps one unit of a reservation after billing is final. In a separate probe, that unit prevented a new attempt from reserving its budget. The unmodified ledger admitted the new attempt. [Tested revision](https://github.com/probityai/agent-evidence-vectors/commit/9136dbe3c296e2929a4cbb85dc4e54937e74b193)

Attempt A reserves 2 of 3 micro-USD, succeeds, then receives a final invoice for 1. The adapter reopens SQLite in a new Python process. We added the F01 reservation probe to F05 and asked whether a distinct attempt B could reserve 2. The amounts below are measured after reopening, immediately before the request for B. [Original P04 ledger](https://github.com/mohammedmessaoudene-cmd/agent-evidence-lab/blob/a3fd0ea597f763a99c73632813ef92d7e22d0ef5/collaborations/open-evidence-lab/p04-execution-billing/upstream/exposure_ledger.py)

| Ledger | Held for A | Known spend | Available | Reserve B | Python verdict |
|---|---:|---:|---:|---|---|
| Unmodified | 0 | 1 | 2 | Admitted | allow |
| Keeps unused reservation after final invoice | 1 | 1 | 1 | Refused | allow |

As a control, releasing exposure too early failed three of the ten shipped scenarios, F01, F05 and X4. The Python reader checks the outstanding reservation while billing is unknown. An additional check that a final bill leaves zero reservation for A would distinguish the two records above. The F05 probe measures the consequence for B. [Reader at the tested revision](https://github.com/probityai/agent-evidence-vectors/blob/9136dbe3c296e2929a4cbb85dc4e54937e74b193/packaging/agent_evidence_vectors/executionbilling.py#L239-L243)

Pico's earlier run covered replay, reductions in known spend, non-dispatch evidence, costs above the final bill and contradictory outcomes. This experiment exercises a separate condition using a mutation from the Lab's earlier local F01 qualification. The result concerns Python, synthetic invoices and a normal process restart. [Earlier run on the pull request](https://github.com/probityai/agent-evidence-vectors/pull/553#issuecomment-6891704142)

## Reproduce

Use Python 3.11 or later. From the directory containing this note, run the following commands with a new checkout and results directory.

```sh
git -c core.autocrlf=false clone --sparse --filter=blob:none --no-checkout https://github.com/probityai/agent-evidence-vectors.git vectors
git -C vectors config core.autocrlf false
git -C vectors sparse-checkout set packaging/agent_evidence_vectors corpora/vectors-execution-billing-finality
git -C vectors fetch origin 9136dbe3c296e2929a4cbb85dc4e54937e74b193
git -C vectors checkout --detach 9136dbe3c296e2929a4cbb85dc4e54937e74b193
python -B -S check_final_hold.py vectors new-results
```

The script checks the source hashes, runs three ledger variants and saves the raw focused observations and runtime reports. Two local runs with Python 3.11 produced identical comparison files. [Source pins](SOURCE_PINS.json) · [Observed results](observed.json) · [MIT license for this addendum](LICENSE)
