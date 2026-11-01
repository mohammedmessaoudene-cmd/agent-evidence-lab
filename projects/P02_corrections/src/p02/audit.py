"""Read-only audit of correction records, observations, and semantic contracts.

This tool does not discover hidden consumers or prove external execution.
Both sides of semantic comparisons are supplied assertions. The SQLite store,
its replay markers, and optional observations are trusted local evidence inputs.
No database state or R1 engine behavior is modified.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys
import time

from .wire import canonical, digest, integer, public_key, verify, Rejected

FIELDS = ("unit", "window_start", "window_end", "dataset_namespace", "dataset_name")
COMPLETE = {"LOCAL_REPLAY", "ATTESTATION_ONLY"}


def _read_snapshot(store, event_id):
    path = Path(store).resolve()
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("BEGIN")
        fixture_row = db.execute("SELECT value FROM meta WHERE key='fixture'").fetchone()
        if fixture_row is None:
            raise ValueError("Store has no registered fixture")
        fixture = json.loads(fixture_row[0])
        event = db.execute("SELECT id,status,digest FROM events WHERE id=?", (event_id,)).fetchone()
        if event is None:
            raise ValueError("Unknown correction event")
        rows = [dict(r) for r in db.execute(
            "SELECT o.*,r.envelope,r.verification,r.event AS receipt_event,r.decision AS receipt_decision FROM obligations o "
            "LEFT JOIN receipt_log r ON r.id=o.receipt "
            "WHERE o.event=? ORDER BY o.decision", (event_id,))]
        state = [dict(r) for r in db.execute("SELECT id,revision,digest FROM leaves ORDER BY id")]
        db.commit()
        return fixture, dict(event), rows, state
    finally:
        db.close()


def _declared_reads(fixture, decision):
    if decision not in fixture["decisions"]:
        return None
    seen, active, leaves = set(), set(), set()

    def visit(node):
        if node in fixture["leaves"]:
            leaves.add(node)
            return
        if node in active or node not in fixture["nodes"]:
            raise ValueError("Unresolvable declared read graph")
        if node in seen:
            return
        active.add(node)
        for parent in fixture["nodes"][node]["inputs"]:
            visit(parent)
        active.remove(node)
        seen.add(node)

    visit(fixture["decisions"][decision]["node"])
    return leaves


def audit_store(store, event_id, observations=None):
    started = time.perf_counter()
    fixture, event, rows, state = _read_snapshot(store, event_id)
    observations = {} if observations is None else observations
    if type(observations) is not dict or set(observations) - {"observed_reads", "semantic_checks"}:
        raise ValueError("Observations require observed_reads and/or semantic_checks only")
    observed_reads = observations.get("observed_reads", [])
    semantic_checks = observations.get("semantic_checks", [])
    if type(observed_reads) is not list or type(semantic_checks) is not list:
        raise ValueError("Observation collections must be arrays")
    findings = []

    def finding(code, **detail):
        findings.append(dict(code=code, **detail))

    owners = {d["owner"] for d in fixture["decisions"].values()}
    identities = owners | {v["issuer"] for v in fixture["leaves"].values()}
    registry = {name: public_key(name) for name in identities}
    current_leaves = {s["id"]: {"revision": s["revision"], "digest": s["digest"]} for s in state}
    counts = Counter(r["status"] for r in rows)
    verified_assertions, recorded_replays, decision_records = 0, 0, []
    for row in rows:
        verified = False
        if row["status"] in COMPLETE:
            try:
                envelope = json.loads(row["envelope"])
                payload = verify(envelope, registry)
                d = fixture["decisions"][row["decision"]]
                required = {"schema", "event_id", "decision_id", "graph_digest", "cutoff", "policy_digest",
                            "frontier", "score", "outcome", "review"}
                if (type(payload) is not dict or set(payload) != required
                        or payload["schema"] != "p02-review/0.1" or payload["review"] != "REEXAMINED"
                        or type(payload["outcome"]) is not bool):
                    raise ValueError("Invalid review payload")
                integer(payload["score"])
                reads = _declared_reads(fixture, row["decision"])
                expected_frontier = {leaf: current_leaves[leaf] for leaf in reads}
                if (envelope["signer"] != d["owner"] or payload["decision_id"] != row["decision"]
                        or payload["event_id"] != event_id or digest(envelope) != row["receipt"]
                        or payload["graph_digest"] != digest(fixture)
                        or payload["policy_digest"] != digest(d)
                        or payload["cutoff"] != fixture["cutoff"]
                        or canonical(payload["frontier"]) != canonical(expected_frontier)
                        or payload["outcome"] != (payload["score"] >= d["threshold"])
                        or row["receipt_event"] != event_id or row["receipt_decision"] != row["decision"]
                        or row["verification"] != row["status"]):
                    raise ValueError("Receipt record and registered scope disagree")
                verified = True
                verified_assertions += 1
                if row["status"] == "LOCAL_REPLAY":
                    recorded_replays += 1
            except (TypeError, KeyError, ValueError, Rejected) as exc:
                finding("INVALID_RECEIPT_RECORD", decision_id=row["decision"], detail=str(exc))
        decision_records.append({
            "decision_id": row["decision"], "owner": fixture["decisions"][row["decision"]]["owner"],
            "recorded_status": row["status"], "signed_assertion_verified": verified,
            "calculation_evidence": ("LOCAL_DETERMINISTIC_REPLAY_RECORDED" if verified and row["status"] == "LOCAL_REPLAY"
                                     else "SIGNED_ASSERTION_ONLY" if verified else "NOT_ESTABLISHED"),
            "external_action_performed": "UNKNOWN",
        })

    read_comparisons = []
    for item in observed_reads:
        if (type(item) is not dict or set(item) != {"consumer", "decision_id", "leaf_ids"}
                or type(item["consumer"]) is not str or not item["consumer"]
                or type(item["decision_id"]) is not str or not item["decision_id"]
                or type(item["leaf_ids"]) is not list
                or any(type(x) is not str or not x for x in item["leaf_ids"])):
            raise ValueError("Invalid observed read record")
        consumer, decision = item["consumer"], item["decision_id"]
        actual = set(item["leaf_ids"])
        if consumer not in owners:
            finding("UNREGISTERED_CONSUMER_OBSERVED", consumer=consumer, decision_id=decision)
        if decision not in fixture["decisions"]:
            finding("UNREGISTERED_DECISION_BY_REGISTERED_CONSUMER" if consumer in owners
                    else "UNREGISTERED_DECISION_OBSERVED", consumer=consumer, decision_id=decision,
                    observed_leaf_ids=sorted(actual), impact_interpretation="POTENTIALLY_OMITTED_IMPACT")
            declared = None
        else:
            if consumer != fixture["decisions"][decision]["owner"]:
                finding("OBSERVED_DECISION_OWNER_MISMATCH", consumer=consumer, decision_id=decision)
            try:
                declared = _declared_reads(fixture, decision)
            except ValueError as exc:
                declared = None
                finding("UNRESOLVABLE_DECLARED_READS", decision_id=decision, detail=str(exc))
            if declared is not None and actual - declared:
                finding("UNDECLARED_READS_OBSERVED", consumer=consumer, decision_id=decision,
                        observed_undeclared_leaf_ids=sorted(actual - declared),
                        impact_interpretation="POTENTIALLY_OMITTED_IMPACT")
        read_comparisons.append({"consumer": consumer, "decision_id": decision,
                                 "observed_leaf_ids": sorted(actual),
                                 "declared_leaf_ids": sorted(declared) if declared is not None else None})

    semantic_results = []
    for item in semantic_checks:
        if (type(item) is not dict or set(item) != {"decision_id", "input_id", "expected", "observed"}
                or type(item["decision_id"]) is not str or type(item["input_id"]) is not str
                or type(item["expected"]) is not dict or type(item["observed"]) is not dict):
            raise ValueError("Invalid semantic comparison")
        expected, observed = item["expected"], item["observed"]
        if set(expected) - set(FIELDS) or set(observed) - set(FIELDS):
            raise ValueError("Unsupported semantic descriptor; no implicit interpretation")
        missing = [field for field in FIELDS if not isinstance(expected.get(field), str)
                   or not expected.get(field) or not isinstance(observed.get(field), str) or not observed.get(field)]
        different = [field for field in FIELDS if field not in missing and expected[field] != observed[field]]
        try:
            declared_inputs = _declared_reads(fixture, item["decision_id"])
        except ValueError:
            declared_inputs = None
        bound = declared_inputs is not None and item["input_id"] in declared_inputs
        if not bound:
            finding("UNBOUND_SEMANTIC_COMPARISON", decision_id=item["decision_id"], input_id=item["input_id"])
        status = "INCONSISTENT_DECLARATIONS" if different else "UNKNOWN" if missing or not bound else "CONSISTENT_DECLARATIONS_ONLY"
        if different:
            finding("SEMANTIC_CONTRACT_MISMATCH", decision_id=item["decision_id"], input_id=item["input_id"],
                    mismatched_fields=different, expected=expected, observed=observed)
        semantic_results.append({"decision_id": item["decision_id"], "input_id": item["input_id"],
                                 "status": status, "missing_fields": missing, "mismatched_fields": different,
                                 "bound_to_declared_decision_input": bound,
                                 "semantic_truth": "UNKNOWN"})

    done = sum(counts[x] for x in COMPLETE)
    blocked = any(k.startswith(("BLOCKED", "UNKNOWN")) for k in counts)
    recorded_closure = ("NO_REGISTERED_OBLIGATIONS" if not rows else "BLOCKED" if blocked
                        else "CLOSED" if done == len(rows) else "PENDING")
    closure = "UNSUPPORTED_RECORDS" if done > verified_assertions else recorded_closure
    semantic_status = ("INCONSISTENT_DECLARATIONS" if any(x["mismatched_fields"] for x in semantic_results)
                       else "UNKNOWN" if not semantic_results or any(x["status"] == "UNKNOWN" for x in semantic_results)
                       else "CONSISTENT_DECLARATIONS_ONLY")
    return {
        "schema": "p02-local-audit/0.2", "event_id": event_id,
        "event_recorded": True, "event_status": event["status"],
        "declared_snapshot_digest": digest(fixture),
        "known_obligations": {"closure": closure, "recorded_closure": recorded_closure,
                              "total": len(rows), "closed_records": done,
                              "supported_closed_records": verified_assertions,
                              "delivered_records": sum(r["delivered"] for r in rows),
                              "closed_fraction": done / len(rows) if rows else None,
                              "supported_closed_fraction": verified_assertions / len(rows) if rows else None,
                              "counts_by_recorded_status": dict(sorted(counts.items()))},
        "known_obligations_closed": bool(rows) and closure == "CLOSED",
        "actual_decision_coverage": "UNKNOWN", "global_consumer_coverage": "UNKNOWN",
        "signature_evidence": {"verified_assertions": verified_assertions,
                               "meaning": "STATEMENT_AUTHORSHIP_UNDER_PUBLIC_TEST_KEY_REGISTRY"},
        "calculation_evidence": {"local_replays_recorded": recorded_replays,
                                 "scope": "RECORDED_DETERMINISTIC_REPLAY_ON_DECLARED_FIXTURE",
                                 "remote_execution_performed": "UNKNOWN"},
        "external_action_performed": "UNKNOWN", "semantic_truth": "UNKNOWN",
        "semantic_contract_status": semantic_status, "semantic_comparisons": semantic_results,
        "observed_read_comparisons": read_comparisons, "decision_records": decision_records,
        "findings": findings, "findings_count": len(findings),
        "leaf_state_snapshot": state,
        "audit_input_trust": "LOCAL_STORE_AND_SUPPLIED_OBSERVATIONS_NOT_INDEPENDENTLY_ATTESTED",
        "observed_log_completeness": "UNKNOWN", "receipt_replay_by_auditor": "NOT_RUN",
        "elapsed_s": time.perf_counter() - started,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--observations")
    parser.add_argument("--out")
    args = parser.parse_args()
    try:
        if args.out and Path(args.out).exists():
            raise ValueError("Use a fresh output path to preserve audit evidence")
        observations = json.loads(Path(args.observations).read_text(encoding="utf-8")) if args.observations else None
        report = audit_store(args.store, args.event, observations)
        text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.out:
            path = Path(args.out)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return 2 if report["findings"] else 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc), "audit": "NOT_COMPLETED"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
