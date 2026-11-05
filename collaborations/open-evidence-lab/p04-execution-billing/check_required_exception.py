"""Reject an omitted mandatory exception field in both synthetic P04 profiles.

Two real local adapter anchors, ten related reader observations of one mechanism.
No external effects or authentic invoices are evaluated.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(root))
    generator = load(root/'generate_cases.py', 'exception_generator')
    v01 = load(root/'run_adapter_contract.py', 'exception_reader_v01')
    v02 = load(root/'run_m4_review.py', 'exception_reader_v02')
    case = next(c for c in generator.cases() if c['id'] == 'F04')
    def inputs(steps):
        return [{k:v for k,v in s.items() if k not in {'raises','expect_return'}} for s in steps]
    def expected_events(steps):
        return [{'exception':s.get('raises'),'return':s.get('expect_return',{})} for s in steps]
    expected = {'id':'F04', 'observed':case['expected'],
                'steps':expected_events(case['steps']), 'probes':expected_events(case['probes'])}
    profiles = [
        ('v01', 'p04_adapter.py', {'id':'F04','budget':case.get('budget',3),
          'steps':inputs(case['steps']),'probes':inputs(case['probes'])},
         [('steps',2),('probes',0)]),
        ('v02', 'p04_state_adapter.py', copy.deepcopy(v02.CASE),
         [('steps',0),('probes',0),('probes',1),('probes',2)])]
    pre = {'mechanism':'missing mandatory exception field is not explicit null',
           'expected_positive':True, 'expected_missing':False, 'expected_conflict':False,
           'profiles':{p[0]:{'input':p[2], 'omission_locations':p[3]} for p in profiles},
           'reader_sha256':{n:hashlib.sha256((root/n).read_bytes()).hexdigest()
                            for n in ('run_adapter_contract.py','run_m4_review.py')}}
    (args.out/'PREEXECUTION.json').write_text(json.dumps(pre,indent=2)+'\n',encoding='utf-8')
    rows = []
    processes = []
    with tempfile.TemporaryDirectory(prefix='p04-required-exception-') as temp:
        for profile, adapter, payload, locations in profiles:
            inp = Path(temp)/(profile+'.json')
            inp.write_text(json.dumps(payload),encoding='utf-8')
            command = [sys.executable,'-S','-B',str(root/adapter),str(inp),'--json']
            result = subprocess.run(command,capture_output=True,timeout=40)
            (args.out/(profile+'.stdout.txt')).write_bytes(result.stdout)
            (args.out/(profile+'.stderr.txt')).write_bytes(result.stderr)
            processes.append({'profile':profile,'returncode':result.returncode,
                              'adapter_sha256':hashlib.sha256((root/adapter).read_bytes()).hexdigest()})
            if result.returncode != 0:
                raise RuntimeError('Adapter operational failure, not a regression result: '+profile)
            observed = json.loads(result.stdout)
            variants = [('native_positive', observed, True)]
            for seq, index in locations:
                changed = copy.deepcopy(observed)
                if changed[seq][index]['exception'] is not None:
                    raise RuntimeError('Positive anchor unexpectedly raised')
                del changed[seq][index]['exception']
                variants.append((f'missing_{seq}_{index}',changed,False))
            conflict = copy.deepcopy(observed)
            seq, index = locations[0]
            conflict[seq][index]['exception'] = 'EvidenceConflict'
            variants.append(('explicit_conflict',conflict,False))
            for variant, value, wanted in variants:
                errors = v01.judge(expected,value) if profile=='v01' else v02.judge(value)
                rows.append({'profile':profile,'variant':variant,'expected_accept':wanted,
                             'actual_accept':not errors,'matches_expected':(not errors)==wanted,
                             'reader_failures':errors})
    required_keys = {(p,v) for p,_,_,locs in profiles for v in
                     ['native_positive','explicit_conflict']+[f'missing_{s}_{i}' for s,i in locs]}
    if len(rows)!=10 or {(r['profile'],r['variant']) for r in rows} != required_keys:
        raise RuntimeError('Bounded matrix identities differ')
    report = {'status':'PASS' if all(r['matches_expected'] for r in rows) else 'FAIL',
              'python':platform.python_version(),'os':platform.system(),
              'mechanisms':1,'native_adapter_runs':2,'related_observations':10,
              'missing_field_observations':6,'rows':rows,'processes':processes,
              'source_sha256':pre['reader_sha256'],
              'ledger_sha256':hashlib.sha256((root/'upstream/exposure_ledger.py').read_bytes()).hexdigest(),
              'scope':'Same-team synthetic local readers. No real external effects or invoice authenticity established.'}
    (args.out/'SUMMARY.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'rows','processes','source_sha256'}},indent=2))
    return int(report['status']!='PASS')


if __name__=='__main__':
    raise SystemExit(main())
