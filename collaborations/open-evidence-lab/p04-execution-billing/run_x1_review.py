"""Reproduce Pico's X1 and dispatch-guard mutation observations offline.

Credit: piiiico, https://github.com/probityai/agent-evidence-vectors/issues/352#issuecomment-6601133451
Same-team AI-assisted reproduction, not independent validation.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import sys
import copy
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
KIT = ROOT
sys.path.insert(0, str(KIT))
import run_review as rr
from run_adapter_contract import judge

PIN = '3b9599c4fa1063156b28aea0588634f9ca04cefe'
X1 = {
    'id': 'X1',
    'invariant': 'invoice before any recorded dispatch does not open the gate',
    'steps': [{'cmd': 'invoice', 'amount': 1, 'event': 'invoice-1'}],
    'expected': {
        'execution_outcome': 'UNKNOWN', 'billing_finality': 'FINAL',
        'known_spend_microusd': 1, 'held_microusd': 0, 'available_microusd': 2,
        'unbounded': False, 'frozen': False,
    },
    'probes': [{'cmd': 'dispatch', 'event': 'late-dispatch',
                'expect_return': {'dispatch_allowed': False}}],
}

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def inspect_x1(mod) -> dict:
    """Observe both axes and dispatch state without claiming an external effect."""
    with tempfile.TemporaryDirectory(prefix='p04-x1-inspect-') as tmp:
        ledger = mod.ExposureLedger(Path(tmp) / 'ledger.sqlite', 3)
        ledger.reserve('A', 2)
        before = ledger.snapshot()['attempts'][0]
        invoice = rr.perform(mod, ledger, X1['steps'][0], 0)
        after = ledger.snapshot()['attempts'][0]
        gate = rr.perform(mod, ledger, X1['probes'][0], 100)
        return {
            'before_invoice': before, 'invoice_return': invoice,
            'after_invoice_before_dispatch_probe': after,
            'later_dispatch_return': gate,
            'external_effect': 'NOT_EVALUATED',
        }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    original = rr.UPSTREAM
    raw = original.read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if blob != PIN:
        raise RuntimeError('Source pin mismatch')
    check = subprocess.run([sys.executable, '-S', '-B', str(KIT/'generate_cases.py'), '--check'],
                           capture_output=True, timeout=20, check=False)
    if check.returncode:
        raise RuntimeError('Original fixtures failed regeneration check')
    cases = json.loads((KIT / 'cases.json').read_text(encoding='utf-8'))['cases']
    if len(cases) != 18:
        raise RuntimeError('Original scenario population changed')
    # Freeze the new expectation before importing/executing any variant.
    (out / 'X1_FROZEN.json').write_text(json.dumps(X1, indent=2) + '\n', encoding='utf-8', newline='\n')
    guard = 'if row["dispatch_state"] != "RESERVED" or row["billing_finality"] != "UNKNOWN":'
    invoice = "last_final_invoice=?,cost_evidence_seen=1,unbounded=0,dispatch_state='POSSIBLE',updated_ns=? WHERE id=?"
    no_write = 'last_final_invoice=?,cost_evidence_seen=1,unbounded=0,updated_ns=? WHERE id=?'
    no_billing = 'if row["dispatch_state"] != "RESERVED":'
    specs = {
        'baseline': [],
        'M1_guard_removed': [(guard, 'if False:')],
        'M2_final_billing_bypasses_guard': [(guard,
            'if (row["dispatch_state"] != "RESERVED" or row["billing_finality"] != "UNKNOWN") and row["billing_finality"] != "FINAL":')],
        'M3_billing_clause_removed': [(guard, no_billing)],
        'M4_invoice_possible_write_removed': [(invoice, no_write)],
        'M5_M3_plus_M4': [(guard, no_billing), (invoice, no_write)],
    }
    expected_failures = {
        'baseline': [],
        'M1_guard_removed': ['F03', 'F04', 'F08', 'F09', 'X1'],
        'M2_final_billing_bypasses_guard': ['F04', 'F08', 'F09', 'X1'],
        'M3_billing_clause_removed': [],
        'M4_invoice_possible_write_removed': [],
        'M5_M3_plus_M4': ['X1'],
    }
    (out / 'EXPECTED_MUTATION_BEHAVIOR.json').write_text(json.dumps(expected_failures, indent=2) + '\n', encoding='utf-8', newline='\n')
    rows = []
    (out / 'mutants').mkdir()
    for name, splices in specs.items():
        path = original
        if splices:
            path = out / 'mutants' / (name + '.py')
            mutated = rr.mutate(raw.decode('utf-8'), splices)
            compile(mutated, str(path), 'exec')
            path.write_text(mutated, encoding='utf-8', newline='\n')
        mod = rr.load_source(path)
        outcomes = [rr.evaluate_case(mod, path, case) for case in [*cases, X1]]
        operational = [r['error'] for r in outcomes if 'error' in r]
        if operational:
            raise RuntimeError('Operational failures do not count as mutation detection: ' + str(operational))
        # In these scenarios only AdmissionDenied, EvidenceValidationError and
        # EvidenceConflict are contractual; any other exception invalidates the run.
        allowed_exceptions = {None, 'AdmissionDenied', 'EvidenceValidationError', 'EvidenceConflict'}
        for r in outcomes:
            for event in r['steps'] + r['probes']:
                if event.get('exception') not in allowed_exceptions:
                    raise RuntimeError('Unexpected implementation error: ' + str(event))
        for record in outcomes:
            observed = record['observed']
            for field in ('known_spend_microusd', 'held_microusd', 'available_microusd'):
                if type(observed[field]) is not int:
                    raise RuntimeError('Non-integer observed amount')
            for field in ('unbounded', 'frozen'):
                if type(observed[field]) is not bool:
                    raise RuntimeError('Non-boolean state flag')
            for event in record['steps'] + record['probes']:
                if any(type(v) is not bool for v in event.get('selected_return', {}).values()):
                    raise RuntimeError('Non-boolean return flag')
        failures = [r['case'] for r in outcomes if not r['pass']]
        (out / (name + '.json')).write_text(json.dumps(outcomes, indent=2) + '\n', encoding='utf-8', newline='\n')
        x1_view = inspect_x1(mod)
        (out / (name + '_X1_state.json')).write_text(json.dumps(x1_view, indent=2) + '\n', encoding='utf-8', newline='\n')
        rows.append({
            'variant': name, 'source_sha256': sha(path),
            'original_cases': 18,
            'original_cases_matching': sum(r['pass'] for r in outcomes[:-1]),
            'X1_matches_expected_refusal': outcomes[-1]['pass'] and outcomes[-1]['probes'][0]['selected_return']['dispatch_allowed'] is False,
            'X1_dispatch_allowed': outcomes[-1]['probes'][0]['selected_return']['dispatch_allowed'],
            'X1_dispatch_state_after_invoice': x1_view['after_invoice_before_dispatch_probe']['dispatch_state'],
            'failed_cases': failures,
            'matches_predeclared_mutation_behavior': failures == expected_failures[name],
            'operational_errors': [],
        })
    # The adapter receives no expected answers. The judge sees them separately.
    x1_input = {'id': 'X1', 'budget': 3, 'steps': X1['steps'],
                'probes': [{k:v for k,v in s.items() if k != 'expect_return'} for s in X1['probes']]}
    input_path = out/'X1_INPUT.json'
    input_path.write_text(json.dumps(x1_input, indent=2)+'\n', encoding='utf-8', newline='\n')
    expected_adapter = {'id':'X1', 'observed': X1['expected'],
                        'steps':[{'exception':None, 'return':{}}],
                        'probes':[{'exception':None, 'return':{'dispatch_allowed':False}}]}
    proc = subprocess.run([sys.executable, '-S', '-B', str(KIT/'p04_adapter.py'), str(input_path), '--json'],
                          capture_output=True, text=True, encoding='utf-8', timeout=45, check=False)
    if proc.returncode:
        raise RuntimeError('X1 adapter operational failure: '+proc.stderr[:200])
    actual_adapter = json.loads(proc.stdout.strip().splitlines()[-1])
    adapter_failures = judge(expected_adapter, actual_adapter)
    (out/'X1_ADAPTER.json').write_text(json.dumps(actual_adapter, indent=2)+'\n', encoding='utf-8', newline='\n')
    reader_probes = []
    for label, value in [('unsafe_dispatch', True), ('integer_is_not_boolean', 0)]:
        tampered = copy.deepcopy(actual_adapter)
        tampered['probes'][0]['return']['dispatch_allowed'] = value
        reader_probes.append({'probe':label, 'failures':judge(expected_adapter, tampered)})
    controls = []
    mod = rr.load_source(original)
    for label in ['ordinary_first_dispatch', 'invoice_unknown_attempt', 'invoice_wrong_role', 'invoice_after_fenced_non_dispatch']:
        with tempfile.TemporaryDirectory(prefix='p04-x1-control-') as tmp:
            ledger = mod.ExposureLedger(Path(tmp)/'db.sqlite', 3)
            ledger.reserve('A', 2)
            if label == 'ordinary_first_dispatch':
                value = rr.perform(mod, ledger, {'cmd':'dispatch'}, 0)
                ok = value['dispatch_allowed'] is True
                observed = 'allowed' if ok else 'refused'
            else:
                item = {'cmd':'invoice','amount':1}
                expected_error = 'EvidenceValidationError'
                if label == 'invoice_unknown_attempt':
                    item['attempt'] = 'unregistered'
                    expected_error = 'UnknownAttempt'
                elif label == 'invoice_wrong_role':
                    item['source'] = 'executor'
                else:
                    rr.perform(mod, ledger, {'cmd':'non_dispatch'}, 0)
                    expected_error = 'EvidenceConflict'
                try:
                    rr.perform(mod, ledger, item, 1)
                except (mod.LedgerError, mod.EvidenceValidationError) as exc:
                    observed = type(exc).__name__
                    ok = observed == expected_error
                else:
                    observed, ok = 'accepted', False
            controls.append({'control':label,'observed':observed,'pass':ok})
    extra_ok = not adapter_failures and all(x['failures'] for x in reader_probes) and all(x['pass'] for x in controls)
    if original.read_bytes() != raw:
        raise RuntimeError('Original source was modified')
    result = {
        'status': 'PASS' if all(r['matches_predeclared_mutation_behavior'] for r in rows) and extra_ok else 'FAIL',
        'run_utc': datetime.now(timezone.utc).isoformat(),
        'os': platform.system(), 'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
        'historical_candidate_commit': 'c7edf5abbdb920e115d791f686bc04cf0524b481',
        'upstream_git_blob': blob, 'upstream_sha256': sha(original),
        'runner_sha256': sha(Path(__file__)), 'cases_sha256': sha(KIT / 'cases.json'),
        'X1_sha256': sha(out / 'X1_FROZEN.json'),
        'distinct_scenarios': 19, 'variants_including_baseline': 6, 'matrix_observations': 114,
        'rows': rows,
        'X1_adapter_failures': adapter_failures,
        'X1_reader_probes': reader_probes,
        'boundary_controls': controls,
        'interpretation': {
            'invoice_before_recorded_dispatch': 'ACCEPTED_FOR_EXISTING_RESERVED_ATTEMPT_WITH_TRUSTED_VALID_EVIDENCE',
            'baseline_has_demonstrated_safety_bug': False,
            'new_case_detects_previously_uncovered_double_mutation': True,
            'M3': 'equivalent for public-API reachable states in unchanged source; not a killed mutant',
            'M4': 'survives the selected gate test, but changes internal dispatch_state; not globally equivalent',
            'external_effect': 'NOT_EVALUATED',
        },
        'limits': ['same-assistant local reproduction, not independent validation',
                   'normal fresh-process reopen, not crash or power-loss proof',
                   'no real invoice or external effect; trusted synthetic evidence',
                   'no Probity CLI, no other operating systems in this execution, no full P04 suite',
                   'test runner performs no remote code modification or publication',
                   '114 matrix observations are not 114 independent experiments'],
    }
    (out / 'SUMMARY.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
