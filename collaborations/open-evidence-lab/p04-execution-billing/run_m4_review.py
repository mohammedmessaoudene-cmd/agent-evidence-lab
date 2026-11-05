"""Check the v0.2 dispatch-state contract and Pico's M4 witness.

Credit: piiiico (Agent Errata), Probity #435 comment 6626271127.
These are same-team tests of synthetic evidence, not independent validation.
"""
from __future__ import annotations
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import sqlite3
import subprocess
import sys
import tempfile
import run_review as rr

ROOT = Path(__file__).resolve().parent
CONTRACT = 'execution-billing-finality/v0.2-proposal'
BOUNDARIES = {'external_effect_established', 'invoice_authenticity',
              'production_durability', 'upstream_acceptance'}
FINAL = {'execution_outcome': 'UNKNOWN', 'billing_finality': 'FINAL',
         'known_spend_microusd': 1, 'held_microusd': 0, 'available_microusd': 2,
         'unbounded': False, 'frozen': False, 'dispatch_state': 'POSSIBLE'}
INITIAL = {**FINAL, 'billing_finality': 'UNKNOWN', 'known_spend_microusd': 0,
           'held_microusd': 2, 'available_microusd': 1, 'dispatch_state': 'RESERVED'}
CASE = {'contract': CONTRACT, 'id': 'X1', 'budget': 3,
        'steps': [{'cmd': 'invoice', 'amount': 1, 'event': 'invoice-1'}],
        'probes': [{'cmd': 'dispatch', 'event': 'late-dispatch'},
                   {'cmd': 'invoice', 'amount': 1, 'event': 'invoice-1'},
                   {'cmd': 'cost', 'amount': 1, 'event': 'cost-after-invoice'}]}
RETURNS = [{'dispatch_allowed': False},
           {'new_event': False, 'newly_finalized': False}, {'state_changed': False}]


def same_state(actual, wanted):
    return (type(actual) is dict and set(actual) == set(wanted)
            and all(type(actual[k]) is type(v) and actual[k] == v for k, v in wanted.items()))


def judge(actual):
    if type(actual) is not dict:
        return ['shape']
    errors = []
    if actual.get('contract') != CONTRACT or actual.get('case') != 'X1':
        errors.append('binding')
    source = actual.get('source_sha256')
    if type(source) is not str or re.fullmatch('[0-9a-f]{64}', source) is None:
        errors.append('source')
    limits = actual.get('must_not_claim')
    if (type(limits) is not list or any(type(x) is not str for x in limits)
            or len(limits) != len(set(limits)) or set(limits) != BOUNDARIES
            or actual.get('external_effect') != 'NOT_EVALUATED'):
        errors.append('claim_boundaries')
    if not same_state(actual.get('initial'), INITIAL):
        errors.append('initial_state')
    for key in ('observed', 'reopened', 'end', 'end_reopened'):
        if not same_state(actual.get(key), FINAL):
            errors.append(key)
    steps, probes = actual.get('steps'), actual.get('probes')
    if type(steps) is not list or len(steps) != 1 or type(probes) is not list or len(probes) != 3:
        return errors + ['events_shape']
    for i, (event, wanted) in enumerate(zip(steps + probes, [{'newly_finalized': True}] + RETURNS)):
        if type(event) is not dict or 'exception' not in event:
            errors.append('event_shape_' + str(i))
            continue
        if event.get('exception') is not None or not same_state(event.get('observed'), FINAL):
            errors.append('event_state_' + str(i))
        values = event.get('return')
        if type(values) is not dict or any(type(values.get(k)) is not type(v) or values.get(k) != v
                                          for k, v in wanted.items()):
            errors.append('event_return_' + str(i))
    return errors


def run(source, case_path):
    p = subprocess.run([sys.executable, '-S', '-B', str(ROOT/'p04_state_adapter.py'),
                        str(case_path), '--source', str(source), '--json'],
                       capture_output=True, text=True, encoding='utf-8', timeout=40, check=False)
    if p.returncode:
        raise RuntimeError('operational failure is not a mutant kill: ' + p.stderr[:300])
    value = json.loads(p.stdout)
    for row in value.get('steps', []) + value.get('probes', []):
        if row.get('exception') is not None:
            raise RuntimeError('unexpected action exception: ' + str(row))
    return value


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    raw = rr.UPSTREAM.read_bytes()
    blob = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    if blob != rr.EXPECTED_BLOB:
        raise RuntimeError('original P04 source changed')
    guard = 'if row["dispatch_state"] != "RESERVED" or row["billing_finality"] != "UNKNOWN":'
    invoice = "last_final_invoice=?,cost_evidence_seen=1,unbounded=0,dispatch_state='POSSIBLE',updated_ns=? WHERE id=?"
    no_write = 'last_final_invoice=?,cost_evidence_seen=1,unbounded=0,updated_ns=? WHERE id=?'
    no_billing = 'if row["dispatch_state"] != "RESERVED":'
    variants = {
        'baseline': [], 'M1_guard_removed': [(guard, 'if False:')],
        'M2_final_billing_bypasses_guard': [(guard, 'if ('+guard[3:-1]+') and row["billing_finality"] != "FINAL":')],
        'M3_billing_clause_removed': [(guard, no_billing)],
        'M4_invoice_possible_write_removed': [(invoice, no_write)],
        'M5_M3_plus_M4': [(guard, no_billing), (invoice, no_write)],
    }
    expected = {name: name in {'baseline', 'M3_billing_clause_removed'} for name in variants}
    # Freeze input, requirements and expected mutation classification before execution.
    for filename, value in [('INPUT.json', CASE), ('EXPECTED.json', {'initial': INITIAL, 'after_invoice': FINAL,
                                                                    'returns': RETURNS, 'variants_pass': expected})]:
        (out/filename).write_text(json.dumps(value, indent=2, sort_keys=True)+'\n', encoding='utf-8', newline='\n')
    rows = []; originals = {}
    (out/'mutants').mkdir()
    for name, changes in variants.items():
        path = rr.UPSTREAM
        if changes:
            path = out/'mutants'/(name+'.py')
            text = rr.mutate(raw.decode('utf-8'), changes)
            compile(text, str(path), 'exec')
            path.write_text(text, encoding='utf-8', newline='\n')
        observed = run(path, out/'INPUT.json')
        originals[name] = observed
        failures = judge(observed)
        (out/(name+'.json')).write_text(json.dumps(observed, indent=2)+'\n', encoding='utf-8', newline='\n')
        rows.append({'variant': name, 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'contract_pass': not failures, 'failures': failures,
                     'matches_expected': (not failures) == expected[name]})
    baseline = originals['baseline']; probes = []
    for phase in ('observed', 'reopened', 'end', 'end_reopened'):
        for value in ('RESERVED', None, False):
            changed = copy.deepcopy(baseline); changed[phase]['dispatch_state'] = value
            probes.append({'probe': phase+'_'+str(value), 'rejected': bool(judge(changed))})
        changed = copy.deepcopy(baseline); del changed[phase]['dispatch_state']
        probes.append({'probe': phase+'_missing', 'rejected': bool(judge(changed))})
    for i in range(3):
        changed = copy.deepcopy(baseline); changed['probes'][i]['observed']['dispatch_state'] = 'RESERVED'
        probes.append({'probe': 'probe_state_'+str(i), 'rejected': bool(judge(changed))})
    changed = copy.deepcopy(baseline); changed['probes'][0]['return']['dispatch_allowed'] = 0
    probes.append({'probe': 'integer_not_boolean', 'rejected': bool(judge(changed))})
    changed = copy.deepcopy(baseline); changed['external_effect'] = 'ESTABLISHED'
    probes.append({'probe': 'invented_external_effect', 'rejected': bool(judge(changed))})
    with tempfile.TemporaryDirectory(prefix='p04-positive-') as tmp:
        mod = rr.load_source(rr.UPSTREAM); ledger = mod.ExposureLedger(Path(tmp)/'db.sqlite', 3)
        ledger.reserve('A', 2)
        positive = rr.perform(mod, ledger, {'cmd': 'dispatch'}, 0)['dispatch_allowed'] is True
    if rr.UPSTREAM.read_bytes() != raw:
        raise RuntimeError('original source modified')
    report = {'status': 'PASS' if all(r['matches_expected'] for r in rows) and all(r['rejected'] for r in probes) and positive else 'FAIL',
              'contract': CONTRACT, 'run_utc': datetime.now(timezone.utc).isoformat(),
              'os': platform.system(), 'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
              'source_blob': blob, 'source_sha256': hashlib.sha256(raw).hexdigest(),
              'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'observer_sha256': hashlib.sha256((ROOT/'p04_state_adapter.py').read_bytes()).hexdigest(),
              'rows': rows, 'malformed_output_probes': probes, 'ordinary_dispatch_positive_control': positive,
              'meaning': 'Versioned observable-state requirement; M3 survives, M4/M5 detected. Original code unchanged.',
              'limits': ['same-team AI-assisted synthetic test', 'not independent human validation',
                         'normal process reopen, not crash/power-loss proof', 'no authentic invoices or external effects',
                         'no Probity CLI in this suite', 'stages and mutations are not independent scenarios']}
    (out/'SUMMARY.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2))
    return int(report['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
