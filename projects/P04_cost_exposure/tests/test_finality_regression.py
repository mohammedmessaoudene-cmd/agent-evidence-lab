"""One finality regression with nineteen explicit checks and synthetic evidence."""
from __future__ import annotations
import argparse
from contextlib import closing
from dataclasses import asdict, is_dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = 'c321eab3e1adfa2169164f63238597f1a1c2a7868d339540a3da574f09c82d0f'


ROLE = {
    "cost_observation": "usage_meter",
    "final_invoice": "provider_billing",
    "response_lost": "client",
    "non_dispatch_proof": "dispatch_gate",
    "dispatch_start": "dispatch_gate",
    "execution_outcome": "executor",
    "enforced_cost_ceiling": "enforcing_dispatcher",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def serializable(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {k: serializable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [serializable(v) for v in value]
    return value


class Probe:
    def __init__(self, module, path, budget=300):
        self.module = module
        self.path = path
        self.ledger = module.ExposureLedger(path, budget)
        self.operations = []
        self.checks = []

    def ev(self, kind, attempt="a", reference=None):
        return self.module.Evidence(kind, ROLE[kind], reference or kind + ":" + attempt, attempt)

    def call(self, method, *args, **kwargs):
        operation = {"method": method, "args": serializable(args), "kwargs": serializable(kwargs)}
        try:
            operation["result"] = getattr(self.ledger, method)(*args, **kwargs)
            operation["raised"] = None
        except Exception as exc:
            operation["result"] = None
            operation["raised"] = {"type": type(exc).__name__, "message": str(exc),
                                   "evidence_persisted": getattr(exc, "evidence_persisted", None),
                                   "account_frozen": getattr(exc, "account_frozen", None)}
        operation["snapshot"] = self.ledger.snapshot()
        self.operations.append(operation)
        return operation

    def check(self, name, observed, expected, category="accounting_safety"):
        self.checks.append({"name": name, "category": category, "observed": observed,
                            "expected": expected, "passed": observed == expected})

    def no_exception(self, operation, name):
        self.check(name, operation["raised"], None, "probe_precondition")

    def exception(self, operation, expected, name):
        self.check(name, operation["raised"]["type"] if operation["raised"] else None, expected)

    def attempt(self, name="a"):
        return next(a for a in self.ledger.snapshot()["attempts"] if a["attempt_id"] == name)

    def reopen(self):
        prior = self.ledger.snapshot()
        self.ledger = self.module.ExposureLedger(self.path)
        self.check("durable_state_preserved_on_reopen", self.ledger.snapshot(), prior)

    def rows(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            return {name: [dict(r) for r in conn.execute(f"SELECT * FROM {name} ORDER BY rowid")]
                    for name in ["events", "conflicts"]}

    def finish(self):
        failed = [c for c in self.checks if not c["passed"]]
        return {"status": "FAIL" if failed else "PASS", "operations": self.operations,
                "checks": self.checks, "failed_checks": failed,
                "final_snapshot": self.ledger.snapshot(), "durable_event_rows": self.rows()}


def reserve(p, attempt="a", amount=100):
    r = p.call("reserve", attempt, amount)
    p.no_exception(r, "reserve_" + attempt)


def gate(p, attempt="a"):
    r = p.call("mark_dispatch_started", attempt, "gate:" + attempt, p.ev("dispatch_start", attempt),
               bounded_by_authorization=True, bound_evidence=p.ev("enforced_cost_ceiling", attempt))
    p.no_exception(r, "gate_" + attempt)
    p.check("initial_gate_permits_exactly_one_claim", (r["result"] or {}).get("dispatch_allowed"), True)


def final_overcap_then_stale_observation(p):
    reserve(p)
    gate(p)
    invoice = p.ev("final_invoice", reference="final-total-120")
    r = p.call("finalize_invoice", "a", "invoice-event", 120, invoice)
    p.no_exception(r, "overcap_final_invoice_recorded")
    s = p.ledger.snapshot()
    p.check("overcap_freeze_is_retained", s["frozen"], True)
    p.check("authoritative_invoice_starts_with_no_unbounded_liability", s["unbounded_exposure_count"], 0)
    p.check("final_invoice_known_spend", s["known_spend_microusd"], 120)

    r = p.call("observe_cost", "a", "older-meter-event", 20, p.ev("cost_observation", reference="older-cumulative-total-20"))
    p.no_exception(r, "older_lower_observation_is_accepted")
    p.check("older_lower_observation_keeps_final_invoice", p.attempt()["billing_finality"], "FINAL")
    p.check("older_lower_observation_cannot_create_unbounded_liability",
            p.ledger.snapshot()["unbounded_exposure_count"], 0, "semantic_finality")
    p.check("known_cost_does_not_fall", p.ledger.snapshot()["known_spend_microusd"], 120)
    p.reopen()

    retry = p.call("finalize_invoice", "a", "invoice-event", 120, invoice)
    p.no_exception(retry, "exact_invoice_replay_returns")
    p.check("exact_invoice_replay_not_newly_finalized", (retry["result"] or {}).get("newly_finalized"), False)
    prior_copy = p.ledger.snapshot()
    p.check("exact_invoice_replay_has_no_unbounded_liability",
            prior_copy["unbounded_exposure_count"], 0, "semantic_finality")

    copied = p.call("finalize_invoice", "a", "new-delivery-same-invoice", 120, invoice)
    p.no_exception(copied, "same_final_invoice_new_delivery_returns")
    p.check("same_final_invoice_new_delivery_not_newly_finalized", (copied["result"] or {}).get("newly_finalized"), False)
    p.check("same_invoice_delivery_identity_does_not_change_exposure",
            [prior_copy["unbounded_exposure_count"], p.ledger.snapshot()["unbounded_exposure_count"]],
            [0, 0], "semantic_finality")
    denied = p.call("reserve", "never-admitted", 1)
    p.exception(denied, "AdmissionDenied", "freeze_still_denies_new_admission")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger-source', type=Path, default=ROOT/'src/exposure_ledger.py')
    parser.add_argument('--expected-sha256', default=SOURCE_SHA256)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not sys.flags.no_site or not __debug__:
        parser.error('Use a direct base Python with -S and without -O')
    source = args.ledger_source.resolve()
    if digest(source) != args.expected_sha256:
        parser.error('Source hash mismatch')
    if args.output.exists():
        parser.error('Use a new output file')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('p04_finality_source', source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='p04-finality-') as temporary:
        p = Probe(module, Path(temporary)/'ledger.sqlite')
        final_overcap_then_stale_observation(p)
        result = p.finish()
    total = len(result['checks'])
    assert total == 19
    report = {
        'status': result['status'], 'cases_run': 1, 'checks_total': total,
        'checks_failed': len(result['failed_checks']), 'result': result,
        'source_sha256': digest(source), 'probe_sha256': digest(Path(__file__)),
        'python': platform.python_version(), 'platform': platform.system(),
        'sqlite': sqlite3.sqlite_version, 'no_site': bool(sys.flags.no_site),
        'historical_23_method_suite_executed': False,
        'scope': 'Final overrun, older observation, reopen and invoice replay. Freeze and known cost retained; no authentic bill or external effect.'}
    args.output.write_bytes((json.dumps(report, indent=2)+'\n').encode('utf-8'))
    print(json.dumps({k: report[k] for k in ['status','cases_run','checks_total','checks_failed']}))
    return 0 if result['status'] == 'PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
