"""Offline P05 normalized trace checker. Run with python -B observer.py FOLDER."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys


COLLECTOR = Path(__file__).resolve().parents[1] / "pilot_r3" / "pilot_collect.py"
PILOT = runpy.run_path(str(COLLECTOR))
ROLES = ("acquisition", "publication", "gateway", "decision", "witness")
LIMIT = 128 * 1024


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def ident(value):
    require(isinstance(value, str) and 0 < len(value.strip()) <= 160, "invalid identifier")
    return value


def integer(value):
    require(type(value) is int and abs(value) < 2**63, "invalid integer")
    return value


def read_local(path):
    require(path.is_file() and not path.is_symlink(), "ordinary file required")
    with path.open("rb") as stream:
        raw = stream.read(LIMIT + 1)
    require(len(raw) <= LIMIT, "file exceeds limit")
    return raw


def read_bundle(folder):
    manifest = PILOT["strict_json"](read_local(folder / "manifest.json"))
    entries = manifest["artifacts"]
    require(isinstance(entries, list) and len(entries) == len(ROLES), "five sources required")
    for item in entries:
        require(item["id"] in ROLES and item["path"] == item["id"] + ".json", "source filename")
        require(0 < integer(item["bytes"]) <= LIMIT, "source size")
    files, errors, _ = PILOT["verify_artifacts"](entries, folder)
    require(not errors and set(files) == set(ROLES), "source identity mismatch")
    sources = {}
    for role in ROLES:
        raw = read_local(folder / files[role]["path"])
        require(hashlib.sha256(raw).hexdigest() == files[role]["sha256"], "source changed")
        sources[role] = PILOT["strict_json"](raw)
    return manifest, sources


def inspect(manifest, sources):
    require(manifest["schema"] == "p05-common-edge/1", "schema")
    scope = manifest["scope"]
    require(scope in ("SYNTHETIC", "CANDIDATE_EXPORT"), "scope")
    run = ident(manifest["run"])
    clock = ident(manifest["clock"])
    point = ident(manifest["point"])
    threshold = integer(manifest["low_below_uv"])
    tables = {}
    all_ids = set()
    for role in ROLES:
        src = sources[role]
        require(src["role"] == role and src["run"] == run and src["scope"] == scope, "source context")
        require(src["clock"] == clock, "clock mismatch")
        ident(src["device"])
        rows = src["rows"]
        require(isinstance(rows, list) and 1 <= len(rows) <= 256, "row count")
        table = {}
        for row in rows:
            rid = ident(row["id"])
            require(rid not in all_ids, "duplicate event")
            all_ids.add(rid)
            require(row["point"] == point and integer(row["t_ns"]) >= 0, "point or time")
            require(row.get("clock", clock) == clock, "clock mismatch")
            table[rid] = row
        tables[role] = table
    require(sources["witness"]["device"] != sources["acquisition"]["device"], "witness instrument reused")
    markers = set()
    declared_by_request = {}
    for a in tables["acquisition"].values():
        marker = (ident(a["boot"]), integer(a["seq"]))
        require(a["seq"] >= 0 and marker not in markers, "duplicate conversion")
        markers.add(marker)
        integer(a["uv"])
        trigger = ident(a["trigger"])
        declared_by_request.setdefault(trigger, []).append(a["id"])
    for p in tables["publication"].values():
        a = tables["acquisition"][p["acq"]]
        require(a["t_ns"] <= p["t_ns"] and integer(p["uv"]) == a["uv"], "publication mismatch")

    direct = set()
    request_ids = set()
    for g in tables["gateway"].values():
        p = tables["publication"][g["publication"]]
        a = tables["acquisition"][p["acq"]]
        request_id = ident(g["request"])
        require(request_id not in request_ids, "duplicate request")
        request_ids.add(request_id)
        started = integer(g["request_ns"])
        require(0 <= started <= g["t_ns"] and p["t_ns"] <= g["t_ns"], "fetch order")
        require(integer(g["uv"]) == p["uv"] and integer(g["acq_ns"]) == a["t_ns"], "fetch replaced acquisition")
        if g["origin"] == "DIRECT":
            require(a["id"] not in direct, "double direct attribution")
            require(started <= a["t_ns"] and a["trigger"] == request_id, "direct trigger mismatch")
            direct.add(a["id"])
        else:
            require(g["origin"] == "CACHE" and p["t_ns"] < started and a["trigger"] != request_id,
                    "cache origin mismatch")
        for conversion_id in declared_by_request.get(request_id, []):
            require(tables["acquisition"][conversion_id]["t_ns"] >= started,
                    "declared conversion predates request")

    used_responses, used_witnesses, edges = set(), set(), set()
    joined = []
    for d in tables["decision"].values():
        g = tables["gateway"][d["response"]]
        w = tables["witness"][d["witness"]]
        require(g["id"] not in used_responses and w["id"] not in used_witnesses, "double decision attribution")
        require(g["t_ns"] <= d["t_ns"] and d["request"] == g["request"], "unlinked decision")
        require(d["input_origin"] == g["origin"] and integer(d["input_uv"]) == g["uv"], "decision input mismatch")
        edge = ident(d["edge"])
        require(edge not in edges and w["edge"] == edge and w["t_ns"] == d["t_ns"], "witness edge mismatch")
        decision_error = integer(d["marker_error_ns"])
        witness_error = integer(w["marker_error_ns"])
        coverage = integer(w["envelope_half_width_ns"])
        require(min(decision_error, witness_error) >= 0 and coverage >= decision_error + witness_error,
                "witness envelope misses decision uncertainty")
        rule = ident(d["rule_id"])
        low = integer(w["lower_uv"])
        high = integer(w["upper_uv"])
        require(low <= high, "witness bounds")
        call = d["call"]
        require(call in ("LOW", "NORMAL", "UNKNOWN"), "unknown decision label")
        truth = "LOW" if high < threshold else "NORMAL" if low >= threshold else "UNKNOWN"
        consumed_id = tables["publication"][g["publication"]]["acq"]
        declared = declared_by_request.get(g["request"], [])
        joined.append({"decision": d["id"], "rule_id": rule, "origin": g["origin"], "reference": truth,
                       "request": g["request"], "consumed_conversion_id": consumed_id,
                       "declared_conversion_ids_for_request": declared,
                       "consumed_response_uses_conversion_triggered_by_request": consumed_id in declared,
                       "low_alarm_disagrees_with_reference": (truth == "NORMAL" and call == "LOW")
                       if truth != "UNKNOWN" else None})
        edges.add(edge)
        used_responses.add(g["id"])
        used_witnesses.add(w["id"])
    require(used_responses == set(tables["gateway"]) and used_witnesses == set(tables["witness"]),
            "unpaired decision or witness")
    return {"scope": scope, "status": "STRUCTURALLY_LINKED", "rows": joined,
            "acquisition_log_completeness": "UNKNOWN",
            "physical_test": "NOT_RUN", "physical_cache_false_alarms": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    try:
        result = inspect(*read_bundle(args.folder.resolve(strict=True)))
    except (OSError, ValueError, KeyError, TypeError, RecursionError, RuntimeError) as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc), "physical_test": "NOT_RUN",
                          "physical_cache_false_alarms": None}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
