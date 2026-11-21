# Avery case and interaction observed on isolated CSM

On 21 November 2026, one disposable ServiceNow CSM simulator run executed Oracle task `task_20251208_123126_960_c4ad7a70_f974dae7`, row 35 of the pinned Oracle partition. The task asks for a case and an interaction through its `social` channel and omits the priority. The case policy specifies `moderate` and an initial state of `new`. The tool schema requires a priority, so the client supplied `moderate` explicitly. [Oracle task partition](https://huggingface.co/datasets/ServiceNow-AI/EnterpriseOps-Gym/blob/c8e538eae8a6205294f0a86675fefdc1fac408f6/oracle/csm-00000-of-00001.parquet) · [Pinned source](https://github.com/ServiceNow/EnterpriseOps-Gym/tree/271f2c357f763376997dfd16807fcde2474ae41b)

| Observation | Official case query | Official linked interaction query |
| --- | ---: | ---: |
| Before the business calls | 0 | 0 |
| After one case registration | 1 | 0 |
| After one interaction registration | 1 | 1 |

The service acknowledged case `CS-0001233` and returned native interaction ID `1233`. The interaction request used the case ID from the first response. Separate evaluator requests ran the two exact task SQL queries against the same disposable database. The case query matches the expected case and its priority, state and channel. The interaction query counts exactly one handled interaction linked to that case. The interaction ID comes from the acknowledgement. [Checked workflow and conductors](https://github.com/mohammedmessaoudene-cmd/agent-evidence-lab/tree/b44f1cf732e4c75460ae2879c03c488fda1f3454/collaborations/dot/p03-avery-runtime) · [Execution job](https://github.com/mohammedmessaoudene-cmd/agent-evidence-lab/actions/runs/44872924563/job/136751234063)

The simulator recorded a `social` channel value in its own case and interaction tables. No external social delivery is measured. The SQL results qualify this Avery fixture. The London policy and grader discrepancy is a separate result. [London comparison](../p03-csm-policy-score/README.md)

[receipt.json](receipt.json) is the exact JSON member from the run artifact. Its SHA-256 is `abe303797e65cf137ae1cea9161c4e27c43ff5b7298a611b8da666889b73c781`. The downloaded ZIP matched GitHub's listed SHA-256 `93f2ac9270c5d2e88c102fb8f33af5c7a7fff6a5777e807eb8dd6cad2ef68a4b`.
