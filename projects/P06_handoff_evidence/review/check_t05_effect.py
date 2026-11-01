"""Inject ACK-without-effect into a copy; run one new oracle challenge only."""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import sys

sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--mode', choices=['classic','adapter'], default='classic')
    ap.add_argument('--fault', choices=['ack_without_effect','none'], default='ack_without_effect')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    original = args.project / 'provider_boundary'
    mutant = args.out / ('faulted_provider_copy' if args.fault!='none' else 'unmodified_provider_copy')
    shutil.copytree(original, mutant, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    target = mutant / 'src/p06_boundary/provider.py'
    before = target.read_bytes().decode('utf8')
    marker = '    effect_id = db.execute("INSERT INTO effects('
    if before.count(marker) != 1:
        raise RuntimeError('Exact fault-insertion anchor not unique')
    addition = ('    # REVIEWER2_FAULT: acknowledges the operation without persisting an effect.\n'
                '    return {"ok":True,"replayed":False,"receipt":{"reviewer2_fault":"ACK_WITHOUT_EFFECT"}}\n')
    after = before.replace(marker, addition + marker, 1) if args.fault!='none' else before
    if args.fault != 'none':
        target.write_bytes(after.encode('utf8'))
    (args.out / 'injected_fault.diff').write_text(''.join(difflib.unified_diff(
        before.splitlines(True), after.splitlines(True), fromfile='exact/provider.py',
        tofile='faulted/provider.py')), encoding='utf8')
    sys.path.insert(0, str(mutant))
    spec = importlib.util.spec_from_file_location('reviewer2_exact_evaluator', mutant / 'run.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.run_case(args.out / 'one_new_case', 'T05',
                             'reviewer2_execute_ack_without_effect' if args.fault!='none' else 'reviewer2_affected_atomic_control',
                             'atomic', args.mode)
    observation_path = args.out / ('one_new_case/T05__atomic__'+args.mode+'/observation.json')
    observation = json.loads(observation_path.read_text()) if observation_path.exists() else None
    report = {
        'base_commit': 'da6e193a2c3290eec3876c9139719b7ec12f3013',
        'experiment': 'NEW_ACK_WITHOUT_EFFECT_ORACLE_CHALLENGE' if args.fault!='none' else 'AFFECTED_T05_ATOMIC_CONTROL_ONLY',
        'argv': sys.argv, 'python': sys.version, 'platform': platform.platform(),
        'mode': args.mode, 'fault': args.fault,
        'mutation': 'One explicit early success return before effect INSERT; copied provider only.' if args.fault!='none' else 'None: unmodified affected provider control.',
        'evaluator_unchanged': (original / 'run.py').read_bytes() == (mutant / 'run.py').read_bytes(),
        'observer_unchanged': (original / 'observe.py').read_bytes() == (mutant / 'observe.py').read_bytes(),
        'source_sha256': {name:hashlib.sha256((original/name).read_bytes()).hexdigest()
                          for name in ['run.py','observe.py','src/p06_boundary/provider.py']},
        'original_provider_sha256': hashlib.sha256((original / 'src/p06_boundary/provider.py').read_bytes()).hexdigest(),
        'mutant_provider_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
        'run_case_result': result,
        'observed_effect_count': None if observation is None else observation['effect_count'],
        'false_positive_reproduced': args.fault!='none' and result['status'] == 'PASS' and observation is not None and observation['effect_count'] == 0,
        'expected_runner_status': 'FAIL' if args.fault!='none' else 'PASS',
        'expectation_met': result['status']==('FAIL' if args.fault!='none' else 'PASS') and observation is not None and observation['effect_count']==(0 if args.fault!='none' else 1),
        'qualification': 'Does not claim the original provider omits effects. The fault challenges the exact published evaluator with an omitted required effect.'
    }
    report['probe_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report['status'] = 'PASS' if report['expectation_met'] else 'FAIL'
    (args.out / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k: report[k] for k in ['mode','fault','evaluator_unchanged','observer_unchanged','observed_effect_count','false_positive_reproduced','expectation_met']}, indent=2))
    return 0 if report['expectation_met'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
