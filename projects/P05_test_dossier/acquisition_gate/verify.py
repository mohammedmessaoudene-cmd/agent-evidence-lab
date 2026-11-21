"""Replay the four expected JSON outputs with Python 3.11+."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent


def execute(*args, exit_code=0):
    run = subprocess.run([sys.executable, "-E", "-s", "-B", *args], cwd=HERE, capture_output=True)
    if run.returncode != exit_code or run.stderr:
        raise RuntimeError(f"{args[0]} exited {run.returncode}: {run.stderr.decode(errors='replace')}")
    return json.loads(run.stdout)


def encode(path, obj):
    path.write_bytes((json.dumps(obj, indent=2) + "\n").encode("utf-8"))


def main():
    expected = json.loads((HERE / "EXPECTED.json").read_bytes())
    results = {"controls": execute("controls.py"),
               "cli_fixture": execute("observer.py", "SYNTHETIC")}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "candidate"
        shutil.copytree(HERE / "SYNTHETIC", root)
        path = root / "acquisition.json"
        acquisitions = json.loads(path.read_bytes())
        acquisitions["rows"].append(dict(acquisitions["rows"][0], id="A2", seq=2,
                                         trigger="Q2", t_ns=51, uv=121))
        encode(path, acquisitions)
        manifest = json.loads((root / "manifest.json").read_bytes())
        entry = next(item for item in manifest["artifacts"] if item["id"] == "acquisition")
        raw = path.read_bytes()
        entry.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        encode(root / "manifest.json", manifest)
        results["cli_q2_declares_a2_consumes_a1"] = execute("observer.py", str(root))
        with (root / "witness.json").open("ab") as stream:
            stream.write(b" ")
        results["cli_modified_byte"] = execute("observer.py", str(root), exit_code=2)

    if expected.keys() != results.keys():
        raise ValueError("Expected output set differs")
    for name, result in results.items():
        if result != expected[name]:
            raise ValueError(f"Output differs: {name}")
    print(json.dumps({"scope": "SYNTHETIC", "named_controls": len(results["controls"]["controls"]),
                      "additional_byte_integrity_control": "REJECTED_AS_EXPECTED",
                      "expected_outputs_reproduced": len(results), "physical_test": "NOT_RUN"}))


if __name__ == "__main__":
    main()
