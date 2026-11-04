"""Offline P04 regression/bridge candidate. Uses only the Python standard library."""
from __future__ import annotations
import argparse
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

ROOT=Path(__file__).resolve().parent
UPSTREAM=ROOT/'upstream/exposure_ledger.py'
EXPECTED_BLOB='3b9599c4fa1063156b28aea0588634f9ca04cefe'


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_source(path):
    name='p04_under_test'
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None: raise RuntimeError('source import unavailable')
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
    return mod


def project(snapshot):
    a=next(x for x in snapshot['attempts'] if x['attempt_id']=='A')
    return {'execution_outcome':a['outcome'],'billing_finality':a['billing_finality'],
        'known_spend_microusd':a['known_spend_microusd'],
        'held_microusd':a['still_exposed_reservation_microusd'],
        'available_microusd':snapshot['available_for_admission_microusd'],
        'unbounded':a['unbounded_exposure'],'frozen':snapshot['frozen']}


def perform(mod,ledger,s,index):
    cmd=s['cmd'];attempt=s.get('attempt','A');event=s.get('event',f'e-{index}')
    roles={'dispatch':('dispatch_start','dispatch_gate'), 'unknown':(s.get('reason','response_lost'),'client'),
           'outcome':('execution_outcome','executor'), 'invoice':('final_invoice','provider_billing'),
           'cost':('cost_observation','usage_meter'), 'non_dispatch':('non_dispatch_proof','dispatch_gate')}
    if cmd=='reserve': return ledger.reserve(attempt,s['amount'])
    kind,role=roles[cmd]
    ev=mod.Evidence(kind,s.get('source',role),f'fixture:{event}',s.get('evidence_attempt',attempt))
    bound=mod.Evidence('enforced_cost_ceiling','provider_contract','fixture:ceiling',attempt)
    if cmd=='dispatch':
        ceiling=s.get('ceiling',True)
        return ledger.mark_dispatch_started(attempt,event,ev,bounded_by_authorization=ceiling,bound_evidence=bound if ceiling else None)
    if cmd=='unknown':
        bounded=s['bounded']
        return ledger.mark_unknown(attempt,event,reason=kind,unbounded=not bounded,evidence=ev,bound_evidence=bound if bounded else None)
    if cmd=='outcome': return ledger.observe_outcome(attempt,event,s['value'],ev)
    if cmd=='invoice': return ledger.finalize_invoice(attempt,event,s['amount'],ev)
    if cmd=='cost': return ledger.observe_cost(attempt,event,s['amount'],ev)
    if cmd=='non_dispatch': return ledger.confirm_non_dispatch(attempt,event,ev)
    raise ValueError('unsupported fixture command')


def run_step(mod,ledger,s,index):
    try:
        result=perform(mod,ledger,s,index)
    except Exception as exc:
        actual=type(exc).__name__
        return {'cmd':s['cmd'],'exception':actual,'ok':actual==s.get('raises')}
    wanted=s.get('expect_return',{})
    ok='raises' not in s and all(result.get(k)==v for k,v in wanted.items())
    return {'cmd':s['cmd'],'exception':None,'selected_return':{k:result.get(k) for k in wanted},'ok':ok}


def evaluate_case(mod,source,case):
    row={'case':case['id'],'invariant':case['invariant'],'expected':case['expected'],'steps':[],'probes':[]}
    with tempfile.TemporaryDirectory(prefix='p04-dual-finality-') as td:
        db=Path(td)/'account.sqlite'
        try:
            ledger=mod.ExposureLedger(db,case.get('budget',3))
            ledger.reserve('A',2)
            for i,step in enumerate(case['steps']): row['steps'].append(run_step(mod,ledger,step,i))
            snapshot=ledger.snapshot();row['observed']=project(snapshot)
            # This is an actual fresh interpreter reading the persisted SQLite file.
            p=subprocess.run([sys.executable,'-S','-B',str(Path(__file__).resolve()),'--snapshot',str(db),'--source',str(source),'--probes-json',json.dumps(case.get('probes',[]))],
                             text=True,encoding='utf-8',capture_output=True,timeout=20,check=False)
            if p.returncode != 0: raise RuntimeError(f'reopen process exit {p.returncode}: {p.stderr[:200]}')
            worker=json.loads(p.stdout)
            row['fresh_process_snapshot_equal']=snapshot==worker['snapshot']
            row['probes']=worker['probes']
            row['probes_executed_in_fresh_process']=True
            row['export']={'contract':'execution-billing-finality/v0.1-proposal','operation_id':'A',
                'execution_outcome':snapshot['attempts'][0]['outcome'],
                'billing_finality':snapshot['attempts'][0]['billing_finality'],
                'external_effect':'NOT_EVALUATED',
                'source_role_authenticity':'TRUSTED_FIXTURE_ASSERTION_NOT_AUTHENTICATED',
                'same_attempt_redispatch':'NOT_INFERRED_FROM_BILLING',
                'snapshot':snapshot,
                'must_not_claim':['external_effect_established','invoice_authenticity','production_durability','upstream_acceptance']}
            row['pass']=(row['observed']==row['expected'] and row['fresh_process_snapshot_equal'] and
                         all(x['ok'] for x in row['steps']+row['probes']))
        except Exception as exc:
            row.update(error=type(exc).__name__+': '+str(exc));row['pass']=False
    return row


def mutate(text,changes):
    for old,new in changes:
        count=text.count(old)
        if count!=1: raise RuntimeError(f'mutant splice count {count}, expected 1: {old[:80]}')
        text=text.replace(old,new,1)
    return text


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path);ap.add_argument('--snapshot',type=Path);ap.add_argument('--source',type=Path,default=UPSTREAM);ap.add_argument('--probes-json',default='[]')
    args=ap.parse_args()
    if args.snapshot:
        mod=load_source(args.source);ledger=mod.ExposureLedger(args.snapshot)
        before=ledger.snapshot()
        probes=[run_step(mod,ledger,s,i) for i,s in enumerate(json.loads(args.probes_json),100)]
        print(json.dumps({'snapshot':before,'probes':probes},sort_keys=True));return
    if not args.out: ap.error('--out is required')
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    raw=UPSTREAM.read_bytes();blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    if blob!=EXPECTED_BLOB: raise SystemExit('upstream Git blob mismatch; refusing to run')
    generator=subprocess.run([sys.executable,'-S','-B',str(ROOT/'generate_cases.py'),'--check'],text=True,capture_output=True,timeout=10)
    if generator.returncode: raise SystemExit('fixture regeneration failed')
    fixture=json.loads((ROOT/'cases.json').read_text(encoding='utf-8'))
    started=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    base=[evaluate_case(load_source(UPSTREAM),UPSTREAM,c) for c in fixture['cases']]
    (out/'base.json').write_text(json.dumps(base,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    old='remainder = 0 if row["billing_finality"] == "FINAL" else max(0, row["authorized_max"] - row["known"])'
    mutators={
       'success_releases_exposure':[(old,'remainder = 0 if row["billing_finality"] == "FINAL" or row["outcome"] == "SUCCEEDED" else max(0, row["authorized_max"] - row["known"])')],
       'invoice_implies_execution':[("UPDATE attempts SET known=?,billing_finality='FINAL',finality_basis='final_invoice',", "UPDATE attempts SET known=?,outcome='SUCCEEDED',billing_finality='FINAL',finality_basis='final_invoice',")],
       'unknown_is_zero':[(old,'remainder = 0 if row["billing_finality"] == "FINAL" or (row["outcome"] == "UNKNOWN" and row["dispatch_state"] == "POSSIBLE") else max(0, row["authorized_max"] - row["known"])')],
       'ignore_unbounded_liability':[
          ('0 if account["frozen"] or unbounded else max(0, nominal)','0 if account["frozen"] else max(0, nominal)'),
          ('snap["frozen"] or snap["unbounded_exposure_count"] or maximum','snap["frozen"] or maximum'),
          ('snapshot["frozen"] or snapshot["unbounded_exposure_count"]:','snapshot["frozen"]:')],
       'refuse_every_admission':[("attempt_id = _id(attempt_id, \"attempt_id\")\n        maximum =", "raise AdmissionDenied('mutant refuses all admissions')\n        attempt_id = _id(attempt_id, \"attempt_id\")\n        maximum =")],
    }
    mutants=[];(out/'mutants').mkdir()
    for name,changes in mutators.items():
        path=out/'mutants'/f'{name}.py';path.write_text(mutate(raw.decode(),changes),encoding='utf-8')
        # Compile errors are not mutation kills.
        compile(path.read_text(encoding='utf-8'),str(path),'exec')
        mod=load_source(path)
        rows=[evaluate_case(mod,path,c) for c in fixture['cases']]
        failures=[r['case'] for r in rows if not r['pass']]
        errors=[r['error'] for r in rows if 'error' in r]
        unexpected=[e for e in errors if not (name=='refuse_every_admission' and e.startswith('AdmissionDenied:'))]
        if unexpected: raise RuntimeError('Operational errors do not count as mutation kills: '+str(unexpected))
        mutants.append({'mutant':name,'detected':bool(failures),'witnesses':failures,'operational_errors':unexpected,'sha256':digest(path)})
        (out/'mutants'/f'{name}.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    result={'status':'PASS' if all(r['pass'] for r in base) and all(m['detected'] for m in mutants) else 'FAIL',
       'run_started_utc':started,'python':platform.python_version(),'os':platform.system(),'sqlite':sqlite3.sqlite_version,
       'upstream_commit':'c21bbbc0f9b087d5f1ed2e2cf4fbf4944b6b0e01','upstream_git_blob':blob,'upstream_sha256':digest(UPSTREAM),
       'cases_sha256':digest(ROOT/'cases.json'),'runner_sha256':digest(__file__),
       'cases':len(base),'matching_cases':sum(r['pass'] for r in base),
       'fresh_process_reopens_matching':sum(r.get('fresh_process_snapshot_equal',False) for r in base),
       'fresh_process_probe_cases':sum(bool(c.get('probes')) for c in fixture['cases']),'selected_mutants':len(mutants),'detected_mutants':sum(m['detected'] for m in mutants),'mutants':mutants,
       'scope':'same-session AI-assisted targeted tests of unchanged P04 source; not original full suite; not independent external validation',
       'not_run':['Probity CLI or corpus','P06 provider','ZTI MCP clients','original P04 full test suite','remote effect owner','real billing provider','other operating systems in this execution']}
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
    if result['status']!='PASS':raise SystemExit(1)

if __name__=='__main__': main()
