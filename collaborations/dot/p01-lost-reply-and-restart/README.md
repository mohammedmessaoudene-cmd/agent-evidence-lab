# Recover the original result after a lost reply and a client restart

A local client commits an operation identity and request to its SQLite journal before sending the request. A separate fixture commits one inert effect and generates a random 64-byte result. A relay captures and withholds the response until the client exits on timeout. A fresh client resumes from the journal and makes a lookup using the original identity.

| Lookup capability | Client observation | Effects before and after lookup |
|---|---|---|
| Available | `RECOVERED`, all 64 original bytes compared equal | 1 and 1 |
| Unavailable | `OUTCOME_PENDING`, no result file | 1 and 1 |

The evaluator reads the fixture's database and intercepted reply separately. The restart process receives no identifier from the withheld response. Only the initial execution and the subsequent lookup appear on the wire between the local processes. The two cases use an ordinary durable journal and lookup. The provider fixture, transport and operation are local. The experiment covers process exit, and provides no evidence for power loss, concurrent retries, a real provider or a production deployment.

## Reproduce

Run with Python 3.11 or later. The standard library is sufficient. The output directory must be new.

```sh
python -I -B -S reprise.py run fresh
python -I -B -S relire.py fresh
```

The scripts reproduce the two cases and verify the ledger, operation journal, reply bytes, process identities and order of events. Run without Python's optimization flag so assertions are active. The output identities, monotonic timestamps and result bytes are fresh in each run, so their hashes differ across runs. [Observed summary from the Windows run](observed.json)

The [earlier P01 supplement](https://github.com/mohammedmessaoudene-cmd/agent-evidence-lab/tree/a3fd0ea597f763a99c73632813ef92d7e22d0ef5/collaborations/p01-dbos-compatibility-r3) tests snapshot recovery in a different fixture. Arjun Garg's [lost-response and process-restart experiments](https://github.com/arjun2075/mcp-b1-lost-response-repro/tree/1a6bd378e2c337d33c7fc25628eac1f84abc3e55/experimental/retry-recovery) informed the distinction between the two failure conditions. The included implementation uses neither project as an execution dependency.

Original work by Mohammed Messaoudene with AI assistance. [MIT licence](LICENSE)
