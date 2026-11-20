"""Read the two local databases and the intercepted response without running the clients."""
import base64
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path


def rows(path, query):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        return db.execute(query).fetchall()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify(directory):
    receipt_bytes = (directory / "RECU.json").read_bytes()
    receipt = json.loads(receipt_bytes)
    assert receipt["script_sha256"] == sha((Path(__file__).parent / "reprise.py").read_bytes())
    assert [c["lookup"] for c in receipt["observed_cases"]] == ["available", "unavailable"]
    results = []
    for evidence in receipt["observed_cases"]:
        case = directory / evidence["lookup"]
        ledger = case / "provider" / "effects.sqlite"
        journal = case / "client" / "intent.sqlite"
        suppressed = json.loads((case / "suppressed_response.json").read_bytes())
        raw = base64.b64decode(suppressed["result"], validate=True)
        assert suppressed["state"] == "COMMITTED" and len(raw) == 64
        (intent,) = rows(journal, "SELECT scope,occurrence,request FROM intent")
        assert rows(ledger, "SELECT id,scope,occurrence,request,result FROM effects") == [(1, *intent, raw)]
        assert sha(journal.read_bytes()) == evidence["intent_sha256_before_and_after"]
        assert sha(raw) == evidence["sha256_original_result"]
        start, resume = evidence["first_client"], evidence["fresh_client"]
        assert start["intent"] == resume["intent"] == dict(zip(("scope", "occurrence", "request"), intent))
        assert start["method"] == "execute" and resume["method"] == "lookup"
        assert evidence["first_process_exit"] == 36 and evidence["second_process_exit"] == 0
        assert start["pid"] == evidence["timeout_event"]["pid"] and start["pid"] != resume["pid"]
        times = [start["journal_committed_ns"], evidence["provider_commit"]["completed_ns"],
                 evidence["suppressed_reply_at_ns"], evidence["timeout_event"]["at_ns"],
                 resume["restarted_ns"], evidence["provider_lookup"]["completed_ns"]]
        assert all(a < b for a, b in zip(times, times[1:]))
        assert evidence["effect_count_before_restart"] == evidence["effect_count_after_lookup"] == 1
        result = case / "client" / "recovered.bin"
        if evidence["lookup"] == "available":
            assert result.read_bytes() == raw and evidence["resolution"] == "RECOVERED"
        else:
            assert not result.exists() and evidence["resolution"] == "OUTCOME_PENDING"
        results.append({"lookup": evidence["lookup"], "original_bytes": len(raw),
                        "effect_count": 1, "client_pid_before": start["pid"],
                        "client_pid_after": resume["pid"], "state": evidence["resolution"],
                        "recovered_file": result.exists()})
    return {"verified": results, "receipt_sha256": sha(receipt_bytes)}


if __name__ == "__main__":
    if not __debug__:
        raise RuntimeError("assertions must be enabled")
    print(json.dumps(verify(Path(sys.argv[1])), indent=2))
