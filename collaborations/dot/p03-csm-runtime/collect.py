"""Read a bounded observation privately and publish only validated evidence."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

LIMIT = 32768
PUBLIC_FIELDS = "d95260ecfd3610282483ebbfb2203ff1f98271a8cc38870ce2978af086d48300"
PUBLIC_NAMES = "5d62d906e65d16b76b3b79460c711894d04f5652fc1029efb9e82ebc5cbffade"
PUBLIC_ORDERED_TOOLS = "349a40e3804bbe16ffa3d5dd80a2fe1298f34b5cd7e3395a27162d5a8db30077"
PUBLIC_PAIRS = "5dc2b818b8b08f52833d78c1fa11f6e8ce2a4da036a91692b46493b65777f39d"
BEFORE = {"installed_product_id": 40, "location_id": 817, "status": "in_use"}
AFTER = {"installed_product_id": 40, "location_id": 692, "status": "in_use"}
STAGES = ("start", "startup", "seed", "catalog", "before", "write", "second_client", "sql", "complete")
OPTIONAL = {"database_id", "served_catalog", "before", "write_reply", "after", "official_verifier_count",
            "started_unix", "finished_unix", "error_type", "write_error_type"}
REQUIRED = {"outcome", "stage", "write_requests_started", "write_outcome", "second_client_initialized"}
READER = """
import os, stat, sys
fd = os.open('/tmp/dot-p03-receipt.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
with os.fdopen(fd, 'rb') as f:
    s = os.fstat(f.fileno())
    if not stat.S_ISREG(s.st_mode) or not 0 < s.st_size <= 32768: sys.exit(1)
    sys.stdout.buffer.write(f.read(32769))
"""


def require(condition):
    if not condition:
        raise ValueError("invalid observation")


def unique(pairs):
    require(len(dict(pairs)) == len(pairs))
    return dict(pairs)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def collect_bytes():
    command = ["timeout", "-k", "2", "8", "docker", "exec", "dot-p03-csm",
               "python", "-I", "-S", "-c", READER]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as child:
        data = child.stdout.read(LIMIT + 1)
        child.stdout.close()
        require(len(data) <= LIMIT and child.wait(timeout=12) == 0)
    return data


def catalog(raw):
    require(type(raw) is dict and set(raw) == {"count", "four_fields_by_name_sha256",
            "full_ordered_tools_sha256", "ordered_four_field_record_sha256", "ordered_tool_names_and_full_record_sha256"})
    count = raw["count"]
    pairs = raw["ordered_tool_names_and_full_record_sha256"]
    require(type(count) is int and 0 <= count <= 128 and type(pairs) is list and len(pairs) == count)
    for item in pairs:
        require(type(item) is list and len(item) == 2 and type(item[0]) is str
                and re.fullmatch(r"[a-z0-9_]{1,120}", item[0]) and type(item[1]) is str
                and re.fullmatch(r"[0-9a-f]{64}", item[1]))
    names = [item[0] for item in pairs]
    field_hashes = raw["ordered_four_field_record_sha256"]
    require(type(field_hashes) is list and len(field_hashes) == count and all(
            type(item) is str and re.fullmatch(r"[0-9a-f]{64}", item) for item in field_hashes))
    field_pairs = [[name, h] for name, h in zip(names, field_hashes, strict=True)]
    for key in ("four_fields_by_name_sha256", "full_ordered_tools_sha256"):
        require(type(raw[key]) is str and re.fullmatch(r"[0-9a-f]{64}", raw[key]))
    out = {"count": count, "ordered_public_names_match": digest(names) == PUBLIC_NAMES,
           "public_fields_match": raw["four_fields_by_name_sha256"] == PUBLIC_FIELDS and digest(field_pairs) == PUBLIC_PAIRS,
           "full_ordered_records_match": raw["full_ordered_tools_sha256"] == PUBLIC_ORDERED_TOOLS}
    if out["public_fields_match"]:
        out["four_fields_by_name_sha256"] = PUBLIC_FIELDS
        out["ordered_tool_names_and_four_field_sha256"] = field_pairs
    if out["full_ordered_records_match"]:
        out["full_ordered_tools_sha256"] = PUBLIC_ORDERED_TOOLS
    if digest(pairs) == PUBLIC_PAIRS:
        out["ordered_tool_names_and_full_record_sha256"] = pairs
    elif out["ordered_public_names_match"]:
        out["ordered_tool_names"] = names
    return out


def observation(data, exercise_result):
    require(0 < len(data) <= LIMIT)
    raw = json.loads(data.decode("utf-8"), object_pairs_hook=unique)
    require(type(raw) is dict and REQUIRED <= raw.keys() <= REQUIRED | OPTIONAL)
    require(raw["stage"] in STAGES and type(raw["write_requests_started"]) is int
            and raw["write_requests_started"] in (0, 1) and type(raw["second_client_initialized"]) is bool)
    require(raw["outcome"] in ("PERSISTED_PRODUCT_40_OBSERVED", "INCOMPLETE"))
    require(raw["write_outcome"] in ("NOT_RUN", "OUTCOME_PENDING", "ACKNOWLEDGED"))
    out = {k: raw[k] for k in ("stage", "write_requests_started", "write_outcome", "second_client_initialized")}
    for key in ("started_unix", "finished_unix"):
        if key in raw:
            require(type(raw[key]) is int and 0 < raw[key] < 4102444800)
    for key in ("error_type", "write_error_type"):
        if key in raw:
            require(type(raw[key]) is str and re.fullmatch(r"[a-zA-Z]{1,80}", raw[key]))
            out[key] = raw[key] if raw[key] in ("ValueError", "KeyError", "TypeError", "TimeoutError",
                    "HTTPError", "HTTPStatusError", "ConnectionError", "JSONDecodeError") else "UNCLASSIFIED"
    if "database_id" in raw:
        db = raw["database_id"]
        require(type(db) is str and re.fullmatch(r"db_[0-9]{13}_[a-z0-9]{9}", db))
        out["database_id_sha256"] = hashlib.sha256(db.encode("ascii")).hexdigest()
    if "served_catalog" in raw:
        out["served_catalog"] = catalog(raw["served_catalog"])
    for key in ("before", "write_reply", "after"):
        if key in raw:
            row = raw[key]
            require(type(row) is dict and set(row) == set(BEFORE) and type(row["installed_product_id"]) is int
                    and type(row["location_id"]) is int and type(row["status"]) is str)
            out[key] = BEFORE.copy() if row == BEFORE else AFTER.copy() if row == AFTER else "UNEXPECTED_ROW"
    if "official_verifier_count" in raw:
        n = raw["official_verifier_count"]
        require(type(n) is int and n in (0, 1))
        out["official_verifier_count"] = n
    served = out.get("served_catalog", {})
    complete = (exercise_result == "success" and raw["outcome"] == "PERSISTED_PRODUCT_40_OBSERVED"
                and out["stage"] == "complete" and "database_id_sha256" in out and served.get("count") == 89
                and served.get("public_fields_match") and served.get("ordered_public_names_match")
                and out.get("before") == BEFORE and out["write_requests_started"] == 1
                and out["write_outcome"] == "ACKNOWLEDGED" and out.get("write_reply") == AFTER
                and out["second_client_initialized"] and out.get("after") == AFTER
                and out.get("official_verifier_count") == 1 and "error_type" not in out and "write_error_type" not in out)
    out["outcome"] = "PERSISTED_PRODUCT_40_OBSERVED" if complete else "INCOMPLETE"
    return out


def main():
    steps = {k: os.environ[k] for k in ("CHECKOUT_RESULT", "INPUT_RESULT", "STARTUP_RESULT", "EXERCISE_RESULT")}
    require(all(s in ("success", "failure", "cancelled", "skipped") for s in steps.values()))
    result = steps["EXERCISE_RESULT"]
    out = {"outcome": "NOT_RUN" if result == "skipped" else "OUTCOME_UNKNOWN"}
    if result != "skipped":
        try:
            out = observation(collect_bytes(), result)
        except (ValueError, OSError, KeyError, TypeError, RecursionError, subprocess.SubprocessError):
            out["receipt_error"] = "REJECTED_OR_UNAVAILABLE"
    receipt = {"commit": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
               "attempt": os.environ["GITHUB_RUN_ATTEMPT"], "runner_label": "ubuntu-24.04",
               "image": os.environ["IMAGE"], "expected_image_config": os.environ["EXPECTED_CONFIG"],
               "fixture_sha256": "71c8e714b920a0f67abd16f06c29818284b741608e0fa3f1a28c1f331aa9e6dc",
               "steps": steps, "observation": out}
    path = Path(os.environ["RUNNER_TEMP"]) / "dot-p03-receipt.json"
    path.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return int(result == "success" and out["outcome"] != "PERSISTED_PRODUCT_40_OBSERVED")


if __name__ == "__main__":
    raise SystemExit(main())
