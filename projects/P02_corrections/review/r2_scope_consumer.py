#!/usr/bin/env python3
"""Actual local synthetic consumer for the R2 omitted-provenance experiment.

The application owns a separate JSON state. It can publish a subset of its
provenance even while producing additional decisions. The optional instrumented
read log is retained by the test harness; it is NOT sent automatically to the
coordinator and is not independently attested in the real world.
No p02 imports, network, external action, LLM or human decision is involved.
"""
import argparse,datetime,hashlib,json,os
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

def canonical(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')
def digest(obj):return hashlib.sha256(canonical(obj)).hexdigest()
def signed(payload,consumer):
 seed=hashlib.sha256(('P02-INSECURE-TEST-KEY:'+consumer).encode('ascii')).digest()
 frame={'payload':payload,'signer':consumer}
 return dict(frame,signature=Ed25519PrivateKey.from_private_bytes(seed).sign(canonical(frame)).hex())

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--request',required=True);ap.add_argument('--state',required=True);ap.add_argument('--trace',required=True);ap.add_argument('--published-lineage',required=True);args=ap.parse_args()
 req=json.loads(Path(args.request).read_text());state_path=Path(args.state)
 state=json.loads(state_path.read_text()) if state_path.exists() else {'consumer':req['consumer'],'outputs':{},'executed_runs':0,'business_action_invocations':0}
 if state['consumer']!=req['consumer']:raise ValueError('Consumer identity cannot change')
 receipts=[];runs=[]
 for decision in req['selected_decisions']:
  recipe=req['recipes'][decision];refs={};values=[]
  for leaf in recipe['inputs']:
   source=req['values'][leaf]
   if type(source['value']) is not int or type(source['revision']) is not int:raise ValueError('Integer fixture values required')
   h=digest({'leaf':leaf,'revision':source['revision'],'value':source['value']})
   if source.get('digest',h)!=h:raise ValueError('Input bytes differ from supplied test digest')
   refs[leaf]={'revision':source['revision'],'digest':h};values.append(source['value'])
  if recipe['op']=='sum':score=sum(values)
  elif recipe['op']=='identity' and len(values)==1:score=values[0]
  else:raise ValueError('Only explicit test identity/sum recipes supported')
  outcome=score>=recipe['threshold']
  result={'score':score,'outcome':outcome,'input_frontier':refs,'run_id':req['run_id']}
  state['outputs'][decision]=result
  record={'consumer':req['consumer'],'decision_id':decision,'leaf_ids':sorted(refs),'frontier':refs,'actual_values_read':dict(zip(recipe['inputs'],values)),'score':score,'outcome':outcome,'recipe':recipe,'run_id':req['run_id'],'pid':os.getpid(),'observed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'evidence_kind':'LOCAL_APPLICATION_INSTRUMENTATION_NOT_EXTERNAL_ATTESTATION'}
  runs.append(record)
  if decision in req.get('receipt_context',{}):
   context=req['receipt_context'][decision]
   payload={'schema':'p02-review/0.1','event_id':context['event_id'],'decision_id':decision,'graph_digest':context['graph_digest'],'cutoff':context['cutoff'],'policy_digest':digest(context['policy']),'frontier':refs,'score':score,'outcome':outcome,'review':'REEXAMINED'}
   receipts.append(signed(payload,req['consumer']))
 state['executed_runs']+=1
 state_path.write_text(json.dumps(state,indent=2)+'\n')
 with Path(args.trace).open('a') as trace:
  for record in runs:trace.write(json.dumps(record,sort_keys=True)+'\n')
 # Deliberate boundary: only these relations reach the published lineage file.
 published=[{'consumer':req['consumer'],'decision_id':d,'leaf_ids':req['recipes'][d]['inputs']} for d in req['publish_lineage_ids']]
 Path(args.published_lineage).write_text(json.dumps(published,indent=2)+'\n')
 print(json.dumps({'pid':os.getpid(),'consumer':req['consumer'],'executed_decisions':req['selected_decisions'],'outputs':{d:state['outputs'][d] for d in req['selected_decisions']},'receipts':receipts,'business_action_invocations':state['business_action_invocations']}))
if __name__=='__main__':main()
