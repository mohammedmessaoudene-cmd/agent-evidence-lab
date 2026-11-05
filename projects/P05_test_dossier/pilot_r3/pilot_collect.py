#!/usr/bin/env python3
"""P05 passive pilot collection checks and cost arithmetic; Python 3.11+, MIT.

No instruments, agents, network calls, file writes or release authorization.
Proof hashes bind bytes only. Human observations and approvals remain declarations.
"""
import argparse
from collections import Counter
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import sys

SCHEMA = "p05-pilot-collection/1"
HUMAN = ("preparation", "installation", "learning", "mapping", "investigation",
         "review", "correction", "support", "post_transfer_support", "maintenance",
         "arbitration")
CASH = ("licenses", "machine_resources", "capital_calibration", "actual_liability",
        "taxes", "other")
QUALITY = ("false_ready", "false_pass", "unjustified_rejections", "lost_fields",
           "invented_fields", "undetected_inconsistencies", "clarifications", "reworks")
CRITICAL = ("FALSE_READY_IDENTITY", "FALSE_READY_POPULATION", "FALSE_READY_LIMITS",
            "INVENTED_VALUE", "INVENTED_EVIDENCE", "UNAUTHORIZED_INSTRUMENT_ACTION",
            "RIGHTS_MISSING", "SOURCE_MISSING", "OUT_OF_SCOPE_DISCLOSURE")
BAD_QUALITY = QUALITY[:6]
PIN = re.compile(r"^[0-9a-f]{64}$")
MAX_INPUT = 1_000_000
MAX_ARTIFACT = 8_000_000


def nonempty(x):
    return isinstance(x, str) and bool(x.strip())


def uint(x):
    return type(x) is int and 0 <= x <= 10**12


def strict_json(raw):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError("duplicate JSON key: " + k)
            result[k] = v
        return result
    def bad_constant(value):
        raise ValueError("non-finite JSON constant: " + value)
    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                      parse_constant=bad_constant)


def number(value, places=2):
    if value is None:
        return None
    with localcontext() as ctx:
        ctx.prec = 40
        d = Decimal(value.numerator) / Decimal(value.denominator)
        return format(d, ".%df" % places)


def money(minor):
    return number(None if minor is None else minor / 100)


def verify_artifacts(entries, root):
    """Read confined ordinary files; never fetch a URL or follow a symlink."""
    found, errors, rows = {}, [], []
    if not isinstance(entries, list) or not 1 <= len(entries) <= 128:
        return {}, ["artifact list missing or outside 1..128"], []
    for item in entries:
        if not isinstance(item, dict):
            errors.append("artifact is not an object")
            continue
        ident, relative = item.get("id"), item.get("path")
        if not nonempty(ident) or ident in found or not nonempty(relative):
            errors.append("artifact identity/path missing or duplicate")
            continue
        try:
            rel = Path(relative)
            if rel.is_absolute() or ".." in rel.parts or not rel.parts:
                raise ValueError("path must be relative without parent traversal")
            node = root
            for part in rel.parts:
                node = node / part
                if node.is_symlink():
                    raise ValueError("symlink artifact is outside the supported profile")
            path = node.resolve(strict=True)
            path.relative_to(root)
            if not path.is_file() or path.stat().st_size > MAX_ARTIFACT:
                raise ValueError("artifact is not an ordinary bounded file")
            raw = path.read_bytes()
            observed = hashlib.sha256(raw).hexdigest()
            if not uint(item.get("bytes")) or len(raw) != item["bytes"]:
                raise ValueError("byte size differs")
            if item.get("sha256") != observed:
                raise ValueError("SHA256 differs")
            found[ident] = item
            rows.append({"id": ident, "bytes": len(raw), "sha256": observed,
                         "status": "BYTE_IDENTITY_MATCH_NOT_AUTHENTICATION"})
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append("artifact %s: %s" % (ident, str(exc)))
    return found, errors, rows


def cost_book(book, label, artifacts, used_ids):
    """All categories explicitly present; missing coverage stays unknown."""
    errors, seconds, cost = [], 0, Fraction(0)
    if not isinstance(book, dict):
        return None, None, [label + ": cost book missing"]
    events = book.get("human_events")
    cash = book.get("cash_events")
    if not isinstance(events, list) or not isinstance(cash, list):
        return None, None, [label + ": human/cash events missing"]
    by_id, human_categories, cash_categories = {}, set(), set()
    for event in events:
        if not isinstance(event, dict):
            errors.append(label + ": invalid human event")
            continue
        eid, category = event.get("event_id"), event.get("category")
        if not nonempty(eid) or eid in used_ids:
            errors.append(label + ": missing/reused event identity")
        else:
            used_ids.add(eid)
            by_id[eid] = event
        if category not in HUMAN:
            errors.append(label + ": unsupported human category")
        else:
            human_categories.add(category)
        if not nonempty(event.get("actor_id")) or event.get("record_ref") not in artifacts:
            errors.append(label + ": actor/time evidence missing")
        s, rate = event.get("active_seconds"), event.get("hourly_minor")
        if not uint(s) or not uint(rate):
            errors.append(label + ": missing/invalid seconds or hourly cost")
        else:
            seconds += s
            cost += Fraction(s * rate, 3600)
    if human_categories != set(HUMAN):
        errors.append(label + ": human category coverage incomplete")
    for event in cash:
        if not isinstance(event, dict):
            errors.append(label + ": invalid cash event")
            continue
        eid, category = event.get("event_id"), event.get("category")
        if not nonempty(eid) or eid in used_ids:
            errors.append(label + ": missing/reused cash identity")
        else:
            used_ids.add(eid)
        if category not in CASH:
            errors.append(label + ": unsupported cash category")
        else:
            cash_categories.add(category)
        amount = event.get("amount_minor")
        if not uint(amount) or event.get("record_ref") not in artifacts:
            errors.append(label + ": cash amount/evidence missing")
        else:
            cost += amount
    if cash_categories != set(CASH):
        errors.append(label + ": cash category coverage incomplete")
    help_record = book.get("assistance")
    if not isinstance(help_record, dict):
        errors.append(label + ": assistance declaration missing")
    else:
        requests, ids = help_record.get("requests"), help_record.get("event_ids")
        if not uint(requests) or not isinstance(ids, list) or help_record.get("complete") is not True:
            errors.append(label + ": assistance incomplete")
        elif len(ids) != len(set(ids)) or (requests == 0 and ids) or (requests > 0 and not ids):
            errors.append(label + ": assistance/event mapping inconsistent")
        elif any(not isinstance(i, str) or i not in by_id or
                 by_id[i].get("category") not in ("support", "post_transfer_support") or
                 not uint(by_id[i].get("active_seconds")) or by_id[i]["active_seconds"] == 0
                 for i in ids):
            errors.append(label + ": declared help lacks a counted support event")
    for key in ("machine_seconds", "calendar_elapsed_seconds", "waiting_calendar_seconds"):
        if not uint(book.get(key)):
            errors.append(label + ": missing/invalid " + key)
    if book.get("timing_ref") not in artifacts or book.get("collection_complete") is not True:
        errors.append(label + ": incomplete time collection/evidence")
    return (None if errors else cost), (None if errors else seconds), errors


def assess(data, root):
    errors, stops, start_missing = [], [], []
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError("unsupported collection schema")
    synthetic = data.get("evidence_kind") == "SYNTHETIC"
    if data.get("evidence_kind") not in ("SYNTHETIC", "OBSERVED_DECLARATIONS", "TEMPLATE_NOT_AN_OBSERVATION"):
        errors.append("evidence kind invalid")
        start_missing.append("evidence kind invalid")
    if data.get("material_release_authorized") is not False:
        errors.append("material_release_authorized must be false")
        start_missing.append("material release must remain forbidden")
    if data.get("evidence_kind") == "TEMPLATE_NOT_AN_OBSERVATION":
        start_missing.append("template is not a completed starting dossier")
    mode = data.get("scope")
    if mode not in ("SYNTHETIC_PAIR", "FULL_PILOT") or (mode == "SYNTHETIC_PAIR" and not synthetic):
        errors.append("scope invalid; pair scope is synthetic only")
        start_missing.append("scope invalid")
    artifacts, artifact_errors, artifact_rows = verify_artifacts(data.get("artifacts"), root)
    errors += artifact_errors
    if artifact_errors:
        stops.append("EVIDENCE_INTEGRITY_UNRESOLVED")
    m = data.get("manifest")
    if not isinstance(m, dict):
        raise ValueError("manifest missing")
    currency = m.get("currency")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        errors.append("currency must be one declared three-letter code")
        start_missing.append("declared currency")
    if m.get("minor_units_per_unit") != 100:
        errors.append("this limited currency profile requires 100 minor units per unit")
        start_missing.append("unsupported monetary unit profile")
    roles = m.get("roles", {})
    if not isinstance(roles, dict):
        roles = {}
    a, b, arb, guardian = (roles.get(k) for k in ("operator_A", "operator_B", "arbiter", "guardian"))
    if not all(nonempty(x) for x in (a, b, arb, guardian)) or a == b or arb in (a, b) or guardian in (a, b):
        start_missing.append("two distinct operators; distinct arbiter/guardian from operators")
    approvals = m.get("approvals", {})
    if not isinstance(approvals, dict):
        approvals = {}
    for key in ("pilot_authorization_ref", "data_rights_ref", "comparison_plan_ref", "freeze_ref"):
        if approvals.get(key) not in artifacts:
            start_missing.append(key)
    rights = m.get("data_rights", {})
    if not isinstance(rights, dict):
        rights = {}
    for key in ("owner_id", "use_basis", "private_destination", "retention_decision"):
        if not nonempty(rights.get(key)):
            start_missing.append("data_rights." + key)
    for flag in ("equal_information_tools_rights_budget", "outputs_hidden_between_operators",
                 "independent_contract_approval", "reserve_answers_hidden", "freeze_before_reserve"):
        if m.get(flag) is not True:
            start_missing.append(flag)
    pins = m.get("code_sha256", {})
    if not isinstance(pins, dict) or any(not isinstance(pins.get(method), str) or not PIN.fullmatch(pins[method])
                                         for method in ("A0", "A1")):
        start_missing.append("both code pins")
        pins = {} if not isinstance(pins, dict) else pins
    if m.get("shared_cost_allocation") != "EQUAL_SPLIT_PREDECLARED":
        errors.append("shared costs need the explicit predeclared equal-split convention")
        start_missing.append("predeclared shared-cost convention")
    if approvals.get("shared_allocation_ref") not in artifacts:
        errors.append("shared-allocation reference missing")
        start_missing.append("shared-allocation approval reference")
    if m.get("cost_window_closed") is not True or m.get("support_followup_closed") is not True:
        errors.append("cost/support observation window not closed")
    jobs = m.get("missions")
    if not isinstance(jobs, list) or not 1 <= len(jobs) <= 16:
        raise ValueError("expected 1..16 declared missions; field plan requires exactly16")
    ids, phases, families, reserve, job_map = set(), Counter(), set(), [], {}
    expected = {}
    for job in jobs:
        if not isinstance(job, dict):
            raise ValueError("mission must be an object")
        jid, phase, family = job.get("job_id"), job.get("phase"), job.get("family_id")
        if not nonempty(jid) or jid in ids:
            errors.append("mission identity missing/duplicate")
            start_missing.append("mission identity missing/duplicate")
            continue
        ids.add(jid); job_map[jid] = job; phases[phase] += 1
        if phase not in ("DEVELOPMENT", "RESERVE") or not nonempty(family):
            start_missing.append(jid + ": phase/family")
        if nonempty(family):
            families.add(family)
        if phase == "RESERVE":
            reserve.append(job)
        sources = job.get("input_artifact_ids")
        if not isinstance(sources, list) or not sources or any(x not in artifacts for x in sources):
            errors.append(jid + ": input evidence missing")
            start_missing.append(jid + ": input evidence missing")
        if job.get("contract_ref") not in artifacts or job.get("contract_approval_ref") not in artifacts:
            errors.append(jid + ": independently approved contract reference missing")
            start_missing.append(jid + ": independently approved contract reference missing")
        if (not isinstance(job.get("operators"), dict)
                or set(job["operators"]) != {"A0", "A1"}
                or not all(nonempty(v) for v in job["operators"].values())
                or set(job["operators"].values()) != {a, b}):
            start_missing.append(jid + ": operator assignment")
        if job.get("first_method") not in ("A0", "A1"):
            start_missing.append(jid + ": first method missing")
        ex = job.get("expected_attempt_ids")
        if not isinstance(ex, dict):
            errors.append(jid + ": attempt register missing")
            ex = {}
        for method in ("A0", "A1"):
            entry = ex.get(method)
            if not isinstance(entry, list) or not entry or any(not nonempty(x) for x in entry):
                errors.append(jid + ": complete attempt register missing for " + method)
                entry = []
            expected[(jid, method)] = entry
    if len(jobs) != 16 or phases != Counter({"DEVELOPMENT": 4, "RESERVE": 12}) or len(families) < 3:
        start_missing.append("full field plan: 4 development +12 reserve and at least3 families")
    if len(reserve) == 12:
        if Counter(j.get("first_method") for j in reserve) != Counter({"A0": 6, "A1": 6}):
            start_missing.append("reserve first-method balance 6/6")
        for method in ("A0", "A1"):
            counts = Counter(j.get("operators", {}).get(method) for j in reserve)
            if counts != Counter({a: 6, b: 6}):
                start_missing.append("reserve operator balance 6/6 for " + method)
    # Pair controls waive only the 16-mission population, never fair-comparison
    # declarations, role separation, approvals, evidence or source identity.
    for item in start_missing:
        if mode == "FULL_PILOT" or not item.startswith("full field plan:"):
            errors.append("start prerequisite: " + item)
    if data.get("evidence_kind") == "TEMPLATE_NOT_AN_OBSERVATION":
        errors.append("template is not an observation")
    if m.get("unpriced_obligations") != []:
        errors.append("unpriced or undeclared cost obligations remain")
    records = data.get("records")
    if not isinstance(records, list) or len(records) > 256:
        raise ValueError("records must be a bounded list")
    used_events, used_attempts = set(), set()
    direct = {"A0": Fraction(0), "A1": Fraction(0)}
    complete = {"A0": True, "A1": True}
    phase_cost = {p: {method: Fraction(0) for method in direct} for p in ("DEVELOPMENT", "RESERVE")}
    human_seconds = {method: 0 for method in direct}
    qtot = {method: Counter() for method in direct}
    observed_attempts, last_outcome, record_rows = {}, {}, []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("record must be an object")
        jid, method, aid = (record.get(k) for k in ("job_id", "method", "attempt_id"))
        if jid not in job_map or method not in direct or not nonempty(aid) or aid in used_attempts:
            errors.append("unknown mission/method or missing/duplicate attempt identity")
            continue
        used_attempts.add(aid)
        observed_attempts.setdefault((jid, method), []).append(aid)
        job = job_map[jid]
        if record.get("operator_id") != job.get("operators", {}).get(method):
            errors.append(aid + ": operator differs from frozen assignment")
        if record.get("input_artifact_ids") != job.get("input_artifact_ids") or record.get("contract_ref") != job.get("contract_ref"):
            errors.append(aid + ": inputs/contract differ from frozen paired inputs")
        if record.get("code_sha256") != pins.get(method):
            errors.append(aid + ": method code pin differs")
        value, seconds, book_errors = cost_book(record.get("cost"), aid, artifacts, used_events)
        errors += book_errors
        if value is None:
            complete[method] = False
        else:
            direct[method] += value
            human_seconds[method] += seconds
            if job.get("phase") in phase_cost:
                phase_cost[job["phase"]][method] += value
        quality = record.get("quality")
        if not isinstance(quality, dict):
            errors.append(aid + ": quality arbitration missing")
            quality = {}
        if quality.get("arbiter_id") != arb or quality.get("blind_before_times") is not True or quality.get("record_ref") not in artifacts:
            errors.append(aid + ": independent blinded arbitration declaration missing")
        if quality.get("documentary_state") not in ("READY_FOR_REVIEW", "INCOMPLETE") or quality.get("measurement_state") not in ("PASS", "FAIL", "UNKNOWN"):
            errors.append(aid + ": documentary/measurement state missing")
        outcome = quality.get("outcome")
        if outcome not in ("RECEIVED", "REJECTED", "ABANDONED"):
            errors.append(aid + ": terminal outcome missing")
        if outcome in ("REJECTED", "ABANDONED") and not nonempty(quality.get("reason")):
            errors.append(aid + ": refusal/abandon reason missing")
        if outcome == "RECEIVED" and quality.get("documentary_state") != "READY_FOR_REVIEW":
            errors.append(aid + ": received dossier declared incomplete")
        last_outcome[(jid, method)] = outcome
        for key in QUALITY:
            if not uint(quality.get(key)):
                errors.append(aid + ": quality count missing: " + key)
            else:
                qtot[method][key] += quality[key]
        findings = quality.get("critical_findings")
        if not isinstance(findings, list) or any(x not in CRITICAL for x in findings):
            errors.append(aid + ": critical-finding declaration missing/invalid")
        elif findings:
            stops += [method + ":" + str(x) for x in findings]
        if uint(quality.get("invented_fields")) and quality["invented_fields"] > 0:
            stops.append(method + ":INVENTED_VALUE_OR_FIELD")
        record_rows.append({"attempt_id": aid, "job_id": jid, "method": method,
                            "cost": money(value), "cost_status": "UNKNOWN" if value is None else "COMPLETE_DECLARATION",
                            "human_active_seconds": seconds, "outcome": outcome,
                            "machine_seconds": record.get("cost", {}).get("machine_seconds") if isinstance(record.get("cost"), dict) else None,
                            "calendar_elapsed_seconds": record.get("cost", {}).get("calendar_elapsed_seconds") if isinstance(record.get("cost"), dict) else None,
                            "waiting_calendar_seconds": record.get("cost", {}).get("waiting_calendar_seconds") if isinstance(record.get("cost"), dict) else None,
                            "included_even_if_rejected_or_abandoned": True})
    for key, attempts in expected.items():
        if observed_attempts.get(key, []) != attempts or not attempts:
            errors.append("attempt population/order differs: " + str(key))
            complete[key[1]] = False
    shared, shared_seconds, shared_errors = cost_book(data.get("shared_cost"), "SHARED", artifacts, used_events)
    errors += shared_errors
    full = {method: (direct[method] + shared / 2 if complete[method] and shared is not None else None)
            for method in direct}
    received = {method: sorted(jid for jid in ids if last_outcome.get((jid, method)) == "RECEIVED") for method in direct}
    comparable = not errors and all(value is not None for value in full.values())
    utility = bool(received["A0"]) and received["A0"] == received["A1"]
    quality_ok = all(qtot["A1"][key] <= qtot["A0"][key] for key in BAD_QUALITY)
    gain = None
    gain_reasons = []
    if not comparable:
        gain_reasons.append("COSTS_OR_COMPARISON_INCOMPLETE")
    if full["A0"] is None or full["A0"] <= 0:
        gain_reasons.append("CONTROL_COST_NOT_POSITIVE")
    if not utility:
        gain_reasons.append("NO_MATCHED_NONEMPTY_RECEIVED_JOB_SET")
    if not quality_ok:
        gain_reasons.append("QUALITY_BELOW_CONTROL")
    if stops:
        gain_reasons.append("CRITICAL_STOP_OR_UNRESOLVED_INTEGRITY")
    if not gain_reasons:
        gain = 100 * (full["A0"] - full["A1"]) / full["A0"]
    return {
        "schema": "p05-pilot-assessment/1", "evidence_kind": data.get("evidence_kind"),
        "scope": mode, "field_pilot_status": "PREPARED_NOT_RUN" if synthetic or data.get("evidence_kind") == "TEMPLATE_NOT_AN_OBSERVATION" else "SUPPLIED_OBSERVATIONS_NOT_AUTHENTICATED",
        "material_release_authorized": False,
        "assessment_status": "STOP" if stops else ("UNKNOWN" if gain_reasons else "COMPLETE_DECLARATION"),
        "documentary_start_gate": "SYNTHETIC_NOT_ELIGIBLE" if synthetic else ("BLOCKED_INPUTS" if start_missing or artifact_errors else "DECLARATIONS_COMPLETE_HUMAN_SIGNOFF_REQUIRED"),
        "start_missing": sorted(set(start_missing)), "currency": currency,
        "direct_method_cost": {k: money(v) if complete[k] else None for k, v in direct.items()},
        "development_direct_cost": {k: money(v) if complete[k] else None for k, v in phase_cost["DEVELOPMENT"].items()},
        "reserve_direct_cost": {k: money(v) if complete[k] else None for k, v in phase_cost["RESERVE"].items()},
        "shared_cost": money(shared), "shared_human_seconds": shared_seconds,
        "comparison_cost_including_half_shared": {k: money(v) for k, v in full.items()},
        "savings_pct": number(gain, 6), "savings_status": "UNKNOWN" if gain is None else ("SYNTHETIC_ARITHMETIC_ONLY" if synthetic else "DESCRIPTIVE_DECLARED_COSTS_ONLY"),
        "savings_unknown_reasons": gain_reasons,
        "twenty_percent_claim": "NOT_ESTABLISHED",
        "quality_counts_all_attempts": {k: dict(v) for k, v in qtot.items()},
        "received_job_ids": received, "assigned_jobs": len(jobs), "attempt_records": len(records),
        "record_costs": record_rows, "errors": sorted(set(errors)), "stop_reasons": sorted(set(stops)),
        "artifact_identity": artifact_rows,
        "limits": ["Hash identity is not authenticity, calibration, rights or human approval.",
                   "Declared absence of omitted attempts/help cannot prove that none was omitted.",
                   "Human sums, machine time and calendar duration may overlap; they are not added together.",
                   "All development costs are counted once; no setup amortization or travel saving is inferred.",
                   "A complete measured FAIL can be received. A coherent forgery can pass documentary checks.",
                   "No population inference, independent validation, commercial demand or agent advantage."]
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--artifact-root", type=Path)
    args = parser.parse_args()
    raw = b""
    try:
        if args.input.stat().st_size > MAX_INPUT:
            raise ValueError("input exceeds finite collection limit")
        raw = args.input.read_bytes()
        root = (args.artifact_root or args.input.parent).resolve(strict=True)
        report = assess(strict_json(raw), root)
        code = 3 if report["stop_reasons"] else 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError, RuntimeError) as exc:
        report = {"schema": "p05-pilot-assessment/1", "assessment_status": "INVALID_INPUT",
                  "field_pilot_status": "NOT_ESTABLISHED", "savings_pct": None,
                  "savings_status": "UNKNOWN", "material_release_authorized": False,
                  "error_type": type(exc).__name__, "error": str(exc)}
        code = 2
    report["input_sha256"] = hashlib.sha256(raw).hexdigest() if raw else None
    report["calculator_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    print(json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
