"""Prepare the pinned public Avery fixture for one disposable CSM exercise."""
import hashlib
import io
import json
from pathlib import Path
import sys
from urllib.request import urlopen
from zipfile import ZipFile

import pyarrow.parquet as pq

SOURCE = "https://raw.githubusercontent.com/ServiceNow/EnterpriseOps-Gym/271f2c357f763376997dfd16807fcde2474ae41b/"
ORACLE = "https://huggingface.co/datasets/ServiceNow-AI/EnterpriseOps-Gym/resolve/c8e538eae8a6205294f0a86675fefdc1fac408f6/oracle/csm-00000-of-00001.parquet"
TASK = "task_20251208_123126_960_c4ad7a70_f974dae7"
PARQUET_SHA = "1b5948db2db3cc0dc643f7fddcbb90c2ac09489615f369b4fe3abbdcd484d697"
ARCHIVE_SHA = "d947543d4fba1aabc4aade73d3df955114187b7a94da7ac825c4c31169ddab47"
CLIENT_SHA = "8c7226cf2c0bdad42c742668640c4606a38277a1ec09eb4823cd840c94477b4d"
SEED_SHA = "71c8e714b920a0f67abd16f06c29818284b741608e0fa3f1a28c1f331aa9e6dc"
ROW_SHA = "7700d6aede4ca86d4319b237aa3be7a9610b80c658e747f993d0d1e78a108a98"
COLUMNS = ("task_id", "system_prompt", "user_prompt", "selected_tools", "verifiers", "gym_servers_config")


def checked(value, digest):
    if hashlib.sha256(value).hexdigest() != digest:
        raise ValueError("input digest mismatch")
    return value


def download(url, limit):
    with urlopen(url, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("input size limit")
    return data


def prepare(directory, parquet, archive, client):
    table = pq.read_table(io.BytesIO(checked(parquet, PARQUET_SHA)), columns=list(COLUMNS))
    row = table.slice(35, 1).to_pylist()[0]
    canonical = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    checked(canonical, ROW_SHA)
    if row["task_id"] != TASK:
        raise ValueError("Oracle row")
    server, = json.loads(row["gym_servers_config"])
    rules = [item["validation_config"] for item in json.loads(row["verifiers"])]
    if len(rules) != 2 or not all(rule["query"].startswith("SELECT COUNT(*)") and
            rule["comparison_type"] == "equals" and rule["expected_value"] == 1 for rule in rules):
        raise ValueError("Oracle queries")
    with ZipFile(io.BytesIO(checked(archive, ARCHIVE_SHA))) as bundle:
        member, = [m for m in bundle.infolist() if m.filename == server["seed_database_file"]]
        seed = checked(bundle.read(member), SEED_SHA)
    checked(client, CLIENT_SHA)
    directory.mkdir()
    (directory / "seed.sql").write_bytes(seed)
    (directory / "mcp_client.py").write_bytes(client)
    (directory / "exercise.py").write_bytes(Path(__file__).with_name("exercise.py").read_bytes())
    (directory / "task.json").write_text(json.dumps({
        "context": server["context"], "queries": [r["query"] for r in rules]
    }), encoding="utf-8")


if __name__ == "__main__":
    prepare(Path(sys.argv[1]), download(ORACLE, 160_000), download(SOURCE + "gym_dbs.zip", 15_000_000),
            download(SOURCE + "benchmark/mcp_client.py", 65_536))
