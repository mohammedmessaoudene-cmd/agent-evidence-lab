"""Three targeted signed-identity regressions using the real Engine and auditor."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.local/deps'))
sys.path.insert(0, str(ROOT / 'src'))
from p02.audit import audit_store
from p02.engine import Engine
from p02.wire import Rejected, sign, verify

PROTOCOL = ROOT / 'protocol/receipt_identity_regression.json'


def save(path, value):
    path.write_bytes((json.dumps(value, indent=2, ensure_ascii=True) + '\n').encode('utf-8'))


def logical_snapshot(engine):
    return hashlib.sha256(('\n'.join(engine.db.iterdump()) + '\n').encode('utf-8')).hexdigest()


def admission_case(folder, contract, case):
    fixture = copy.deepcopy(contract['fixture'])
    engine = Engine(folder / 'store.sqlite', fixture, contract['mode'])
    try:
        for event, leaf, value in [('1', 'A', 20), ('2', 'B', 30)]:
            correction = engine.correction(event, fixture['leaves'][leaf]['issuer'],
                                           [{'leaf': leaf, 'revision': 1, 'value': value}])
            assert engine.ingest(correction) == 'APPLIED'
        payload = copy.deepcopy(engine.make_receipt('1', 'D_main')['payload'])
        payload['event_id'] = case['event_id']
        submitted = sign(payload, 'consumer-a')
        verify(submitted, engine.registry)
        save(folder / 'submitted_receipt.json', submitted)
        before = logical_snapshot(engine)
        statements = []
        accepted, rejection, returned = False, None, None
        engine.db.set_trace_callback(statements.append)
        try:
            returned = engine.accept_receipt(submitted, replay=True)
            accepted = True
        except Rejected as error:
            rejection = str(error)
        finally:
            engine.db.set_trace_callback(None)
        after = logical_snapshot(engine)
        engine_status = engine.summary('1')['status']
        audit = audit_store(engine.path, '1')
        save(folder / 'audit_after.json', audit)
        wanted = case['expected_acceptance']
        unchanged = before == after
        checks = {
            'acceptance_matches_oracle': accepted == wanted,
            'rejection_is_explicit': wanted or rejection == 'invalid review identity',
            'rejection_preserves_logical_store': wanted or unchanged,
            'rejection_precedes_sql': wanted or not statements,
            'valid_receipt_has_supported_local_replay': not wanted or (
                returned == 'LOCAL_REPLAY' and engine_status == 'COMPLETE_REGISTERED_LOCAL_REPLAY'
                and audit['known_obligations_closed']
                and audit['signature_evidence']['verified_assertions'] == 1),
            'coverage_and_external_action_remain_unknown': (
                audit['global_consumer_coverage'] == audit['external_action_performed'] == 'UNKNOWN'),
        }
        return {
            'case_id': case['case_id'], 'mode': contract['mode'],
            'status': 'PASS' if all(checks.values()) else 'FAIL', 'checks': checks,
            'evidence': {
                'signature_valid_in_test_registry': True,
                'receipt_event_id_type': type(case['event_id']).__name__,
                'expected_acceptance': wanted, 'receipt_accepted': accepted,
                'returned_verification': returned, 'rejection': rejection,
                'logical_store_unchanged': unchanged,
                'logical_store_before_sha256': before, 'logical_store_after_sha256': after,
                'admission_sql_statements': len(statements),
                'engine_status': engine_status,
                'audit_closure': audit['known_obligations']['closure'],
                'known_obligations_closed': audit['known_obligations_closed'],
                'audit_finding_codes': [f['code'] for f in audit['findings']],
                'actual_decision_coverage': audit['actual_decision_coverage'],
                'external_action_performed': audit['external_action_performed'],
            },
        }
    finally:
        engine.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not sys.flags.no_site or sys.flags.optimize:
        parser.error('Use a direct base Python with -S and without -O')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    contract = json.loads(PROTOCOL.read_text(encoding='utf-8'))
    assert [r['case_id'] for r in contract['cases']] == ['valid_string', 'integer_event_id', 'boolean_event_id']
    results = []
    for case in contract['cases']:
        folder = out / case['case_id']
        folder.mkdir()
        try:
            row = admission_case(folder, contract, case)
        except Exception as error:
            row = {'case_id': case['case_id'], 'mode': contract['mode'], 'status': 'HARNESS_ERROR',
                   'error_type': type(error).__name__, 'error': str(error)}
            (folder / 'traceback.txt').write_text(traceback.format_exc(), encoding='utf-8')
        save(folder / 'case_result.json', row)
        results.append(row)
        print(row['case_id'], row['status'], flush=True)
    names = ['src/p02/engine.py', 'src/p02/audit.py', 'src/p02/wire.py',
             'tests/test_receipt_identity.py', 'protocol/receipt_identity_regression.json']
    report = {
        'project': 'P02', 'finding': contract['finding'], 'case_records': len(results),
        'passed': sum(r['status'] == 'PASS' for r in results),
        'failed': sum(r['status'] != 'PASS' for r in results),
        'python': platform.python_version(), 'platform': platform.system(), 'sqlite': sqlite3.sqlite_version,
        'python_site_import_disabled': bool(sys.flags.no_site),
        'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names},
        'results': results, 'scope': contract['scope'], 'limits': contract['limits'],
        'prior_38_cases_rerun': False, 'runtime_or_interop_controls_added': False,
    }
    save(out / 'results.json', report)
    print(json.dumps({k: report[k] for k in ('case_records', 'passed', 'failed')}))
    return 1 if report['failed'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
