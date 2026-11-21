# Observing a persistent product update in EnterpriseOps-Gym CSM

The official synthetic CSM case starts product **40** at location **817** with status `in_use`. On 21 November 2026, one call to the documented `update_installed_product_details` tool moved it to location **692**. A second MCP client instance read back location 692 and status `in_use` from the same live database. The corresponding official SQL verifier returned **1**. The server's 89 tools matched the public NVIDIA catalog in order and in full record content. [Completed job](https://github.com/mohammedmessaoudene-cmd/agent-evidence-lab/actions/runs/44854268191/job/136692631222) · [Exact observed receipt](observed.json)

| Observation | Recorded value |
|---|---|
| Read by the first client before the update | 40 / 817 / `in_use` |
| Number of update requests | 1 |
| Acknowledged tool reply | 40 / 692 / `in_use` |
| Read using a second client instance | 40 / 692 / `in_use` |
| Official count for the requested state | 1 |
| Served tools matching the public reference | 89 / 89 |

## Reproduction and evidence identity

The experiment recipe is retained at Git commit `7fa4e35345bb3501bf48a29e96867d0ff2ebfdb1`. The one-off workflow uses a GitHub-hosted Ubuntu 24.04 runner. After it verifies the public inputs, the pinned CSM container runs without network access or published ports. The client and service communicate on container loopback, and the workflow removes the container after collecting the receipt. The branch and parent conditions limit the recorded run to the intended execution. To repeat in another authorized isolated runner, use the same preparation, container, exercise and receipt collection steps at the pinned recipe. [Workflow](https://github.com/mohammedmessaoudene-cmd/agent-evidence-lab/blob/7fa4e35345bb3501bf48a29e96867d0ff2ebfdb1/.github/workflows/dot-p03-runtime.yml) · [Experiment code](https://github.com/mohammedmessaoudene-cmd/agent-evidence-lab/tree/7fa4e35345bb3501bf48a29e96867d0ff2ebfdb1/collaborations/dot/p03-csm-runtime)

The CSM image digest is `sha256:eaa456ac9aa85728426e7d3813a0bbca0949d6a8695be30e26f03894e6e6b189`. The initial SQL fixture has SHA-256 `71c8e714b920a0f67abd16f06c29818284b741608e0fa3f1a28c1f331aa9e6dc`. The GitHub artifact ZIP records SHA-256 `adcbad3812e84dfbc097f216ed3119e54372645e2dbb4f637571e0e9f92c1c85`. Its only member is preserved byte-for-byte as `observed.json`, SHA-256 `c3d7b9798ad046469402dc4a463eb50296a5b6055c22d85cfa54e5c5e05968e4`. [Official case](https://github.com/ServiceNow/EnterpriseOps-Gym/blob/271f2c357f763376997dfd16807fcde2474ae41b/data/revised/csm/task_20251205_154853_044_d4a463c3_fce76046.json) · [NVIDIA catalog](https://huggingface.co/datasets/nvidia/NeMo-Gym-EnterpriseOps-Assets/blob/8918dc64b8575d5ff476e62e1cc3687523ab59c2/enterpriseops_gym/tools/csm.json) · [Workflow run and artifact](https://github.com/mohammedmessaoudene-cmd/agent-evidence-lab/actions/runs/44854268191)

The result covers an ordinary product update and persisted state observed by two clients in one live simulator instance. Durability across service restart, the larger notification task, changes to other records and transfer to a real enterprise environment remain untested. ServiceNow's fixture and client and NVIDIA's catalog were fetched from their original repositories for this experiment. The supplement preserves the observation, and the original sources keep their upstream terms.
