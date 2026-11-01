#!/usr/bin/env python3
"""Post-hoc internally reviewed counterexamples for P05 R2; no hardware or network.

Each run directory is new and contains pre-execution expectations, both source
inputs, native command output, and result summaries. Never overwrites a round.
Mutations of real framework exports are explicitly not fresh framework output.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()


def cases():
    # Expectations fixed in this file before execution, after source-code review.
    return [
        ("control_pass", "READY_FOR_REVIEW", "PASS", "Unchanged native PASS exports"),
        ("control_fail", "READY_FOR_REVIEW", "FAIL", "Unchanged complete native FAIL exports"),
        ("coherent_forgery", "READY_FOR_REVIEW", "PASS", "Source value and corresponding free-text log changed consistently; document-only acceptance expected; authentication must remain absent"),
        ("json_exponent_overflow", "INCOMPLETE", "UNKNOWN", "Legal JSON numeric exponent overflows Python float; both review and packet serialization must fail closed without crashing"),
        ("contradictory_contract_bounds", "INCOMPLETE", "UNKNOWN", "Externally supplied digest matches a contract whose numerical upper bound disagrees with its validator string"),
        ("allow_fail_integer_zero", "INCOMPLETE", "UNKNOWN", "Boolean runtime override supplied as integer zero; unsupported/malformed metadata must not be silently treated as False"),
        ("dimensions_boolean_false", "INCOMPLETE", "UNKNOWN", "Native dimensional descriptor is a boolean, not an absent/list descriptor"),
        ("conditional_validators_integer_zero", "INCOMPLETE", "UNKNOWN", "Conditional validators encoded as zero instead of a list or missing value"),
        ("checkpoint_extra", "INCOMPLETE", "UNKNOWN", "Additional checkpoint semantics outside the declared scalar profile"),
        ("outcome_details_nonempty", "INCOMPLETE", "UNKNOWN", "Additional outcome details conflict with treating this as an unqualified scalar profile"),
        ("marginal_true", "INCOMPLETE", "UNKNOWN", "Marginal result requires a policy absent from this profile"),
        ("phase_result_extra_exception", "INCOMPLETE", "UNKNOWN", "Phase result contains additional exception semantics alongside CONTINUE"),
        ("deep_json_nesting", "CAPACITY_DEPENDENT", "CAPACITY_DEPENDENT", "At 1100 nested arrays this runtime can parse safely, but full-object copy may reach its own limit: structured READY/PASS or INCOMPLETE/UNKNOWN is acceptable, with no release or authentication"),
        ("deep_json_parser_limit", "INCOMPLETE", "UNKNOWN", "10000 nested arrays exceed this runtime's JSON parser recursion limit; structured rejection is required"),
        ("exported_measurement_time_outside", "INCOMPLETE", "UNKNOWN", "If a measurement timestamp is supplied, a timestamp outside its phase is inconsistent"),
        ("calibration_covers_phase_only", "INCOMPLETE", "UNKNOWN", "Scope clarification: full declared run interval, not only phase interval, is required by the candidate's conservative profile"),
        ("valid_exported_measurement_time", "READY_FOR_REVIEW", "PASS", "A provided integer timestamp within its phase is retained as an unauthenticated claim"),
        ("false_override_empty_lists", "READY_FOR_REVIEW", "PASS", "Boolean false and empty descriptor lists are accepted controls for the malformed falsy-value fixes"),
        ("phase_marginal_true", "INCOMPLETE", "UNKNOWN", "Phase declares a marginal result while run remains nonmarginal; not supported by scalar profile"),
        ("measurement_marginal_true", "INCOMPLETE", "UNKNOWN", "Measurement declares marginality outside scalar profile"),
        ("phase_marginal_integer_zero", "INCOMPLETE", "UNKNOWN", "Marginality metadata must use Boolean false/null, not integer zero"),
        ("run_marginal_integer_zero", "INCOMPLETE", "UNKNOWN", "Run marginality encoded as integer zero is not Boolean false"),
    ]


def prepare(out, selected=None, historical_depth_oracle=False):
    out.mkdir(parents=True, exist_ok=False)
    pristine_contract = (ROOT / "protocol/contract.json").read_bytes()
    first = "P05-DEMO-001.json"
    definitions = []
    for name, status, summary, detail in cases():
        if selected is not None and name not in selected:
            continue
        if name == "deep_json_nesting" and historical_depth_oracle:
            status, summary = "INCOMPLETE", "UNKNOWN"
            detail = "Historical oracle, later recognized as too strict: required structured rejection even though this runtime safely parses the inert note"
        folder = out / "cases" / name
        inputs = folder / "input"
        inputs.mkdir(parents=True)
        original_dir = ROOT / "runtime/exports" / ("fail" if name == "control_fail" else "pass")
        for source in sorted(original_dir.glob("*.json")):
            (inputs / source.name).write_bytes(source.read_bytes())
        contract = json.loads(pristine_contract)
        target = inputs / first
        record = json.loads(target.read_bytes())
        measurement = record["phases"][0]["measurements"]["voltage"]
        if name == "coherent_forgery":
            measurement["measured_value"] = 3.31
            for log in record["log_records"]:
                log["message"] = log["message"].replace("3.3 V", "3.31 V")
            target.write_bytes(encode(record))
        elif name == "json_exponent_overflow":
            target.write_bytes(target.read_bytes().replace(b'"measured_value": 3.3', b'"measured_value": 1e999'))
        elif name == "contradictory_contract_bounds":
            contract["measurement"]["upper"] = 3.5
        elif name == "allow_fail_integer_zero":
            measurement["allow_fail"] = 0
            target.write_bytes(encode(record))
        elif name == "dimensions_boolean_false":
            measurement["dimensions"] = False
            target.write_bytes(encode(record))
        elif name == "conditional_validators_integer_zero":
            measurement["conditional_validators"] = 0
            target.write_bytes(encode(record))
        elif name == "checkpoint_extra":
            record["checkpoints"] = [{"name": "additional-checkpoint", "outcome": "FAIL"}]
            target.write_bytes(encode(record))
        elif name == "outcome_details_nonempty":
            record["outcome_details"] = [{"code": "unexpected", "description": "Unreviewed semantics"}]
            target.write_bytes(encode(record))
        elif name == "marginal_true":
            record["marginal"] = True
            target.write_bytes(encode(record))
        elif name == "phase_result_extra_exception":
            record["phases"][0]["result"]["exception"] = "unreviewed exception"
            target.write_bytes(encode(record))
        elif name == "deep_json_nesting":
            target.write_bytes(target.read_bytes().replace(b'"test_name":', b'"deep_note":' + b'[' * 1100 + b'0' + b']' * 1100 + b',\n"test_name":'))
        elif name == "deep_json_parser_limit":
            target.write_bytes(target.read_bytes().replace(b'"test_name":', b'"deep_note":' + b'[' * 10000 + b'0' + b']' * 10000 + b',\n"test_name":'))
        elif name == "exported_measurement_time_outside":
            measurement["set_time_millis"] = record["end_time_millis"] + 1
            target.write_bytes(encode(record))
        elif name == "calibration_covers_phase_only":
            phase = record["phases"][0]
            inst = record["metadata"]["p05"]["instruments"][0]
            inst["calibration_valid_from_millis"] = phase["start_time_millis"]
            inst["calibration_valid_until_millis"] = phase["end_time_millis"]
            target.write_bytes(encode(record))
        elif name == "valid_exported_measurement_time":
            measurement["set_time_millis"] = record["phases"][0]["start_time_millis"]
            target.write_bytes(encode(record))
        elif name == "false_override_empty_lists":
            measurement["allow_fail"] = False
            measurement["dimensions"] = []
            measurement["conditional_validators"] = []
            target.write_bytes(encode(record))
        elif name == "phase_marginal_true":
            record["phases"][0]["marginal"] = True
            target.write_bytes(encode(record))
        elif name == "measurement_marginal_true":
            measurement["marginal"] = True
            target.write_bytes(encode(record))
        elif name == "phase_marginal_integer_zero":
            record["phases"][0]["marginal"] = 0
            target.write_bytes(encode(record))
        elif name == "run_marginal_integer_zero":
            record["marginal"] = 0
            target.write_bytes(encode(record))
        contract_raw = pristine_contract if name != "contradictory_contract_bounds" else encode(contract)
        (folder / "contract.json").write_bytes(contract_raw)
        definition = {"case": name, "expected_status": status, "expected_summary": summary,
                      "detail": detail, "population": "CONSTRUCTED_SOFTWARE_CASE_NOT_FIELD_INCIDENT",
                      "source_kind": "NATIVE_FRAMEWORK_EXPORT" if name.startswith("control_") else "CONTROLLED_MUTATION_OF_REAL_EXPORT",
                      "scope": "POSTHOC_PROFILE_CLARIFICATION" if name == "calibration_covers_phase_only" else "POSTHOC_ADVERSARIAL_CASE",
                      "expected_contract_sha256": sha256(contract_raw),
                      "source_hashes": {p.name: sha256(p.read_bytes()) for p in sorted(inputs.glob("*.json"))}}
        if name == "deep_json_nesting":
            definition["oracle_revision"] = "HISTORICAL_TOO_STRICT" if historical_depth_oracle else "FINAL_CAPACITY_DEPENDENT_WITH_AUTHENTICATION_BOUNDARY"
            definition["allowed_decisions"] = [["INCOMPLETE", "UNKNOWN"]] if historical_depth_oracle else [["READY_FOR_REVIEW", "PASS"], ["INCOMPLETE", "UNKNOWN"]]
        (folder / "EXPECTATION.json").write_bytes(encode(definition))
        definitions.append(definition)
    (out / "EXPECTATIONS_PRE_EXECUTION.json").write_bytes(encode(definitions))
    return definitions


def run(candidate, control, out, selected=None, historical_depth_oracle=False):
    definitions = prepare(out, selected, historical_depth_oracle)
    rows = []
    for definition in definitions:
        name = definition["case"]
        folder = out / "cases" / name
        for label, script in (("candidate", candidate), ("control", control)):
            target = folder / (label + ".json")
            command = [sys.executable, str(script), "--contract", str(folder / "contract.json"),
                       "--expected-contract-sha256", definition["expected_contract_sha256"],
                       "--input-dir", str(folder / "input"), "--out", str(target)]
            if label == "candidate":
                command.extend(["--packet-out", str(folder / "packet.json")])
            started = time.perf_counter()
            process = subprocess.run(command, capture_output=True, text=True, timeout=20)
            elapsed = time.perf_counter() - started
            (folder / (label + ".stdout.txt")).write_text(process.stdout, encoding="utf-8")
            (folder / (label + ".stderr.txt")).write_text(process.stderr, encoding="utf-8")
            result = json.loads(target.read_bytes()) if target.exists() else {}
            status, summary = result.get("status"), result.get("measurement_summary")
            structured = bool(result) and process.returncode in (0, 2) and not process.stderr
            passed = structured and status == definition["expected_status"] and summary == definition["expected_summary"] and result.get("material_release_authorized") is False
            if definition["expected_status"] == "CAPACITY_DEPENDENT":
                passed = (structured and [status, summary] in definition["allowed_decisions"]
                          and result.get("material_release_authorized") is False
                          and result.get("evidence_authentication") == "NOT_IMPLEMENTED"
                          and result.get("clock_authentication") == "UNKNOWN"
                          and result.get("calibration_authentication") == "UNKNOWN")
            if name == "coherent_forgery":
                passed = passed and result.get("evidence_authentication") == "NOT_IMPLEMENTED" and result.get("clock_authentication") == "UNKNOWN" and result.get("calibration_authentication") == "UNKNOWN"
            rows.append({"case": name, "comparator": label, "script_sha256": sha256(script.read_bytes()),
                         "returncode": process.returncode, "structured": structured, "status": status,
                         "measurement_summary": summary, "expected_status": definition["expected_status"],
                         "expected_summary": definition["expected_summary"], "expectation_met": passed,
                         "elapsed_seconds": elapsed, "scope": definition["scope"],
                         "issue_codes": [x.get("code") for x in result.get("issues", [])]})
    agreements = []
    for definition in definitions:
        pair = [row for row in rows if row["case"] == definition["case"]]
        equal = len(pair) == 2 and (pair[0]["status"], pair[0]["measurement_summary"]) == (pair[1]["status"], pair[1]["measurement_summary"])
        agreements.append({"case": definition["case"], "decision_agrees": equal,
                           "capacity_dependent_oracle": definition["expected_status"] == "CAPACITY_DEPENDENT"})
    summary = {"study_kind": "POSTHOC_SOFTWARE_COUNTEREXAMPLES_NOT_FIELD_VALIDATION", "distinct_cases": len(definitions),
               "executions": len(rows), "candidate_expectations_met": sum(x["expectation_met"] for x in rows if x["comparator"] == "candidate"),
               "control_expectations_met": sum(x["expectation_met"] for x in rows if x["comparator"] == "control"),
               "decision_pairs_compared": len(agreements), "decision_pairs_in_agreement": sum(x["decision_agrees"] for x in agreements),
               "decision_comparison": agreements,
               "rows": rows}
    (out / "SUMMARY.json").write_bytes(encode(summary))
    print(json.dumps({k: v for k, v in summary.items() if k not in ("rows", "decision_comparison")}, indent=2))
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", type=Path, default=ROOT / "src/openhtf_adapter.py")
    p.add_argument("--control", type=Path, default=ROOT / "control/competent_script.py")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--only", nargs="+", choices=[x[0] for x in cases()])
    p.add_argument("--historical-depth-oracle", action="store_true", help="Reproduce the initial, too-strict oracle at 1100 levels; final replay omits this flag")
    args = p.parse_args()
    run(args.candidate.resolve(), args.control.resolve(), args.out.resolve(), set(args.only) if args.only else None, args.historical_depth_oracle)


if __name__ == "__main__":
    main()
