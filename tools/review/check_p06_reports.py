"""Four distinct synthetic-report mutations plus one contract control.

No parser/provider experiment is executed. The 20/14 fields below are declared
fixture data used only to challenge report validation, not physical run counts.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys

sys.dont_write_bytecode = True

PARSER_CASES = {
    'actual_p06_dossier': True, 'memory_name_incompatible': False,
    'memory_type_incompatible': False, 'memory_version_incompatible': False,
    'other_mission_id': False, 'unknown_pending_obligation': False,
    'duplicate_obligation_id': False, 'forged_permission_is_only_data': True,
    'duplicate_mission_member': False, 'overflow_exponent': False,
    'unsafe_integer': False, 'named_nan': False, 'unpaired_surrogate': False,
    'valid_unicode': True}
PROVIDER_CASES = [
    ('T01','atomic'), ('T01','opaque'), ('T01','contract_violating_skip'),
    ('T02','atomic'), ('T02','opaque'), ('T03','atomic'),
    ('T04','atomic'), ('T04','contract_violating_skip'),
    ('T05','atomic'), ('T05','contract_violating_split')]


def fixture():
    provider_rows = []
    for case, profile in PROVIDER_CASES:
        unsafe = (case,profile) in {('T01','contract_violating_skip'),('T05','contract_violating_split')}
        for mode in ('classic','adapter'):
            provider_rows.append({'case_id':case,'provider_profile':profile,'mode':mode,'status':'PASS',
                                  'meaning':'EXPECTED_UNSAFE_COUNTEREXAMPLE_OBSERVED' if unsafe else 'EXPECTED_BOUNDED_BEHAVIOR_OBSERVED',
                                  'metrics':{'contract_violation_observed':unsafe}})
    provider = {'planned_case_runs':20,'case_runs':20,'passed':20,'failed':0,
                'unsafe_counterexamples_observed':4,'results':provider_rows}
    parser_rows = []; protocol_cases = []; files = {}
    for name, expected in PARSER_CASES.items():
        wire = json.dumps({'SYNTHETIC_REPORT_ONLY':name},sort_keys=True,separators=(',',':')).encode()
        digest = hashlib.sha256(wire).hexdigest(); files[name] = wire
        parser_rows.append({'name':name,'expected':expected,'joint_admitted':expected,
                            'pass':True,'identical_bytes':True,
                            'python_raw':{'accepted':True,'bounded_canonical_sha256':digest},
                            'node_raw':{'accepted':True,'bounded_canonical_sha256':digest,
                                        'received_sha256':digest,'received_bytes':len(wire)},
                            'byte_evidence':{'python_input_sha256':digest,'saved_file_sha256':digest,'node_stdin_sha256':digest,
                                             'python_input_bytes':len(wire),'saved_file_bytes':len(wire),'node_stdin_bytes':len(wire)}})
        protocol_cases.append({'name':name,'expected_admitted':expected,'sha256':digest})
    parsers = {'cases':14,'expected_results':14,'rows':parser_rows}
    protocol = {'experiment':'SYNTHETIC_REPORT_CONTRACT_CONTROL_NOT_EXECUTION',
                'dossier_sha256':hashlib.sha256(files['actual_p06_dossier']).hexdigest(),'cases':protocol_cases}
    return provider, parsers, protocol, files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verifier',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args = ap.parse_args(); args.out.mkdir(parents=True,exist_ok=False)
    src = args.verifier.resolve()
    spec = importlib.util.spec_from_file_location('reviewer2_report_contract_matrix',src)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    rows = []
    variants = ['valid_synthetic_contract_control','provider_failed_row','provider_duplicate_identity',
                'parser_duplicate_case','parser_semantic_contradiction']
    for name in variants:
        provider, parsers, protocol, files = fixture()
        if name=='provider_failed_row': provider['results'][0]['status']='FAIL'
        elif name=='provider_duplicate_identity': provider['results'][1]=copy.deepcopy(provider['results'][0])
        elif name=='parser_duplicate_case': parsers['rows'][1]=copy.deepcopy(parsers['rows'][0])
        elif name=='parser_semantic_contradiction': parsers['rows'][1]['joint_admitted']=True
        root=args.out/name; pd=root/'P06_provider'; jd=root/'P06_parsers'
        pd.mkdir(parents=True);jd.mkdir()
        (pd/'summary.json').write_text(json.dumps(provider),encoding='utf8')
        (jd/'result.json').write_text(json.dumps(parsers),encoding='utf8')
        protocol_bytes=json.dumps(protocol).encode();(jd/'protocol.json').write_bytes(protocol_bytes)
        (jd/'protocol.sha256').write_text(hashlib.sha256(protocol_bytes).hexdigest()+'\n')
        for case,wire in files.items(): (jd/(case+'.json.txt')).write_bytes(wire)
        try:
            module.verify('P06',root)
            outcome={'accepted':True}
        except Exception as exc:
            outcome={'accepted':False,'error_type':type(exc).__name__,'error':str(exc)}
        rows.append({'name':name,'expected_acceptance':name=='valid_synthetic_contract_control',
                     **outcome,'expectation_met':outcome['accepted']==(name=='valid_synthetic_contract_control')})
    report={'historical_review_base_commit':'da6e193a2c3290eec3876c9139719b7ec12f3013','experiment':'SYNTHETIC_REPORT_CONTRACT_MATRIX',
            'argv':sys.argv,'python':sys.version,'platform':platform.platform(),
            'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),
            'distinct_report_mutations':4,'synthetic_contract_controls':1,
            'physical_provider_or_parser_runs':0,'rows':rows,
            'qualification':'These are report-coherence tests, not an execution authenticity service or a 20/14-case campaign.'}
    (args.out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'report_variants':len(rows),'distinct_mutations':4,'physical_provider_or_parser_runs':0,
                      'outcomes':{r['name']:r['accepted'] for r in rows}},indent=2))
    return 0 if all(r['expectation_met'] for r in rows) else 1


if __name__=='__main__': raise SystemExit(main())
