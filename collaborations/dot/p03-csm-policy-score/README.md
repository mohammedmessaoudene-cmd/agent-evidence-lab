# The default case priority changes one EnterpriseOps-Gym check

Three of the four official database checks accept a hypothetical completed London relocation with the policy's default ticket priority, `moderate`. All four accept the same end state with priority `low`. Across 10,619 rows in 17 tables, the two states differ in exactly one cell. The reference task asks for a device move, continued operation and notifications to account contacts. It does not specify a ticket priority. The conflict concerns the task's built-in default and its second SQL check. [ServiceNow task and policy](https://github.com/ServiceNow/EnterpriseOps-Gym/blob/271f2c357f763376997dfd16807fcde2474ae41b/data/revised/csm/task_20251205_154853_044_d4a463c3_fce76046.json) · [Measured counts](observed.json)

| State tested offline | Device | Ticket | First contact | Second contact |
|---|---:|---:|---:|---:|
| Original fixture | 0 | 0 | 0 | 0 |
| Only the previously observed device move represented | 1 | 0 | 0 | 0 |
| Completed hypothetical records, default priority `moderate` | 1 | 0 | 1 | 1 |
| Same records, priority `low` | 1 | 1 | 1 | 1 |

Each cell is the integer returned by one unchanged query in file order. Each verifier asks for a count of one. The last two columns describe database records for the two account contacts. This comparison made zero service calls. The earlier isolated CSM job actually moved the device, read it back using a second client and ran the first official check. It did not run the three ticket and notification checks. [Earlier CSM run](https://github.com/mohammedmessaoudene-cmd/agent-evidence-lab/actions/runs/44854268191/job/136692631222)

## Reproduce the comparison

Use the task JSON and its named SQL fixture from ServiceNow commit `271f2c357f763376997dfd16807fcde2474ae41b`. Check their SHA-256 digests against the observation. The SQL file contains inserts for 17 tables. For this comparison, create those tables in SQLite memory from their insert column lists, using integer affinity on identifier columns, text affinity elsewhere and the first identifier as the primary key. Load all 10,616 rows. This models end-state data without simulating service transitions. [Task JSON](https://github.com/ServiceNow/EnterpriseOps-Gym/blob/271f2c357f763376997dfd16807fcde2474ae41b/data/revised/csm/task_20251205_154853_044_d4a463c3_fce76046.json) · [Fixture archive](https://github.com/ServiceNow/EnterpriseOps-Gym/blob/271f2c357f763376997dfd16807fcde2474ae41b/gym_dbs.zip)

1. Evaluate the untouched fixture, then a copy with installed product 40 moved from location 817 to 692, keeping `in_use`.
2. In the copy, represent one hypothetical closed `alert` ticket numbered by database ID 1233, belonging to account 8, primary contact 10, product 25 and installed product 40. Set its priority to `moderate`. Represent one `update` notification for that ticket for each of the two active contacts of account 8. Obtain the addresses by joining the contacts' portal user identifiers to their active user rows.
3. Clone that entire state. Change only `customer_case.priority` for ticket 1233 to `low`. Compare the corresponding rows by primary key across all tables and verify the one-cell difference.
4. For each of the four states, open a read-only scoring connection and evaluate the following expression. The result is a vector of four counts. The observation also records the SHA-256 of each query's original UTF-8 text.

```python
counts = [connection.execute(v["validation_config"]["query"]).fetchone()[0]
          for v in task["verifiers"]]
```

The task, policy, queries and seed data come from ServiceNow's EnterpriseOps-Gym repository under Apache License 2.0. The Dot laboratory produced the comparison and aggregate observation. [Upstream license](https://github.com/ServiceNow/EnterpriseOps-Gym/blob/271f2c357f763376997dfd16807fcde2474ae41b/LICENSE)
