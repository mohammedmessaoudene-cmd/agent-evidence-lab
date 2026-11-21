"""Read the disposable observation and retain only bounded evidence."""
import json
import os
from pathlib import Path
import re
import subprocess

STAGES = ("startup", "seed", "before", "create_case", "read_case", "register_interaction", "read_interaction", "complete")
STATUSES = ("NOT_RUN", "OUTCOME_PENDING", "ACKNOWLEDGED")
READER = """
import os, stat, sys
fd = os.open('/tmp/dot-p03-receipt.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
with os.fdopen(fd, 'rb') as f:
    info = os.fstat(f.fileno())
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 2048: sys.exit(1)
    sys.stdout.buffer.write(f.read(2049))
"""


def require(value):
    if not value:
        raise ValueError("invalid observation")


def unique(pairs):
    require(len(dict(pairs)) == len(pairs))
    return dict(pairs)


def observation(data, success):
    require(0 < len(data) <= 2048)
    raw = json.loads(data.decode("utf-8"), object_pairs_hook=unique)
    required = {"stage", "case_write", "interaction_write"}
    optional = {"database_id_sha256", "served_schemas_match", "before", "after_case", "after_interaction",
                "case_id", "case_number", "interaction_id"}
    require(type(raw) is dict and required <= raw.keys() <= required | optional)
    require(raw["stage"] in STAGES and raw["case_write"] in STATUSES and raw["interaction_write"] in STATUSES)
    if "database_id_sha256" in raw:
        require(type(raw["database_id_sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", raw["database_id_sha256"]))
    if "served_schemas_match" in raw:
        require(raw["served_schemas_match"] is True)
    for key in ("before", "after_case", "after_interaction"):
        if key in raw:
            require(type(raw[key]) is list and len(raw[key]) == 2 and
                    all(type(n) is int and 0 <= n <= 10000 for n in raw[key]))
    if "case_id" in raw:
        require(type(raw["case_id"]) is int and raw["case_id"] == 1233)
    if "case_number" in raw:
        require(raw["case_number"] == "CS-0001233")
    if "interaction_id" in raw:
        require(type(raw["interaction_id"]) is int and 0 < raw["interaction_id"] <= 2**31-1)
    good = (success and raw.keys() == required | optional and raw["stage"] == "complete"
            and raw["case_write"] == raw["interaction_write"] == "ACKNOWLEDGED"
            and raw["before"] == [0, 0] and raw["after_case"] == [1, 0] and raw["after_interaction"] == [1, 1])
    return {**raw, "outcome": "CASE_AND_INTERACTION_OBSERVED" if good else "INCOMPLETE"}


def main():
    stages = {k: os.environ[k] for k in ("CHECKOUT_RESULT", "INPUT_RESULT", "STARTUP_RESULT", "EXERCISE_RESULT")}
    require(all(v in ("success", "failure", "cancelled", "skipped") for v in stages.values()))
    attempted = stages["EXERCISE_RESULT"] != "skipped"
    result = {"outcome": "OUTCOME_UNKNOWN" if attempted else "NOT_RUN"}
    if attempted:
        try:
            with subprocess.Popen(["timeout", "-k", "2", "8", "docker", "exec", "dot-p03-csm",
                                   "python", "-I", "-S", "-c", READER], stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL) as child:
                data = child.stdout.read(2049)
                child.stdout.close()
                require(child.wait(timeout=12) == 0)
            result = observation(data, all(v == "success" for v in stages.values()))
        except (ValueError, TypeError, OSError, KeyError, RecursionError, subprocess.SubprocessError):
            result["receipt_error"] = "REJECTED_OR_UNAVAILABLE"
    receipt = {"task_id": "task_20251208_123126_960_c4ad7a70_f974dae7", "oracle_row_zero_based": 35,
               "oracle_sha256": "1b5948db2db3cc0dc643f7fddcbb90c2ac09489615f369b4fe3abbdcd484d697",
               "seed_sha256": "71c8e714b920a0f67abd16f06c29818284b741608e0fa3f1a28c1f331aa9e6dc",
               "commit": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
               "attempt": os.environ["GITHUB_RUN_ATTEMPT"], "image": os.environ["IMAGE"],
               "image_config": os.environ["EXPECTED_CONFIG"], "steps": stages, "observation": result}
    dest = Path(os.environ["RUNNER_TEMP"]) / "dot-p03-receipt.json"
    dest.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return int(stages["EXERCISE_RESULT"] == "success" and result["outcome"] != "CASE_AND_INTERACTION_OBSERVED")


if __name__ == "__main__":
    raise SystemExit(main())
