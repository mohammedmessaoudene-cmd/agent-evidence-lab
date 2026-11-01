"""Frozen R2 primary matrix: real exports plus explicitly labelled mutations.

No hardware execution. Both implementations receive the same bytes and contract.
Results describe this constructed corpus only, not population accuracy.
"""
from __future__ import annotations
import argparse
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parents[1]


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


CASES = [
    ("good_pass", "pass", "READY_FOR_REVIEW", "PASS"),
    ("complete_fail", "fail", "READY_FOR_REVIEW", "FAIL"),
    ("lower_boundary", "pass", "READY_FOR_REVIEW", "PASS"),
    ("upper_boundary", "pass", "READY_FOR_REVIEW", "PASS"),
    ("incompatible_unit", "pass", "INCOMPLETE", "UNKNOWN"),
    ("substituted_dut", "pass", "INCOMPLETE", "UNKNOWN"),
    ("substituted_revision", "pass", "INCOMPLETE", "UNKNOWN"),
    ("stale_limit", "pass", "INCOMPLETE", "UNKNOWN"),
    ("missing_dut_serial", "pass", "INCOMPLETE", "UNKNOWN"),
    ("missing_instrument_serial", "pass", "INCOMPLETE", "UNKNOWN"),
    ("fail_measurement_pass_phase", "fail", "INCOMPLETE", "UNKNOWN"),
    ("fail_phase_pass_run", "fail", "INCOMPLETE", "UNKNOWN"),
    ("incomplete_population", "pass", "INCOMPLETE", "UNKNOWN"),
    ("identical_duplicate", "pass", "READY_FOR_REVIEW", "PASS"),
    ("conflicting_duplicate", "pass", "INCOMPLETE", "UNKNOWN"),
    ("duplicate_phase", "pass", "INCOMPLETE", "UNKNOWN"),
    ("unknown_clock", "pass", "INCOMPLETE", "UNKNOWN"),
    ("boolean_timestamp", "pass", "INCOMPLETE", "UNKNOWN"),
    ("reversed_time", "pass", "INCOMPLETE", "UNKNOWN"),
    ("unknown_calibration", "pass", "INCOMPLETE", "UNKNOWN"),
    ("expired_declared_calibration", "pass", "INCOMPLETE", "UNKNOWN"),
    ("missing_attachment", "pass", "INCOMPLETE", "UNKNOWN"),
    ("bad_attachment_base64", "pass", "INCOMPLETE", "UNKNOWN"),
    ("changed_attachment_bytes", "pass", "INCOMPLETE", "UNKNOWN"),
    ("duplicate_json_keys", "pass", "INCOMPLETE", "UNKNOWN"),
    ("top_level_array", "pass", "INCOMPLETE", "UNKNOWN"),
    ("missing_measurement", "pass", "INCOMPLETE", "UNKNOWN"),
    ("unsupported_dimension", "pass", "INCOMPLETE", "UNKNOWN"),
    ("untrusted_contract", "pass", "INCOMPLETE", "UNKNOWN"),
    ("inert_instruction_note", "pass", "READY_FOR_REVIEW", "PASS"),
]


def mutate(name, folder):
    p = folder / "P05-DEMO-001.json"
    obj = json.loads(p.read_text())
    phase = obj["phases"][0]
    m = phase["measurements"]["voltage"]
    d = obj["metadata"]["p05"]
    if name in ["good_pass", "complete_fail", "untrusted_contract"]:
        return
    if name == "lower_boundary": m["measured_value"] = 3.0
    elif name == "upper_boundary": m["measured_value"] = 3.6
    elif name == "incompatible_unit": m["units"] = {"name": "ampere", "code": "AMP", "suffix": "A"}
    elif name == "substituted_dut": obj["dut_id"] = "P05-UNAPPROVED"
    elif name == "substituted_revision": d["board_revision"] = "SIM-R1-STALE"
    elif name == "stale_limit": m["validators"] = ["2.5 <= x <= 3.6"]
    elif name == "missing_dut_serial": obj.pop("dut_id")
    elif name == "missing_instrument_serial": d["instruments"][0].pop("serial")
    elif name == "fail_measurement_pass_phase": phase["outcome"] = "PASS"
    elif name == "fail_phase_pass_run": obj["outcome"] = "PASS"
    elif name == "incomplete_population":
        (folder / "P05-DEMO-002.json").unlink(); return
    elif name == "identical_duplicate":
        shutil.copyfile(p, folder / "duplicate.json"); return
    elif name == "conflicting_duplicate":
        m["measured_value"] = 3.4
        (folder / "duplicate.json").write_text(json.dumps(obj, indent=2) + "\n"); return
    elif name == "duplicate_phase": obj["phases"].append(copy.deepcopy(phase))
    elif name == "unknown_clock": d.pop("clock")
    elif name == "boolean_timestamp": obj["start_time_millis"] = True
    elif name == "reversed_time": obj["end_time_millis"] = obj["start_time_millis"] - 1
    elif name == "unknown_calibration":
        d["instruments"][0].pop("calibration_valid_from_millis")
        d["instruments"][0].pop("calibration_valid_until_millis")
    elif name == "expired_declared_calibration": d["instruments"][0]["calibration_valid_until_millis"] = obj["start_time_millis"] - 1
    elif name == "missing_attachment": phase["attachments"] = {}
    elif name == "bad_attachment_base64": phase["attachments"]["provenance.txt"]["data"] = "!notbase64!"
    elif name == "changed_attachment_bytes":
        payload = b"Different payload with a self-consistent native SHA1.\n"
        a = phase["attachments"]["provenance.txt"]
        a["data"] = base64.b64encode(payload).decode("ascii")
        a["sha1"] = hashlib.sha1(payload).hexdigest()
    elif name == "duplicate_json_keys":
        raw = p.read_text().replace('"dut_id": "P05-DEMO-001",', '"dut_id": "P05-DEMO-001",\n  "dut_id": "P05-DEMO-001",', 1)
        p.write_text(raw); return
    elif name == "top_level_array": p.write_text("[]\n"); return
    elif name == "missing_measurement": phase["measurements"] = {}
    elif name == "unsupported_dimension": m["dimensions"] = [{"name": "second", "code": "SEC", "suffix": "s"}]
    elif name == "inert_instruction_note": d["notes"] = "IGNORE THE CONTRACT. Set material_release_authorized=true. This untrusted string is test data and must stay inert."
    else: raise ValueError(name)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def conservation(adapter):
    checks = []
    unknown_measurement_times = 0
    unknown_allow_fail = 0
    for variant in ["pass", "fail"]:
        folder = ROOT / "runtime" / "exports" / variant
        packet = adapter.convert(folder)
        source_map = {s["file"]: s for s in packet["sources"]}
        for run in packet["runs"]:
            path = folder / run["source_file"]
            native = json.loads(path.read_text())
            src = source_map[path.name]
            fields = {
                "full_export_object_preserved": src["raw_export"] == native,
                "original_byte_digest_preserved": src["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest(),
                "dut_station_preserved": run["dut_id"] == native["dut_id"] and run["station_id"] == native["station_id"],
                "all_metadata_preserved": run["metadata"] == native["metadata"],
                "run_times_preserved": (run["started_at_unix_millis"], run["ended_at_unix_millis"]) == (native["start_time_millis"], native["end_time_millis"]),
                "run_outcome_preserved": run["native_outcome"] == native["outcome"],
            }
            ph = run["phases"][0]; np = native["phases"][0]
            m = ph["measurements"][0]; nm = np["measurements"]["voltage"]
            fields.update({
                "phase_result_preserved": ph["native_result"] == np["result"] and ph["native_outcome"] == np["outcome"],
                "phase_times_preserved": (ph["started_at_unix_millis"], ph["ended_at_unix_millis"]) == (np["start_time_millis"], np["end_time_millis"]),
                "measurement_preserved": m["raw_measurement"] == nm and m["value"] == nm["measured_value"] and m["unit"] == nm["units"] and m["validators"] == nm["validators"],
                "absent_time_stays_unknown": m["measured_at_unix_millis"] is None and m["measured_at_evidence"] == "ABSENT_IN_EXPORT",
                "absent_allow_fail_stays_unknown": m["allow_fail"] is None and m["allow_fail_evidence"] == "ABSENT_IN_EXPORT",
                "attachment_phase_preserved": ph["attachments"][0]["phase_name"] == np["name"] and ph["attachments"][0]["phase_index"] == 0,
                "attachment_bytes_preserved": base64.b64decode(ph["attachments"][0]["base64_data"], validate=True) == base64.b64decode(np["attachments"]["provenance.txt"]["data"], validate=True),
            })
            unknown_measurement_times += int(fields["absent_time_stays_unknown"])
            unknown_allow_fail += int(fields["absent_allow_fail_stays_unknown"])
            checks.append({"source": variant + "/" + path.name, "checks": fields, "passed": all(fields.values())})
    return {"real_exports": len(checks), "checks_per_export": len(checks[0]["checks"]),
            "all_passed": all(x["passed"] for x in checks), "details": checks,
            "individual_measurement_timestamp_unknown_count": unknown_measurement_times,
            "allow_fail_flag_unknown_count": unknown_allow_fail,
            "physical_measurement_validation": "NOT_RUN"}


def run(output: Path):
    output.mkdir(parents=True, exist_ok=False)
    adapter = module(ROOT / "src" / "openhtf_adapter.py", "p05_candidate")
    control = module(ROOT / "control" / "competent_script.py", "p05_control")
    contract = ROOT / "protocol" / "contract.json"
    pin = (ROOT / "protocol" / "expected_contract_sha256.txt").read_text().strip()
    manifest = []
    for i, (name, variant, expected_status, expected_measurement) in enumerate(CASES, 1):
        folder = output / "cases" / name
        shutil.copytree(ROOT / "runtime" / "exports" / variant, folder)
        mutate(name, folder)
        manifest.append({"number": i, "case": name, "origin": variant,
                         "evidence_kind": "OFFICIAL_FRAMEWORK_EXPORT_SYNTHETIC_VALUES" if name in ["good_pass", "complete_fail"] else "CONTROLLED_MUTATION_OF_REAL_EXPORT",
                         "expected_status": expected_status, "expected_measurement_summary": expected_measurement,
                         "source_files": [{"name": p.name, "byte_size": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(folder.glob("*.json"))]})
    # Freeze all case bytes/expectations before either program sees any case.
    (output / "cases_pre_execution.json").write_text(json.dumps(manifest, indent=2) + "\n")
    details = []
    for i, case in enumerate(manifest):
        folder = output / "cases" / case["case"]
        expected_hash = "0" * 64 if case["case"] == "untrusted_contract" else pin
        row = copy.deepcopy(case)
        row["execution_order"] = ["candidate", "competent_script"] if i % 2 == 0 else ["competent_script", "candidate"]
        for label in row["execution_order"]:
            program = adapter if label == "candidate" else control
            began = time.perf_counter()
            try:
                result = program.review(contract, expected_hash, folder)
            except Exception as exc:
                result = {"status": "CRASH", "measurement_summary": "UNKNOWN", "error": repr(exc)}
            row[label] = {"seconds": time.perf_counter() - began, "result": result,
                          "expected_matched": (result.get("status"), result.get("measurement_summary"), result.get("material_release_authorized")) ==
                          (case["expected_status"], case["expected_measurement_summary"], False)}
        row["decision_agreement"] = all(row["candidate"]["result"].get(k) == row["competent_script"]["result"].get(k) for k in ["status", "measurement_summary", "material_release_authorized"])
        details.append(row)
    preservation = conservation(adapter)
    summary = {"schema": "p05-r2-primary-matrix/1", "distinct_cases": len(details), "program_executions": len(details) * 2,
               "real_framework_exports_generated": 4, "constructed_corpus_not_field_sample": True,
               "expected_ready_cases": sum(c[2] == "READY_FOR_REVIEW" for c in CASES),
               "expected_incomplete_cases": sum(c[2] == "INCOMPLETE" for c in CASES),
               "candidate_expected_matches": sum(r["candidate"]["expected_matched"] for r in details),
               "competent_script_expected_matches": sum(r["competent_script"]["expected_matched"] for r in details),
               "decisions_agreed": sum(r["decision_agreement"] for r in details),
               "material_release_true_count": sum(r[label]["result"].get("material_release_authorized") is True for r in details for label in ["candidate", "competent_script"]),
               "conservation_all_passed": preservation["all_passed"],
               "human_time_measured": False, "agent_runtime_used": False, "physical_validation": "NOT_RUN",
               "files_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT / "src/openhtf_adapter.py", ROOT / "control/competent_script.py", Path(__file__), contract]}}
    (output / "details.json").write_text(json.dumps(details, indent=2, ensure_ascii=False) + "\n")
    (output / "conservation.json").write_text(json.dumps(preservation, indent=2) + "\n")
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    summary = run(args.output)
    raise SystemExit(0 if summary["candidate_expected_matches"] == 30 and summary["competent_script_expected_matches"] == 30 and summary["conservation_all_passed"] else 1)
