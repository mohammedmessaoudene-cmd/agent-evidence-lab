"""Probe the published worker CLI under explicit real process encodings.

The child wrapper records its encodings, then runs the unchanged target module.
The wrapper does not change stdio, authorization, dispatch, exceptions or output.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import locale
import os
from pathlib import Path
import platform
import runpy
import sqlite3
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rows(path, table):
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in db.execute('SELECT * FROM "' + table + '"')]
    finally:
        db.close()


def state(root):
    return {"missions": rows(root / "coordinator.sqlite", "missions"),
            "obligations": rows(root / "coordinator.sqlite", "obligations"),
            "effects": rows(root / "provider.sqlite", "effects"),
            "provider_events": rows(root / "provider.sqlite", "events")}


def source_imports(source):
    sys.path.insert(0, str(source))
    sys.dont_write_bytecode = True
    os.environ["PYTHONPATH"] = str(source)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"


def child_worker(root, mode, subject, lose_ack, label, old_source=None):
    save(root / (label + ".encodings.json"), {
        "pid": os.getpid(), "preferred_encoding": locale.getpreferredencoding(False),
        "stdin_encoding": sys.stdin.encoding, "stdout_encoding": sys.stdout.encoding,
        "stderr_encoding": sys.stderr.encoding, "utf8_mode": sys.flags.utf8_mode,
        "no_site": sys.flags.no_site, "encoding_label_note": "ASCII labels request UTF8 disabled; actual Windows locale encoding is recorded, not assumed ASCII",
        "LC_ALL": os.environ.get("LC_ALL"), "LANG": os.environ.get("LANG"),
        "PYTHONUTF8": os.environ.get("PYTHONUTF8"),
        "PYTHONCOERCECLOCALE": os.environ.get("PYTHONCOERCECLOCALE")})
    if old_source is not None:
        target = old_source / "old_worker.py"
        sys.argv = [str(target), str(root), "--input", str(root / "old-request.json"),
                    "--mode", mode, "--ready", str(root / "old-ready.json"),
                    "--resume", str(root / "old-resume")]
        runpy.run_path(str(target), run_name="__main__")
        return
    sys.argv = ["p06_boundary.worker", str(root), "--mode", mode, "--subject", subject]
    if lose_ack:
        sys.argv.append("--lose-ack")
    runpy.run_module("p06_boundary.worker", run_name="__main__")


def launch(source, root, mode, enc, label, subject="A", lose_ack=False, old_cli=False):
    env = dict(os.environ)
    env.update(LC_ALL="C", LANG="C", PYTHONUTF8="1" if enc == "UTF-8" else "0",
               PYTHONCOERCECLOCALE="0", PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(source))
    argv = [sys.executable, "-S", "-B", str(Path(__file__).resolve()), "--source", str(source),
            "--child", str(root), "--mode", mode, "--subject", subject, "--label", label]
    if lose_ack:
        argv.append("--lose-ack")
    if old_cli:
        argv.append("--old-cli")
    started = time.time_ns()
    process = subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        stdout, stderr = process.communicate(timeout=20)
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()
    (root / (label + ".stdout.bin")).write_bytes(stdout)
    (root / (label + ".stderr.bin")).write_bytes(stderr)
    try:
        result = json.loads(stdout) if stdout else None
    except (ValueError, UnicodeError):
        result = None
    return {"argv": argv, "pid": process.pid, "returncode": process.returncode,
            "started_ns": started, "finished_ns": time.time_ns(), "result": result,
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(), "stdout_bytes": len(stdout),
            "stderr_sha256": hashlib.sha256(stderr).hexdigest(), "stderr_bytes": len(stderr),
            "stderr_text": stderr.decode("utf-8", errors="replace"),
            "encodings": json.loads((root / (label + ".encodings.json")).read_text(encoding="utf-8"))}


def run_case(source, root, mode, fixture_type, encoding, opaque=False, ack_loss=False):
    from p06_boundary.contract import example_manifest, normalize_manifest, envelope, import_envelope
    from p06_boundary.common import digest
    from p06_boundary.coordinator import Coordinator, initialize as coordinator_init
    from p06_boundary.provider import initialize as provider_init
    root.mkdir(parents=True, exist_ok=False)
    manifest = example_manifest("P06-transport-ascii")
    if fixture_type == "unicode":
        manifest["mission"] = "P06-transfert-é-🚀"
        manifest["memory"]["subject"] = "service-é-🚀"
        for obligation in manifest["obligations"]:
            obligation["payload"]["subject"] = manifest["memory"]["subject"]
            obligation["payload"]["label"] += "-confirmé-🚀"
    normalized = import_envelope(envelope(manifest)) if mode == "adapter" else normalize_manifest(manifest)
    save(root / "manifest.json", manifest)
    (root / "fixture.key").write_bytes(hashlib.sha256(b"P06 public Unicode transport fixture only").digest())
    provider_init(root / "provider.sqlite", {"lookup": False, "idempotency": False} if opaque else None)
    coordinator_init(root / "coordinator.sqlite", root / "fixture.key", manifest)
    worker = launch(source, root, mode, encoding, "initial", lose_ack=ack_loss)
    after = state(root)
    observation = {"case": ("I03_OPAQUE_ACK" if opaque else "I03_ATOMIC_ACK") if ack_loss else "I03_TRANSPORT", "mode": mode,
                   "fixture": fixture_type, "encoding_selected": encoding, "contract_valid": True,
                   "normalized_contract_sha256": digest(normalized), "worker": worker, "state": after,
                   "completed_two": bool(worker["returncode"] == 0 and worker["result"]
                       and worker["result"].get("status") == "COMPLETE"
                       and len(after["effects"]) == 2
                       and [o["status"] for o in after["obligations"]] == ["DONE", "DONE"])}
    if ack_loss:
        coord = Coordinator(root / "coordinator.sqlite", root / "fixture.key")
        current = coord.snapshot(manifest["mission"])
        coord.release(current["mission"], current["owner"], current["epoch"])
        observation["supervisor_releases"] = 1
        observation["restart"] = launch(source, root, mode, encoding, "restart", subject="B")
        observation["after_restart"] = state(root)
        observation["provider_exit73_observed_in_rpc_error"] = bool(worker["result"]
            and worker["result"].get("error") == "ACK_LOST"
            and "provider exit=73;" in worker["result"].get("detail", ""))
        if opaque:
            observation["unknown_preserved_without_retry"] = (
                observation["provider_exit73_observed_in_rpc_error"]
                and [o["status"] for o in after["obligations"]] == ["UNKNOWN", "PENDING"]
                and len(after["effects"]) == 1
                and [o["status"] for o in observation["after_restart"]["obligations"]] == ["UNKNOWN", "PENDING"]
                and len(observation["after_restart"]["effects"]) == 1
                and observation["restart"]["result"].get("error") == "UNRESOLVED_OUTCOME")
        else:
            observation["atomic_reconciled_after_lost_ack"] = (
                observation["provider_exit73_observed_in_rpc_error"]
                and [o["status"] for o in after["obligations"]] == ["INTENT", "PENDING"]
                and len(after["effects"]) == 1
                and [o["status"] for o in observation["after_restart"]["obligations"]] == ["DONE", "DONE"]
                and len(observation["after_restart"]["effects"]) == 2
                and observation["restart"]["result"].get("status") == "COMPLETE")
    save(root / "observation.json", observation)
    return observation


def old_cli_case(source, root, mode):
    from p06_boundary.contract import example_manifest
    from p06_boundary.common import rpc
    from p06_boundary.coordinator import Coordinator, initialize as coordinator_init
    from p06_boundary.provider import initialize as provider_init
    root.mkdir(parents=True, exist_ok=False)
    manifest = example_manifest("P06-old-cli-é-🚀")
    save(root / "manifest.json", manifest)
    (root / "fixture.key").write_bytes(hashlib.sha256(b"P06 old CLI public fixture").digest())
    provider_init(root / "provider.sqlite")
    coordinator_init(root / "coordinator.sqlite", root / "fixture.key", manifest)
    coordinator = Coordinator(root / "coordinator.sqlite", root / "fixture.key")
    claim = coordinator.acquire(manifest, "A")
    fence = rpc(root / "provider.sqlite", root / "fixture.key", {"op":"fence", "mission":claim["mission"], "grant":claim["grant"]})
    coordinator.activate(claim["mission"], "A", claim["epoch"], fence["fence_ack"])
    request = coordinator.prepare(claim["mission"], "01-reserve", "A", claim["epoch"])
    save(root / "old-request.json", {"schema":"p06-r2-boundary-envelope/1", "request":request} if mode == "adapter" else request)
    (root / "old-resume").write_text("resume\n", encoding="utf-8")
    process = launch(source, root, mode, "ASCII", "old-cli", old_cli=True)
    after = state(root)
    observation = {"case":"I03_OLD_CLI", "mode":mode, "worker":process, "state":after,
                   "old_cli_utf8_reply_received":bool(process["returncode"] == 0 and process["result"]
                       and process["result"].get("ok") is True and len(after["effects"]) == 1),
                   "scope":"Transport only; gate already released, no old-owner handover property tested."}
    save(root / "observation.json", observation)
    return observation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1] / "provider_boundary/src")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--phase", choices=["before", "intermediate", "after"], default="after")
    parser.add_argument("--child", type=Path)
    parser.add_argument("--mode", choices=["classic", "adapter"])
    parser.add_argument("--subject", default="A")
    parser.add_argument("--label", default="initial")
    parser.add_argument("--lose-ack", action="store_true")
    parser.add_argument("--old-cli", action="store_true")
    parser.add_argument("--only-old-cli", action="store_true")
    args = parser.parse_args(); source = args.source.resolve()
    source_imports(source)
    if args.child:
        child_worker(args.child.resolve(), args.mode, args.subject, args.lose_ack, args.label, source if args.old_cli else None)
        return
    if args.out is None:
        parser.error("--out required")
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    metadata = {"argv": sys.argv, "phase": args.phase, "python": sys.version,
                "platform": platform.platform(), "started_ns": time.time_ns(),
                "source": str(source),
                "protocol_sha256": hashlib.sha256((HERE / ("UNICODE_PROTOCOL.json" if args.phase == "before" else "UNICODE_CORRECTION_PROTOCOL.json")).read_bytes()).hexdigest(),
                "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "source_sha256": {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(source.rglob("*.py"))}}
    save(out / "run_metadata.json", metadata)
    observations = []
    for mode in ["classic", "adapter"]:
        if args.only_old_cli:
            observations.append(old_cli_case(source, out / (mode + "_old_cli_ASCII"), mode))
            continue
        for fixture_type, encoding in [("ascii", "ASCII"), ("unicode", "UTF-8"), ("unicode", "ASCII")]:
            observations.append(run_case(source, out / (mode + "_" + fixture_type + "_" + encoding), mode, fixture_type, encoding))
        if args.phase == "after":
            observations.append(run_case(source, out / (mode + "_atomic_ACK_ASCII"), mode, "unicode", "ASCII", ack_loss=True))
            observations.append(run_case(source, out / (mode + "_opaque_ACK_ASCII"), mode, "unicode", "ASCII", opaque=True, ack_loss=True))
            observations.append(old_cli_case(source, out / (mode + "_old_cli_ASCII"), mode))
    summary = {"project_id": "P06", "phase": args.phase, "observations": observations,
               "case_observations": len(observations), "completed_two": sum(o.get("completed_two", False) for o in observations),
               "unknown_preserved": sum(o.get("unknown_preserved_without_retry", False) for o in observations),
               "atomic_reconciled": sum(o.get("atomic_reconciled_after_lost_ack", False) for o in observations),
               "old_cli_utf8_reply_received": sum(o.get("old_cli_utf8_reply_received", False) for o in observations),
               "finished_ns": time.time_ns()}
    if args.phase == "after" and not args.only_old_cli:
        summary["status"] = "PASS" if (summary["case_observations"], summary["completed_two"],
            summary["unknown_preserved"], summary["atomic_reconciled"],
            summary["old_cli_utf8_reply_received"]) == (12, 6, 2, 2, 2) else "FAIL"
    else:
        summary["status"] = "OBSERVATION_ONLY"
    save(out / "summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "observations"}))
    return 1 if summary["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
