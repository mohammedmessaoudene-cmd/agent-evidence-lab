# Related work: separate candidate cases, not integrations

P04 is the only submission proposed with this package. The following links make adjacent work discoverable without claiming that Open Evidence Lab has adopted it. Neither project was executed as part of the P04 run.

## P06: provider authority during handoff

[Existing P06 package](https://github.com/mohammedmessaoudene-cmd/agent-evidence-lab/tree/c21bbbc0f9b087d5f1ed2e2cf4fbf4944b6b0e01/projects/P06_handoff_evidence).

Possible separate case: a valid receipt does not itself ensure that the provider enforces the current worker's authority at the effect boundary. A useful submission would retain an unsafe control and an enforced-fence control, with the provider ledger read separately. Its historical local SQLite/HMAC fixtures must not be described as remote provider validation.

Status here: **not submitted, not integrated, not rerun**. A focused export and a freshly pinned run are required before a concrete proposal.

## ZTI-MCP: constraints across delegated agents

[Existing ZTI-MCP repository](https://github.com/mohammedmessaoudene-cmd/zti-mcp).

Possible separate case: two delegated agents share a root budget or a cumulative restriction; individually acceptable actions must not bypass that root constraint when combined. Include an allowed positive control and one deliberately removed enforcement check. The protected local SQLite effect boundary must remain explicit; do not extend it to later network or physical effects.

Status here: **not submitted, not integrated, not rerun**. Select and pin one existing scenario, export its observations, and obtain feedback before attempting a Lab adapter.

## Contribution policy

Do not announce an integrated portfolio. Do not open duplicate issues, mass-tag maintainers, or treat silence as approval. Keep one focused proposal in the Lab thread. Any follow-up needs its own source pin, reproduction command, positive control, discriminating counterexample and explicit limits. No third-party assignment or validation is assumed.
