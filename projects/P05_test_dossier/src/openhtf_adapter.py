"""P05 passive OpenHTF import and documentary review, schema version 2.

Reads real OutputToJSON bytes. Does not import instruments, operate hardware,
authenticate measurements, certify calibration, or authorize material release.
The full original export object is retained; unknown fields stay unknown.
Only the contract's simple scalar in_range profile has automated review here.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any

MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_TIME_MS = 253402300799999  # Last millisecond of year 9999, UTC convention.


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw: bytes | str) -> Any:
    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                raise ValueError("duplicate JSON key: " + key)
            obj[key] = value
        return obj
    def floating(text):
        value = float(text)
        if not math.isfinite(value):
            raise ValueError("nonfinite JSON numeric literal: " + text)
        return value
    return json.loads(raw, object_pairs_hook=pairs, parse_float=floating, parse_constant=lambda value:
                      (_ for _ in ()).throw(ValueError("nonfinite JSON: " + value)))


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def millis(value: Any) -> bool:
    return type(value) is int and 0 <= value <= MAX_TIME_MS


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def problem(code: str, location: str, detail: str) -> dict:
    return {"code": code, "location": location, "detail": detail}


def convert(input_dir: Path | str) -> dict:
    """Normalize each source without filling absent native measurements/metadata.

    Raw objects and raw byte digests are separate from interpreted fields.
    Attachment data stays inline; attachment names never become filesystem paths.
    Errors are documentary issues, not crashes or default-PASS outcomes.
    """
    root = Path(input_dir).resolve()
    packet = {"schema": "p05-openhtf-packet/2", "sources": [], "runs": [],
              "conversion_issues": [], "source_byte_authentication": "NOT_IMPLEMENTED"}
    if not root.is_dir():
        packet["conversion_issues"].append(problem("INPUT_DIRECTORY", "input", "Directory absent"))
        return packet
    paths = sorted(root.glob("*.json"))
    if not paths:
        packet["conversion_issues"].append(problem("NO_EXPORTS", "input", "No JSON exports"))
    for path in paths:
        label = path.name
        try:
            if not path.resolve().is_relative_to(root) or not path.is_file():
                raise ValueError("source path leaves evidence directory")
            if path.stat().st_size > MAX_SOURCE_BYTES:
                raise ValueError("source exceeds 10 MiB import profile")
            raw = path.read_bytes()
            obj = strict_json(raw)
            source = {"file": label, "sha256": sha256(raw), "byte_size": len(raw),
                      "raw_export": copy.deepcopy(obj)}
            packet["sources"].append(source)
            if not isinstance(obj, dict):
                raise ValueError("top-level export must be an object")
            metadata = obj.get("metadata")
            p05 = metadata.get("p05") if isinstance(metadata, dict) else None
            run = {"source_file": label, "source_sha256": source["sha256"],
                   "dut_id": obj.get("dut_id"), "station_id": obj.get("station_id"),
                   "started_at_unix_millis": obj.get("start_time_millis"),
                   "ended_at_unix_millis": obj.get("end_time_millis"),
                   "native_outcome": obj.get("outcome"),
                   "declared_metadata": copy.deepcopy(p05),
                   "metadata": copy.deepcopy(metadata), "phases": []}
            packet["runs"].append(run)
            phases = obj.get("phases")
            if not isinstance(phases, list):
                raise ValueError("phases must be an array")
            for pi, phase in enumerate(phases):
                if not isinstance(phase, dict):
                    raise ValueError("phase must be an object")
                ph = {"index": pi, "name": phase.get("name"),
                      "started_at_unix_millis": phase.get("start_time_millis"),
                      "ended_at_unix_millis": phase.get("end_time_millis"),
                      "native_outcome": phase.get("outcome"),
                      "native_result": copy.deepcopy(phase.get("result")),
                      "measurements": [], "attachments": []}
                run["phases"].append(ph)
                measurements = phase.get("measurements")
                if not isinstance(measurements, dict):
                    raise ValueError("measurements must be an object")
                for key, measure in measurements.items():
                    if not isinstance(measure, dict):
                        raise ValueError("measurement must be an object")
                    ph["measurements"].append({
                        "key": key, "name": measure.get("name"),
                        "value": copy.deepcopy(measure.get("measured_value")),
                        "unit": copy.deepcopy(measure.get("units")),
                        "validators": copy.deepcopy(measure.get("validators")),
                        "dimensions": copy.deepcopy(measure.get("dimensions")),
                        "conditional_validators": copy.deepcopy(measure.get("conditional_validators")),
                        "native_outcome": measure.get("outcome"),
                        "measured_at_unix_millis": measure.get("set_time_millis"),
                        "measured_at_evidence": "EXPORTED_FIELD_UNAUTHENTICATED" if "set_time_millis" in measure else "ABSENT_IN_EXPORT",
                        "allow_fail": measure.get("allow_fail"),
                        "allow_fail_evidence": "EXPORTED_FIELD_UNAUTHENTICATED" if "allow_fail" in measure else "ABSENT_IN_EXPORT",
                        "raw_measurement": copy.deepcopy(measure)})
                attachments = phase.get("attachments")
                if not isinstance(attachments, dict):
                    raise ValueError("attachments must be an object")
                for name, item in attachments.items():
                    if not isinstance(item, dict):
                        raise ValueError("attachment must be an object")
                    att = {"name": name, "phase_index": pi, "phase_name": phase.get("name"),
                           "mime_type": item.get("mimetype"), "native_sha1": item.get("sha1"),
                           "base64_data": item.get("data"), "decoded_size": None,
                           "decoded_sha256": None, "decoded_sha1": None}
                    ph["attachments"].append(att)
                    try:
                        payload = base64.b64decode(item["data"], validate=True)
                        att.update(decoded_size=len(payload), decoded_sha256=sha256(payload),
                                   decoded_sha1=hashlib.sha1(payload).hexdigest())
                    except (KeyError, TypeError, ValueError, binascii.Error):
                        packet["conversion_issues"].append(problem("ATTACHMENT_ENCODING", label + ":" + name,
                                                                  "Inline base64 bytes absent or invalid"))
        except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
            packet["conversion_issues"].append(problem("SOURCE_REJECTED", label, str(exc)))
    return packet


def inspect_contract(contract: Any) -> list[dict]:
    issues = []
    def require(ok, code, detail):
        if not ok:
            issues.append(problem(code, "contract", detail))
    if not isinstance(contract, dict):
        return [problem("CONTRACT_TYPE", "contract", "Expected object")]
    require(contract.get("schema") == "p05-openhtf-contract/2", "CONTRACT_SCHEMA", "Unsupported contract schema")
    require(contract.get("profile") == "SIMPLE_SCALAR_IN_RANGE", "CONTRACT_PROFILE", "Only simple scalar in_range is reviewed")
    for key in ["identity", "work_order", "measurement", "clock_policy", "instrument_policy"]:
        require(isinstance(contract.get(key), dict), "CONTRACT_FIELDS", key + " must be an object")
    if issues:
        return issues
    ident, order, spec = contract["identity"], contract["work_order"], contract["measurement"]
    require(all(nonempty(ident.get(k)) for k in ["product", "board_revision", "firmware_sha256", "procedure_version"]),
            "CONTRACT_IDENTITY", "Four specification identities are required")
    runs = order.get("expected_runs")
    require(isinstance(runs, dict) and bool(runs) and all(nonempty(k) and nonempty(v) for k, v in runs.items())
            and len(set(runs.values())) == len(runs), "CONTRACT_POPULATION", "Unique DUT and run identities required")
    require(all(nonempty(order.get(k)) for k in ["lot_id", "station_id", "evidence_kind"]), "CONTRACT_WORK_ORDER", "Missing work order identity")
    require(all(nonempty(spec.get(k)) for k in ["phase", "name", "instrument_id"]), "CONTRACT_TEST", "Phase, measure and instrument IDs required")
    require(isinstance(spec.get("unit"), dict) and set(spec["unit"]) == {"name", "code", "suffix"}
            and all(nonempty(spec["unit"].get(k)) for k in ["name", "code", "suffix"]),
            "CONTRACT_UNIT", "Full expected unit required")
    require(finite_number(spec.get("lower")) and finite_number(spec.get("upper")) and spec["lower"] <= spec["upper"],
            "CONTRACT_LIMITS", "Finite ordered limits required")
    require(isinstance(spec.get("validators"), list) and len(spec["validators"]) == 1 and nonempty(spec["validators"][0]),
            "CONTRACT_VALIDATORS", "One exact approved validator string required")
    require(spec.get("validators") == [f"{spec.get('lower')} <= x <= {spec.get('upper')}"],
            "CONTRACT_LIMITS_TEXT", "Validator text and numeric approved bounds disagree")
    require(all(nonempty(contract["clock_policy"].get(k)) for k in ["basis", "status"]), "CONTRACT_CLOCK", "Explicit clock declaration policy required")
    require(all(nonempty(contract["instrument_policy"].get(k)) for k in ["id", "serial", "calibration_status"]),
            "CONTRACT_INSTRUMENT", "Instrument identity and declaration policy required")
    require(contract["instrument_policy"].get("id") == spec.get("instrument_id"),
            "CONTRACT_INSTRUMENT_BINDING", "Test and instrument policy disagree")
    attachments = contract.get("required_attachments")
    require(isinstance(attachments, list) and bool(attachments) and all(isinstance(a, dict) and
            all(nonempty(a.get(k)) for k in ["phase", "name", "mimetype", "sha256"]) for a in attachments),
            "CONTRACT_ATTACHMENTS", "Required attachment manifest needed")
    require(contract.get("release_policy") == "NEVER_AUTHORIZE", "CONTRACT_RELEASE", "Passive review cannot authorize release")
    return issues


def review_packet(contract: Any, packet: dict, actual_contract_hash: str,
                  expected_contract_hash: str) -> dict:
    issues = list(packet["conversion_issues"])
    issues += inspect_contract(contract)
    if not expected_contract_hash or actual_contract_hash != expected_contract_hash:
        issues.append(problem("UNTRUSTED_CONTRACT", "contract", "Digest must arrive independently and match bytes"))
    outcomes = []
    replays = 0
    def issue(code, location, detail):
        issues.append(problem(code, location, detail))
    def finish():
        return {"schema": "p05-openhtf-review/2", "status": "INCOMPLETE" if issues else "READY_FOR_REVIEW",
                "measurement_summary": "UNKNOWN" if issues else ("FAIL" if any(x["result"] == "FAIL" for x in outcomes) else "PASS"),
                "material_release_authorized": False, "physical_validation": "NOT_RUN",
                "evidence_authentication": "NOT_IMPLEMENTED", "instrument_equivalence": "NOT_ESTABLISHED",
                "clock_authentication": "UNKNOWN", "calibration_authentication": "UNKNOWN",
                "human_review_time": "NOT_MEASURED", "decision_engine": "DETERMINISTIC_RULES_NOT_AGENT",
                "duplicate_identical_exports": replays, "source_count": len(packet["sources"]),
                "unique_reviewed_run_count": len(outcomes), "outcomes": outcomes, "issues": issues,
                "contract_sha256": actual_contract_hash,
                "scope": "Documentary consistency for a pinned simple scalar profile; declarations and source bytes are unauthenticated"}
    if inspect_contract(contract):
        return finish()
    order, spec = contract["work_order"], contract["measurement"]
    expected = order["expected_runs"]
    seen_hashes, seen_runs, seen_duts = set(), set(), set()
    raw_by_file = {s["file"]: s["raw_export"] for s in packet["sources"]}
    for run in packet["runs"]:
        loc = run["source_file"]
        if run["source_sha256"] in seen_hashes:
            replays += 1
            continue
        seen_hashes.add(run["source_sha256"])
        raw = raw_by_file[loc]
        declared = run["declared_metadata"]
        if not isinstance(declared, dict):
            issue("DECLARATIONS_MISSING", loc, "metadata.p05 object required; no defaults inferred")
            continue
        dut, run_id = run["dut_id"], declared.get("run_id")
        if not nonempty(dut) or dut not in expected or run_id != expected.get(dut):
            issue("DUT_RUN_IDENTITY", loc, "DUT/run differ from independently pinned population")
        if nonempty(dut):
            if dut in seen_duts:
                issue("DUPLICATE_DUT", loc, "Different export bytes for the same expected DUT need adjudication")
            seen_duts.add(dut)
        if not nonempty(run_id) or run_id in seen_runs:
            issue("DUPLICATE_OR_MISSING_RUN", loc, "Missing or reused logical run identity")
        if nonempty(run_id):
            seen_runs.add(run_id)
        if run["station_id"] != order["station_id"]:
            issue("STATION_IDENTITY", loc, "Station differs from work order")
        for key, expected_value in contract["identity"].items():
            if declared.get(key) != expected_value:
                issue("SPECIFICATION_IDENTITY", loc + ":" + key, "Missing or substituted approved identity")
        for key in ["lot_id", "evidence_kind"]:
            if declared.get(key) != order[key]:
                issue("WORK_ORDER_IDENTITY", loc + ":" + key, "Missing or conflicting declaration")
        if declared.get("clock") != contract["clock_policy"]:
            issue("CLOCK_DECLARATION", loc, "Required clock basis declaration absent or conflicting; authenticity remains unknown")
        begin, end = run["started_at_unix_millis"], run["ended_at_unix_millis"]
        valid_time = millis(begin) and millis(end) and 0 < begin <= end
        if not valid_time:
            issue("RUN_TIME", loc, "Finite integer epoch milliseconds ordered within representable range required")
        for field in ["subtests", "branches", "checkpoints", "diagnoses", "diagnosers", "outcome_details"]:
            if raw.get(field):
                issue("UNSUPPORTED_RUN_SEMANTICS", loc + ":" + field, "Retained but outside scalar profile")
        if raw.get("marginal") is not None and (type(raw["marginal"]) is not bool or raw["marginal"]):
            issue("UNSUPPORTED_MARGINAL", loc, "Marginal results require explicit policy")
        instruments = declared.get("instruments")
        inst = None
        if not isinstance(instruments, list) or len(instruments) != 1 or not isinstance(instruments[0], dict):
            issue("INSTRUMENT_DECLARATION", loc, "Exactly one instrument declaration required in this profile")
        else:
            inst = instruments[0]
            for key, expected_value in contract["instrument_policy"].items():
                if inst.get(key) != expected_value:
                    issue("INSTRUMENT_IDENTITY", loc + ":" + key, "Missing/conflicting declared instrument field")
            cf, cu = inst.get("calibration_valid_from_millis"), inst.get("calibration_valid_until_millis")
            if not millis(cf) or not millis(cu) or cf > cu:
                issue("CALIBRATION_UNKNOWN", loc, "Declared validity interval absent/invalid; no authentication inferred")
            elif valid_time and not cf <= begin <= end <= cu:
                issue("CALIBRATION_INTERVAL", loc, "Run falls outside declared interval; measurement instant itself remains unknown")
        if declared.get("measurement_instruments") != {spec["name"]: spec["instrument_id"]}:
            issue("INSTRUMENT_MAPPING", loc, "Measurement-to-instrument declaration differs from contract")
        phases = run["phases"]
        if len(phases) != 1 or phases[0]["name"] != spec["phase"]:
            issue("PHASE_COVERAGE", loc, "Exactly one approved phase required by this profile")
        computed = []
        for ph in phases:
            ploc = loc + ":phase[" + str(ph["index"]) + "]"
            raw_ph = raw["phases"][ph["index"]]
            if raw_ph.get("marginal") is not None and (type(raw_ph["marginal"]) is not bool or raw_ph["marginal"]):
                issue("UNSUPPORTED_MARGINAL", ploc, "Marginal phase or invalid flag needs a separate profile")
            pb, pe = ph["started_at_unix_millis"], ph["ended_at_unix_millis"]
            valid_phase_time = millis(pb) and millis(pe) and pb <= pe
            if not valid_time or not valid_phase_time or not begin <= pb <= pe <= end:
                issue("PHASE_TIME", ploc, "Phase range must fit run; no individual measurement time inferred")
            if ph["native_result"] != {"phase_result": "CONTINUE"}:
                issue("PHASE_CONTROL_FLOW", ploc, "Control flow is not the supported CONTINUE profile")
            for field in ["diagnosers", "diagnosis_results", "failure_diagnosis_results", "subtest_name"]:
                if raw_ph.get(field):
                    issue("UNSUPPORTED_PHASE_SEMANTICS", ploc + ":" + field, "Retained; not interpreted as scalar-only proof")
            ms = ph["measurements"]
            if len(ms) != 1 or ms[0]["key"] != spec["name"] or ms[0]["name"] != spec["name"]:
                issue("MEASUREMENT_COVERAGE", ploc, "Required measurement absent, extra or renamed")
            phase_results = []
            for m in ms:
                mloc = ploc + ":" + str(m["key"])
                native_marginal = m["raw_measurement"].get("marginal")
                if native_marginal is not None and (type(native_marginal) is not bool or native_marginal):
                    issue("UNSUPPORTED_MARGINAL", mloc, "Marginal measurement or invalid flag needs a separate profile")
                if m["unit"] != spec["unit"]:
                    issue("UNIT_MISMATCH", mloc, "Exact unit object required; no implicit scaling")
                if m["validators"] != spec["validators"]:
                    issue("LIMITS_MISMATCH", mloc, "Exported validator strings differ from approved contract; strings are not executed")
                for field in ["dimensions", "conditional_validators"]:
                    if m[field] is not None and (not isinstance(m[field], list) or bool(m[field])):
                        issue("UNSUPPORTED_MEASUREMENT", mloc + ":" + field, "Only null/absent or an empty array is supported in the scalar profile")
                if m["allow_fail"] is not None and (type(m["allow_fail"]) is not bool or m["allow_fail"]):
                    issue("UNSUPPORTED_ALLOW_FAIL", mloc, "Failure override requires another explicit profile")
                mt = m["measured_at_unix_millis"]
                if mt is not None and (not millis(mt) or not valid_phase_time or not pb <= mt <= pe):
                    issue("MEASUREMENT_TIME", mloc, "If exported, measurement timestamp must lie in phase")
                value = m["value"]
                if not finite_number(value):
                    issue("VALUE_TYPE", mloc, "Finite numeric scalar required, not bool or imputed value")
                    continue
                result = "PASS" if spec["lower"] <= value <= spec["upper"] else "FAIL"
                phase_results.append(result)
                if m["native_outcome"] != result:
                    issue("MEASUREMENT_OUTCOME", mloc, "Numeric result disagrees with native measurement outcome")
            expected_phase = "FAIL" if "FAIL" in phase_results else "PASS"
            if not phase_results or ph["native_outcome"] != expected_phase:
                issue("PHASE_OUTCOME", ploc, "Phase outcome differs from complete scalar profile")
            computed.extend(phase_results)
            for att in ph["attachments"]:
                if not nonempty(att["mime_type"]) or att["decoded_sha1"] is None or att["native_sha1"] != att["decoded_sha1"]:
                    issue("ATTACHMENT_INTEGRITY", ploc + ":" + att["name"], "Native SHA1/base64/MIME consistency failed")
        for required in contract["required_attachments"]:
            matches = [a for ph in phases if ph["name"] == required["phase"] for a in ph["attachments"] if a["name"] == required["name"]]
            if len(matches) != 1:
                issue("ATTACHMENT_COVERAGE", loc + ":" + required["name"], "Exactly one attachment in its approved phase required")
            elif matches[0]["mime_type"] != required["mimetype"] or matches[0]["decoded_sha256"] != required["sha256"]:
                issue("ATTACHMENT_CONTENT", loc + ":" + required["name"], "Attachment differs from approved bytes or MIME")
        result = "FAIL" if "FAIL" in computed else "PASS"
        if not computed or run["native_outcome"] != result:
            issue("RUN_OUTCOME", loc, "Run outcome disagrees with scalar-profile outcomes")
        outcomes.append({"dut_id": dut, "run_id": run_id, "result": result,
                         "native_outcome": run["native_outcome"], "source_sha256": run["source_sha256"]})
    if seen_duts != set(expected):
        issue("POPULATION_MISMATCH", "input", "Observed DUT population differs from independently pinned work order")
    return finish()


def review(contract_path: Path | str, expected_contract_sha256: str, input_dir: Path | str,
           packet_out: Path | str | None = None) -> dict:
    packet = convert(input_dir)
    try:
        raw = Path(contract_path).read_bytes()
        contract = strict_json(raw)
        result = review_packet(contract, packet, sha256(raw), expected_contract_sha256)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
        result = {"schema": "p05-openhtf-review/2", "status": "INCOMPLETE", "measurement_summary": "UNKNOWN",
                  "material_release_authorized": False, "physical_validation": "NOT_RUN",
                  "evidence_authentication": "NOT_IMPLEMENTED", "instrument_equivalence": "NOT_ESTABLISHED",
                  "clock_authentication": "UNKNOWN", "calibration_authentication": "UNKNOWN",
                  "issues": packet["conversion_issues"] + [problem("INPUT_REJECTED", "review", str(exc))]}
    if packet_out is not None:
        packet["review"] = result
        Path(packet_out).write_text(json.dumps(packet, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--contract", type=Path, required=True)
    p.add_argument("--expected-contract-sha256", required=True)
    p.add_argument("--input-dir", type=Path, required=True)
    p.add_argument("--out", type=Path)
    p.add_argument("--packet-out", type=Path)
    args = p.parse_args()
    result = review(args.contract, args.expected_contract_sha256, args.input_dir, args.packet_out)
    text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.out:
        args.out.write_text(text)
    print(text, end="")
    return 0 if result["status"] == "READY_FOR_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
