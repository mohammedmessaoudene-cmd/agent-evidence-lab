"""Run the preregistered provider-boundary cases offline, using real processes.

Usage: python run.py --out results/fresh
Outputs refuse overwrite. This uses portable stdlib process/file primitives;
the recorded environment, not source appearance, determines platforms tested.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import time
import traceback

BASE=Path(__file__).resolve().parent
SRC=BASE/'src'
sys.path.insert(0,str(SRC))
os.environ['PYTHONPATH']=str(SRC)+os.pathsep+os.environ.get('PYTHONPATH','')

from p06_boundary.common import Refusal, canonical, decode64, read_json, rpc, verify
from p06_boundary.contract import example_manifest
from p06_boundary.coordinator import Coordinator, initialize as coord_init
from p06_boundary.provider import initialize as provider_init
from observe import observe


PROFILES={
 'atomic':{},
 'opaque':{'lookup':False,'idempotency':False},
 'contract_violating_skip':{'fixture_enforcement':'skip_fence'},
 'contract_violating_split':{'fixture_enforcement':'split_check'},
}
MATRIX=[
 ('T01','old_owner_after_authentic_barrier',['atomic','opaque','contract_violating_skip']),
 ('T02','lost_effect_ack',['atomic','opaque']),
 ('T03','expiry_while_old_worker_waits',['atomic']),
 ('T04','different_mission_id',['atomic','contract_violating_skip']),
 ('T05','pause_between_check_and_effect',['atomic','contract_violating_split']),
]


def write_json(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def require(condition,message):
    if not condition:raise AssertionError(message)


def wait_file(path,process=None,timeout=10):
    until=time.monotonic()+timeout
    while not path.exists():
        if process is not None and process.poll() is not None:
            out,err=process.communicate()
            raise AssertionError(f'Process ended before gate {path.name}: {process.returncode}; {out}; {err}')
        if time.monotonic()>=until:raise AssertionError('Gate timeout '+str(path))
        time.sleep(.005)
    return read_json(path)


def collect(p,timeout=20):
    out,err=p.communicate(timeout=timeout)
    try:result=json.loads(out) if out.strip() else None
    except ValueError:result={'unparsed':out}
    return {'pid':p.pid,'exit':p.returncode,'stdout':result,'stderr':err}


class Fixture:
    def __init__(self,path,mode,profile,case):
        self.path=path;path.mkdir(parents=True,exist_ok=False)
        self.mode=mode;self.profile=profile;self.processes=[];self.live=[]
        self.manifest=example_manifest('boundary-mission')
        write_json(path/'manifest.json',self.manifest)
        (path/'fixture.key').write_bytes(hashlib.sha256(b'P06 R2 public local fixture only').digest())
        provider_init(path/'provider.sqlite',PROFILES[profile])
        coord_init(path/'coordinator.sqlite',path/'fixture.key',self.manifest,delegation_seconds=120)
        self.coord=Coordinator(path/'coordinator.sqlite',path/'fixture.key')
        self.meta={'case':case,'mode':mode,'provider_profile':profile,'activated_barriers':[],
                   'actual_rpc_transport':'local subprocess stdin/stdout','supervisor_releases':0}

    def request(self,request,**kwargs):
        return rpc(self.path/'provider.sqlite',self.path/'fixture.key',request,**kwargs)

    def reserve(self,subject,lease=30):
        return self.coord.acquire(self.manifest,subject,lease)

    def activate(self,claim,ack):
        # Verify on the receiver side, then record enough evidence for an
        # independent implementation to authenticate the same receipt again.
        verify(ack['fence_ack'],(self.path/'fixture.key').read_bytes(),'fence_receipt')
        self.coord.activate(claim['mission'],claim['subject'],claim['epoch'],ack['fence_ack'])
        state=self.coord.snapshot(claim['mission'])
        self.meta['activated_barriers'].append({'token':ack['fence_ack'],'activated_at':time.time(),
            'expected':{'mission':claim['mission'],'epoch':claim['epoch'],'subject':claim['subject'],'contract_hash':state['contract_hash']}})

    def claim(self,subject='A',lease=30):
        c=self.reserve(subject,lease)
        ack=self.request({'op':'fence','mission':c['mission'],'grant':c['grant']})
        self.activate(c,ack)
        return c

    def release(self):
        s=self.coord.snapshot(self.manifest['mission'])
        self.coord.release(s['mission'],s['owner'],s['epoch'])
        self.meta['supervisor_releases']+=1

    def intent(self,claim):
        return self.coord.prepare(claim['mission'],'01-reserve',claim['subject'],claim['epoch'])

    def old_worker(self,request):
        ready=self.path/'old-ready.json';resume=self.path/'old-resume'
        content=request if self.mode=='classic' else {'schema':'p06-r2-boundary-envelope/1','request':request}
        inp=self.path/'old-request.json';write_json(inp,content)
        p=subprocess.Popen([sys.executable,str(SRC/'old_worker.py'),str(self.path),'--input',str(inp),
             '--mode',self.mode,'--ready',str(ready),'--resume',str(resume)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.live.append(p)
        self.meta['old_worker_readiness']=wait_file(ready,p)
        return p,resume

    def run_worker(self,subject='A',lose_ack=False):
        args=[sys.executable,'-m','p06_boundary.worker',str(self.path),'--subject',subject,'--mode',self.mode]
        if lose_ack:args.append('--lose-ack')
        p=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);self.live.append(p)
        r=collect(p);self.processes.append(r);return r

    def finish_old(self,p):
        r=collect(p);self.processes.append(r)
        require(r['exit']==0,'old worker unexpected runtime failure: '+str(r))
        return r['stdout']

    def fence_process(self,claim):
        request={'op':'fence','mission':claim['mission'],'grant':claim['grant']}
        p=subprocess.Popen([sys.executable,'-m','p06_boundary.provider',str(self.path/'provider.sqlite'),str(self.path/'fixture.key')],
             stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.live.append(p)
        p.stdin.write(canonical(request));p.stdin.close();p.stdin=None
        return p

    def save(self):
        self.meta['processes']=self.processes
        write_json(self.path/'case_metadata.json',self.meta)
        observation=observe(self.path)
        write_json(self.path/'observation.json',observation)
        return observation

    def cleanup(self):
        for p in self.live:
            if p.poll() is None:
                p.kill()
                p.communicate(timeout=5)


def run_case(out,case_id,name,profile,mode):
    f=Fixture(out/f'{case_id}__{profile}__{mode}',mode,profile,name)
    r={'case_id':case_id,'case':name,'provider_profile':profile,'mode':mode,'status':'FAIL'}
    try:
        if case_id=='T01':
            a=f.claim();request=f.intent(a);p,resume=f.old_worker(request)
            f.release();b=f.claim('B')
            require(p.poll() is None,'old process must still be alive at B activation')
            f.meta['old_alive_after_new_owner_activation']=True
            resume.write_text('continue\n',encoding='utf-8')
            response=f.finish_old(p);r['old_response']=response
            exp=json.loads(decode64(request['grant'].split('.')[0]))['exp']
            require(response['submitted_at']<exp,'stale test confounded by expiry')
            if profile=='contract_violating_skip':require(response['ok'],'faulted provider did not accept old action')
            else:require(response.get('error')=='FENCED','old action was not fenced')
        elif case_id=='T02':
            first=f.run_worker(lose_ack=True)
            require(first['stdout'].get('error')=='ACK_LOST','commit then lost stdout not observed')
            f.release();second=f.run_worker('B')
            if profile=='opaque':require(second['stdout'].get('error')=='UNRESOLVED_OUTCOME','opaque outcome was retried or called complete')
            else:require(second['exit']==0,'cooperative recovery did not complete')
            r['receiver_knows_effect_without_offline_oracle']=profile=='atomic'
        elif case_id=='T03':
            a=f.claim(lease=2);request=f.intent(a);p,resume=f.old_worker(request)
            exp=json.loads(decode64(request['grant'].split('.')[0]))['exp']
            require(f.meta['old_worker_readiness']['ready_at']<exp,'lease expired before pause started')
            while time.time()<=exp+.03:time.sleep(.01)
            require(p.poll() is None,'paused old worker no longer alive')
            resume.write_text('continue\n',encoding='utf-8')
            response=f.finish_old(p);r['old_response']=response
            require(response.get('error')=='GRANT_EXPIRED','expired request accepted')
            r['expiry_during_real_pause']=True
        elif case_id=='T04':
            a=f.claim();request=f.intent(a);request['mission']='different-mission'
            p,resume=f.old_worker(request);resume.write_text('continue\n',encoding='utf-8')
            response=f.finish_old(p);r['old_response']=response
            require(response.get('error')=='SCOPE_MISMATCH','cross-mission request accepted')
        elif case_id=='T05':
            a=f.claim();request=f.intent(a)
            provider_ready=f.path/'provider-prechecked.json';provider_resume=f.path/'provider-resume'
            request['fixture_pause_after_validation']={'ready':str(provider_ready),'resume':str(provider_resume)}
            old,old_resume=f.old_worker(request);old_resume.write_text('continue\n',encoding='utf-8')
            f.meta['provider_precheck']=wait_file(provider_ready,old)
            f.release();b=f.reserve('B');bp=f.fence_process(b)
            if profile=='contract_violating_split':
                br=collect(bp);f.processes.append(br)
                require(br['exit']==0 and br['stdout'].get('ok'),'new fence did not finish while split provider paused')
                f.activate(b,br['stdout'])
                require(old.poll() is None,'old process not alive after B activation')
                f.meta['old_alive_after_new_owner_activation']=True
                provider_resume.write_text('continue\n',encoding='utf-8')
                response=f.finish_old(old)
            else:
                # The new fence cannot commit while old provider transaction
                # is open. Releasing A allows effect -> fence order.
                time.sleep(.05)
                f.meta['new_fence_finished_while_old_transaction_open']=bp.poll() is not None
                require(bp.poll() is None,'atomic provider allowed fence to bypass open transaction')
                provider_resume.write_text('continue\n',encoding='utf-8')
                response=f.finish_old(old)
                br=collect(bp);f.processes.append(br)
                require(br['exit']==0 and br['stdout'].get('ok'),'new fence failed after atomic commit')
                f.activate(b,br['stdout'])
            require(response['ok'],'old admitted operation failed unexpectedly')
            r['old_response']=response
        observation=f.save()
        require(not observation['missing_effect_events'] and not observation['false_done'],'observer integrity error')
        expected_bad=profile.startswith('contract_violating') and case_id in {'T01','T05'}
        require(observation['contract_violation_observed']==expected_bad,'observer failed expected contract classification')
        if expected_bad:
            require(observation['all_recorded_barriers_authenticated'],'counterexample lacks authenticated barrier')
            require(observation['effect_count']==1 and len(observation['stale_effects_after_fence'])==1,'missing unique stale effect')
            r['meaning']='EXPECTED_UNSAFE_COUNTEREXAMPLE_OBSERVED'
        else:r['meaning']='EXPECTED_BOUNDED_BEHAVIOR_OBSERVED'
        if case_id in {'T03','T04'} or (case_id=='T01' and not expected_bad):
            require(observation['effect_count']==0,'unexpected provider effect')
        if case_id=='T02':
            if profile=='opaque':require((observation['effect_count'],observation['done'],observation['unknown'],observation['pending'])==(1,0,1,1),'opaque knowledge state mismatch')
            else:require((observation['effect_count'],observation['done'],observation['business_duplicates'])==(2,2,0),'recovery duplicated/lost obligations')
        if case_id=='T05' and profile=='atomic':
            require(observation['effect_count']==1 and observation['business_duplicates']==0,
                    'atomic T05 requires one committed effect')
            effect=observation['observed_effects'][0]
            require((effect['mission'],effect['obligation'],effect['epoch'],effect['subject'])==
                    (a['mission'],'01-reserve',a['epoch'],a['subject']), 'atomic T05 wrong effect binding')
            effect_seq=[e['seq'] for e in observation['provider_causal_trace']
                        if e['event']=='EFFECT_COMMIT' and e['detail']['effect_id']==effect['id']]
            fence_seq=[e['seq'] for e in observation['provider_causal_trace']
                       if e['event']=='FENCE_COMMIT' and
                       (e['detail']['mission'],e['detail']['epoch'],e['detail']['subject'])==
                       (b['mission'],b['epoch'],b['subject'])]
            require(len(effect_seq)==len(fence_seq)==1 and effect_seq[0]<fence_seq[0],
                    'atomic T05 effect must precede the new fence')
        r['metrics']={k:observation[k] for k in ['effect_count','done','unknown','pending','business_duplicates','contract_violation_observed','all_recorded_barriers_authenticated']}
        r['status']='PASS'
    except Exception as exc:
        r['error']=str(exc);r['traceback']=traceback.format_exc()
        try:f.save()
        except Exception as save_exc:r['save_error']=str(save_exc)
    finally:
        f.cleanup()
        write_json(f.path/'result.json',r)
    return r


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    start=time.time();t0=time.perf_counter()
    metadata={'project_id':'P06','revision':'R2-provider-boundary','python':sys.version,'platform':platform.platform(),
      'sqlite':sqlite3.sqlite_version,'started_at':start,'argv':sys.argv,
      'protocol_sha256':hashlib.sha256((BASE/'PROTOCOL.json').read_bytes()).hexdigest(),
      'source_sha256':{str(x.relative_to(BASE)):hashlib.sha256(x.read_bytes()).hexdigest() for x in sorted(BASE.rglob('*.py')) if 'results' not in x.parts},
      'windows_executed':os.name=='nt','source_windows_portability':'EXECUTED_THIS_RUN' if os.name=='nt' else 'NOT_RUN'}
    write_json(out/'run_metadata.json',metadata)
    result=[]
    for case_id,name,profiles in MATRIX:
        for profile in profiles:
            for mode in ['classic','adapter']:
                row=run_case(out/'cases',case_id,name,profile,mode);result.append(row)
                print(row['status'],case_id,profile,mode,flush=True)
    summary={'metadata':metadata,'planned_case_runs':20,'case_runs':len(result),
      'passed':sum(r['status']=='PASS' for r in result),'failed':sum(r['status']!='PASS' for r in result),
      'unsafe_counterexamples_observed':sum(r.get('meaning')=='EXPECTED_UNSAFE_COUNTEREXAMPLE_OBSERVED' for r in result),
      'elapsed_seconds':time.perf_counter()-t0,'results':result,
      'inference':'Authenticity of a fence receipt does not prove atomic enforcement. Expected unsafe observations are positive detection results, not safe provider outcomes.',
      'runtime_integrations_measured':False,'human_effort_measured':False,'remote_business_effects':False}
    write_json(out/'summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in {'metadata','results'}},indent=2),flush=True)
    if summary['failed']:raise SystemExit(1)


if __name__=='__main__':main()
