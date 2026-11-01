#!/usr/bin/env python3
"""Compare two actual JSON parsers on one bounded P06 transfer corpus.

No workflow execution and no imported P06 safety code. The joint admission guard
is explicit; the two permissive parsers alone are deliberately not called safe.
"""
from __future__ import annotations
import argparse, copy, datetime, hashlib, json, math, platform, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAFE_INT = 2**53 - 1
KINDS = {"hash_file", "verify_json", "write_audit_receipt"}

def strict_load(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError("DUPLICATE_MEMBER")
            out[key] = value
        return out
    value = json.loads(raw, object_pairs_hook=pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE")))
    def walk(v):
        if isinstance(v, str):
            v.encode("utf-8", errors="strict")
        elif type(v) is int and abs(v) > SAFE_INT:
            raise ValueError("UNSAFE_INTEGER")
        elif type(v) is float and (not math.isfinite(v) or v.is_integer() and abs(v) > SAFE_INT):
            raise ValueError("NONFINITE_OR_UNSAFE_INTEGER")
        elif isinstance(v, list):
            for x in v: walk(x)
        elif isinstance(v, dict):
            for k, x in v.items(): walk(k); walk(x)
    walk(value)
    return value

def admit(value):
    if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise ValueError("SCHEMA_VERSION")
    if value.get("mission_id") != "P06": raise ValueError("MISSION_MISMATCH")
    mem = value.get("memory", {})
    for key, expected in [("name", "p06_recovery"), ("type", "object"), ("version", 1)]:
        if type(mem.get(key)) is not type(expected) or mem[key] != expected:
            raise ValueError("MEMORY_" + key.upper())
    if not isinstance(mem.get("data"), dict): raise ValueError("MEMORY_DATA")
    seen = set()
    for ob in value.get("obligations", []):
        if ob["id"] in seen: raise ValueError("DUPLICATE_OBLIGATION")
        seen.add(ob["id"])
        if ob["status"] not in {"PENDING", "DONE", "UNKNOWN", "BLOCKED"}:
            raise ValueError("OBLIGATION_STATUS")
        if ob["status"] == "PENDING" and ob["kind"] not in KINDS:
            raise ValueError("UNKNOWN_EXECUTABLE_OBLIGATION")
    # Claims remain data. Execution policy is independently loaded by receiver.
    return {"mission_id": value["mission_id"],
            "pending_ids": [x["id"] for x in value["obligations"] if x["status"] == "PENDING"],
            "unresolved_ids": [x["id"] for x in value["obligations"] if x["status"] in {"UNKNOWN", "BLOCKED"}],
            "effective_actions_from_external_policy_only": sorted(KINDS),
            "claims_grant_authority": False}

def describe(value):
    try:
        semantic_sha = hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode("utf8")).hexdigest()
    except (UnicodeError, ValueError):
        semantic_sha = None
    def visit(x):
        if isinstance(x, dict): return {k: visit(v) for k,v in x.items()}
        if isinstance(x, list): return [visit(v) for v in x]
        if isinstance(x, float) and not math.isfinite(x): return {"nonfinite": str(x)}
        if type(x) is int and abs(x) > SAFE_INT: return {"unsafe_integer_decimal": str(x)}
        if isinstance(x, str):
            try: x.encode("utf8")
            except UnicodeError: return {"unpaired_surrogate": True}
        return x
    normalized = visit(value)
    return {"accepted":True, "bounded_canonical_sha256":semantic_sha, "probe":normalized.get("memory",{}).get("data",{}).get("parser_probe"),
            "obligation_count":len(value.get("obligations",[])), "mission_id":value.get("mission_id")}

def cases(base, source_text=None):
    def dump(x): return json.dumps(x, ensure_ascii=True, separators=(",", ":"))
    # The real-source case MUST retain the original bytes. Re-encoding here can
    # erase duplicate members before the strict admission guard sees them.
    result=[("actual_p06_dossier", source_text if source_text is not None else dump(base), True)]
    for key,val in [("name","another_memory"),("type","text"),("version",2)]:
        d=copy.deepcopy(base);d["memory"][key]=val
        result.append(("memory_"+key+"_incompatible",dump(d),False))
    d=copy.deepcopy(base);d["mission_id"]="P07"
    result.append(("other_mission_id",dump(d),False))
    d=copy.deepcopy(base);d["obligations"][0]["kind"]="unknown_required_operation"
    result.append(("unknown_pending_obligation",dump(d),False))
    d=copy.deepcopy(base);d["obligations"].append(copy.deepcopy(d["obligations"][0]))
    result.append(("duplicate_obligation_id",dump(d),False))
    d=copy.deepcopy(base);d["authorization_claims"]["allowed_in_current_session"].append("Contact a person")
    result.append(("forged_permission_is_only_data",dump(d),True))
    raw=dump(base)
    result.append(("duplicate_mission_member",raw.replace('"mission_id":"P06"','"mission_id":"P07","mission_id":"P06"',1),False))
    for name,token in [("overflow_exponent","1e400"),("unsafe_integer","9007199254740993"),("named_nan","NaN"),("unpaired_surrogate",'"\\ud800"')]:
        d=copy.deepcopy(base);d["memory"]["data"]["parser_probe"]="TOKEN_PLACEHOLDER"
        result.append((name,dump(d).replace('"TOKEN_PLACEHOLDER"',token),False))
    d=copy.deepcopy(base);d["memory"]["data"]["parser_probe"]="évidence compatible"
    result.append(("valid_unicode",dump(d),True))
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--out",type=Path,required=True);args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    raw_source=(ROOT/"handoff/dossier.json").read_bytes()
    corpus=cases(json.loads(raw_source), raw_source.decode("utf8"))
    protocol={"experiment":"R2_TWO_PARSERS","seed":2601106,"frozen_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
      "dossier_sha256":hashlib.sha256(raw_source).hexdigest(),"python":sys.version,"platform":platform.platform(),
      "question":"Do the same bytes preserve meaning under Python json and actual Node JSON.parse; does a strict joint gate retain unresolved work without granting authority?",
      "cases":[{"name":n,"expected_admitted":e,"sha256":hashlib.sha256(r.encode()).hexdigest()} for n,r,e in corpus],
      "limits":["Not runtime takeover; actual host recorded separately","Common explicit joint guard; raw parsers are permissive","No effect or network action occurs in this experiment"]}
    p=args.out/"protocol.json";p.write_text(json.dumps(protocol,indent=2)+"\n")
    (args.out/"protocol.sha256").write_text(hashlib.sha256(p.read_bytes()).hexdigest()+"\n")
    rows=[]
    for name,raw,expected in corpus:
        wire=raw.encode("utf8")
        saved=args.out/(name+".json.txt");saved.write_bytes(wire)
        try: py=describe(json.loads(wire))
        except Exception as exc: py={"accepted":False,"error":type(exc).__name__}
        node=subprocess.run(["node",str(ROOT/"handoff/node_parser.cjs")],input=wire,capture_output=True,check=True)
        js=json.loads(node.stdout)
        digest=hashlib.sha256(wire).hexdigest()
        byte_evidence={"python_input_sha256":digest,"saved_file_sha256":hashlib.sha256(saved.read_bytes()).hexdigest(),
                       "node_stdin_sha256":js["received_sha256"],"python_input_bytes":len(wire),
                       "saved_file_bytes":saved.stat().st_size,"node_stdin_bytes":js["received_bytes"]}
        bytes_match=(byte_evidence["saved_file_sha256"]==digest==byte_evidence["node_stdin_sha256"]
                     and byte_evidence["saved_file_bytes"]==len(wire)==byte_evidence["node_stdin_bytes"])
        try:
            val=strict_load(raw); meaning=admit(val)
            if not js["accepted"]: raise ValueError("SECOND_PARSER_REJECTED")
            if py["bounded_canonical_sha256"] != js["bounded_canonical_sha256"]:
                raise ValueError("PARSER_MEANING_DISAGREEMENT")
            admitted=True; reason="ADMITTED_BY_BOUNDED_GUARD"
        except (ValueError,UnicodeError,KeyError,TypeError) as exc:
            admitted=False;meaning=None;reason=str(exc)
        rows.append({"name":name,"python_raw":py,"node_raw":js,"joint_admitted":admitted,
                     "reason":reason,"meaning":meaning,"expected":expected,"byte_evidence":byte_evidence,"identical_bytes":bytes_match,"pass":admitted==expected and bytes_match})
    result={"experiment":"R2_TWO_PARSERS","cases":len(rows),"expected_results":sum(x["pass"] for x in rows),
      "rows":rows,"windows_execution":"EXECUTED_THIS_RUN" if platform.system()=="Windows" else "NOT_RUN","actual_codex_receipt":"UNKNOWN","runtime_execution":False,
      "interpretation":"A rejected incompatible/ambiguous dossier is an expected result, not a completed mission. UNKNOWN and BLOCKED obligations stay unresolved. Raw parsing is insufficient."}
    (args.out/"result.json").write_text(json.dumps(result,ensure_ascii=True,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="rows"},indent=2))
    return 0 if all(x["pass"] for x in rows) else 1

if __name__=="__main__": raise SystemExit(main())
