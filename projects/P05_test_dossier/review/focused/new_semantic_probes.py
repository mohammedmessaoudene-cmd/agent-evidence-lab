"""New constructed semantic probes; no historical matrices or real instruments.

The expectations are fixed before the first execution. Native field-type
expectations derive from pinned OpenHTF TestRecord/PhaseRecord and the public
out_of_profile_policy. Contract-extension cases test explicit policy matching,
not authenticity. Original exports contain synthetic assigned values only.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

UPSTREAM_TYPES = "https://github.com/google/openhtf/blob/87426bad5bc3d846b3025a2dc18987e020cedb00/openhtf/core/test_record.py"

CASES = [
    ("run_subtests_integer_zero", "INCOMPLETE", "UNKNOWN", "A native List[SubtestRecord] field is replaced by integer zero; malformed non-list is outside the scalar profile."),
    ("run_outcome_details_empty_object", "INCOMPLETE", "UNKNOWN", "Native List[OutcomeDetails] is replaced by an empty object, not an empty list."),
    ("phase_failure_diagnosis_boolean_false", "INCOMPLETE", "UNKNOWN", "Native List[DiagResultEnum] is replaced by Boolean false, not an empty list."),
    ("phase_subtest_name_empty_list", "INCOMPLETE", "UNKNOWN", "Native Optional[Text] subtest_name is replaced by an array; this is not a missing/null association."),
    ("phase_diagnosis_results_explicit_null", "INCOMPLETE", "UNKNOWN", "Native List[DiagResultEnum] is explicitly null, not an absent field or an empty list; missing knowledge must not be interpreted as no diagnoses."),
    ("valid_explicit_empty_structures", "READY_FOR_REVIEW", "PASS", "Positive typed control with explicit empty native collections and a null optional subtest name; no new physical observation."),
    ("contract_instrument_interval_policy_conflict", "INCOMPLETE", "UNKNOWN", "The independently pinned contract explicitly fixes calibration_valid_until_millis to a different value than the declarations; time containment alone cannot satisfy exact instrument policy matching."),
    ("contract_instrument_interval_policy_match", "READY_FOR_REVIEW", "PASS", "Positive contract-extension control: the exact approved calibration_valid_until_millis is supplied in both declarations."),
]

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def encode(value):
    return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode("utf-8")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--candidate",type=Path)
    p.add_argument("--control",type=Path)
    p.add_argument("--assert-expected",action="store_true")
    p.add_argument("--only",nargs="+",choices=[x[0] for x in CASES])
    a=p.parse_args()
    project=a.project.resolve()
    a.out.mkdir(parents=True,exist_ok=False)
    definitions=[]
    contract_raw=(project/"protocol/contract.json").read_bytes()
    for name,status,summary,reason in CASES:
        if a.only and name not in a.only:
            continue
        d=a.out/"cases"/name
        (d/"input").mkdir(parents=True)
        contract=json.loads(contract_raw)
        for src in sorted((project/"runtime/exports/pass").glob("*.json")):
            (d/"input"/src.name).write_bytes(src.read_bytes())
        target=d/"input/P05-DEMO-001.json"
        obj=json.loads(target.read_bytes());ph=obj["phases"][0]
        if name=="run_subtests_integer_zero": obj["subtests"]=0
        elif name=="run_outcome_details_empty_object": obj["outcome_details"]={}
        elif name=="phase_failure_diagnosis_boolean_false": ph["failure_diagnosis_results"]=False
        elif name=="phase_subtest_name_empty_list": ph["subtest_name"]=[]
        elif name=="phase_diagnosis_results_explicit_null": ph["diagnosis_results"]=None
        elif name=="valid_explicit_empty_structures":
            for field in ["subtests","branches","checkpoints","diagnosers","diagnoses","outcome_details"]:obj[field]=[]
            for field in ["diagnosers","diagnosis_results","failure_diagnosis_results"]:ph[field]=[]
            ph["subtest_name"]=None
        elif name.startswith("contract_instrument_interval_policy_"):
            contract["instrument_policy"]["calibration_valid_until_millis"]=4102444799999 if name.endswith("conflict") else 4102444800000
        if not name.startswith("contract_"): target.write_bytes(encode(obj))
        raw=encode(contract) if name.startswith("contract_") else contract_raw
        (d/"contract.json").write_bytes(raw)
        definition={"case":name,"expected_status":status,"expected_summary":summary,"reason":reason,
                    "source_kind":"CONTROLLED_SYNTHETIC_MUTATION_OF_PUBLISHED_RECORD_OR_CONTRACT",
                    "expected_contract_sha256":sha(raw),"input_sha256":{f.name:sha(f.read_bytes()) for f in sorted((d/"input").glob("*.json"))}}
        (d/"EXPECTATION.json").write_bytes(encode(definition));definitions.append(definition)
    (a.out/"EXPECTATIONS_BEFORE_EXECUTION.json").write_bytes(encode(definitions))
    rows=[]
    for definition in definitions:
        d=a.out/"cases"/definition["case"]
        for label,relative in [("candidate","src/openhtf_adapter.py"),("control","control/competent_script.py")]:
            override = a.candidate if label == "candidate" else a.control
            script = override.resolve() if override else project/relative
            argv=[sys.executable,"-B",str(script),"--contract",str((d/"contract.json").resolve()),"--expected-contract-sha256",definition["expected_contract_sha256"],"--input-dir",str((d/"input").resolve())]
            proc=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
            (d/(label+".stdout.json")).write_bytes(proc.stdout)
            (d/(label+".stderr.txt")).write_bytes(proc.stderr)
            try:result=json.loads(proc.stdout)
            except (ValueError,UnicodeError):result={}
            observed=[result.get("status"),result.get("measurement_summary")]
            rows.append({"case":definition["case"],"program":label,"script_sha256":sha(script.read_bytes()),"returncode":proc.returncode,
                         "command_template":["python","-B",relative,"--contract","CASE/contract.json","--expected-contract-sha256",definition["expected_contract_sha256"],"--input-dir","CASE/input"],
                         "observed":observed,"expected":[definition["expected_status"],definition["expected_summary"]],
                         "expectation_met":observed==[definition["expected_status"],definition["expected_summary"]] and result.get("material_release_authorized") is False and proc.returncode in (0,2) and proc.stderr==b"",
                         "material_release_authorized":result.get("material_release_authorized"),"evidence_authentication":result.get("evidence_authentication"),
                         "issues":[x.get("code") for x in result.get("issues",[])],"stdout_sha256":sha(proc.stdout),"stderr_sha256":sha(proc.stderr)})
    summary={"schema":"p05-new-semantic-probes/1","kind":"NEW_CONSTRUCTED_CASES_NOT_FIELD_SAMPLE","cases":len(definitions),"executions":len(rows),
             "python":sys.version,"upstream_native_field_types":UPSTREAM_TYPES,"rows":rows,
             "historical_matrices_rerun":False,"physical_tests":0,"human_time_measured":False,"agent_in_decision_runtime":False}
    (a.out/"SUMMARY.json").write_bytes(encode(summary))
    print(json.dumps({"cases":len(definitions),"executions":len(rows),"rows":[{k:r[k] for k in ["case","program","observed","expected","expectation_met","issues"]} for r in rows]},ensure_ascii=False,indent=2))
    return 1 if a.assert_expected and not all(r["expectation_met"] for r in rows) else 0

if __name__=="__main__": raise SystemExit(main())
