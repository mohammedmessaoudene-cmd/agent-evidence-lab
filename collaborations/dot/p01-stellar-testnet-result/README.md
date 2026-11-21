# Recovering a lost Stellar Testnet reply after a client restart

On 21 November 2026, a new client process recovered all **32 original result bytes** from a Stellar Testnet transaction. Its only request was a GET by the transaction hash committed to SQLite before submission. The account history showed **one creation of the test marker** before and after recovery. A classical reader with the same journal and read access recovered the same bytes. [Recorded observations](observed.json) · [Public transaction](https://horizon-testnet.stellar.org/transactions/f18f42a9b4d874a425743d3e88ca1fd960fe4e9920f31e3cd4b438d889e9f470)

| Observation | Ledger through which account history was read | Marker creations |
|---|---:|---:|
| Before submission | 5,841,294 | 0 |
| After commit, before client timeout | 5,841,299 | 1 |
| After recovery in the new process | 5,841,323 | 1 |

Friendbot funded one fresh test account as a separate setup action. The client submitted one synchronous transaction containing a single `manage_data` operation. A local relay captured Horizon’s successful reply 6.126 seconds after the client requested submission. It withheld every response byte until the client timed out at 120.007 seconds and exited. The new process read the journal and looked up the transaction. The evaluator compared the complete decoded `TransactionResult` to the captured original and the classical lookup. The three HTTP JSON bodies also happened to match byte for byte, at 2,751 bytes each. [Confirmation ledger](https://horizon-testnet.stellar.org/ledgers/5841299)

The counter covered successful operations on the dedicated account with the marker’s name, across all transaction hashes. The evaluator also read the stored value and the account’s data effects. It saw one `data_created` and zero updates or removals for that name. The creation and funding of the test account were outside the marker count. Horizon records these result bytes alongside the submitted transaction hash. Another successful `manage_data` transaction can produce identical result bytes. [Operation](https://horizon-testnet.stellar.org/operations/25088188171173889) · [Recorded effects for the operation](https://horizon-testnet.stellar.org/operations/25088188171173889/effects)

## Read-only verification

Run from this directory in a POSIX shell with Python 3. The example sends four HTTPS GET requests to the public Testnet Horizon service. It verifies the committed result, ledger and marker creation while the records are retained.

```sh
python3 - <<'PY'
import base64
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

def get(path):
    with urlopen("https://horizon-testnet.stellar.org" + path, timeout=15) as response:
        return json.load(response)

observed = json.loads(Path("observed.json").read_bytes())
tx = observed["transaction"]
record = get("/transactions/" + tx["hash"])
result = base64.b64decode(record["result_xdr"], validate=True)
assert record["hash"] == tx["hash"] and record["successful"] is True
assert record["ledger"] == tx["confirmation_ledger"] and record["operation_count"] == 1
assert get("/ledgers/" + str(record["ledger"]))["hash"] == tx["confirmation_ledger_hash"]
assert result == base64.b64decode(observed["original_result"]["base64"], validate=True)
assert hashlib.sha256(result).hexdigest() == observed["original_result"]["sha256_decoded"]
op = get("/operations/" + tx["operation_id"])
assert (op["id"], op["transaction_hash"], op["type"], op["name"], op["value"]) == (
    tx["operation_id"], tx["hash"], "manage_data", tx["marker_name"], tx["marker_value_base64"])
effects = get("/operations/" + tx["operation_id"] + "/effects?limit=200")["_embedded"]["records"]
matching = [e for e in effects if e.get("name") == tx["marker_name"]]
assert len(matching) == 1
effect = matching[0]
assert (effect["id"], effect["type"], effect["account"], effect["value"]) == (
    tx["effect_id"], "data_created", record["source_account"], tx["marker_value_base64"])
print(f"Verified {len(result)} result bytes and the recorded marker creation.")
PY
```

Horizon served both the transaction and the indexed effect history. The timeout, process change and withheld bytes were measured on the experiment host. The public reads verify ledger records available at query time. Testnet resets can remove them. This single run gives no basis for a production reliability rate or a performance advantage. [Testnet retention and resets](https://github.com/stellar/stellar-docs/blob/e0625e4f3b900ac52d7a31f07da20f564f753c96/docs/networks/index.mdx) · [Earlier local experiment](https://github.com/mohammedmessaoudene-cmd/agent-evidence-lab/tree/73c39c45779e1e633621bcbacf9afee541d1634e/collaborations/dot/p01-lost-reply-and-restart)

The run used the Stellar Development Foundation’s Go SDK at commit `78e4fe2872d6417ca742264f3b2049c8ff4ab42e` for transaction construction, signing and XDR verification. The SDK is distributed under Apache 2.0. This report and its verification snippet are covered by the repository’s MIT license. Prepared by Mohammed Messaoudene with AI assistance. [SDK source](https://github.com/stellar/go-stellar-sdk/tree/78e4fe2872d6417ca742264f3b2049c8ff4ab42e) · [SDK license](https://github.com/stellar/go-stellar-sdk/blob/78e4fe2872d6417ca742264f3b2049c8ff4ab42e/LICENSE) · [Repository license](../../../LICENSE)
