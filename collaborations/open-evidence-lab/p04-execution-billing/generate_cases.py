"""Generate frozen, synthetic dual-finality scenarios; never imports the SUT."""
import argparse
import hashlib
import json
from pathlib import Path


def step(cmd, **kw):
    return dict(cmd=cmd, **kw)


def expected(outcome='UNKNOWN', billing='UNKNOWN', known=0, held=2, available=1,
             unbounded=False, frozen=False, **kw):
    return dict(execution_outcome=outcome, billing_finality=billing,
                known_spend_microusd=known, held_microusd=held,
                available_microusd=available, unbounded=unbounded, frozen=frozen, **kw)


def cases():
    dispatch = step('dispatch', expect_return={'dispatch_allowed': True})
    lost = step('unknown', bounded=True)
    invoice = step('invoice', amount=1, event='invoice-1')
    no_retry = step('dispatch', event='second-dispatch', expect_return={'dispatch_allowed': False})
    return [
      dict(id='F01', invariant='Success is not final billing', steps=[dispatch,step('outcome',value='SUCCEEDED')], expected=expected(outcome='SUCCEEDED'), probes=[step('reserve',attempt='B',amount=2,raises='AdmissionDenied')]),
      dict(id='F02', invariant='Failure is not zero cost', steps=[dispatch,step('outcome',value='FAILED')], expected=expected(outcome='FAILED')),
      dict(id='F03', invariant='Bounded lost response retains liability', steps=[dispatch,lost], expected=expected(), probes=[no_retry]),
      dict(id='F04', invariant='Final invoice does not establish execution', steps=[dispatch,lost,invoice], expected=expected(billing='FINAL',known=1,held=0,available=2), probes=[no_retry,step('reserve',attempt='B',amount=2,expect_return={'newly_reserved':True})]),
      dict(id='F05', invariant='Real invoice releases only the remainder', steps=[dispatch,step('outcome',value='SUCCEEDED'),invoice], expected=expected(outcome='SUCCEEDED',billing='FINAL',known=1,held=0,available=2)),
      dict(id='F06', invariant='Cumulative cost is not final cost', steps=[dispatch,step('cost',amount=1)], expected=expected(known=1,held=1)),
      dict(id='F07', invariant='Unbounded liability blocks new admissions', budget=9, steps=[dispatch,step('unknown',bounded=False)], expected=expected(available=0,unbounded=True),probes=[step('reserve',attempt='B',amount=1,raises='AdmissionDenied')]),
      dict(id='F08', invariant='Zero invoice does not prove no execution', steps=[dispatch,lost,step('invoice',amount=0)], expected=expected(billing='FINAL',held=0,available=3),probes=[no_retry]),
      dict(id='F09', invariant='Pre-dispatch fenced evidence can release', steps=[step('non_dispatch')], expected=expected(outcome='NOT_DISPATCHED',billing='FINAL',held=0,available=3),probes=[no_retry]),
      dict(id='F10', invariant='Executor cannot assert final invoice role', steps=[dispatch,step('invoice',amount=1,source='executor',raises='EvidenceValidationError')], expected=expected()),
      dict(id='F11', invariant='Invoice must bind same attempt', steps=[dispatch,step('invoice',amount=1,evidence_attempt='other',raises='EvidenceValidationError')], expected=expected()),
      dict(id='F12', invariant='Contradictory invoice freezes rather than releases', steps=[dispatch,step('cost',amount=1),step('invoice',amount=0,raises='EvidenceConflict')], expected=expected(billing='CONFLICT',known=1,held=1,available=0,unbounded=True,frozen=True)),
      dict(id='F13', invariant='One account shares outstanding exposure', steps=[step('reserve',attempt='B',amount=2,raises='AdmissionDenied')], expected=expected()),
      dict(id='F14', invariant='Positive control permits another affordable operation', budget=4, steps=[dispatch], expected=expected(available=2),probes=[step('reserve',attempt='B',amount=2,expect_return={'newly_reserved':True})]),
      dict(id='F15', invariant='Same invoice event is idempotent', steps=[dispatch,invoice,step('invoice',amount=1,event='invoice-1',expect_return={'new_event':False,'newly_finalized':False})], expected=expected(billing='FINAL',known=1,held=0,available=2)),
      dict(id='F16', invariant='Late lost response cannot reopen settled billing', steps=[dispatch,invoice,step('unknown',bounded=False)], expected=expected(billing='FINAL',known=1,held=0,available=2)),
      dict(id='F17', invariant='Unconfirmed cancellation is not release', steps=[dispatch,step('unknown',bounded=True,reason='unconfirmed_cancellation')], expected=expected()),
      dict(id='F18', invariant='Authorization cap alone does not authorize dispatch', steps=[step('dispatch',ceiling=False,raises='AdmissionDenied')], expected=expected()),
    ]


def payload():
    return {'contract':'execution-billing-finality/v0.1-proposal',
            'origin':'new same-team targeted cases; not upstream Probity corpus',
            'scope':'trusted semantic evidence; no remote invoice, external effect or signature verification',
            'cases':cases()}


def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
    dst=Path(__file__).with_name('cases.json')
    raw=(json.dumps(payload(),ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode()
    generated={dst:raw}
    expectations=[]
    for c in cases():
        def inputs(steps): return [{k:v for k,v in s.items() if k not in {'raises','expect_return'}} for s in steps]
        def oracle(steps): return [{'exception':s.get('raises'),'return':s.get('expect_return',{})} for s in steps]
        inp={'id':c['id'],'budget':c.get('budget',3),'steps':inputs(c['steps']),'probes':inputs(c.get('probes',[]))}
        expectations.append({'id':c['id'],'observed':c['expected'],'steps':oracle(c['steps']),'probes':oracle(c.get('probes',[]))})
        generated[dst.parent/'fixtures/inputs'/f"{c['id']}.json"]=(json.dumps(inp,indent=2,sort_keys=True)+'\n').encode()
    generated[dst.parent/'fixtures/expected.json']=(json.dumps(expectations,indent=2,sort_keys=True)+'\n').encode()
    for path,data in generated.items():
        if a.check:
            if not path.exists() or path.read_bytes()!=data: raise SystemExit('generated files differ: '+str(path))
        else:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    print(json.dumps({'cases':len(cases()),'sha256':hashlib.sha256(raw).hexdigest()}))

if __name__=='__main__': main()
