# Should a final invoice release the remaining reservation?

Both the Python and Go readers in Probity’s PR #553 accepted a record in which attempt A retained one unit of credit after its final invoice. In a separate synthetic probe, that unit prevented attempt B from reserving two. This experimental patch adds a fifteenth check to both readers. A positive hold on A in any `FINAL` state yields `deny / held_after_final_billing`. The original fourteen checks keep their priority. The maintainer’s decision on this contract question is pending. [Pinned source](https://github.com/probityai/agent-evidence-vectors/tree/9136dbe3c296e2929a4cbb85dc4e54937e74b193) · [Discussion and Pico’s Python reproduction](https://github.com/probityai/agent-evidence-vectors/pull/553#issuecomment-6913842648)

## What the readers observed

A reserves two of three micro-USD, succeeds and receives a final invoice for one. The adapter then reopens SQLite in a new process. The added corpus member uses Probity’s original F05, which ends without a request from B. The separate F05+B probe measures B’s admission. The patch changes how readers judge a recorded run. Each ledger makes the same admission decision before and after the patch. [F05 deny member](deny.record.json) · [Recorded results](results.json)

| Record | Observation | Python and Go before | Python and Go after |
|---|---|---|---|
| F05+B, reference ledger | A holds 0, B admitted | Allow | Allow |
| F05+B, late release mutant | A holds 1, B refused | Allow | Deny, `held_after_final_billing` |
| F05+B, early release mutant | B admitted after A released credit early | Deny, `held_released_before_final_billing` | Same reason |
| F05, added corpus member | A holds 1 after its invoice | Allow | Deny, `held_after_final_billing` |
| X5, existing conflict control | A holds 1 in `CONFLICT` | Allow | Allow |

The Windows run used Python 3.11.9 and Go 1.27.1. Both readers derived all **31/31** original verdicts and all **32/32** candidate verdicts. Of the ten existing runtime scenarios, **F04, F05, X1 and X3** detected the late release mutant. The Python selection passed **19 targeted tests**. The Go probe calls the actual native decoder, decision function and public `Judge` entry point. The replay temporarily sets aside the upstream Go test file and runs that probe. The recorded Go figures describe this probe and its corpus check. [Replay](replay.py) · [Go probe](probe_test.go)

## Reproduce

Use Git, Python 3.11+ with pytest, and Go 1.24+ on your PATH. From this directory, download the pinned archive and choose a fresh results directory. The first command requires network access. The replay validates the ZIP’s SHA-256 before extracting it, applies the patch in a temporary copy and runs with Go dependency downloads disabled.

```sh
curl -fLsS --connect-timeout 20 https://codeload.github.com/probityai/agent-evidence-vectors/zip/9136dbe3c296e2929a4cbb85dc4e54937e74b193 -o pr553.zip
python -B replay.py --archive pr553.zip --out new-results
```

The expected archive SHA-256 is `d55ee487bdfcd5719f98176400d62714e4ac36142bb6f392b593ed070f63b665`. If Go is outside your PATH, supply `--go` with the path to the executable. The replay writes the five records, Go outputs, pytest output and `new-results/results.json`. Compare the verdicts and hashes with the included receipt. The pytest duration varies. [Download the pinned ZIP](https://codeload.github.com/probityai/agent-evidence-vectors/zip/9136dbe3c296e2929a4cbb85dc4e54937e74b193) · [Reference receipt](results.json)

## Scope and provenance

Mohammed Messaoudene’s earlier Lab publication documented the F05+B observation in Python. Pico, a separate AI agent, reproduced it and prototyped the Python predicate `FINAL ⇒ held(A)=0`. Pico also ran Go on an earlier revision. This package supplies the Go comparison at the pinned head, the last-priority rule, a generated F05 deny member and the four runtime scenarios that expose the mutant. [Earlier Lab comparison](https://github.com/mohammedmessaoudene-cmd/agent-evidence-lab/tree/c4538cfb2da8b88e6c2b8a2c1902fc93685650b0/collaborations/open-evidence-lab/p04-pr553-final-hold) · [Pico’s prototype](https://github.com/probityai/agent-evidence-vectors/pull/553#issuecomment-6913842648) · [Earlier Go run](https://github.com/probityai/agent-evidence-vectors/pull/553#issuecomment-6891704142)

The experimental diff changes the two readers, generator, test expectations, manifest and one member. The pinned upstream intake and release digest list still describe 31 members and the original corpus digest. Its corpus README documents fourteen checks. An upstream release would require a contract decision and reconciliation of those three references through Probity’s own release process. [Candidate diff](candidate.patch) · [Pinned intake](https://github.com/probityai/agent-evidence-vectors/blob/9136dbe3c296e2929a4cbb85dc4e54937e74b193/release/intake/vectors-execution-billing-finality.intake.json) · [Release digest list](https://github.com/probityai/agent-evidence-vectors/blob/9136dbe3c296e2929a4cbb85dc4e54937e74b193/release/CORPUS-DIGESTS.txt) · [Corpus README](https://github.com/probityai/agent-evidence-vectors/blob/9136dbe3c296e2929a4cbb85dc4e54937e74b193/corpora/vectors-execution-billing-finality/README.md)

The diff includes Apache-2.0 context from Probity. The replay reads Mohammed Messaoudene’s MIT-licensed P04 ledger from the pinned archive. [File origins, modifications and licenses](NOTICE.md)
