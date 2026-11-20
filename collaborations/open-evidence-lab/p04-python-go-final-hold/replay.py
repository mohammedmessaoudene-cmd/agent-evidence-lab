"""Replay the offline Python/Go comparison using a pinned #553 source zip."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
COMMIT = "9136dbe3c296e2929a4cbb85dc4e54937e74b193"
ARCHIVE = "d55ee487bdfcd5719f98176400d62714e4ac36142bb6f392b593ed070f63b665"
CORPUS = Path("corpora/vectors-execution-billing-finality")
READER = Path("packaging/agent_evidence_vectors/executionbilling.py")
MUTANT = "final-invoice-retains-remainder"
MEMBER = "f05-final-invoice-retains-remainder"
LATE = "held_after_final_billing"
EARLY = "held_released_before_final_billing"
ALLOW = "finality_held"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def execute(cmd, root, env, codes=(0,)):
    r = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True, timeout=600)
    if r.returncode not in codes:
        raise RuntimeError(f"{cmd!r} exited {r.returncode}\n{r.stdout}\n{r.stderr}")
    return r


def extract(archive, root):
    with ZipFile(archive) as z:
        for member in z.infolist():
            if member.is_dir():
                continue
            prefix, path = member.filename.split("/", 1)
            assert prefix == "agent-evidence-vectors-" + COMMIT
            rel = Path(path)
            go_source = (rel.parent.as_posix() in ("corpusreaders", "aee", "observedeffect")
                         and path.endswith(".go") and not path.endswith("_test.go"))
            if (go_source or path.startswith(CORPUS.as_posix() + "/") or
                path in ("go.mod", "LICENSE", "corpusreaders/executionbilling_test.go",
                         READER.as_posix(), "packaging/agent_evidence_vectors/__init__.py",
                         "packaging/agent_evidence_vectors/executionbilling_runtime.py")):
                dest = root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(member))


def make_records(root, records, work, env):
    corpus = root / CORPUS
    manifest = json.loads((corpus / "MANIFEST.json").read_bytes())
    scenario = next(v["runtime"]["scenario"] for v in manifest["vectors"]
                    if v["id"] == "allow-f01-control-final-invoice")
    assert scenario["id"] == "F05" and scenario["probes"] == []
    scenario.update(id="F05-with-second-reservation", probes=[
        {"cmd": "reserve", "amount": 2, "attempt": "B"}])
    scenario_file = work / "scenario.json"
    save(scenario_file, scenario)
    source = (corpus / "tests/p04/exposure_ledger.py").read_bytes()
    old = (b'remainder = 0 if row["billing_finality"] == "FINAL" else '
           b'max(0, row["authorized_max"] - row["known"])')
    assert source.count(old) == 1
    variants = {"reference": source, "stuck_hold": source.replace(old, b'remainder = '
                b'max(0, row["authorized_max"] - row["known"])'),
                "early_release": source.replace(old, old.replace(
                    b'== "FINAL"', b'== "FINAL" or row["outcome"] == "SUCCEEDED"'))}
    observations = {}
    for name, source in variants.items():
        ledger = work / (name + ".py")
        ledger.write_bytes(source)
        cmd = [sys.executable, "-B", str(corpus / "tests/billing_adapter.py"),
               str(scenario_file), "--json", "--source", str(ledger)]
        record = json.loads(execute(cmd, root, env).stdout)
        assert record["sourceSha256"] == digest(ledger)
        assert record["reopened"] == record["observed"] and record["endReopened"] == record["end"]
        probe = record["probes"][0]
        if probe["exception"] == "AdmissionDenied":
            admission = "refused"
        else:
            assert probe["exception"] is None and probe["return"]["newlyReserved"] is True
            admission = "admitted"
        fields = ("heldMicroUsd", "knownSpendMicroUsd", "availableMicroUsd")
        observations[name] = {"beforeB": [record["reopened"][k] for k in fields],
                              "reservationB": admission, "ledgerSha256": digest(ledger)}
        save(records / (name + ".json"), record)
    assert [(observations[x]["beforeB"], observations[x]["reservationB"])
            for x in variants] == [([0, 1, 2], "admitted"), ([1, 1, 1], "refused"),
                                   ([0, 1, 2], "admitted")]
    conflict = corpus / "cases/allow-x5-non-dispatch-after-cost-conflict/record.json"
    state = json.loads(conflict.read_bytes())["end"]
    assert state["billingFinality"] == "CONFLICT" and state["heldMicroUsd"] == 1
    shutil.copyfile(conflict, records / "conflict.json")
    return observations


def compare(root, records, work, output, env, go, phase):
    corpus = root / CORPUS
    target = {"reference": ALLOW, "conflict": ALLOW, "early_release": EARLY,
              "stuck_hold": ALLOW if phase == "before" else LATE,
              "member": ALLOW if phase == "before" else LATE}
    python_rows = {}
    for path in sorted(records.glob("*.json")):
        run = execute([sys.executable, "-B", str(root / READER), str(path), "--json"],
                      root, env, (0, 1))
        verdict = json.loads(run.stdout)
        reason = target[path.stem]
        assert verdict == {"decision": "allow" if reason == ALLOW else "deny", "reason": reason}
        assert run.returncode == int(reason != ALLOW)
        python_rows[path.stem] = verdict
    cli = execute([sys.executable, "-B", str(root / READER)], root, env).stdout.strip()
    count = 31 if phase == "before" else 32
    assert cli == f"answered {count} of {count} cases", cli
    # Omit upstream's external test file here: the harness calls the native
    # package functions and its public Judge entry point without ancillary tests.
    native_test = root / "corpusreaders/executionbilling_test.go"
    deferred = work / "deferred_go_test"
    native_test.rename(deferred)
    try:
        run = execute([go, "test", "-count=1", "-v", "./corpusreaders",
                       "-run", "^TestP04FinalHoldProbe$"], root, env)
    finally:
        deferred.rename(native_test)
    (output / (phase + "_go.log")).write_bytes(run.stdout.encode())
    go_rows = {}
    for line in run.stdout.splitlines():
        if line.startswith("P04_RECORD "):
            value = json.loads(line.removeprefix("P04_RECORD "))
            go_rows[Path(value.pop("case")).stem] = value
    assert go_rows == python_rows and f"P04_CORPUS {count}" in run.stdout.splitlines()
    return {"python": python_rows, "go": go_rows, "pythonCorpus": cli, "goCorpus": count}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--go", default=shutil.which("go"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not args.go:
        parser.error("supply a Go 1.24+ executable using --go")
    archive = args.archive.resolve()
    assert digest(archive) == ARCHIVE
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    records = output / "records"
    records.mkdir()
    with tempfile.TemporaryDirectory(dir=output) as scratch:
        work = Path(scratch)
        root = work / "source"
        extract(archive, root)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TEMP=scratch, TMP=scratch,
                   TMPDIR=scratch, GOENV="off", GOWORK="off", GOTOOLCHAIN="local",
                   GOTELEMETRY="off", GOPROXY="off", GOSUMDB="off", GOFLAGS="",
                   GOCACHE=str(work / "go-cache"), GOPATH=str(work / "gopath"),
                   P04_RECORDS=str(records), P04_CORPUS=str(root / CORPUS))
        go = str(Path(args.go).resolve()) if Path(args.go).is_file() else args.go
        report = {"commit": COMMIT, "archiveSha256": ARCHIVE,
                  "candidatePatchSha256": digest(HERE / "candidate.patch"),
                  "pythonVersion": sys.version.split()[0],
                  "goVersion": execute([go, "version"], root, env).stdout.strip()}
        shutil.copyfile(HERE / "probe_test.go", root / "corpusreaders/p04_probe_test.go")
        report["observations"] = make_records(root, records, work, env)
        shutil.copyfile(HERE / "deny.record.json", records / "member.json")
        report["before"] = compare(root, records, work, output, env, go, "before")
        # Pin Git's output bytes for manifest digests on Windows as well as Linux.
        apply = ["git", "-c", "core.autocrlf=false", "apply"]
        execute([*apply, "--check", str(HERE / "candidate.patch")], root, env)
        execute([*apply, str(HERE / "candidate.patch")], root, env)
        assert (records / "member.json").read_bytes() == (
            root / CORPUS / "cases" / MEMBER / "record.json").read_bytes()
        report["after"] = compare(root, records, work, output, env, go, "after")
        manifest = json.loads((root / CORPUS / "MANIFEST.json").read_bytes())
        mutant = next(m for m in manifest["mutants"] if m["id"] == MUTANT)
        assert set(mutant["killedBy"]) == {"F04", "F05", "X1", "X3"}
        assert set(mutant["killedBy"].values()) == {LATE}
        report["manifest"] = {"counts": manifest["counts"], "killedBy": mutant["killedBy"],
                              "corpusDigest": manifest["corpusDigest"]}
        tests = ["test_reference_reader_agrees_with_every_case",
                 "test_corpus_digest_routine_recomputes_the_manifest",
                 "test_every_check_is_forced_by_a_member",
                 "test_mutation_table_matches_the_published_classification",
                 f"test_runtime_contract_fails_each_mutant_where_the_table_says[{MUTANT}]"]
        test_file = str(CORPUS / "tests/test_corpus.py")
        pytest = execute([sys.executable, "-B", "-m", "pytest", "-p", "no:cacheprovider",
                          "-q", *(test_file+"::"+t for t in tests)], root, env)
        (output / "after_pytest.log").write_bytes(pytest.stdout.encode())
        report["targetedPytest"] = pytest.stdout.strip().splitlines()[-1]
        report["recordSha256"] = {p.name: digest(p) for p in sorted(records.iterdir())}
    save(output / "results.json", report)
    print(output / "results.json")


if __name__ == "__main__":
    main()
