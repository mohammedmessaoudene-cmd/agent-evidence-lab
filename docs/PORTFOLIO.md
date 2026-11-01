# Portfolio: useful artifacts and limits

This portfolio records six different engineering questions. It is not a claim that six new products or research breakthroughs have been demonstrated. Each project can be useful as a small case study even when its more ambitious hypothesis is unsupported.

The public project README is authoritative for the exact files and commands included in that package. Results from the earlier local research campaign are identified below as historical context; they are not automatically results of a new run of the extracted public package.

## P01 — A test proposal for memory recovery

**Artifact:** [P01_memory_recovery](../projects/P01_memory_recovery/).

**Useful question.** After a DBOS workflow is interrupted and its backing memory store changes, does recovery use the original journaled snapshot when subsequent compaction removes it from message history?

**Current candidate.** One 153-line test module, based on Pydantic AI commit `d44704ec72744e4fc0bd5a3d5dd877462a24da5b`, with no production changes. A real SQLite DBOS journal and deterministic FunctionModel exercise an in-process BaseException interruption. The test checks PENDING, changes A to B, resumes the same workflow ID, observes three actual compactions and requires one original A snapshot in each subsequent model request, with one store read overall.

The recorded Windows run used DBOS 2.29.0: the candidate and the selected existing recording-dispatch test both passed, with no skips. Bypassing the DBOS capability step made the candidate fail on B while the selected dispatch test passed. The initial mutation run used a base-interpreter child with extra pytest plugins; the baseline used a virtual environment. That historical comparison and its limitation are retained. A subsequent targeted comparison used the same interpreter, environment and37 registered plugin modules in both arms: baseline2 PASS, mutant candidateFAIL on B and selected dispatch fakePASS, no errors/skips. This resolves the environment difference for those targeted outcomes; it does not establish superiority over the complete upstream suite or an OS-process recovery guarantee. See the P01 controlled comparison receipt and logs.

**Strong alternative and prior work.** Pydantic AI already has Memory dispatch tests and a Temporal replay test from [PR10903](https://github.com/pydantic/pydantic-ai/pull/10903). Its DBOS tests already use in-process interruptions. [Issue #11191](https://github.com/pydantic/pydantic-ai/issues/11191) requests additional engine recovery coverage. The candidate composes those established patterns for that requested scenario.

**Limit.** One native integration test plus one recording-dispatch test is not two independent reproductions. The mutation does not show that every existing native DBOS test would miss the defect. There is no new production bug, OS kill/restart, fresh interpreter, Prefect result, full-lock installation or full-suite CI claim. The historical process-restart experiment was a separate artifact and is not substituted for this candidate.

**Next decision.** Publish the illustrative test and ask maintainers whether the in-process boundary is useful. Follow the contributing process for agreement and assignment before a non-trivial PR. Stop polishing or expanding it without a new technical need or maintainer response. Maintainer acceptance remains a separate external event.

## P02 — Audit declared corrections and decisions

**Artifact:** [P02_corrections](../projects/P02_corrections/).

**Useful question.** Can an auditor see which declared downstream decisions were reviewed after an input version changed, and which evidence supports closure?

**Historical result.** The earlier local campaign emitted and read events through the official OpenLineage Python SDK's file transport. It preserved a counter-case in which a registered consumer closes a declared decision while another stale decision remains. A receipt therefore supports a claim about the declared scope, not completeness of real-world dependencies. The extracted public package's own README defines which of these paths it reproduces.

**Strong alternatives and prior work.** PROV, OpenLineage, existing catalogs and application-specific audit records already describe dependencies and versions. [OpenLineage #4484](https://github.com/OpenLineage/OpenLineage/issues/4484) includes prior agent-lineage discussion and a third-party implementation. That is relevant prior work, not a request for this particular package.

**Limit.** Dependency coverage and human audit savings remain unknown. A Python/Node exchange is not evidence of two independent organizations adopting a convention. Historical Windows directory-fsync limitations, single-writer assumptions, and lack of power-loss testing must not become general durability guarantees.

**Next decision.** Use the examples to test one real, authorized audit task against an existing, competently configured lineage stack. Measure instrumentation, review effort, false alerts and missed scope. Stop a standalone product or new protocol effort if an existing profile provides the same evidence at lower total effort. No public outreach is needed merely because an adjacent issue exists.

## P03 — Reproduce a known verifier defect

**Artifact:** [P03_verifier_reproduction](../projects/P03_verifier_reproduction/).

**Useful question.** Does aggregating verifier results by a non-unique name silently discard a distinct failed check?

**Historical result.** On eight constructed states for a public CSM task, the examined main version produced two false successes. The existing PR24 and the local adapter each produced zero. These are selected diagnostic fixtures, not a field error rate or an agent benchmark score. The earlier component test used the actual verifier and task SQL with a SQLite fixture replacing its HTTP service; it did not run the complete gym, an LLM, or an MCP handshake.

**Strong alternative and prior work.** [EnterpriseOps-Gym PR24](https://github.com/ServiceNow/EnterpriseOps-Gym/pull/24) already fixes duplicate result keys. Its discussion also distinguishes lost checks from contradictory task data. A fix that retains all checks cannot decide which contradictory business requirement is intended.

A separate historical comparison detected 17 of 19 unilateral fault families with both a strong contract and the differential approach: no detection gain. Shared defects in reference and candidate can escape their comparison.

**Limit.** Matching two environments is not business correctness. A Python connection guard is not a system sandbox; the publication does not extend its claims to child processes, native connections or all import/setup paths.

**Next decision.** Offer a concise reproduction only if it contributes a useful runnable case to the existing discussion. Do not submit a redundant fix or relabel the known issue as a discovery. Stop when interpreting a task requires an unavailable authorized business specification.

## P04 — Preserve uncertain cost exposure

**Artifact:** [P04_cost_exposure](../projects/P04_cost_exposure/).

**Useful question.** After a timeout, lost response, duplicate callback or delayed settlement, how much budget is known to be spent, still exposed, or reconciled?

**Useful artifact.** A conservative ledger and counter-cases can make uncertainty explicit. An attempt without a final receipt must not disappear from exposure merely because the local caller stopped waiting. The public package's README specifies which accounting and callback paths are actually included.

**Historical result.** The allocation candidate completed 15 of 75 held-out tasks, exactly as many as a simple conditional rule. The 600 historical observations came from two 2024 configurations on 300 tasks. Missing human times, verification durations and logs were not replaced by zeros. These data do not establish a superior optimizer.

**Strong alternative.** The simple conditional rule and native LiteLLM reservation/reconciliation mechanisms are substantive comparators. Executing selected real callback functions with doubles is not the same as testing a running proxy, Redis, PostgreSQL and provider billing. The historical bridge retained uncertainty at the non-atomic boundary between local ledger and upstream counter.

**Limit.** No real invoice reconciliation, complete proxy deployment or human cost reduction is established. Repeated random seeds on the same tasks do not create new independent tasks. Do not tune against an already inspected holdout or choose the baseline after seeing it.

**Next decision.** If a deployment owner identifies a concrete accounting gap, test the actual proxy path with a local provider that charges nothing. A new allocation claim requires a new prospective reserve and complete cost accounting. Stop the optimizer claim on the present tie; publish the negative result and useful accounting cases.

## P05 — Prepare a test dossier and an unexecuted pilot

**Artifact:** [P05_test_dossier](../projects/P05_test_dossier/).

**Useful question.** Can a second operator understand a test record's identity, expected population, limits, missing evidence and outcome without inventing measurements?

**Historical result.** Documentary adapters were checked against synthetic OpenHTF exports. A complete FAIL could be ready for review, and a coherently falsified dossier could still appear ready with a PASS outcome. Hashes did not prove physical origin, instrument calibration or permission to release material.

The earlier radio experiment's descriptive difference interval included zero. Its 643 fragments were not 643 independent incidents. Cost scenarios used assumed human times and did not establish a 20% saving. These historical radio results are not a claim that the public documentary kit includes the radio corpus or reproduces that study.

**Strong alternative.** A competent conventional script is the primary comparator. An agent is optional and would need a separately measured benefit.

**Prepared pilot.** The protocol proposes four development missions and twelve reserve missions, at least three product families, two operators and a separate adjudicator. It is **PREPARED_NOT_RUN**. Forms for real observations must remain blank until such observations occur. Any supplied example answers must be labeled synthetic.

**Limit.** No hardware tests, customer data, willingness to pay, field adoption, physical certification or measured human savings are established. READY_FOR_REVIEW does not authorize material release. Referenced radio data have separate non-commercial/share-alike terms; the repository's MIT license does not relicense them.

**Next decision.** Start only with authorized inputs, established rights and actual operators. Count preparation, review, correction, maintenance, assistance and rejected attempts. Stop on a critical false-ready judgment, fabricated evidence, missing rights, or quality below the conventional control. No service gain should be manufactured from assumed hours.

## P06 — Transfer evidence and unresolved obligations

**Artifact:** [P06_handoff_evidence](../projects/P06_handoff_evidence/).

**Useful question.** When work changes owner, can the receiver distinguish completed, retryable and unresolved obligations from the evidence the provider actually exposes?

**Historical result.** Local provider and runtime cases preserved dangerous examples, including an effect by an old owner after an authentic receipt. Parser regression checks were corrected to pass identical bytes to Python and Node; repeated cases were not counted as additional independent experiments.

Three separate DBOS cases used a cooperative SQLite provider: normal execution, interruption/recovery with lookup, and interruption/recovery with an opaque provider. A workflow could finish while an obligation remained UNKNOWN. Those historical engine tests do not imply that a smaller extracted handoff package reruns DBOS.

**Strong alternatives and prior work.** A conventional queue and journal, provider-side idempotency/lookup, runtime leases and fencing, and existing portable-workflow facilities are the baseline. Classic-to-Handoff-Kit and Classic-to-Classic produced the same result in the examined comparison.

**Limit.** A receipt's authenticity, a workflow's serialization format, and atomic authority enforcement by an external provider are distinct properties. Historical DBOS workflow data used portable_json while step outputs remained py_pickle; that is not cross-SDK checkpoint migration. No hostile federation, 25% human-effort reduction or adoption is established.

**Next decision.** Retain the small handoff dossier if it improves a receiver's understanding of a concrete case. A new SDK or common standard requires repeated unmet interoperability needs and evidence beyond one cooperative implementation. Stop the cross-SDK superiority claim without that evidence.

## Rules for interpreting the portfolio

1. Keep historical observations, package-reproduction checks and future plans visibly separate.
2. Keep the strongest applicable baseline. A known fix, competent script or native mechanism cannot be replaced by a weaker comparator to create a gain.
3. Preserve failed runs and unresolved states. Expected detection of a dangerous condition is not a safety endorsement of the condition.
4. Do not convert fixture counts into independent incidents, tests into users, hashes into authenticity, or issue comments into adoption.
5. Code and the two review passes are AI-assisted internal work. Their agreement is not independent reproduction or external approval.
6. Publication is complete when the stated artifacts are publicly readable and match their recorded version. Scientific novelty, maintainer acceptance, field benefit and commercial viability each require their own evidence.

Original contributions and retained third-party notices have different scopes. In particular, the Pydantic-derived P01 test retains its MIT notice. Source references describe prior work and do not grant rights over any material not actually licensed for redistribution.

