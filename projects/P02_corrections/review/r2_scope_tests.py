#!/usr/bin/env python3
"""Preregistered R2 same-consumer and semantic-boundary experiments.

No R1 random graph corpus is repeated. Actual local application subprocesses
produce the omitted decisions. Expected counterexamples count as PASS when the
limitation is correctly exposed; PASS does not mean full coverage was achieved.
"""
import argparse,copy,datetime,hashlib,json,os,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from p02.engine import Engine
from p02.wire import canonical,digest,sign,verify,Rejected
from p02.audit import audit_store

def dump(path,obj):Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def fixture(value=10,threshold=15):
 return {'leaves':{'A':{'issuer':'publisher-a','revision':0,'value':value,'unit':'synthetic'}},'nodes':{'a':{'op':'identity','inputs':['A']}},'decisions':{'D_known':{'node':'a','owner':'consumer-a','threshold':threshold,'policy':'ge-v1'}},'graph_complete':True,'membership_closed':True,'cutoff':'r2-same-enrolled-consumer','data_kind':'SYNTHETIC'}
def change(e,value=20,event='C1',revision=1):
 env=e.correction(event,'publisher-a',[{'leaf':'A','revision':revision,'value':value}]);verify(env,e.registry);e.ingest(env);return env

def audit_unchanged(e,observations=None):
 before=hashlib.sha256('\n'.join(e.db.iterdump()).encode()).hexdigest()
 report=audit_store(e.path,'C1',observations)
 after=hashlib.sha256('\n'.join(e.db.iterdump()).encode()).hexdigest()
 assert before==after,'Audit mutated logical store'
 assert report['actual_decision_coverage']=='UNKNOWN'
 assert report['global_consumer_coverage']=='UNKNOWN'
 assert report['external_action_performed']=='UNKNOWN'
 assert report['semantic_truth']=='UNKNOWN'
 assert report['observed_log_completeness']=='UNKNOWN'
 return report

def child(folder,name,request,state_name='application_state.json',trace_name='actual_read_trace.jsonl'):
 req=folder/(name+'_request.json');dump(req,request)
 cmd=[sys.executable,'-S',str(ROOT/'review/r2_scope_consumer.py'),'--request',str(req),'--state',str(folder/state_name),'--trace',str(folder/trace_name),'--published-lineage',str(folder/'published_lineage.json')]
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
 dump(folder/(name+'_process.json'),{'command':cmd,'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
 assert p.returncode==0,p.stderr
 return json.loads(p.stdout)

def request(e,recipes,selected,run_id,receipts=None):
 return {'consumer':'consumer-a','recipes':recipes,'selected_decisions':selected,'values':e.state(),'run_id':run_id,'publish_lineage_ids':['D_known'],'receipt_context':receipts or {}}
def receipt_context(e):return {'D_known':{'event_id':'C1','graph_digest':e.graph_digest,'cutoff':e.fixture['cutoff'],'policy':e.fixture['decisions']['D_known']}}
def observed_from_trace(path):
 latest={}
 for line in path.read_text().splitlines():
  row=json.loads(line);latest[row['decision_id']]={k:row[k] for k in ['consumer','decision_id','leaf_ids']}
 return list(latest.values())

def same_consumer_undeclared_decision(folder,mode):
 f=fixture();e=Engine(folder/'store.sqlite',f,mode)
 recipes={d:{'op':'identity','inputs':['A'],'threshold':15} for d in ['D_known','D_hidden']}
 try:
  initial=child(folder,'initial',request(e,recipes,list(recipes),'initial'))
  dump(folder/'application_before_correction.json',json.loads((folder/'application_state.json').read_text()))
  correction=change(e);dump(folder/'correction.json',correction)
  updated=child(folder,'notified_known_only',request(e,recipes,['D_known'],'after_C1_known_only',receipt_context(e)))
  assert len(updated['receipts'])==1
  assert e.accept_receipt(updated['receipts'][0],replay=True)=='LOCAL_REPLAY'
  actual=json.loads((folder/'application_state.json').read_text());dump(folder/'application_after_known_review.json',actual)
  assert actual['outputs']['D_hidden']['outcome'] is False
  # Replay the actual hidden recipe in a different local state, with no claim
  # that the original consumer was notified or that this was a business action.
  correct=child(folder,'reference_hidden_replay',request(e,recipes,['D_hidden'],'reference_only'),state_name='reference_replay_state.json',trace_name='reference_replay_trace.jsonl')
  assert correct['outputs']['D_hidden']['outcome'] is True
  assert actual['consumer']==initial['consumer']==updated['consumer']=='consumer-a'
  assert 'consumer-a' in e.registry and set(e.fixture['decisions'])=={'D_known'}
  published=json.loads((folder/'published_lineage.json').read_text());assert {x['decision_id'] for x in published}=={'D_known'}
  plain=audit_unchanged(e);dump(folder/'audit_without_observed_reads.json',plain)
  observations={'observed_reads':observed_from_trace(folder/'actual_read_trace.jsonl')};dump(folder/'observations.json',observations)
  observed=audit_unchanged(e,observations);dump(folder/'audit_with_observed_reads.json',observed)
  assert plain['known_obligations_closed'] and plain['known_obligations']['total']==1
  assert not plain['findings']
  gaps=[x for x in observed['findings'] if x['code']=='UNREGISTERED_DECISION_BY_REGISTERED_CONSUMER']
  assert len(gaps)==1 and gaps[0]['decision_id']=='D_hidden'
  assert not any(x['code']=='UNREGISTERED_CONSUMER_OBSERVED' for x in observed['findings'])
  env=dict(os.environ,PYTHONPATH=os.pathsep.join([str(ROOT/'src'),os.environ.get('PYTHONPATH','')]))
  cli=subprocess.run([sys.executable,'-S','-m','p02.audit','--store',e.path,'--event','C1','--observations',str(folder/'observations.json'),'--out',str(folder/'audit_cli.json')],env=env,capture_output=True,text=True,timeout=20)
  assert cli.returncode==2,cli.stderr
  dump(folder/'audit_cli_process.json',{'exit_code':cli.returncode,'stdout':cli.stdout,'stderr':cli.stderr})
  return {'consumer':'consumer-a','consumer_was_already_registered':True,'declared_membership_closed':True,'known_obligations_closed':True,'known_closed_fraction':1.0,'same_consumer_omitted_decision':'D_hidden','actual_stale_outcome':False,'reference_replayed_outcome':True,'process_ids':[initial['pid'],updated['pid'],correct['pid']],'all_processes_executed':True,'lineage_published_for':['D_known'],'observed_gap':gaps[0],'without_observation_gap_discovery':'NOT_POSSIBLE_FROM_SUPPLIED_MESSAGES','actual_decision_coverage':observed['actual_decision_coverage'],'external_action_performed':observed['external_action_performed'],'audit_cli_exit_with_finding':2,'audit_mutated_logical_store':False}
 finally:e.close()

def same_consumer_omitted_edge(folder,mode):
 f=fixture(value=0);f['leaves']['B']={'issuer':'publisher-a','revision':0,'value':20,'unit':'synthetic'}
 f['nodes']['b']={'op':'identity','inputs':['B']};f['decisions']['D_omitted']={'node':'b','owner':'consumer-a','threshold':25,'policy':'ge-v1'}
 e=Engine(folder/'store.sqlite',f,mode)
 recipes={'D_known':{'op':'identity','inputs':['A'],'threshold':15},'D_omitted':{'op':'sum','inputs':['A','B'],'threshold':25}}
 try:
  initial=child(folder,'initial',request(e,recipes,list(recipes),'initial'))
  assert initial['outputs']['D_omitted']['score']==e.outputs()['D_omitted']['score']==20
  change(e);updated=child(folder,'notified_known_only',request(e,recipes,['D_known'],'after_C1_known_only',receipt_context(e)))
  e.accept_receipt(updated['receipts'][0],replay=True)
  reference=child(folder,'reference_omitted_replay',request(e,recipes,['D_omitted'],'reference_only'),state_name='reference_replay_state.json',trace_name='reference_replay_trace.jsonl')
  actual=json.loads((folder/'application_state.json').read_text())
  assert actual['outputs']['D_omitted']['outcome'] is False and reference['outputs']['D_omitted']['outcome'] is True
  obs={'observed_reads':observed_from_trace(folder/'actual_read_trace.jsonl')};dump(folder/'observations.json',obs)
  report=audit_unchanged(e,obs);dump(folder/'audit.json',report)
  gaps=[x for x in report['findings'] if x['code']=='UNDECLARED_READS_OBSERVED']
  assert len(gaps)==1 and gaps[0]['observed_undeclared_leaf_ids']==['A']
  assert report['known_obligations_closed'] and report['known_obligations']['total']==1
  return {'consumer':'consumer-a','both_decisions_registered_to_same_owner':True,'initial_actual_and_declared_score':20,'corrected_actual_score':40,'stale_declared_score':20,'missed_rule_outcome':True,'gap':gaps[0],'known_closed_fraction':1.0,'actual_decision_coverage':'UNKNOWN','audit_mutated_logical_store':False}
 finally:e.close()

def authenticated_liar(folder,mode):
 e=Engine(folder/'store.sqlite',fixture(),mode)
 recipes={'D_known':{'op':'identity','inputs':['A'],'threshold':15}}
 try:
  initial=child(folder,'initial',request(e,recipes,['D_known'],'initial'))
  change(e);payload=copy.deepcopy(e.make_receipt('C1','D_known')['payload']);payload['score']=999;payload['outcome']=True
  lie=sign(payload,'consumer-a');verify(lie,e.registry);dump(folder/'authenticated_false_receipt.json',lie)
  assert e.accept_receipt(lie,replay=False)=='ATTESTATION_ONLY'
  try:e.accept_receipt(lie,replay=True)
  except Rejected as exc:replay_rejected=str(exc)
  else:raise AssertionError('False score accepted by local replay')
  report=audit_unchanged(e);dump(folder/'audit.json',report)
  app=json.loads((folder/'application_state.json').read_text())
  assert app['executed_runs']==1 and app['outputs']['D_known']['score']==10
  assert report['signature_evidence']['verified_assertions']==1 and report['calculation_evidence']['local_replays_recorded']==0
  assert report['known_obligations_closed'] and report['external_action_performed']=='UNKNOWN'
  return {'authentic_test_signature':True,'accepted_as':'ATTESTATION_ONLY','local_replay_rejection':replay_rejected,'application_runs':app['executed_runs'],'application_score_not_recomputed':app['outputs']['D_known']['score'],'claimed_score':999,'fixture_business_action_invocations':app['business_action_invocations'],'auditor_external_action':'UNKNOWN','auditor_remote_execution':report['calculation_evidence']['remote_execution_performed'],'known_obligations_closed':True,'audit_mutated_logical_store':False}
 finally:e.close()

def descriptors():return {'unit':'K','window_start':'2015-01-01T00:00:00Z','window_end':'2015-01-04T00:00:00Z','dataset_namespace':'urn:publisher','dataset_name':'temperature/location-A'}
def semantic_case(folder,mode,kind):
 expected=descriptors();observed=copy.deepcopy(expected)
 if kind=='unit':observed['unit']='degC';initial=1999;value=2000;threshold=27315;true_score=29315
 elif kind=='window':observed.update(window_start='2015-02-01T00:00:00Z',window_end='2015-02-04T00:00:00Z');initial=9;value=10;threshold=15;true_score=20
 elif kind=='identity':observed['dataset_name']='temperature/location-B';initial=9;value=10;threshold=15;true_score=20
 elif kind=='coherent_lie':initial=1999;value=2000;threshold=27315;true_score=29315
 else:raise ValueError(kind)
 f=fixture(initial,threshold);f['leaves']['A'].update(observed)
 e=Engine(folder/'store.sqlite',f,mode)
 try:
  env=change(e,value);e.drain();receipt=json.loads(e.db.execute('SELECT envelope FROM receipt_log').fetchone()[0]);verify(env,e.registry);verify(receipt,e.registry)
  assert e.outputs()['D_known']['outcome'] is False and true_score>=threshold
  obs={'semantic_checks':[{'decision_id':'D_known','input_id':'A','expected':expected,'observed':observed}]};dump(folder/'observations.json',obs)
  report=audit_unchanged(e,obs);dump(folder/'audit.json',report);dump(folder/'valid_correction_and_receipt.json',{'correction':env,'receipt':receipt})
  if kind=='coherent_lie':
   assert report['semantic_contract_status']=='CONSISTENT_DECLARATIONS_ONLY' and not report['findings']
  else:assert report['semantic_contract_status']=='INCONSISTENT_DECLARATIONS' and any(x['code']=='SEMANTIC_CONTRACT_MISMATCH' for x in report['findings'])
  if kind=='unit':assert 2000+27315==true_score
  return {'kind':kind,'all_test_signatures_and_hashes_consistent':True,'raw_pipeline_output':e.outputs()['D_known'],'known_obligations_closed':report['known_obligations_closed'],'semantic_contract_status':report['semantic_contract_status'],'semantic_truth':'UNKNOWN','synthetic_expected_score_under_intended_meaning':true_score,'synthetic_expected_rule_outcome':True,'declared_comparison':report['semantic_comparisons'],'expected':expected,'observed':observed,'data_mutation':'Labeled synthetic values only; NASA data untouched','unit_value_encoding':'Centidegrees in unit example; exact 27315 centikelvin offset' if kind in ('unit','coherent_lie') else 'Synthetic arbitrary integer scores','negative_limit':'A coherent false unit declaration remains undetectable without an independent semantic reference' if kind=='coherent_lie' else 'Hash and signature consistency does not establish intended units/window/identity','audit_mutated_logical_store':False}
 finally:e.close()
def unit_contract_mismatch(folder,mode):return semantic_case(folder,mode,'unit')
def time_window_contract_mismatch(folder,mode):return semantic_case(folder,mode,'window')
def identity_contract_mismatch(folder,mode):return semantic_case(folder,mode,'identity')
def coherent_false_metadata(folder,mode):return semantic_case(folder,mode,'coherent_lie')

def missing_semantic_contracts(folder,mode):
 e=Engine(folder/'store.sqlite',fixture(),mode)
 try:
  change(e);e.drain();base=descriptors();missing=copy.deepcopy(base);del missing['unit']
  inputs=[{}, {'semantic_checks':[{'decision_id':'D_known','input_id':'A','expected':{},'observed':{}}]}, {'semantic_checks':[{'decision_id':'D_known','input_id':'A','expected':base,'observed':missing}]}]
  reports=[audit_unchanged(e,x) for x in inputs]
  assert all(x['semantic_contract_status']=='UNKNOWN' for x in reports)
  dump(folder/'audits.json',reports)
  return {'cases':['no semantic contract','empty pair','missing observed unit'],'semantic_statuses':[x['semantic_contract_status'] for x in reports],'actual_decision_coverage':['UNKNOWN']*3,'audit_mutated_logical_store':False}
 finally:e.close()

def stale_receipt_state(folder,mode):
 e=Engine(folder/'store.sqlite',fixture(),mode)
 try:
  change(e,20,'C1',1);old=e.make_receipt('C1','D_known');e.accept_receipt(old,replay=True)
  before=audit_unchanged(e);change(e,30,'C2',2)
  try:e.accept_receipt(old,replay=True)
  except Rejected as exc:reason=str(exc)
  else:raise AssertionError('Stale receipt accepted')
  reopened=audit_unchanged(e);assert not reopened['known_obligations_closed']
  e.drain();after=audit_unchanged(e);assert after['known_obligations_closed']
  dump(folder/'audit_transitions.json',{'before':before,'reopened':reopened,'after':after})
  return {'before_closure':before['known_obligations']['closure'],'after_new_correction_closure':reopened['known_obligations']['closure'],'stale_receipt_rejected':reason,'after_replay_closure':after['known_obligations']['closure'],'actual_decision_coverage':'UNKNOWN','audit_mutated_logical_store':False}
 finally:e.close()

CASES=[same_consumer_undeclared_decision,same_consumer_omitted_edge,authenticated_liar,unit_contract_mismatch,time_window_contract_mismatch,identity_contract_mismatch,coherent_false_metadata,missing_semantic_contracts,stale_receipt_state]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args();out=Path(args.out).resolve()
 if out.exists() and any(out.iterdir()):raise SystemExit('Use a new output directory; preserve previous evidence')
 out.mkdir(parents=True,exist_ok=True)
 freeze=json.loads((ROOT/'protocol/r2_scope_freeze.json').read_text());assert hashlib.sha256((ROOT/freeze['protocol']).read_bytes()).hexdigest()==freeze['sha256']
 sources={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['src/p02/engine.py','src/p02/wire.py','src/p02/audit.py','review/r2_scope_consumer.py','review/r2_scope_tests.py']}
 results=[]
 for mode in ['classic_sql','portable_graph']:
  for case in CASES:
   folder=out/(case.__name__+'_'+mode);folder.mkdir();entry={'case_id':case.__name__,'mode':mode};start=time.perf_counter()
   try:entry.update(status='PASS',evidence=case(folder,mode))
   except Exception as exc:entry.update(status='FAIL',error=str(exc),traceback=traceback.format_exc())
   entry['elapsed_s']=time.perf_counter()-start;results.append(entry);print(case.__name__,mode,entry['status'],flush=True)
 result={'project_id':'P02','cycle':'R2','scope':'Actual local application processes and readonly audit; synthetic values, no external organization/action','protocol':freeze,'source_sha256':sources,'case_records':len(results),'passed':sum(x['status']=='PASS' for x in results),'failed':sum(x['status']=='FAIL' for x in results),'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'unchanged_R1_corpus_repeated':False,'results':results}
 dump(out/'results.json',result);print(json.dumps({k:result[k] for k in ['case_records','passed','failed']}));return bool(result['failed'])
if __name__=='__main__':raise SystemExit(main())
