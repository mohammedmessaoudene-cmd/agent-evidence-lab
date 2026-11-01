"""Adversarial checks of an archive verifier; no measurement program executes.

All mutations affect disposable copies of an existing evidence directory.
Source files in the pinned snapshot are used only to compare recorded digests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pinned-project", type=Path, required=True)
    parser.add_argument("--delta-project", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--portable-only", action="store_true", help="Verify evidence from the explicit 41-observation subset")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    programs = ["src/openhtf_adapter.py", "control/competent_script.py"]
    runner_rel = "review/run_targeted_review.py"
    for name, source in [("pinned", args.pinned_project), ("changed", args.delta_project)]:
        for relative in [*programs, runner_rel]:
            destination = args.out / ("snapshot_" + name) / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            origin = args.delta_project / relative if relative == runner_rel else source / relative
            shutil.copyfile(origin, destination)
    definitions = [
        ("intact_records_pinned_sources", "pinned", "PASS", None),
        ("contradictory_recorded_pin", "pinned", "FAIL", "source SHA256"),
        ("missing_positive_report", "pinned", "FAIL", "Required report"),
        ("missing_positive_packet", "pinned", "FAIL", "Required packet"),
        ("changed_packet_raw_export", "pinned", "FAIL", "raw export preservation"),
        ("contradictory_semantic_stdout", "pinned", "FAIL", "stdout decision contradicts recorded observation"),
        ("historical_records_changed_sources", "changed", "FAIL", "source SHA256"),
    ]
    rows = []
    for case, snapshot, expected, error_fragment in definitions:
        folder = args.out / case
        shutil.copytree(args.evidence, folder, symlinks=True)
        if case == "contradictory_recorded_pin":
            path = folder / "semantic/SUMMARY.json"
            summary = read(path)
            original_pin = summary["rows"][0]["script_sha256"]
            summary["rows"][0]["script_sha256"] = "0" * 64
            write(path, summary)
        elif case == "missing_positive_report":
            (folder / "output_guards/fresh_control_report_control_corrected/report.json").unlink()
        elif case == "missing_positive_packet":
            (folder / "output_guards/two_fresh_reports_nested_candidate_corrected/new/nested/packet.json").unlink()
        elif case == "changed_packet_raw_export":
            path = folder / "output_guards/two_fresh_reports_nested_candidate_corrected/new/nested/packet.json"
            packet = read(path)
            packet["sources"][0]["raw_export"]["metadata"]["oracle_only_mutation"] = True
            write(path, packet)
        elif case == "contradictory_semantic_stdout":
            row = read(folder / "semantic/SUMMARY.json")["rows"][0]
            path = folder / "semantic/cases" / row["case"] / (row["program"] + ".stdout.json")
            result = read(path)
            result["status"] = "READY_FOR_REVIEW"
            result["measurement_summary"] = "PASS"
            write(path, result)
        runner = args.out / ("snapshot_" + snapshot) / runner_rel
        command = [sys.executable, "-B", "-S", str(runner.resolve()),
                   "--out", str(folder.resolve()), "--verify-only"]
        if args.portable_only:
            command.append("--portable-only")
        proc = subprocess.run(command,
                              capture_output=True, timeout=10)
        (folder / "oracle.stdout.txt").write_bytes(proc.stdout)
        (folder / "oracle.stderr.txt").write_bytes(proc.stderr)
        result = read(folder / "VERIFICATION.json")
        row = {"case": case, "source_snapshot": snapshot, "expected_status": expected,
               "status": result["status"], "returncode": proc.returncode,
               "error": result["error"], "business_programs_executed": 0,
               "invocations_recorded": len(result["invocations"]),
               "expected_met": result["status"] == expected
                   and proc.returncode == (0 if expected == "PASS" else 1)
                   and not proc.stderr and not result["invocations"]
                   and (error_fragment is None or error_fragment in (result["error"] or ""))}
        if case == "contradictory_recorded_pin":
            row["recorded_pin_before_mutation"] = original_pin
            row["recorded_pin_after_mutation"] = "0" * 64
        rows.append(row)
    result = {"schema": "p05-verifier-integrity-probe/1", "rows": rows,
              "profile": "PORTABLE_SUBSET_41_OBSERVATIONS" if args.portable_only else "WITH_SYMLINKS_45_OBSERVATIONS",
              "verifier_processes": len(rows), "business_programs_executed": 0,
              "all_expectations_met": all(row["expected_met"] for row in rows),
              "runner_sha256": digest(args.delta_project / runner_rel),
              "source_snapshots": {name: {relative: digest(args.out / ("snapshot_" + name) / relative)
                                           for relative in programs} for name in ("pinned", "changed")},
              "scope": "Archive readback assertions only; intact historical records retain their execution-source pins"}
    write(args.out / "SUMMARY.json", result)
    print(json.dumps(result, indent=2))
    return 0 if result["all_expectations_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
