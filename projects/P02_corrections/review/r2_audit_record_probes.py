#!/usr/bin/env python3
"""Targeted R2 record-integrity and evidence-state probes (no R1 corpus rerun).

--source results/scope_r2/pre_fix_sources reconstructs that preserved snapshot
in a temporary package; it is expected to reproduce historic failures.
"""
import argparse,copy,hashlib,json,sys,tempfile,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--source',default='src');ap.add_argument('--cases',default='all');args=ap.parse_args()
source=Path(args.source);source=source if source.is_absolute() else ROOT/source
historical_temp=None
if (source/'audit.py.txt').exists():
    historical_temp=tempfile.TemporaryDirectory(prefix='p02-r2-history-')
    package=Path(historical_temp.name)/'p02';package.mkdir();(package/'__init__.py').write_text('')
    for path in source.glob('*.py.txt'):(package/path.name[:-4]).write_bytes(path.read_bytes())
    source=package.parent
sys.path.insert(0,str(source))
from p02.engine import Engine
from p02.wire import sign,digest,canonical
from p02.audit import audit_store
OUT=Path(args.out).resolve()
if OUT.exists() and any(OUT.iterdir()):raise SystemExit('Use a new output directory')
OUT.mkdir(parents=True,exist_ok=True)

def fixture():return {'leaves':{'A':{'issuer':'publisher-a','revision':0,'value':10}},'nodes':{'a':{'op':'identity','inputs':['A']}},'decisions':{'D1':{'node':'a','owner':'consumer-a','threshold':15,'policy':'ge-v1'}},'graph_complete':True,'membership_closed':True,'cutoff':'r2-record-epoch'}
def setup(folder,mode):
 e=Engine(folder/'store.sqlite',fixture(),mode)
 e.ingest(e.correction('C1','publisher-a',[{'leaf':'A','revision':1,'value':20}]))
 return e,e.make_receipt('C1','D1')
def save(folder,name,obj):(folder/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def state(e):return {'obligation':[dict(r) for r in e.db.execute('SELECT * FROM obligations')],'receipt_log':[dict(r) for r in e.db.execute('SELECT * FROM receipt_log')]}
def report(folder,e):
 r=audit_store(e.path,'C1');save(folder,'audit.json',r);save(folder,'state.json',state(e));return r

def invalid_signature(folder,e,r):
 e.accept_receipt(r,replay=True)
 row=e.db.execute('SELECT id,envelope FROM receipt_log').fetchone();broken=json.loads(row['envelope'])
 broken['signature']=('0' if broken['signature'][0]!='0' else '1')+broken['signature'][1:]
 with e.db:e.db.execute('UPDATE receipt_log SET envelope=? WHERE id=?',(canonical(broken).decode(),row['id']))
 audit=report(folder,e)
 assert any(x['code']=='INVALID_RECEIPT_RECORD' for x in audit['findings'])
 assert audit['signature_evidence']['verified_assertions']==0
 assert audit['known_obligations_closed'] is False,audit
 return {'audit':audit,'mutation':'Stored signature changed; deliberately corrupt copied local store, not an engine-admitted message.'}

def promotion(folder,e,r):
 e.accept_receipt(r,replay=False);before=state(e);save(folder,'before_promotion.json',before)
 e.accept_receipt(r,replay=True);after=state(e);audit=report(folder,e)
 assert audit['signature_evidence']['verified_assertions']==1,audit
 assert audit['calculation_evidence']['local_replays_recorded']==1,audit
 assert not any(x['code']=='INVALID_RECEIPT_RECORD' for x in audit['findings']),audit
 return {'before':before,'after':after,'audit':audit,'mutations':'NONE; public legitimate accept_receipt API only.'}

def weaker_retry(folder,e,r):
 e.accept_receipt(r,replay=True);before=state(e);save(folder,'before_weaker_retry.json',before)
 e.accept_receipt(r,replay=False);audit=report(folder,e)
 assert audit['calculation_evidence']['local_replays_recorded']==1,audit
 assert audit['signature_evidence']['verified_assertions']==1,audit
 assert not any(x['code']=='INVALID_RECEIPT_RECORD' for x in audit['findings']),audit
 return {'before':before,'after':state(e),'audit':audit,'mutations':'NONE; same exact signed receipt retried through weaker verification mode.'}

def injected_scope(folder,e,r,field):
 e.accept_receipt(r,replay=True);p=copy.deepcopy(r['payload'])
 if field=='cutoff':p['cutoff']='wrong-epoch'
 else:p['frontier']['A']={'revision':0,'digest':digest({'leaf':'A','revision':0,'value':10})}
 forged=sign(p,'consumer-a');rid=digest(forged)
 with e.db:
  e.db.execute('INSERT INTO receipt_log VALUES(?,?,?,?,?)',(rid,'C1','D1',canonical(forged).decode(),'LOCAL_REPLAY'))
  e.db.execute('UPDATE obligations SET receipt=? WHERE event=? AND decision=?',(rid,'C1','D1'))
 audit=report(folder,e)
 assert audit['signature_evidence']['verified_assertions']==0,audit
 assert audit['known_obligations_closed'] is False,audit
 return {'audit':audit,'mutation':'Consistently signed/rehashed stored receipt has wrong '+field+'; injected store mutation, not accepted by the engine.'}
def wrong_cutoff(folder,e,r):return injected_scope(folder,e,r,'cutoff')
def stale_frontier(folder,e,r):return injected_scope(folder,e,r,'frontier')

def unbound_semantics(folder,e,r):
 e.accept_receipt(r,replay=True)
 descriptor={'unit':'K','window_start':'2015-01-01T00:00:00Z','window_end':'2015-01-04T00:00:00Z','dataset_namespace':'urn:publisher','dataset_name':'temperature/A'}
 obs={'semantic_checks':[{'decision_id':'DOES_NOT_EXIST','input_id':'ALSO_ABSENT','expected':descriptor,'observed':descriptor}]}
 audit=audit_store(e.path,'C1',obs);save(folder,'audit.json',audit)
 assert audit['semantic_contract_status']!='CONSISTENT_DECLARATIONS_ONLY',audit
 return {'audit':audit,'reason':'The pair of declarations is not bound to a registered decision/input.'}

cases=[invalid_signature,promotion,weaker_retry,wrong_cutoff,stale_frontier,unbound_semantics]
if args.cases!='all':cases=[c for c in cases if c.__name__ in set(args.cases.split(','))]
results=[]
for mode in ['classic_sql','portable_graph']:
 for case in cases:
  folder=OUT/(case.__name__+'_'+mode);folder.mkdir();engine=None
  entry={'case_id':case.__name__,'mode':mode}
  try:
   engine,receipt=setup(folder,mode);save(folder,'valid_original_receipt.json',receipt)
   entry['evidence']=case(folder,engine,receipt);entry['status']='PASS'
  except Exception as exc:entry.update(status='FAIL',error=str(exc),traceback=traceback.format_exc())
  finally:
   if engine:engine.close()
  results.append(entry);print(case.__name__,mode,entry['status'],flush=True)
result={'project_id':'P02','cycle':'R2','scope':'Targeted local records/evidence state; no R1 graph corpus rerun','source_sha256':{n:hashlib.sha256((source/'p02'/n).read_bytes()).hexdigest() for n in ['engine.py','wire.py','audit.py']},'case_records':len(results),'passed':sum(x['status']=='PASS' for x in results),'failed':sum(x['status']=='FAIL' for x in results),'results':results}
save(OUT,'results.json',result);print(json.dumps({k:result[k] for k in ['case_records','passed','failed']}))
if historical_temp:historical_temp.cleanup()
raise SystemExit(bool(result['failed']))
