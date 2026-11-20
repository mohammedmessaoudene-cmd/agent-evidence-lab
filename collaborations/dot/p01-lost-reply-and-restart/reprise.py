"""Local lost-reply and process-restart witness; use 'run FRESH_OUTPUT_DIRECTORY'."""
import base64
import hashlib
import json
import os
import queue
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from contextlib import closing
from pathlib import Path


SCRIPT = Path(__file__).resolve()
PYTHON = [sys.executable, "-I", "-B", "-S", str(SCRIPT)]
TIMEOUT = 4.0


def require(condition, reason):
    if not condition:
        raise AssertionError(reason)


def emit(data, output=sys.stdout):
    print(json.dumps(data, sort_keys=True), file=output, flush=True)


def store_bytes(path, data):
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_intent(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        (record,) = db.execute("SELECT scope, occurrence, request FROM intent").fetchall()
    return dict(zip(("scope", "occurrence", "request"), record))


def client(action):
    journal = Path("intent.sqlite")
    if action == "start":
        record = ("local-fixture", str(uuid.uuid4()), "record one inert marker")
        with closing(sqlite3.connect(journal)) as db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("CREATE TABLE intent(scope TEXT, occurrence TEXT, request TEXT)")
            db.execute("INSERT INTO intent VALUES (?,?,?)", record)
            db.commit()
        emit({"method": "execute", "intent": read_intent(journal), "pid": os.getpid(),
              "journal_committed_ns": time.perf_counter_ns()})
        inbox = queue.Queue()
        threading.Thread(target=lambda: inbox.put(sys.stdin.buffer.readline()), daemon=True).start()
        try:
            data = inbox.get(timeout=TIMEOUT)
        except queue.Empty:
            emit({"event": "TIMEOUT", "pid": os.getpid(), "at_ns": time.perf_counter_ns()})
            os._exit(36)
        raise ValueError(f"unexpected data or EOF before timeout: {len(data)} bytes")
    require(action == "resume", "unrecognized client command")
    intent = read_intent(journal)
    emit({"method": "lookup", "intent": intent, "pid": os.getpid(),
          "restarted_ns": time.perf_counter_ns()})
    reply = json.loads(sys.stdin.buffer.readline())
    if reply["state"] == "FOUND":
        store_bytes(Path("recovered.bin"), base64.b64decode(reply["result"], validate=True))
        emit({"state": "RECOVERED"})
    else:
        require(reply == {"state": "LOOKUP_UNAVAILABLE"}, "unknown reply")
        emit({"state": "OUTCOME_PENDING"})


def provider(method, availability):
    intent = json.load(sys.stdin)
    key = (intent["scope"], intent["occurrence"], intent["request"])
    with closing(sqlite3.connect("effects.sqlite")) as db:
        if method == "execute":
            db.execute("PRAGMA synchronous=FULL")
            db.execute("CREATE TABLE IF NOT EXISTS effects("
                       "id INTEGER PRIMARY KEY, scope TEXT, occurrence TEXT, request TEXT, result BLOB)")
            original = secrets.token_bytes(64)
            db.execute("INSERT INTO effects(scope,occurrence,request,result) VALUES (?,?,?,?)",
                       (*key, original))
            db.commit()
            reply = {"state": "COMMITTED", "result": base64.b64encode(original).decode("ascii")}
        elif method == "lookup" and availability == "available":
            (row,) = db.execute("SELECT result FROM effects WHERE scope=? AND occurrence=? AND request=?",
                                key).fetchall()
            reply = {"state": "FOUND", "result": base64.b64encode(row[0]).decode("ascii")}
        elif method == "lookup" and availability == "unavailable":
            reply = {"state": "LOOKUP_UNAVAILABLE"}
        else:
            raise ValueError("unrecognized provider command")
    emit({"method": method, "pid": os.getpid(), "completed_ns": time.perf_counter_ns()}, sys.stderr)
    emit(reply)


def inspect_effects(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        rows = db.execute("SELECT id,scope,occurrence,request,result FROM effects ORDER BY id").fetchall()
    return rows


def call_provider(folder, message, availability):
    proc = subprocess.run([*PYTHON, "provider", message["method"], availability], cwd=folder,
                          input=json.dumps(message["intent"]).encode(), capture_output=True,
                          timeout=10, check=True)
    return proc.stdout, json.loads(proc.stderr)


def observe_case(case_dir, availability):
    client_dir = case_dir / "client"
    provider_dir = case_dir / "provider"
    client_dir.mkdir(parents=True)
    provider_dir.mkdir()
    journal = client_dir / "intent.sqlite"
    ledger = provider_dir / "effects.sqlite"
    pipes = dict(stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=client_dir)
    with subprocess.Popen([*PYTHON, "client", "start"], **pipes) as first:
        first_msg = json.loads(first.stdout.readline())
        require(first_msg["pid"] == first.pid and first_msg["method"] == "execute", "start command")
        expected = read_intent(journal)
        require(expected == first_msg["intent"], "durable request prior to effect")
        before_journal = digest(journal.read_bytes())
        response_bytes, commit_event = call_provider(provider_dir, first_msg, availability)
        response = json.loads(response_bytes)
        require(response["state"] == "COMMITTED", "provider did not commit")
        original = base64.b64decode(response["result"], validate=True)
        before = inspect_effects(ledger)
        require(len(before) == 1 and before[0] == (1, expected["scope"], expected["occurrence"],
                expected["request"], original), "original and actual effect count before restart")
        store_bytes(case_dir / "suppressed_response.json", response_bytes)
        dropped_ns = time.perf_counter_ns()
        # Keep stdin open without forwarding the provider's response: a real timed wait.
        require(first.wait(timeout=10) == 36, "first client did not exit after timeout")
        lost_event = json.loads(first.stdout.readline())
        require(lost_event["event"] == "TIMEOUT" and not first.stdout.read() and not first.stderr.read(),
                "unexpected first-client output")
    with subprocess.Popen([*PYTHON, "client", "resume"], **pipes) as second:
        second_msg = json.loads(second.stdout.readline())
        require(second_msg["pid"] == second.pid and second_msg["method"] == "lookup", "restart command")
        require(second_msg["intent"] == expected, "new client did not reuse the complete intent")
        recovery_bytes, lookup_event = call_provider(provider_dir, second_msg, availability)
        out, err = second.communicate(recovery_bytes, timeout=10)
        require(second.returncode == 0 and not err, "recovery process failed")
        resolution = json.loads(out)["state"]
    timeline = [first_msg["journal_committed_ns"], commit_event["completed_ns"], dropped_ns,
                lost_event["at_ns"], second_msg["restarted_ns"], lookup_event["completed_ns"]]
    require(first_msg["pid"] != second_msg["pid"], "client PID reuse")
    require(timeline == sorted(set(timeline)), f"unexpected event ordering: {timeline}")
    after = inspect_effects(ledger)
    require(after == before and before_journal == digest(journal.read_bytes()),
            "effect or pre-saved client intent changed during recovery")
    recovered_file = client_dir / "recovered.bin"
    if availability == "available":
        require(resolution == "RECOVERED" and recovered_file.read_bytes() == original,
                "recovered bytes differ from the original committed result")
    else:
        require(resolution == "OUTCOME_PENDING" and not recovered_file.exists(),
                "resolution must remain pending without provider lookup")
    return {"lookup": availability, "resolution": resolution, "client_intent": expected,
            "intent_sha256_before_and_after": before_journal, "first_client": first_msg,
            "provider_commit": commit_event, "suppressed_reply_at_ns": dropped_ns,
            "timeout_event": lost_event, "first_process_exit": 36, "fresh_client": second_msg,
            "provider_lookup": lookup_event, "second_process_exit": 0,
            "methods_observed": [first_msg["method"], second_msg["method"]],
            "effect_count_before_restart": len(before), "effect_count_after_lookup": len(after),
            "sha256_original_result": digest(original), "original_result_bytes": len(original),
            "sha256_recovered_result": digest(recovered_file.read_bytes()) if recovered_file.exists() else None,
            "full_bytes_compared_equal": True if recovered_file.exists() else None}


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    cases = [observe_case(out / ability, ability) for ability in ("available", "unavailable")]
    receipt = {"verdict": "LOCAL_CONJUNCTION_AND_PENDING_CONTROL_OBSERVED",
               "provider_kind": "local inert SQLite fixture", "transport": "local subprocess pipes",
               "mechanism": "ordinary durable intent and lookup", "observed_cases": cases,
               "script_sha256": digest(SCRIPT.read_bytes()), "python": sys.version.split()[0],
               "event_clock": time.get_clock_info("perf_counter").implementation,
               "actual_external_provider": "NOT_RUN", "power_loss": "NOT_TESTED",
               "boundary": "Trusted local OS, separate client and provider working directories. The client receives the provider reply only on lookup; the evaluator alone reads the ledger and the suppressed reply."}
    store_bytes(out / "RECU.json", (json.dumps(receipt, indent=2) + "\n").encode("utf-8"))
    emit({"verdict": receipt["verdict"], "cases": [case["resolution"] for case in cases]})


if __name__ == "__main__":
    role = sys.argv[1]
    if role == "run":
        run(Path(sys.argv[2]).resolve())
    elif role == "client":
        client(sys.argv[2])
    elif role == "provider":
        provider(sys.argv[2], sys.argv[3])
    else:
        raise ValueError("unknown role")
