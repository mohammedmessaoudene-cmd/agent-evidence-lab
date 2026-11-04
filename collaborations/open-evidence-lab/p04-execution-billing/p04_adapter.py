"""Proposed external scenario adapter: consumes inputs, not expected verdicts."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from run_review import load_source, perform, project, UPSTREAM, EXPECTED_BLOB


def capture(mod,ledger,steps,start=0):
    rows=[]
    for i,s in enumerate(steps,start):
        # Forbidden oracle fields must never reach the runtime adapter.
        if set(s)&{'raises','expect_return','expected'}: raise ValueError('oracle field in input')
        try:
            value=perform(mod,ledger,s,i)
            rows.append({'exception':None,'return':{k:value[k] for k in
                ('new_event','newly_finalized','dispatch_allowed','newly_reserved') if k in value}})
        except (mod.LedgerError,mod.EvidenceValidationError,ValueError) as exc:
            rows.append({'exception':type(exc).__name__,'return':{}})
    return rows


def main():
    p=argparse.ArgumentParser();p.add_argument('scenario',type=Path);p.add_argument('--json',action='store_true');p.add_argument('--reopen',type=Path)
    a=p.parse_args();case=json.loads(a.scenario.read_text(encoding='utf-8'))
    if set(case)!={'id','budget','steps','probes'}:raise ValueError('unexpected input fields')
    b=UPSTREAM.read_bytes()
    if hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()!=EXPECTED_BLOB:raise ValueError('source identity mismatch')
    mod=load_source(UPSTREAM)
    if a.reopen:
        ledger=mod.ExposureLedger(a.reopen);before=ledger.snapshot()
        print(json.dumps({'snapshot':before,'probes':capture(mod,ledger,case['probes'],100)},sort_keys=True));return
    with tempfile.TemporaryDirectory(prefix='p04-adapter-') as td:
        db=Path(td)/'account.sqlite';ledger=mod.ExposureLedger(db,case['budget']);ledger.reserve('A',2)
        steps=capture(mod,ledger,case['steps']);before=ledger.snapshot()
        child=subprocess.run([sys.executable,'-S','-B',str(Path(__file__).resolve()),str(a.scenario.resolve()),'--reopen',str(db),'--json'],
                             text=True,encoding='utf-8',capture_output=True,timeout=20,check=False)
        if child.returncode:raise RuntimeError('fresh-worker failure: '+child.stderr[:200])
        other=json.loads(child.stdout)
        print(json.dumps({'contract':'execution-billing-finality/v0.1-proposal','case':case['id'],
            'observed':project(before),'fresh_process_snapshot_equal':before==other['snapshot'],
            'steps':steps,'probes':other['probes'],'external_effect':'NOT_EVALUATED',
            'source_sha256':hashlib.sha256(b).hexdigest(),
            'must_not_claim':['external_effect_established','invoice_authenticity','production_durability','upstream_acceptance']},sort_keys=True))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'operational_error':type(exc).__name__+': '+str(exc)}));raise SystemExit(2)
