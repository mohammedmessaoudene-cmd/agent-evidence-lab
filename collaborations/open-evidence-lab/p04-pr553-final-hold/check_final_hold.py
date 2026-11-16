"""Reproduce the final-invoice reservation comparison against a pinned PR checkout.

Usage: python -B check_final_hold.py CHECKOUT NEW_RESULTS_DIRECTORY
Requires Python 3.11+ and the standard library. All ledger runs use synthetic inputs.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


REFERENCE = "c321eab3e1adfa2169164f63238597f1a1c2a7868d339540a3da574f09c82d0f"
ORIGINAL = b'remainder = 0 if row["billing_finality"] == "FINAL" else max(0, row["authorized_max"] - row["known"])'
MUTANTS = {
    "early_release": ORIGINAL.replace(b'== "FINAL"', b'== "FINAL" or row["outcome"] == "SUCCEEDED"'),
    "stuck_hold": b'remainder = max(0, row["authorized_max"] - row["known"])',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def money(state):
    return [state[k] for k in ("heldMicroUsd", "knownSpendMicroUsd", "availableMicroUsd")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    root = args.checkout.resolve()
    output = args.results.resolve()
    pins = json.loads(Path(__file__).with_name("SOURCE_PINS.json").read_text(encoding="utf-8"))
    for relative, digest in pins["filesSha256"].items():
        if sha((root / relative).read_bytes()) != digest:
            raise ValueError(f"{relative}: source bytes differ from the pinned revision")
    output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(root / "packaging"))
    from agent_evidence_vectors import executionbilling as reader
    from agent_evidence_vectors import executionbilling_runtime as runtime

    corpus = root / "corpora" / "vectors-execution-billing-finality"
    adapter = corpus / "tests" / "billing_adapter.py"
    source = (corpus / "tests" / "p04" / "exposure_ledger.py").read_bytes()
    if sha(source) != REFERENCE or source.count(ORIGINAL) != 1:
        raise ValueError("the baseline source or mutation site differs from the pin")
    manifest = json.loads((corpus / "MANIFEST.json").read_text(encoding="utf-8"))
    scenarios = reader.scenarios(manifest["vectors"])
    fixtures = {s["id"]: s for s in scenarios}
    probe = {"cmd": "reserve", "amount": 2, "attempt": "B"}
    if fixtures["F05"]["probes"] or fixtures["F01"]["probes"] != [probe]:
        raise ValueError("the shipped F05 or F01 scenario changed")
    focused = [
        fixtures["F01"],
        {**fixtures["F05"], "id": "F05-with-second-reservation", "probes": [probe]},
    ]
    summary = {
        "corpusDigest": manifest["corpusDigest"],
        "reader": sha(Path(reader.__file__).read_bytes()),
        "adapter": sha(adapter.read_bytes()),
        "python": sys.version.split()[0],
        "arms": {},
    }
    variants = {"reference": source}
    for name, replacement in MUTANTS.items():
        variants[name] = source.replace(ORIGINAL, replacement)
    for name, data in variants.items():
        arm = output / name
        arm.mkdir()
        ledger = arm / "exposure_ledger.py"
        ledger.write_bytes(data)
        command = [sys.executable, "-B", "-S", str(adapter), "--source", str(ledger)]
        report = runtime.check_runtime(command, corpus)
        if report["verifier"]["vectorsExecuted"] != len(scenarios) or any(
            not row["observed"] for row in report["vectors"]
        ):
            raise RuntimeError(f"{name}: incomplete observations")
        save(arm / "runtime.json", report)
        arm_summary = {
            "source": sha(data),
            "shipped": report["totals"],
            "failedScenarios": [row["id"] for row in report["vectors"] if row["reasons"]],
            "focused": {},
        }
        for scenario in focused:
            case = scenario["id"]
            scenario_file = arm / f"{case}.scenario.json"
            save(scenario_file, scenario)
            proc = subprocess.run([*command, str(scenario_file), "--json"],
                                  capture_output=True, text=True, timeout=120, check=True)
            record = json.loads(proc.stdout.strip().splitlines()[-1])
            if record["sourceSha256"] != sha(data) or record["scenario"] != scenario:
                raise ValueError(f"{name}/{case}: ledger or input mismatch")
            save(arm / f"{case}.record.json", record)
            billed = case != "F01"
            expected_money = [0, 1, 2] if billed else [2, 0, 1]
            reservation = record["probes"][0]
            allowed = reservation["exception"] is None and reservation["return"].get("newlyReserved") is True
            refused = reservation["exception"] == "AdmissionDenied"
            if not (allowed or refused):
                raise ValueError(f"{name}/{case}: incomplete admission observation")
            unchanged = record["observed"] == record["reopened"] and record["end"] == record["endReopened"]
            arm_summary["focused"][case] = {
                "beforeB": money(record["reopened"]),
                "reservationB": "admitted" if allowed else "refused",
                "normalReopenEqual": unchanged,
                "reader": reader.decide(record),
                "runtimeProblems": runtime.judge(scenario, record),
                "pairedExpectationMet": unchanged and money(record["reopened"]) == expected_money
                and (allowed if billed else refused),
            }
        summary["arms"][name] = arm_summary
    save(output / "comparison.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    expected_failures = {"reference": [], "early_release": ["F01", "F05", "X4"], "stuck_hold": []}
    for name, failures in expected_failures.items():
        if summary["arms"][name]["failedScenarios"] != failures:
            raise ValueError(f"{name}: different classifications on the shipped scenarios")
    for name, expected_amounts, admission in [
        ("reference", [0, 1, 2], "admitted"), ("stuck_hold", [1, 1, 1], "refused")
    ]:
        observed = summary["arms"][name]["focused"]["F05-with-second-reservation"]
        if (observed["beforeB"] != expected_amounts or observed["reservationB"] != admission
                or not observed["normalReopenEqual"] or observed["runtimeProblems"]
                or observed["reader"] != {"decision": "allow", "reason": "finality_held"}):
            raise ValueError(f"{name}: different result on the final-invoice probe")


if __name__ == "__main__":
    main()
