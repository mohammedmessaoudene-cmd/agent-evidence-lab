# Agent Evidence Lab

Six small research packages for inspecting what an agent integration actually establishes: memory recovery, correction tracking, verifier behavior, uncertain costs, test dossiers, and mission handoff.

The useful output is a reproducible case, a test proposal, or a clearly bounded negative result. These packages do not establish a new protocol, superior optimizer, production reliability, market demand, or upstream adoption. The cases were selected to examine particular failure modes; their pass counts are not representative benchmark scores.

## Start with a question

| Project | Question and artifact | Main boundary |
| --- | --- | --- |
| [P01 — Memory recovery](projects/P01_memory_recovery/) | Does a journaled Memory snapshot survive DBOS recovery and later compaction? A proposed Pydantic AI test. | In-process interruption; no fresh worker or host-failure proof. |
| [P02 — Correction audit](projects/P02_corrections/) | Which declared decisions need review after an input changes? Audit examples and counter-cases. | Closing declared obligations does not discover every real dependency. |
| [P03 — Verifier reproduction](projects/P03_verifier_reproduction/) | Can duplicate verifier names hide a failed check? A reproduction of a known issue and comparison with its existing fix. | PR24 already addresses the aggregation defect; no new discovery claimed. |
| [P04 — Cost exposure](projects/P04_cost_exposure/) | What remains financially unresolved after an uncertain attempt? A conservative cost ledger. | Unknown costs are not zero; no superior allocation policy is established. |
| [P05 — Test dossier](projects/P05_test_dossier/) | Can another operator inspect a complete, traceable test dossier? Documentary examples and a pilot protocol. | Synthetic inputs and an unexecuted field pilot; no physical certification or measured savings. |
| [P06 — Handoff evidence](projects/P06_handoff_evidence/) | Which obligations can a receiving worker safely close? Handoff examples and uncertainty cases. | An authentic receipt or successful workflow does not prove external authority enforcement. |

Read the selected project's README before running anything. It identifies its inputs, dependencies, commands, observed results and exclusions. There is no single repository-wide pass/fail score. [The portfolio notes](docs/PORTFOLIO.md) explain the strongest alternatives, prior work, and reasons to stop each line of investigation.

## Read outcomes literally

A check can pass because it correctly detects a dangerous result. For example, an expected counter-case may produce a duplicate effect or expose a stale decision. “Expected behavior observed” does not make that behavior safe for production.

- **PASS** means the stated check met its expectation in its declared environment.
- **FAIL / VIOLATION** records a failed expectation or a contract violation. An intentionally broken implementation may be expected to fail.
- **UNKNOWN / INCONCLUSIVE** means the available evidence does not settle the question.
- **NOT_RUN / NOT_TESTED / PREPARED_NOT_RUN** means no corresponding execution is claimed.

Keep the test expectation, the observed system behavior, and the broader conclusion separate. A workflow engine reporting SUCCESS may still leave a business obligation UNKNOWN. A complete dossier may document a FAIL and still be ready for review.

Historical experiment results and checks of the extracted publication package are different records. A replay of supplied fixtures does not repeat the original data collection, a provider deployment, or a field study. Test cases, assertions, reruns and review passes must not be added together as independent experiments.

## Evidence and review

Code, documentation, experiment preparation and reviews used AI assistance. The review process uses two AI-assisted passes: technical examination and strategic review of claims, alternatives and usefulness. These are internal reviews within the same project, not independent validation, certification, or human maintainer approval. Review conclusions apply to the artifact version and scope stated in their records.

Recorded executions are bounded local or hosted CI checks tied to their stated source version and environment. A real library may still use a simulated provider, synthetic data or a deterministic model. The linked P01 CI run qualifies its two selected cases; subsequent edits require their own checks. Where publication copies redact local paths or machine names, their provenance records distinguish the original and published bytes.

Hashes and manifests check artifact consistency. They do not prove scientific validity, independent origin, external delivery or adoption. P01's initial installation limitation is retained as history; the frozen upstream installation and its two selected tests subsequently passed in [hosted Ubuntu CI at fa7e467](https://github.com/mohammedmessaoudene-cmd/agent-evidence-lab/actions/runs/41327039712). That run does not qualify later corrective sources in the other projects.

## Upstream contribution

P01 is an illustrative proposal for [Pydantic AI #11191](https://github.com/pydantic/pydantic-ai/issues/11191). A [single focused scope proposal](https://github.com/pydantic/pydantic-ai/issues/11191#issuecomment-6560812372) has been posted and read back; maintainer agreement and assignment precede a non-trivial upstream PR. The next evidence is a maintainer response. P03 credits the existing [EnterpriseOps-Gym PR24](https://github.com/ServiceNow/EnterpriseOps-Gym/pull/24); a reproduction does not justify a duplicate fix.

Publishing a package or posting an issue comment is not upstream acceptance. No funding award, customer deployment or institutional endorsement is claimed.

## Licenses

Original project material is offered under the repository's MIT license. Third-party material retains its own license and notices; the root license does not relicense it. Consult the project-level notices before reuse.

The P01 candidate derives from Pydantic AI test patterns under **MIT**, with the [Pydantic Services Inc. notice](projects/P01_memory_recovery/LICENSE) retained. It is not described as dual MIT/Apache licensed. Referenced datasets and dependencies have separate terms; a public source link does not grant redistribution or commercial-use rights.

