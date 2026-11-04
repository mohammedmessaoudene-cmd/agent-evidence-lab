"""Adversarial checks of the proposed contract reader, not of upstream P04."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--allow-weak-reader',action='store_true');a=p.parse_args()
    if a.out.exists():raise SystemExit('refusing to overwrite probe report')
    spec=importlib.util.spec_from_file_location('judge_under_test',ROOT/'run_adapter_contract.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    expected=next(x for x in json.loads((ROOT/'fixtures/expected.json').read_text()) if x['id']=='F04')
    original=next(x['output'] for x in json.loads((ROOT/'results/adapter1/report.json').read_text())['rows'] if x['case']=='F04')
    checks=[]
    edits=[('boolean_money',lambda x:x['observed'].__setitem__('known_spend_microusd',True)),
           ('float_money',lambda x:x['observed'].__setitem__('available_microusd',2.0)),
           ('integer_instead_of_boolean',lambda x:x['observed'].__setitem__('frozen',0)),
           ('duplicate_claim_boundary',lambda x:x['must_not_claim'].append(x['must_not_claim'][0])),
           ('missing_source_identity',lambda x:x.pop('source_sha256')),
           ('unsupported_effect_claim',lambda x:x.__setitem__('external_effect','committed')),
           ('dropped_claim_boundary',lambda x:x['must_not_claim'].pop()),
           ('integer_probe_flag',lambda x:x['probes'][1]['return'].__setitem__('newly_reserved',1))]
    for name,edit in edits:
        record=copy.deepcopy(original);edit(record)
        try:failures=m.judge(expected,record)
        except Exception as exc:failures=['reader_crashed:'+type(exc).__name__]
        checks.append({'case':name,'rejected':bool(failures),'reader_failures':failures,'crashed':any(t.startswith('reader_crashed') for t in failures)})
    control=m.judge(expected,original)
    result={'scope':'8 malformed adapter-output probes, same-team; not extra P04 scenarios',
            'positive_control_accepted':not control,'rejected':sum(x['rejected'] and not x['crashed'] for x in checks),'total':len(checks),'checks':checks}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if not a.allow_weak_reader and (control or result['rejected']!=len(checks)):raise SystemExit(1)

if __name__=='__main__':main()
