"""Read-only observer with no import of the implementation under test.

Its direct database access is a laboratory oracle unavailable to a normal
opaque-provider client. It is not an external provider truth service.
"""
import argparse
import base64
import collections
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3


def rows(path, query):
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    try:return [dict(row) for row in db.execute(query)]
    finally:db.close()


def unbase64(value):
    return base64.urlsafe_b64decode(value+'='*(-len(value)%4))


def check_receipt(entry,key):
    token=entry['token']
    body,sig=token.split('.')
    signature_valid=hmac.compare_digest(unbase64(sig),hmac.new(key,body.encode(),hashlib.sha256).digest())
    claims=json.loads(unbase64(body))
    binding_valid=(claims.get('kind')=='fence_receipt' and claims.get('aud')=='p06-provider'
                   and claims.get('provider')=='local-fixture'
                   and all(claims.get(k)==entry['expected'][k] for k in ['mission','epoch','subject','contract_hash']))
    valid_when_activated=claims['nbf']<=entry['activated_at']<claims['exp']
    return {'signature_valid':signature_valid,'binding_valid':binding_valid,
            'valid_when_activated':valid_when_activated,'claims':claims}


def observe(root):
    root=Path(root)
    meta=json.loads((root/'case_metadata.json').read_text(encoding='utf-8'))
    effects=rows(root/'provider.sqlite','SELECT * FROM effects ORDER BY id')
    pevents=rows(root/'provider.sqlite','SELECT * FROM events ORDER BY seq')
    cevents=rows(root/'coordinator.sqlite','SELECT * FROM events ORDER BY seq')
    missions=rows(root/'coordinator.sqlite','SELECT * FROM missions')
    obligations=rows(root/'coordinator.sqlite','SELECT * FROM obligations ORDER BY id')
    by_id={e['id']:e for e in effects}
    fences={};violations=[];logged_effects=set();compact=[]
    for event in pevents:
        d=json.loads(event['detail'])
        if event['event'] in {'FENCE_COMMIT','PRECHECK_OK','EFFECT_COMMIT','REJECT','LOOKUP','IDEMPOTENT_REPLAY'}:
            compact.append({'seq':event['seq'],'event':event['event'],'detail':d,'pid':event['pid'],'wall_ns':event['wall_ns']})
        if event['event']=='FENCE_COMMIT':
            fences[d['mission']]={'epoch':d['epoch'],'subject':d['subject'],'fence_event_seq':event['seq']}
        if event['event']=='EFFECT_COMMIT':
            effect=by_id.get(d['effect_id'])
            if effect is None:continue
            logged_effects.add(effect['id'])
            fence=fences.get(effect['mission'])
            if not fence or (effect['epoch'],effect['subject'])!=(fence['epoch'],fence['subject']):
                violations.append({'effect_id':effect['id'],'effect_epoch':effect['epoch'],
                    'effect_subject':effect['subject'],'effect_event_seq':event['seq'],
                    'mission':effect['mission'],'current_fence':fence})
    missing_events=sorted(set(by_id)-logged_effects)
    receipts=[check_receipt(entry,(root/'fixture.key').read_bytes()) for entry in meta.get('activated_barriers',[])]
    receipt_checks_ok=all(r['signature_valid'] and r['binding_valid'] and r['valid_when_activated'] for r in receipts)
    business=collections.Counter((e['mission'],e['obligation']) for e in effects)
    false_done=[]
    for ob in obligations:
        if ob['status']!='DONE':continue
        r=json.loads(ob['receipt'])['record']
        e=by_id.get(r['effect_id'])
        if not e or (e['mission'],e['obligation'],json.loads(e['payload']))!=(ob['mission'],ob['id'],json.loads(ob['payload'])):
            false_done.append(ob['id'])
    return {'observer':'stdlib-only SQL and independent HMAC verification; no runtime imports',
        'case':meta['case'],'mode':meta['mode'],'provider_profile':meta['provider_profile'],
        'receipt_checks':receipts,'recorded_barrier_receipt_count':len(receipts),
        'all_recorded_barriers_authenticated':receipt_checks_ok if receipts else None,
        'observed_effects':[{'id':e['id'],'mission':e['mission'],'obligation':e['obligation'],
                            'epoch':e['epoch'],'subject':e['subject'],'payload':json.loads(e['payload'])} for e in effects],
        'stale_effects_after_fence':violations,'contract_violation_observed':bool(violations),
        'effect_count':len(effects),'business_duplicates':sum(v-1 for v in business.values()),
        'done':sum(x['status']=='DONE' for x in obligations),'unknown':sum(x['status']=='UNKNOWN' for x in obligations),
        'pending':sum(x['status']=='PENDING' for x in obligations),'false_done':false_done,
        'missing_effect_events':missing_events,
        'mission_state':[{'mission':m['mission'],'owner':m['owner'],'epoch':m['epoch'],'phase':m['phase']} for m in missions],
        'obligation_state':[{'id':o['id'],'status':o['status']} for o in obligations],
        'provider_causal_trace':compact,
        'coordinator_causal_trace':[{'seq':e['seq'],'event':e['event'],'detail':json.loads(e['detail']),'pid':e['pid']} for e in cevents],
        'scope':'Local effects genuinely stored in separate provider DB; observer access is trusted laboratory instrumentation, not knowledge available to an opaque-provider client.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('case_dir',type=Path);parser.add_argument('--out',type=Path)
    args=parser.parse_args();result=observe(args.case_dir)
    output=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.out:
        with args.out.open('x',encoding='utf-8') as f:f.write(output)
    else:print(output,end='')
