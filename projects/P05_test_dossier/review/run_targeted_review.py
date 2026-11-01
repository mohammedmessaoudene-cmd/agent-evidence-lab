"""Exercise the new P05 defects and three specifically affected historical cases.

This runner does not run the historical 30/22 matrices. It requires filesystem
link support for the requested link probes; unavailable support is an error,
never a silently passing or skipped claim. No SDK or instrument is imported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def boundary(result, label):
    require(result.get("material_release_authorized") is False, label + ": release")
    for key, value in [("physical_validation", "NOT_RUN"),
                       ("instrument_equivalence", "NOT_ESTABLISHED"),
                       ("evidence_authentication", "NOT_IMPLEMENTED"),
                       ("clock_authentication", "UNKNOWN"),
                       ("calibration_authentication", "UNKNOWN")]:
        require(result.get(key) == value, label + ": " + key)


def source_pin(row, label):
    scripts = {"candidate": "src/openhtf_adapter.py", "control": "control/competent_script.py"}
    require(label in scripts, "Unknown source program")
    require(row.get("script_sha256") == digest(ROOT / scripts[label]), "Recorded source SHA256 differs from current program: " + label)


def decision(result, observed, expected, returncode, label, api=False):
    actual = [result.get("status"), result.get("measurement_summary")]
    require(actual == observed, label + ": stdout decision contradicts recorded observation")
    permitted = [["READY_FOR_REVIEW", "PASS"], ["INCOMPLETE", "UNKNOWN"]] if expected == ["CAPACITY_DEPENDENT", "CAPACITY_DEPENDENT"] else [expected]
    require(actual in permitted, label + ": stdout decision contradicts expectation")
    require(returncode is None if api else returncode == (0 if actual[0] == "READY_FOR_REVIEW" else 2), label + ": decision/exit code mismatch")
    boundary(result, label)


def packet_file(path, inputs, result):
    require(path.is_file(), "Required packet file absent")
    packet = read(path)
    require(packet.get("review") == result, "Packet review differs from stdout")
    sources = packet.get("sources", [])
    expected_names = {p.name for p in inputs.glob("*.json")}
    require(len(sources) == len(expected_names) and {s.get("file") for s in sources} == expected_names, "Packet source population")
    for source in sources:
        original = inputs / source["file"]
        require(source["raw_export"] == read(original), "Packet raw export preservation")
        require(source["sha256"] == digest(original), "Packet raw byte digest")
        require(source["byte_size"] == original.stat().st_size, "Packet raw byte size")
    return packet


def verify(out, portable_only=False):
    stages = []
    semantic = read(out / "semantic/SUMMARY.json")
    require(semantic["cases"] == 8 and len(semantic["rows"]) == 16, "semantic cardinality")
    for row in semantic["rows"]:
        source_pin(row, row["program"])
        require(row["expectation_met"], "semantic " + row["case"])
        expected_code = 0 if row["expected"][0] == "READY_FOR_REVIEW" else 2
        require(row["returncode"] == expected_code, "semantic exit code")
        result = read(out / "semantic/cases" / row["case"] / (row["program"] + ".stdout.json"))
        decision(result, row["observed"], row["expected"], row["returncode"], row["case"])
    stages.append({"stage": "new_semantic_profile", "cases": 8, "records": 16, "passed": 16})

    cli = read(out / "cli/SUMMARY.json")
    require(len(cli["rows"]) == 7, "CLI cardinality")
    for row in cli["rows"]:
        source_pin(row, row["program"])
        good = row["case"].startswith("unicode_")
        expected = ["READY_FOR_REVIEW", "PASS"] if good else ["INCOMPLETE", "UNKNOWN"]
        require([row["status"], row["measurement_summary"]] == expected, "CLI " + row["case"])
        require(row["returncode"] == (0 if good else 2), "CLI exit code")
        require(row["structured_stdout"] and not row["stderr"] and not row["protected_files_changed"], "CLI evidence preservation")
        folder = out / "cli" / (row["case"] + "_" + row["program"])
        decision(read(folder / "stdout.txt"), [row["status"], row["measurement_summary"]], expected, row["returncode"], row["case"])
        if good:
            packet_file(folder / "packet.json", folder / "input", read(folder / "stdout.txt"))
    stages.append({"stage": "new_cli_boundaries", "records": 7, "passed": 7})

    guards = read(out / "output_guards/SUMMARY.json")
    guard_count = 12 if portable_only else 14
    require(guards["corrected_records"] == guard_count and len(guards["rows"]) == guard_count, "output guard cardinality")
    require(all(row["version"] == "corrected" and row["expected_met"] for row in guards["rows"]), "output guard expectations")
    for row in guards["rows"]:
        source_pin(row, row["program"])
        folder = out / "output_guards" / (row["case"] + "_" + row["program"] + "_corrected")
        result = read(folder / "stdout.txt")
        decision(result, [row["status"], row["measurement_summary"]], row["expected_after_fix"], row["returncode"], row["case"], api=row["case"] == "review_api_packet_alias")
        if row["case"] in ("fresh_control_report", "two_fresh_reports_nested"):
            report = folder / ("report.json" if row["case"] == "fresh_control_report" else "new/nested/report.json")
            require(report.is_file() and read(report) == result, "Required report absent or inconsistent")
        if row["case"] in ("two_fresh_reports_nested", "escaped_surrogate_packet"):
            path = folder / ("packet.json" if row["case"] == "escaped_surrogate_packet" else "new/nested/packet.json")
            packet_file(path, folder / "input", result)
    stages.append({"stage": "new_output_guards", "records": guard_count, "passed": guard_count,
                   "cli_executions": guard_count - 1, "review_api_calls": 1})

    if not portable_only:
        cyclic = read(out / "cyclic/SUMMARY.json")
        require(cyclic.get("source_sha256") == digest(ROOT / "src/openhtf_adapter.py"), "Cyclic probe source SHA256 mismatch")
        require(len(cyclic["rows"]) == 2 and all(row["expected_met"] for row in cyclic["rows"]), "cyclic output guards")
        for row in cyclic["rows"]:
            result = read(out / "cyclic" / row["case"] / "stdout.txt")
            decision(result, [row["status"], row["measurement_summary"]], ["INCOMPLETE", "UNKNOWN"], row["returncode"], row["case"])
        stages.append({"stage": "cyclic_path_guards", "records": 2, "passed": 2})

    affected = read(out / "affected_historical/SUMMARY.json")
    require(affected["distinct_cases"] == 3 and len(affected["rows"]) == 6, "affected historical cardinality")
    require({row["case"] for row in affected["rows"]} == {"control_fail", "coherent_forgery", "deep_json_nesting"}, "affected historical selection")
    require(all(row["expectation_met"] for row in affected["rows"]), "affected historical expectations")
    for row in affected["rows"]:
        source_pin(row, row["comparator"])
        result = read(out / "affected_historical/cases" / row["case"] / (row["comparator"] + ".json"))
        decision(result, [row["status"], row["measurement_summary"]], [row["expected_status"], row["expected_summary"]], row["returncode"], row["case"])
    stages.append({"stage": "three_affected_historical_cases", "cases": 3, "records": 6, "passed": 6,
                   "reason": "Changed output persistence/serialization and native structure guards touch these paths; no new independent cases claimed"})
    return stages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--portable-only", action="store_true", help="Explicit subset without symbolic-link cases; these cases are NOT_RUN, never counted as passed")
    args = parser.parse_args()
    out = args.out.resolve()
    if not args.verify_only:
        out.mkdir(parents=True, exist_ok=False)
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    commands = [
        ("semantic", ["review/focused/new_semantic_probes.py", "--project", str(ROOT), "--out", str(out / "semantic"), "--assert-expected"]),
        ("cli", ["review/focused/probe_cli_boundaries.py", "--project", str(ROOT), "--out", str(out / "cli")]),
        ("output_guards", ["review/focused/probe_output_guards.py", "--project", str(ROOT), "--program-project", str(ROOT), "--corrected-only", "--out", str(out / "output_guards")]),
        ("cyclic", ["review/focused/probe_cyclic_output.py", "--project", str(ROOT), "--program-project", str(ROOT), "--out", str(out / "cyclic")]),
        ("affected_historical", ["review/counterexamples.py", "--only", "control_fail", "coherent_forgery", "deep_json_nesting", "--out", str(out / "affected_historical")]),
    ]
    if args.portable_only:
        commands = [(name, command) for name, command in commands if name != "cyclic"]
        for name, command in commands:
            if name == "output_guards":
                command.extend(["--only", "two_outputs_same_path", "later_output_is_contract", "existing_report", "hardlink_to_source", "two_fresh_reports_nested", "fresh_control_report", "later_parent_is_file", "parent_is_file", "escaped_surrogate_packet", "review_api_packet_alias"])
    invocations = []
    try:
        if not args.verify_only:
            for name, command in commands:
                proc = subprocess.run([sys.executable, "-B", "-S", *command], cwd=ROOT,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      env=environment, timeout=120)
                (out / (name + ".stdout.txt")).write_bytes(proc.stdout)
                (out / (name + ".stderr.txt")).write_bytes(proc.stderr)
                invocations.append({"stage": name, "returncode": proc.returncode,
                                    "script": command[0], "script_sha256": digest(ROOT / command[0])})
                require(proc.returncode == 0 and not proc.stderr, name + ": subprocess failed; inspect saved trace")
        stages = verify(out, args.portable_only)
        status, error = "PASS", None
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired) as exc:
        status, error, stages = "FAIL", type(exc).__name__ + ": " + str(exc), []
    summary = {
        "schema": "p05-targeted-public-review/1", "status": status, "error": error,
        "execution_mode": "VERIFY_EXISTING_REPORTS" if args.verify_only else "EXECUTE_NEW_AND_AFFECTED_ONLY",
        "profile": "PORTABLE_SUBSET_41_OBSERVATIONS" if args.portable_only else "WITH_SYMLINKS_45_OBSERVATIONS",
        "symbolic_link_cases": "NOT_RUN_BY_EXPLICIT_SUBSET" if args.portable_only else "EXECUTED",
        "python": platform.python_version(), "platform": platform.system(),
        "candidate_sha256": digest(ROOT / "src/openhtf_adapter.py"),
        "control_sha256": digest(ROOT / "control/competent_script.py"),
        "stages": stages, "invocations": invocations,
        "historical_full_matrices_rerun": 0,
        "framework_regenerations": 0, "physical_tests": 0,
        "human_time_measured": False, "agent_in_decision_runtime": False,
        "scope": "Constructed software regressions and explicitly affected old cases; not independent field samples or a superiority score",
    }
    target = out / ("VERIFICATION.json" if args.verify_only else "TARGETED_REVIEW.json")
    target.write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
