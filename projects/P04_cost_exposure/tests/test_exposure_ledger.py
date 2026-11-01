r"""P04 R2 new local tests only. No network/provider calls or R1 reruns.

Linux/macOS: python tests/test_exposure_ledger.py --report results/exposure_ledger_tests.json
Windows:    python -S tests\test_exposure_ledger.py --report results\exposure_ledger_tests.json

Subprocesses use the active Python executable. Crashes use Popen.kill(), which
works on Windows as TerminateProcess and on POSIX as SIGKILL. Results record the
platform actually tested; cross-platform commands are not a Windows test claim.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from exposure_ledger import (  # noqa: E402
    AdmissionDenied, ConfigurationConflict, Evidence, EvidenceConflict,
    EvidenceValidationError, ExposureLedger, MAX_MONEY, UnknownAttempt,
)

EVIDENCE = []
SOURCE = {"cost_observation": "usage_meter", "final_invoice": "provider_billing",
          "response_lost": "client", "unconfirmed_cancellation": "client",
          "non_dispatch_proof": "dispatch_gate", "dispatch_start": "dispatch_gate",
          "execution_outcome": "executor", "enforced_cost_ceiling": "enforcing_dispatcher"}


def ev(kind, attempt="a", reference=None, source=None):
    return Evidence(kind, source or SOURCE[kind], reference or (kind + ":" + attempt), attempt)


RACE_BARRIER = """
import os,time
from pathlib import Path
barrier=Path(sys.argv[3]);(barrier/('ready-'+str(os.getpid()))).touch()
until=time.monotonic()+10
while not (barrier/'go').exists():
    if time.monotonic()>until:raise RuntimeError('barrier timeout')
    time.sleep(0.002)
"""


class ExposureLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="p04_r2_exposure_")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "ledger.sqlite"
        self.ledger = ExposureLedger(self.path, 200)

    def snap(self):
        return self.ledger.snapshot()

    def child(self, code, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        return subprocess.Popen([sys.executable, "-S", "-c", code, str(self.path), *args],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)

    def collect(self, process, expected=0):
        try:
            out, err = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            out, err = process.communicate()
            self.fail(f"child timeout, pid={process.pid}, stderr={err!r}")
        self.assertEqual(process.returncode, expected, (out, err))
        return {"pid": process.pid, "returncode": process.returncode, "output": json.loads(out), "stderr": err}

    def concurrent(self, code, n, name):
        barrier = Path(self.tmp.name) / name
        barrier.mkdir()
        children = []
        try:
            for i in range(n):
                children.append(self.child(code, str(i), str(barrier)))
            until = time.monotonic() + 10
            while len(list(barrier.glob("ready-*"))) != n:
                if time.monotonic() > until or any(p.poll() is not None for p in children):
                    self.fail("not all subprocesses reached the barrier")
                time.sleep(0.002)
            (barrier / "go").touch()
            results = [self.collect(p) for p in children]
            EVIDENCE.append({"test": self.id(), "contenders_ready_before_release": n,
                             "processes": results, "snapshot": self.snap()})
            return results
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                child.communicate()

    def test_known_partial_cost_and_lost_reply_do_not_release(self):
        self.ledger.reserve("a", 100)
        self.ledger.observe_cost("a", "meter20", 20, ev("cost_observation"))
        self.assertEqual(self.snap()["unbounded_exposure_count"], 1)
        self.assertEqual(self.snap()["available_for_admission_microusd"], 0)
        self.ledger.mark_unknown("a", "lost", evidence=ev("response_lost"))
        s = self.snap()
        self.assertEqual((s["known_spend_microusd"], s["still_exposed_reservation_microusd"]), (20, 80))
        self.assertEqual(s["nominal_available_microusd"], 100)
        self.assertEqual(s["unbounded_exposure_count"], 1)
        self.assertEqual(s["available_for_admission_microusd"], 0)
        with self.assertRaises(AdmissionDenied):
            self.ledger.reserve("b", 1)
        result = self.ledger.finalize_invoice("a", "invoice70", 70, ev("final_invoice"))
        self.assertTrue(result["newly_finalized"])
        self.assertEqual(result["attempt"]["outcome"], "UNKNOWN")
        s = self.snap()
        self.assertEqual((s["known_spend_microusd"], s["still_exposed_reservation_microusd"], s["available_for_admission_microusd"]), (70, 0, 130))
        EVIDENCE.append({"test": self.id(), "after_final_invoice": s})

    def test_finite_unknown_requires_distinct_enforced_bound_evidence(self):
        self.ledger.reserve("a", 100)
        self.ledger.observe_cost("a", "known20", 20, ev("cost_observation"))
        with self.assertRaises(EvidenceValidationError):
            self.ledger.mark_unknown("a", "no-proof", unbounded=False, evidence=ev("response_lost"))
        with self.assertRaises(EvidenceValidationError):
            self.ledger.mark_unknown("a", "estimate-only", unbounded=False, evidence=ev("response_lost"),
                                     bound_evidence=Evidence("estimated_cost", "usage_meter", "estimate100", "a"))
        self.ledger.mark_unknown("a", "bounded-lost", unbounded=False, evidence=ev("response_lost"),
                                 bound_evidence=ev("enforced_cost_ceiling"))
        s = self.snap()
        self.assertEqual((s["known_spend_microusd"], s["still_exposed_reservation_microusd"]), (20, 80))
        self.assertEqual(s["unbounded_exposure_count"], 0)
        self.assertEqual(s["available_for_admission_microusd"], 100)
        self.assertTrue(s["attempts"][0]["has_enforced_cost_ceiling"])
        reopened = ExposureLedger(self.path)
        reopened.observe_cost("a", "later-meter30", 30, ev("cost_observation", reference="new-meter30"))
        reopened.observe_outcome("a", "observed-end", "SUCCEEDED", ev("execution_outcome"))
        self.assertEqual(reopened.snapshot()["unbounded_exposure_count"], 0)
        self.assertEqual(reopened.snapshot()["available_for_admission_microusd"], 100)

    def test_unconfirmed_cancellation_and_estimate_never_become_final_bill(self):
        self.ledger.reserve("a", 100)
        with self.assertRaises(EvidenceValidationError):
            self.ledger.observe_cost("a", "estimated-input", 2, Evidence("estimated_cost", "usage_meter", "input-estimate", "a"))
        self.ledger.mark_unknown("a", "cancel", reason="unconfirmed_cancellation", evidence=ev("unconfirmed_cancellation"))
        s = self.snap()
        self.assertEqual((s["known_spend_microusd"], s["still_exposed_reservation_microusd"]), (0, 100))
        self.assertEqual(s["attempts"][0]["billing_finality"], "UNKNOWN")
        with self.assertRaises(EvidenceValidationError):
            self.ledger.finalize_invoice("a", "fake-zero", 0, ev("unconfirmed_cancellation"))
        self.assertEqual(self.snap()["still_exposed_reservation_microusd"], 100)

    def test_durable_duplicate_events_survive_json_and_reopen(self):
        self.ledger.reserve("a", 100)
        evidence = ev("cost_observation")
        first = self.ledger.observe_cost("a", "same-event", 20, evidence)
        serialized = json.dumps({"kind": evidence.kind, "source": evidence.source,
                                 "reference": evidence.reference, "attempt_id": evidence.attempt_id})
        other = ExposureLedger(self.path)
        duplicate = other.observe_cost("a", "same-event", 20, Evidence(**json.loads(serialized)))
        self.assertTrue(first["new_event"])
        self.assertFalse(duplicate["new_event"])
        self.assertFalse(duplicate["state_changed"])
        self.assertEqual(other.snapshot()["known_spend_microusd"], 20)
        self.assertEqual(other.snapshot()["event_count"], 1)
        self.assertEqual(other.snapshot()["unbounded_exposure_count"], 1)

    def test_contradictory_larger_duplicate_retains_cost_and_freezes(self):
        self.ledger.reserve("a", 100)
        self.ledger.finalize_invoice("a", "invoice-id", 40, ev("final_invoice"))
        with self.assertRaises(EvidenceConflict) as conflict:
            self.ledger.finalize_invoice("a", "invoice-id", 80, ev("final_invoice"))
        self.assertTrue(conflict.exception.evidence_persisted)
        s = ExposureLedger(self.path).snapshot()
        self.assertEqual((s["known_spend_microusd"], s["still_exposed_reservation_microusd"]), (80, 20))
        self.assertEqual(s["attempts"][0]["last_final_invoice_microusd"], 40)
        self.assertEqual(s["attempts"][0]["billing_finality"], "CONFLICT")
        self.assertTrue(s["frozen"])
        self.assertEqual(s["available_for_admission_microusd"], 0)
        with self.assertRaises(EvidenceConflict):
            self.ledger.finalize_invoice("a", "invoice-id", 80, ev("final_invoice"))
        self.assertEqual(self.snap()["conflict_count"], 1)
        EVIDENCE.append({"test": self.id(), "snapshot": self.snap()})

    def test_late_bigger_observation_after_finality_is_not_discarded(self):
        self.ledger.reserve("a", 100)
        self.ledger.finalize_invoice("a", "final40", 40, ev("final_invoice"))
        with self.assertRaises(EvidenceConflict):
            self.ledger.observe_cost("a", "late90", 90, ev("cost_observation"))
        self.assertEqual(self.snap()["known_spend_microusd"], 90)
        self.assertEqual(self.snap()["still_exposed_reservation_microusd"], 10)
        self.assertTrue(self.snap()["frozen"])

    def test_lower_final_bill_cannot_erase_observed_floor(self):
        self.ledger.reserve("a", 100)
        self.ledger.observe_cost("a", "cost90", 90, ev("cost_observation", reference="meter90"))
        self.ledger.observe_cost("a", "stale20", 20, ev("cost_observation", reference="older-meter20"))
        self.assertEqual(self.snap()["known_spend_microusd"], 90)
        self.assertEqual(self.snap()["available_for_admission_microusd"], 0)
        with self.assertRaises(EvidenceConflict):
            self.ledger.finalize_invoice("a", "invoice80", 80, ev("final_invoice"))
        self.assertEqual((self.snap()["known_spend_microusd"], self.snap()["still_exposed_reservation_microusd"]), (90, 10))
        self.assertTrue(self.snap()["frozen"])

    def test_overcap_knowledge_recorded_before_and_after_final_invoice(self):
        self.ledger.reserve("a", 100)
        self.ledger.observe_cost("a", "cost120", 120, ev("cost_observation"))
        self.assertTrue(self.snap()["frozen"])
        self.assertEqual(self.snap()["known_spend_microusd"], 120)
        self.ledger.finalize_invoice("a", "final130", 130, ev("final_invoice"))
        s = self.snap()
        self.assertEqual(s["known_spend_microusd"], 130)
        self.assertEqual(s["attempts"][0]["authorization_overrun_microusd"], 30)
        self.assertEqual(s["unbounded_exposure_count"], 0)
        self.assertTrue(s["frozen"])
        self.assertEqual(s["nominal_available_microusd"], 70)
        with self.assertRaises(AdmissionDenied):
            self.ledger.reserve("b", 1)

    def test_execution_outcome_and_bill_finality_are_independent(self):
        self.ledger.reserve("a", 100)
        self.ledger.observe_outcome("a", "success", "SUCCEEDED", ev("execution_outcome"))
        self.assertEqual(self.snap()["attempts"][0]["billing_finality"], "UNKNOWN")
        self.assertEqual(self.snap()["still_exposed_reservation_microusd"], 100)
        self.assertEqual(self.snap()["unbounded_exposure_count"], 1)
        self.ledger.finalize_invoice("a", "final70", 70, ev("final_invoice"))
        self.ledger.mark_unknown("a", "late-client-cancel", reason="unconfirmed_cancellation", evidence=ev("unconfirmed_cancellation"))
        s = self.snap()
        self.assertEqual(s["attempts"][0]["outcome"], "SUCCEEDED")
        self.assertEqual(s["attempts"][0]["billing_finality"], "FINAL")
        self.assertEqual((s["known_spend_microusd"], s["still_exposed_reservation_microusd"]), (70, 0))

    def test_non_dispatch_proof_is_role_scoped_and_fenced(self):
        self.ledger.reserve("a", 100)
        with self.assertRaises(EvidenceValidationError):
            self.ledger.confirm_non_dispatch("a", "client-assertion", ev("non_dispatch_proof", source="client"))
        proof = self.ledger.confirm_non_dispatch("a", "gate-proof", ev("non_dispatch_proof"))
        self.assertTrue(proof["newly_finalized"])
        self.assertEqual(proof["attempt"]["outcome"], "NOT_DISPATCHED")
        self.assertEqual(self.snap()["available_for_admission_microusd"], 200)
        later = self.ledger.mark_dispatch_started("a", "later-dispatch", ev("dispatch_start"),
                                                  bounded_by_authorization=True, bound_evidence=ev("enforced_cost_ceiling"))
        self.assertFalse(later["dispatch_allowed"])

    def test_non_dispatch_after_possible_dispatch_or_cost_is_rejected(self):
        self.ledger.reserve("a", 100)
        claimed = self.ledger.mark_dispatch_started("a", "start", ev("dispatch_start"),
                                                    bounded_by_authorization=True, bound_evidence=ev("enforced_cost_ceiling"))
        self.assertTrue(claimed["dispatch_allowed"])
        with self.assertRaises(EvidenceConflict):
            self.ledger.confirm_non_dispatch("a", "incompatible-proof", ev("non_dispatch_proof"))
        self.assertEqual(self.snap()["still_exposed_reservation_microusd"], 100)
        self.assertTrue(self.snap()["frozen"])

    def test_invalid_money_scope_and_budget_reopen(self):
        for amount in [-1, 1.5, True, "3", MAX_MONEY + 1]:
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                self.ledger.reserve("bad", amount)
        self.ledger.reserve("a", 100)
        with self.assertRaises(ConfigurationConflict):
            self.ledger.reserve("a", 101)
        with self.assertRaises(ConfigurationConflict):
            ExposureLedger(self.path, 999)
        with self.assertRaises(EvidenceValidationError):
            self.ledger.observe_cost("a", "scope-wrong", 5, ev("cost_observation", attempt="other"))
        with self.assertRaises(UnknownAttempt):
            self.ledger.observe_cost("missing", "missing", 5, ev("cost_observation", attempt="missing"))
        with self.assertRaises(AdmissionDenied):
            self.ledger.mark_dispatch_started("a", "estimated-bound", ev("dispatch_start"))
        self.assertEqual(self.snap()["known_spend_microusd"], 0)

    def test_actual_process_kill_before_reconciliation_keeps_exposure(self):
        marker = Path(self.tmp.name) / "committed.json"
        code = """
import json,sys,time
from pathlib import Path
from exposure_ledger import ExposureLedger,Evidence
l=ExposureLedger(sys.argv[1]);l.reserve('crashed',100)
l.observe_cost('crashed','observed20',20,Evidence('cost_observation','usage_meter','meter20','crashed'))
Path(sys.argv[2]).write_text(json.dumps({'phase':'ungated-cost-committed-no-loss-callback-no-reconciliation','snapshot':l.snapshot()}))
while True:time.sleep(0.05)
"""
        child = self.child(code, str(marker))
        try:
            until = time.monotonic() + 10
            while not marker.exists():
                if time.monotonic() > until or child.poll() is not None:
                    self.fail("child did not commit pre-reconciliation state")
                time.sleep(0.002)
            child.kill()
            out, err = child.communicate(timeout=10)
            self.assertNotEqual(child.returncode, 0)
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate()
        reopened = ExposureLedger(self.path)
        before = reopened.snapshot()
        self.assertEqual((before["known_spend_microusd"], before["still_exposed_reservation_microusd"]), (20, 80))
        self.assertEqual(before["available_for_admission_microusd"], 0)
        reopened.finalize_invoice("crashed", "final75", 75, ev("final_invoice", "crashed"))
        self.assertEqual(reopened.snapshot()["available_for_admission_microusd"], 125)
        EVIDENCE.append({"test": self.id(), "pid": child.pid, "returncode": child.returncode,
                         "termination": "subprocess.Popen.kill", "stderr": err,
                         "committed_marker": json.loads(marker.read_text()), "reopened_before_invoice": before,
                         "after_invoice": reopened.snapshot()})

    def test_actual_process_exit_after_final_commit_replays_once(self):
        self.ledger.reserve("a", 100)
        code = """
import json,os,sys
from exposure_ledger import ExposureLedger,Evidence
l=ExposureLedger(sys.argv[1]);r=l.finalize_invoice('a','final-commit',70,Evidence('final_invoice','provider_billing','invoice-a','a'))
print(json.dumps({'phase':'invoice-committed-before-ack','result':r}),flush=True)
os._exit(73)
"""
        evidence = self.collect(self.child(code), 73)
        reopened = ExposureLedger(self.path)
        result = reopened.finalize_invoice("a", "final-commit", 70, ev("final_invoice", reference="invoice-a"))
        self.assertFalse(result["new_event"])
        self.assertFalse(result["newly_finalized"])
        self.assertEqual(reopened.snapshot()["known_spend_microusd"], 70)
        EVIDENCE.append({"test": self.id(), "child": evidence, "reopened_snapshot": reopened.snapshot()})

    def test_concurrent_reservations_cannot_overallocate(self):
        self.path = Path(self.tmp.name) / "small.sqlite"
        self.ledger = ExposureLedger(self.path, 100)
        code = """
import json,sys
from exposure_ledger import ExposureLedger,AdmissionDenied
l=ExposureLedger(sys.argv[1])
""" + RACE_BARRIER + """
try:r=l.reserve('worker'+sys.argv[2],30);out={'admitted':r['newly_reserved']}
except AdmissionDenied:out={'admitted':False}
print(json.dumps(out),flush=True)
"""
        results = self.concurrent(code, 8, "reserve-race")
        self.assertEqual(sum(r["output"]["admitted"] for r in results), 3)
        self.assertEqual(self.snap()["still_exposed_reservation_microusd"], 90)

    def test_concurrent_cumulative_cost_writers_keep_maximum(self):
        self.ledger.reserve("a", 100)
        code = """
import json,sys
from exposure_ledger import ExposureLedger,Evidence
l=ExposureLedger(sys.argv[1])
""" + RACE_BARRIER + """
i=int(sys.argv[2]);r=l.observe_cost('a','writer'+str(i),10*(i+1),Evidence('cost_observation','usage_meter','meter'+str(i),'a'))
print(json.dumps(r),flush=True)
"""
        self.concurrent(code, 8, "observed-race")
        s = self.snap()
        self.assertEqual((s["known_spend_microusd"], s["still_exposed_reservation_microusd"]), (80, 20))
        self.assertFalse(s["frozen"])
        self.assertEqual(s["unbounded_exposure_count"], 1)
        self.assertEqual(s["available_for_admission_microusd"], 0)

    def test_ungated_usage_alone_blocks_extra_admission_until_final_bill(self):
        self.ledger.reserve("a", 100)
        self.ledger.observe_cost("a", "usage20", 20, ev("cost_observation"))
        s = self.snap()
        self.assertEqual(s["schema_version"], 2)
        self.assertFalse(s["attempts"][0]["has_enforced_cost_ceiling"])
        self.assertEqual(s["nominal_available_microusd"], 100)
        self.assertEqual(s["available_for_admission_microusd"], 0)
        with self.assertRaises(AdmissionDenied):
            self.ledger.reserve("b", 100)
        self.ledger.finalize_invoice("a", "final70", 70, ev("final_invoice"))
        self.assertTrue(self.ledger.reserve("b", 100)["newly_reserved"])
        EVIDENCE.append({"test": self.id(), "before_invoice": s, "after_invoice_and_new_reservation": self.snap()})

    def test_ungated_execution_outcome_alone_blocks_extra_admission(self):
        self.ledger.reserve("a", 100)
        self.ledger.observe_outcome("a", "done", "SUCCEEDED", ev("execution_outcome"))
        s = self.snap()
        self.assertEqual(s["attempts"][0]["billing_finality"], "UNKNOWN")
        self.assertEqual(s["attempts"][0]["outcome"], "SUCCEEDED")
        self.assertEqual(s["unbounded_exposure_count"], 1)
        with self.assertRaises(AdmissionDenied):
            self.ledger.reserve("b", 100)
        self.ledger.finalize_invoice("a", "final70", 70, ev("final_invoice"))
        self.assertEqual(self.snap()["unbounded_exposure_count"], 0)
        self.assertTrue(self.ledger.reserve("b", 100)["newly_reserved"])
        EVIDENCE.append({"test": self.id(), "before_invoice": s, "after_invoice_and_new_reservation": self.snap()})

    def test_persisted_ceiling_survives_reopen_for_cost_and_outcome(self):
        self.ledger.reserve("a", 100)
        self.ledger.mark_dispatch_started("a", "start", ev("dispatch_start"),
                                         bounded_by_authorization=True, bound_evidence=ev("enforced_cost_ceiling"))
        reopened = ExposureLedger(self.path)
        reopened.observe_cost("a", "usage20", 20, ev("cost_observation"))
        reopened.observe_outcome("a", "done", "SUCCEEDED", ev("execution_outcome"))
        s = reopened.snapshot()
        self.assertTrue(s["attempts"][0]["has_enforced_cost_ceiling"])
        self.assertEqual(s["attempts"][0]["enforced_ceiling_evidence"]["kind"], "enforced_cost_ceiling")
        self.assertEqual((s["known_spend_microusd"], s["still_exposed_reservation_microusd"]), (20, 80))
        self.assertEqual((s["unbounded_exposure_count"], s["available_for_admission_microusd"]), (0, 100))

    def test_old_schema_one_is_rejected_without_business_data_migration(self):
        old = Path(self.tmp.name) / "old-prototype.sqlite"
        with closing(sqlite3.connect(old)) as conn, conn:
            conn.execute("CREATE TABLE account (id INTEGER PRIMARY KEY, version INTEGER, budget INTEGER, frozen INTEGER, freeze_reason TEXT)")
            conn.execute("INSERT INTO account VALUES(1,1,200,0,NULL)")
            conn.execute("CREATE TABLE sentinel (value TEXT)")
            conn.execute("INSERT INTO sentinel VALUES('preserve me')")
        with self.assertRaisesRegex(ConfigurationConflict, "schema 1"):
            ExposureLedger(old)
        with closing(sqlite3.connect(old)) as conn, conn:
            self.assertEqual(conn.execute("SELECT version FROM account").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT value FROM sentinel").fetchone()[0], "preserve me")
            self.assertEqual({r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}, {"account", "sentinel"})

    def test_concurrent_duplicate_finalization_is_durable_once(self):
        self.ledger.reserve("a", 100)
        code = """
import json,sys
from exposure_ledger import ExposureLedger,Evidence
l=ExposureLedger(sys.argv[1])
""" + RACE_BARRIER + """
r=l.finalize_invoice('a','same-invoice-event',70,Evidence('final_invoice','provider_billing','invoice70','a'))
print(json.dumps(r),flush=True)
"""
        results = self.concurrent(code, 6, "final-race")
        self.assertEqual(sum(r["output"]["newly_finalized"] for r in results), 1)
        self.assertEqual(sum(r["output"]["new_event"] for r in results), 1)
        self.assertEqual(self.snap()["known_spend_microusd"], 70)
        self.assertEqual(self.snap()["event_count"], 1)

    def test_concurrent_dispatch_and_non_dispatch_proof_are_fenced(self):
        self.ledger.reserve("a", 100)
        code = """
import json,sys
from exposure_ledger import ExposureLedger,Evidence,EvidenceConflict
l=ExposureLedger(sys.argv[1])
""" + RACE_BARRIER + """
try:
 if sys.argv[2]=='0':
  r=l.mark_dispatch_started('a','start',Evidence('dispatch_start','dispatch_gate','start-a','a'),bounded_by_authorization=True,bound_evidence=Evidence('enforced_cost_ceiling','enforcing_dispatcher','fixture-cap100','a'))
 else:r=l.confirm_non_dispatch('a','proof',Evidence('non_dispatch_proof','dispatch_gate','no-dispatch-a','a'))
except EvidenceConflict as e:r={'conflict':str(e),'dispatch_allowed':False,'newly_finalized':False}
print(json.dumps(r),flush=True)
"""
        results = self.concurrent(code, 2, "gate-race")
        dispatch = sum(r["output"].get("dispatch_allowed", False) for r in results)
        not_sent = sum(r["output"].get("newly_finalized", False) for r in results)
        self.assertEqual(dispatch + not_sent, 1)
        s = self.snap()
        if dispatch:
            self.assertTrue(s["frozen"])
            self.assertEqual(s["still_exposed_reservation_microusd"], 100)
        else:
            self.assertEqual(s["attempts"][0]["outcome"], "NOT_DISPATCHED")
            self.assertEqual(s["still_exposed_reservation_microusd"], 0)

    def test_concurrent_lost_reply_and_final_invoice_keep_finality(self):
        self.ledger.reserve("a", 100)
        code = """
import json,sys
from exposure_ledger import ExposureLedger,Evidence
l=ExposureLedger(sys.argv[1])
""" + RACE_BARRIER + """
if sys.argv[2]=='0':r=l.mark_unknown('a','lost',evidence=Evidence('response_lost','client','lost-a','a'))
else:r=l.finalize_invoice('a','invoice',70,Evidence('final_invoice','provider_billing','invoice70','a'))
print(json.dumps(r),flush=True)
"""
        self.concurrent(code, 2, "cancel-final-race")
        s = self.snap()
        self.assertEqual(s["attempts"][0]["billing_finality"], "FINAL")
        self.assertEqual(s["attempts"][0]["outcome"], "UNKNOWN")
        self.assertEqual((s["known_spend_microusd"], s["still_exposed_reservation_microusd"], s["unbounded_exposure_count"]), (70, 0, 0))


class TimedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def startTest(self, test):
        self.started = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        failed = {str(t) for t, _ in self.failures + self.errors}
        self.records.append({"test": test.id(), "seconds": time.perf_counter() - self.started,
                             "status": "FAIL" if str(test) in failed else "PASS"})
        super().stopTest(test)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    parser.add_argument("--tests", nargs="+", help="Affected-only method names")
    args = parser.parse_args()
    before = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    suite = (unittest.TestSuite(ExposureLedgerTests(name) for name in args.tests) if args.tests else
             unittest.defaultTestLoader.loadTestsFromTestCase(ExposureLedgerTests))
    result = unittest.TextTestRunner(verbosity=2, resultclass=TimedResult).run(suite)
    report = {
        "project_id": "P04", "revision": "R2", "component": "exposure_ledger",
        "started_utc": before, "elapsed_seconds": time.perf_counter() - started,
        "status": "PASS" if result.wasSuccessful() and not result.skipped else "FAIL_OR_INCOMPLETE",
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
        "selected_tests": args.tests or "ALL_NEW_R2_LEDGER_TESTS", "tests": result.records,
        "process_and_state_evidence": EVIDENCE,
        "python": platform.python_version(), "platform": platform.platform(), "sqlite": sqlite3.sqlite_version,
        "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                          [ROOT / "src/exposure_ledger.py", Path(__file__).resolve()]},
        "scope": "Local SQLite fixtures; actual concurrent subprocesses and abrupt process termination; no provider/network/paid calls.",
        "not_tested": [*(["Windows execution"] if platform.system() != "Windows" else []), "provider bill authenticity", "end-to-end exactly-once external effects",
                       "real enforced provider cost ceiling", "power loss", "network filesystem", "multi-host Redis/server deployment"],
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sys.exit(0 if result.wasSuccessful() else 1)
