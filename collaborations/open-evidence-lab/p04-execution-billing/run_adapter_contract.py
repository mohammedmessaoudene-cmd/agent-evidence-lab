"""Judge an external adapter. This file neither imports nor executes P04 directly."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shlex
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
FORBIDDEN={'external_effect_established','invoice_authenticity','production_durability','upstream_acceptance'}


def compare_events(wanted,actual):
    if not isinstance(actual,list) or len(wanted)!=len(actual):return False
    for w,a in zip(wanted,actual):
        if not isinstance(a,dict) or a.get('exception')!=w['exception']:return False
        r=a.get('return')
        if not isinstance(r,dict) or any(type(r.get(k)) is not type(v) or r.get(k)!=v for k,v in w['return'].items()):return False
    return True


def judge(expected,actual):
    # Python considers True == 1 and False == 0. Protocol types must not.
    if not isinstance(actual,dict):return ['invalid_shape']
    observed=actual.get('observed')
    money=('known_spend_microusd','held_microusd','available_microusd')
    flags=('unbounded','frozen')
    if not isinstance(observed,dict) or set(observed)!=set(expected['observed']):return ['invalid_state_shape']
    if any(type(observed[k]) is not int or not 0 <= observed[k] <= (1<<63)-1 for k in money):return ['invalid_money_type']
    if any(type(observed[k]) is not bool for k in flags):return ['invalid_boolean_type']
    if not isinstance(actual.get('source_sha256'),str) or re.fullmatch('[0-9a-f]{64}',actual['source_sha256']) is None:return ['invalid_source_identity']
    limits=actual.get('must_not_claim')
    if not isinstance(limits,list) or any(type(v) is not str for v in limits) or len(limits)!=len(set(limits)):return ['invalid_claim_boundaries']
    failures=[]
    if actual.get('contract')!='execution-billing-finality/v0.1-proposal':failures.append('contract')
    if actual.get('case')!=expected['id']:failures.append('case_binding')
    if actual.get('observed')!=expected['observed']:failures.append('state')
    if actual.get('fresh_process_snapshot_equal') is not True:failures.append('reopen')
    if actual.get('external_effect')!='NOT_EVALUATED':failures.append('unsupported_effect_claim')
    if set(actual.get('must_not_claim',[]))!=FORBIDDEN:failures.append('claim_boundaries')
    if not compare_events(expected['steps'],actual.get('steps')):failures.append('steps')
    if not compare_events(expected['probes'],actual.get('probes')):failures.append('probes')
    return failures


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--adapter')
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    command=shlex.split(a.adapter) if a.adapter else [sys.executable,'-S','-B',str(ROOT/'p04_adapter.py')]
    expected=json.loads((ROOT/'fixtures/expected.json').read_text(encoding='utf-8'))
    rows=[]
    for c in expected:
        proc=subprocess.run(command+[str(ROOT/'fixtures/inputs'/f"{c['id']}.json"),'--json'],capture_output=True,text=True,encoding='utf-8',timeout=45,check=False)
        errors=[];observed={}
        if proc.returncode!=0:errors=['operational_error']
        else:
            try:observed=json.loads(proc.stdout.strip().splitlines()[-1]);errors=judge(c,observed)
            except (ValueError,IndexError,TypeError):errors=['invalid_adapter_output']
        rows.append({'case':c['id'],'pass':not errors,'failures':errors,'output':observed})
    result={'status':'PASS' if all(r['pass'] for r in rows) else 'FAIL','cases':len(rows),'matched':sum(r['pass'] for r in rows),
        'runtime':platform.python_version(),'label':'same-team adapter contract run; same 18 scenarios, not 18 new independent experiments',
        'expected_sha256':hashlib.sha256((ROOT/'fixtures/expected.json').read_bytes()).hexdigest(),'rows':rows}
    (a.out/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
    if result['status']!='PASS':raise SystemExit(1)

if __name__=='__main__':main()
