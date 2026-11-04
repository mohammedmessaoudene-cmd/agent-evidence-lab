"""Versioned P04 state observer; never reads expected verdicts.

Synthetic local evidence only. See INPUT_CONTRACT.md, v0.2 extension.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from run_review import load_source, perform, project, UPSTREAM

CONTRACT = 'execution-billing-finality/v0.2-proposal'
BOUNDARIES = ['external_effect_established', 'invoice_authenticity',
              'production_durability', 'upstream_acceptance']


def view(ledger):
    snap = ledger.snapshot()
    result = project(snap)
    result['dispatch_state'] = next(a for a in snap['attempts']
                                    if a['attempt_id'] == 'A')['dispatch_state']
    return result


def act(mod, ledger, step, index):
    if set(step) & {'expected', 'raises', 'expect_return'}:
        raise ValueError('oracle field in runtime input')
    try:
        result = perform(mod, ledger, step, index)
    except (mod.LedgerError, mod.EvidenceValidationError) as exc:
        return {'exception': type(exc).__name__, 'return': {}, 'observed': view(ledger)}
    keys = ('new_event', 'newly_finalized', 'dispatch_allowed', 'state_changed')
    return {'exception': None, 'return': {k: result[k] for k in keys if k in result},
            'observed': view(ledger)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('scenario', type=Path)
    p.add_argument('--source', type=Path, default=UPSTREAM)
    p.add_argument('--reopen', type=Path)
    p.add_argument('--json', action='store_true')
    args = p.parse_args()
    case = json.loads(args.scenario.read_text(encoding='utf-8'))
    if set(case) != {'contract', 'id', 'budget', 'steps', 'probes'} or case['contract'] != CONTRACT:
        raise ValueError('unsupported input contract')
    source = args.source.resolve()
    mod = load_source(source)
    if args.reopen:
        ledger = mod.ExposureLedger(args.reopen)
        start = view(ledger)
        events = [act(mod, ledger, s, i) for i, s in enumerate(case['probes'], 100)]
        end = view(ledger)
        reopened = view(mod.ExposureLedger(args.reopen))
        print(json.dumps({'reopened': start, 'probes': events, 'end': end,
                          'end_reopened': reopened}, sort_keys=True))
        return
    with tempfile.TemporaryDirectory(prefix='p04-state-') as tmp:
        db = Path(tmp) / 'ledger.sqlite'
        ledger = mod.ExposureLedger(db, case['budget'])
        ledger.reserve('A', 2)
        initial = view(ledger)
        events = [act(mod, ledger, s, i) for i, s in enumerate(case['steps'])]
        observed = view(ledger)
        child = subprocess.run([sys.executable, '-S', '-B', str(Path(__file__).resolve()),
                                str(args.scenario.resolve()), '--source', str(source),
                                '--reopen', str(db), '--json'],
                               capture_output=True, text=True, encoding='utf-8', timeout=25,
                               check=False)
        if child.returncode:
            raise RuntimeError('state observer subprocess failed: ' + child.stderr[:200])
        result = json.loads(child.stdout)
        result.update(contract=CONTRACT, case=case['id'], initial=initial, steps=events,
                      observed=observed, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                      external_effect='NOT_EVALUATED', must_not_claim=BOUNDARIES)
        print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'operational_error': type(exc).__name__ + ': ' + str(exc)}), file=sys.stderr)
        raise SystemExit(2)
