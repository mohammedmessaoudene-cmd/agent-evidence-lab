"""Fetch pinned public inputs for the isolated CSM exercise."""
import hashlib
import io
import json
from pathlib import Path
import sys
from urllib.request import urlopen
from zipfile import ZipFile

UPSTREAM = "https://raw.githubusercontent.com/ServiceNow/EnterpriseOps-Gym/271f2c357f763376997dfd16807fcde2474ae41b/"
TASK = "data/revised/csm/task_20251205_154853_044_d4a463c3_fce76046.json"
SEED = "Domain Wise DBs and Task-DB Mappings/csm/dbs/db_1762254390925_u5icw4thh.sql"
SEED_SHA = "71c8e714b920a0f67abd16f06c29818284b741608e0fa3f1a28c1f331aa9e6dc"


def checked(data, expected):
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("public input digest mismatch")
    return data


def download(path, expected):
    with urlopen(UPSTREAM + path, timeout=60) as response:
        return checked(response.read(15_000_001), expected)


def prepare(directory):
    directory.mkdir()
    task = download(TASK, "3cc8440866e8b75d7473ce8154c90b77b9aa1a9df990801b0142f5fdef5636bc")
    server, = json.loads(task)["gym_servers_config"]
    if server["seed_database_file"] != SEED:
        raise ValueError("unexpected case fixture")
    archive = download("gym_dbs.zip", "d947543d4fba1aabc4aade73d3df955114187b7a94da7ac825c4c31169ddab47")
    with ZipFile(io.BytesIO(archive)) as bundle:
        member, = (m for m in bundle.infolist() if m.filename == SEED and m.file_size == 1376655)
        (directory / "seed.sql").write_bytes(checked(bundle.read(member), SEED_SHA))
    (directory / "task.json").write_bytes(task)
    client = download("benchmark/mcp_client.py", "8c7226cf2c0bdad42c742668640c4606a38277a1ec09eb4823cd840c94477b4d")
    (directory / "mcp_client.py").write_bytes(client)
    script = Path(__file__).with_name("exercise.py")
    (directory / script.name).write_bytes(script.read_bytes())


if __name__ == "__main__":
    prepare(Path(sys.argv[1]))
