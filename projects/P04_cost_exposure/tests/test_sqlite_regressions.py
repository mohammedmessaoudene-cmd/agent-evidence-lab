"""Six bounded SQLite regressions/controls; strict statuses, no old suite replay."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = ROOT / 'src/exposure_ledger.py'
SOURCE_SHA256 = 'c321eab3e1adfa2169164f63238597f1a1c2a7868d339540a3da574f09c82d0f'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def portable_path(path):
    path = Path(path)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.relative_to(HERE.parent).as_posix()
    except ValueError:
        return "<runtime-or-temporary>/" + path.name


def error_record(error):
    return {"type": type(error).__name__, "error": str(error),
            "frames": [{"file": portable_path(f.filename), "line": f.lineno,
                        "function": f.name, "statement": f.line}
                       for f in traceback.extract_tb(error.__traceback__)]}


def load_target(source=SOURCE, expected_hash=SOURCE_SHA256):
    if digest(source) != expected_hash:
        raise RuntimeError("source-under-test hash mismatch")
    name = "_p04_exact_public_sqlite_ledger"
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def evidence(module, kind, attempt, reference=None):
    source = {"cost_observation": "usage_meter", "final_invoice": "provider_billing",
              "dispatch_start": "dispatch_gate", "enforced_cost_ceiling": "enforcing_dispatcher",
              "response_lost": "client", "execution_outcome": "executor"}[kind]
    return module.Evidence(kind, source, reference or ("synthetic-" + kind), attempt)


def probe_connection_setup_cleanup(module):
    """Native malformed-file error, without monkeypatch or synthetic failure."""
    with tempfile.TemporaryDirectory(prefix="p04-public-sqlite-setup-") as temporary:
        path = Path(temporary) / "malformed.sqlite"
        path.write_bytes(b"This ordinary input file is not a SQLite database.\n" * 8)
        held_error = None
        connection = None
        try:
            module.ExposureLedger(path, 100)
        except sqlite3.DatabaseError as error:
            held_error = error  # Ordinary retained exception/traceback, e.g. an error report.
        try:
            if held_error is None:
                raise AssertionError("malformed SQLite input did not produce the expected native error")
            cursor = held_error.__traceback__
            frame_name = None
            while cursor is not None:
                candidate = cursor.tb_frame.f_locals.get("conn")
                if isinstance(candidate, sqlite3.Connection):
                    connection = candidate
                    frame_name = cursor.tb_frame.f_code.co_name
                cursor = cursor.tb_next
            if connection is None:
                raise AssertionError("no native connection found in the retained exception traceback")
            native_connection_still_usable = None
            try:
                # Unlike SELECT, getlimit does not parse the malformed schema.
                # It succeeds on an open native connection and raises on close.
                native_connection_still_usable = connection.getlimit(sqlite3.SQLITE_LIMIT_LENGTH) > 0
            except sqlite3.ProgrammingError as error:
                if "closed" not in str(error).lower():
                    raise
                native_connection_still_usable = False
            defect = native_connection_still_usable
            return {
                "status": "DEFECT_REPRODUCED" if defect else "NO_DEFECT_IN_CHECK",
                "native_error_type": type(held_error).__name__,
                "native_error": str(held_error),
                "real_connection_usable_after_exception": native_connection_still_usable,
                "traceback_frame_retaining_connection": frame_name,
                "exception_retained": True,
                "instrumentation": "none; native sqlite3.Connection recovered from the actual exception traceback",
                "structured_error": error_record(held_error),
                "limits": "resource lifetime defect; no financial loss or Windows file-lock behavior is inferred",
            }
        finally:
            if connection is not None:
                connection.close()
            held_error = None


def probe_normalized_memory_alias(module):
    with tempfile.TemporaryDirectory(prefix="p04-public-sqlite-memory-") as temporary:
        original_cwd = Path.cwd()
        results = []
        try:
            os.chdir(temporary)
            for spelling in (":memory:", "./:memory:", "././:memory:"):
                item = {"input": spelling}
                try:
                    ledger = module.ExposureLedger(spelling, 100)
                    item.update(constructor_accepted=True, stored_path=portable_path(ledger.path))
                    try:
                        ledger.snapshot()
                        item["snapshot_succeeded"] = True
                    except sqlite3.DatabaseError as error:
                        item.update(snapshot_succeeded=False, snapshot_error_type=type(error).__name__, snapshot_error=str(error))
                except ValueError as error:
                    item.update(constructor_accepted=False, error_type=type(error).__name__, error=str(error))
                results.append(item)
            defects = [r for r in results if r.get("constructor_accepted") and r.get("stored_path") == ":memory:"]
            if not defects:
                assert all(not r["constructor_accepted"] for r in results), results
                assert not list(Path(temporary).iterdir())
            return {"status": "DEFECT_REPRODUCED" if defects else "NO_DEFECT_IN_CHECK",
                    "cases": results, "files_created": [p.name for p in Path(temporary).iterdir()],
                    "limits": "persistence input-contract violation; constructor succeeds but the next operation fails closed"}
        finally:
            os.chdir(original_cwd)


def probe_relative_path_rebinding(module):
    with tempfile.TemporaryDirectory(prefix="p04-public-sqlite-path-") as temporary:
        parent = Path(temporary)
        left, right = parent / "left", parent / "right"
        left.mkdir()
        right.mkdir()
        original_cwd = Path.cwd()
        try:
            os.chdir(left)
            ledger = module.ExposureLedger("ledger.sqlite", 100)
            ledger.reserve("original-job", 60)
            before = ledger.snapshot()
            os.chdir(right)
            independent = module.ExposureLedger("ledger.sqlite", 1_000)
            unrelated_before = independent.snapshot()
            # Only the process CWD has changed. Reuse the *same* ledger object.
            observed_after_cwd_change = ledger.snapshot()
            try:
                reservation = ledger.reserve("rebound-job", 200)
            except module.AdmissionDenied as error:
                reservation = {"newly_reserved": False, "rejected": True, "error": str(error)}
            independent_after = independent.snapshot()
            original_after = module.ExposureLedger(left / "ledger.sqlite").snapshot()
            defect = (observed_after_cwd_change["authorized_budget_microusd"] == 1_000
                      and reservation["newly_reserved"]
                      and original_after["authorized_budget_microusd"] == 100
                      and [a["attempt_id"] for a in independent_after["attempts"]] == ["rebound-job"])
            if not defect:
                assert observed_after_cwd_change == before
                assert reservation.get("rejected") is True
                assert independent_after == unrelated_before
                assert original_after == before
            return {
                "status": "DEFECT_REPRODUCED" if defect else "NO_DEFECT_IN_CHECK",
                "ledger_stored_path": portable_path(ledger.path),
                "ledger_stored_path_is_absolute": Path(ledger.path).is_absolute(),
                "same_object_reused": True,
                "original_snapshot": before,
                "unrelated_snapshot_before": unrelated_before,
                "same_object_snapshot_after_cwd_change": observed_after_cwd_change,
                "new_reservation": reservation,
                "original_file_after": original_after,
                "unrelated_file_after": independent_after,
                "limits": "all operations use the public API; no file replacement or arbitrary SQL. This is account-file rebinding, not over-allocation inside one SQLite file",
            }
        finally:
            os.chdir(original_cwd)


def wait_for(path, *, timeout=8.0, children=()):
    deadline = time.monotonic() + timeout
    while not path.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("bounded local marker wait expired: " + path.name)
        if any(child.poll() is not None for child in children):
            raise RuntimeError("a child exited before marker " + path.name)
        time.sleep(.005)


def spawn_worker(source, source_hash, role, database, sync, index=0):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    command = [sys.executable, "-S", "-B", str(Path(__file__).resolve()),
               "--worker", role, "--source", str(source), "--expected-source-sha256", source_hash,
               "--database", str(database), "--sync-dir", str(sync), "--index", str(index)]
    return subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", env=env)


def collect_worker(child):
    out, err = child.communicate(timeout=10)
    if child.returncode != 0:
        raise RuntimeError(f"local child failed ({child.returncode}): {err[-2000:]}")
    if err:
        raise RuntimeError("unexpected child stderr: " + err[-2000:])
    return json.loads(out)


def close_workers(children):
    # Own every child from the first successful launch, including exited ones.
    for child in children:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)


def worker_main(args):
    module = load_target(args.source, args.expected_source_sha256)
    ledger = module.ExposureLedger(args.database)
    sync = args.sync_dir
    if args.worker == "snapshot_writer":
        (sync / "writer-ready").touch()
        wait_for(sync / "account-row-read")
        result = ledger.finalize_invoice("snapshot-job", "late-final", 120,
                                         evidence(module, "final_invoice", "snapshot-job"))
        (sync / "writer-committed").touch()
        print(json.dumps({"result": result, "snapshot_after_commit": ledger.snapshot(),
                          "no_site": bool(sys.flags.no_site), "no_bytecode": bool(sys.dont_write_bytecode)}))
    else:
        index = args.index
        (sync / f"ready-{index}").touch()
        wait_for(sync / "reserve-go")
        reserved = ledger.reserve("shared-job", 60)
        (sync / f"reserved-{index}").touch()
        wait_for(sync / "gate-go")
        gate = ledger.mark_dispatch_started(
            "shared-job", f"gate-{index}", evidence(module, "dispatch_start", "shared-job", f"synthetic-start-{index}"),
            bounded_by_authorization=True,
            bound_evidence=evidence(module, "enforced_cost_ceiling", "shared-job", "synthetic-shared-cap60"))
        print(json.dumps({"index": index, "reservation": reserved, "gate": gate,
                          "no_site": bool(sys.flags.no_site), "no_bytecode": bool(sys.dont_write_bytecode)}))
    return 0


def probe_snapshot_interleaving(module):
    """Pause after the account SELECT executes; commit a writer before attempts."""
    source = Path(module.__file__).resolve()
    source_hash = digest(source)
    children = []
    with tempfile.TemporaryDirectory(prefix="p04-public-sqlite-snapshot-") as temporary:
        folder = Path(temporary)
        database = folder / "ledger.sqlite"
        ledger = module.ExposureLedger(database, 200)
        ledger.reserve("snapshot-job", 100)
        original_connect = ledger._connect
        paused_once = False

        class PausedConnection:
            def __init__(self, native):
                self.native = native

            def execute(self, sql, parameters=()):
                nonlocal paused_once
                cursor = self.native.execute(sql, parameters)
                if sql == "SELECT * FROM account WHERE id=1" and not paused_once:
                    paused_once = True
                    (folder / "account-row-read").touch()
                    wait_for(folder / "writer-committed", children=children)
                return cursor

            def __getattr__(self, name):
                return getattr(self.native, name)

        @contextmanager
        def paused_connect():
            with original_connect() as native:
                yield PausedConnection(native)

        try:
            children.append(spawn_worker(source, source_hash, "snapshot_writer", database, folder))
            wait_for(folder / "writer-ready", children=children)
            # Only connection delegation is instrumented; the exact production
            # snapshot(), _snapshot() and _transaction() methods all execute.
            with patch.object(ledger, "_connect", paused_connect):
                during = ledger.snapshot()
            child_result = collect_worker(children[0])
            after = ledger.snapshot()
            old_tuple = (during["frozen"], during["known_spend_microusd"],
                         during["still_exposed_reservation_microusd"], during["event_count"])
            new_tuple = (after["frozen"], after["known_spend_microusd"],
                         after["still_exposed_reservation_microusd"], after["event_count"])
            assert paused_once and old_tuple == (False, 0, 100, 0), old_tuple
            assert new_tuple == (True, 120, 0, 1), new_tuple
            result = {"status": "POSITIVE_CONTROL_PASS", "snapshot_during_writer_commit": during,
                      "snapshot_after_reader_transaction": after, "writer": child_result,
                      "writer_committed_between_account_and_attempt_reads": True,
                      "scope": "one deterministic interleaving; no stress/throughput or power-loss claim"}
        finally:
            close_workers(children)
        result["children_reaped"] = all(child.returncode is not None for child in children)
    result["temporary_directory_removed"] = not folder.exists()
    return result


def probe_same_attempt_concurrency(module):
    """Three cooperative claimants of one ID: one reservation, one dispatch."""
    source = Path(module.__file__).resolve()
    source_hash = digest(source)
    children = []
    with tempfile.TemporaryDirectory(prefix="p04-public-sqlite-claims-") as temporary:
        folder = Path(temporary)
        database = folder / "ledger.sqlite"
        ledger = module.ExposureLedger(database, 100)
        try:
            for index in range(3):
                children.append(spawn_worker(source, source_hash, "reserve_and_gate", database, folder, index))
            for index in range(3):
                wait_for(folder / f"ready-{index}", children=children)
            (folder / "reserve-go").touch()
            for index in range(3):
                wait_for(folder / f"reserved-{index}", children=children)
            (folder / "gate-go").touch()
            results = [collect_worker(child) for child in children]
            snapshot = ledger.snapshot()
            reservations = sum(r["reservation"]["newly_reserved"] for r in results)
            dispatches = sum(r["gate"]["dispatch_allowed"] for r in results)
            assert reservations == 1 and dispatches == 1, (reservations, dispatches)
            assert len(snapshot["attempts"]) == 1
            assert snapshot["still_exposed_reservation_microusd"] == 60
            assert snapshot["available_for_admission_microusd"] == 40
            assert snapshot["event_count"] == 3 and not snapshot["frozen"]
            result = {"status": "POSITIVE_CONTROL_PASS", "contenders": 3,
                      "successful_new_reservations": reservations, "dispatch_permissions": dispatches,
                      "results": results, "snapshot": snapshot,
                      "scope": "new same-ID reservation and same-attempt dispatch race; no actual external effect"}
        finally:
            close_workers(children)
        result["children_reaped"] = all(child.returncode is not None for child in children)
    result["temporary_directory_removed"] = not folder.exists()
    return result


def probe_sql_integer_boundaries(module):
    """Exact 64-bit storage, SQL guards and Python aggregate non-overflow."""
    with tempfile.TemporaryDirectory(prefix="p04-public-sqlite-integers-") as temporary:
        folder = Path(temporary)
        database = folder / "ledger.sqlite"
        maximum = module.MAX_MONEY
        ledger = module.ExposureLedger(database, maximum)
        ledger.reserve("large", maximum - 1)
        ledger.reserve("small", 1)
        full = ledger.snapshot()
        assert type(full["nominal_committed_microusd"]) is int
        assert full["nominal_committed_microusd"] == maximum
        assert full["available_for_admission_microusd"] == 0
        rejected_sql = []
        connection = sqlite3.connect(database)
        try:
            for field, value in (("known", -1), ("known", 1.25), ("known", "not-number"),
                                 ("known", None), ("authorized_max", 1.25), ("known", maximum + 1)):
                try:
                    connection.execute("UPDATE attempts SET " + field + "=? WHERE id='large'", (value,))
                    raise AssertionError("invalid persisted money was accepted: " + field)
                except (sqlite3.IntegrityError, OverflowError) as error:
                    rejected_sql.append({"field": field, "value_repr": repr(value), "error_type": type(error).__name__})
                finally:
                    connection.rollback()
            # Native SQLite type affinity may coerce a numeric string, but its
            # stored type remains integer; this is distinct from API validation.
            connection.execute("UPDATE attempts SET known='2' WHERE id='large'")
            sql_affinity = connection.execute("SELECT known,typeof(known) FROM attempts WHERE id='large'").fetchone()
            connection.rollback()
            assert sql_affinity == (2, "integer")
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            connection.close()
        # Exact accepted per-row maximum; aggregate may legitimately exceed
        # int64 after overrun and must not wrap, erase liability or admit work.
        ledger.finalize_invoice("large", "large-final", maximum - 2,
                                evidence(module, "final_invoice", "large"))
        one_free = ledger.snapshot()
        assert one_free["available_for_admission_microusd"] == 1
        ledger.reserve("last-unit", 1)
        ledger.finalize_invoice("small", "small-overrun", maximum,
                                evidence(module, "final_invoice", "small"))
        overrun = ledger.snapshot()
        expected_known = 2 * maximum - 2
        assert overrun["known_spend_microusd"] == expected_known
        assert type(overrun["known_spend_microusd"]) is int
        assert overrun["frozen"] and overrun["available_for_admission_microusd"] == 0
        result = {"status": "POSITIVE_CONTROL_PASS", "maximum_stored_microusd": maximum,
                  "full_budget_snapshot": full, "one_unit_remaining_snapshot": one_free,
                  "overrun_aggregate_exact_integer": overrun["known_spend_microusd"],
                  "overrun_snapshot": overrun, "sql_invalid_money_rejections": rejected_sql,
                  "numeric_string_SQL_affinity": {"stored_value": sql_affinity[0], "stored_type": sql_affinity[1]},
                  "scope": "temporary DB only; SQL probes test stored-value constraints, not hostile-file authenticity"}
    result["temporary_directory_removed"] = not folder.exists()
    return result

PROBES = {
    'connection_setup_cleanup': probe_connection_setup_cleanup,
    'normalized_memory_alias': probe_normalized_memory_alias,
    'relative_path_rebinding': probe_relative_path_rebinding,
    'snapshot_interleaving': probe_snapshot_interleaving,
    'same_attempt_concurrency': probe_same_attempt_concurrency,
    'sql_integer_boundaries': probe_sql_integer_boundaries,
}
EXPECTED = {name: 'NO_DEFECT_IN_CHECK' if i < 3 else 'POSITIVE_CONTROL_PASS'
            for i, name in enumerate(PROBES)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', nargs='+', choices=tuple(PROBES), default=list(PROBES))
    parser.add_argument('--report', type=Path)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--expected-source-sha256', default=SOURCE_SHA256)
    parser.add_argument('--worker', choices=('snapshot_writer', 'reserve_and_gate'))
    parser.add_argument('--database', type=Path)
    parser.add_argument('--sync-dir', type=Path)
    parser.add_argument('--index', type=int, default=0)
    args = parser.parse_args()
    if not sys.flags.no_site or not __debug__:
        parser.error('Use a direct base Python with -S and without -O')
    args.source = args.source.resolve()
    if args.worker:
        return worker_main(args)
    if args.report is None:
        parser.error('--report is required')
    report_path = args.report.resolve()
    if report_path.exists():
        parser.error('Use a new report path')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    module = load_target(args.source, args.expected_source_sha256)
    results = {}
    for name in args.cases:
        try:
            result = PROBES[name](module)
        except Exception as error:
            result = {'status': 'UNEXPECTED_PROBE_ERROR', **error_record(error)}
        result['expected_status'] = EXPECTED[name]
        result['expectation_met'] = result['status'] == EXPECTED[name]
        results[name] = result
        print(name, result['status'], flush=True)
    passed = sum(r['expectation_met'] for r in results.values())
    report = {
        'status': 'PASS' if passed == len(results) else 'FAIL_OR_INCOMPLETE',
        'cases_run': len(results), 'passed': passed, 'failed': len(results)-passed,
        'source_sha256': digest(args.source), 'probe_sha256': digest(Path(__file__)),
        'python': platform.python_version(), 'platform': platform.system(),
        'sqlite': sqlite3.sqlite_version, 'no_site': bool(sys.flags.no_site),
        'cases': results, 'historical_23_method_suite_executed': False,
        'scope': 'Native local SQLite calls, three defect paths and three bounded controls. No WAL-reset, power-loss, stress or external-provider qualification.'}
    report_path.write_bytes((json.dumps(report, indent=2)+'\n').encode('utf-8'))
    return 0 if report['status'] == 'PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
