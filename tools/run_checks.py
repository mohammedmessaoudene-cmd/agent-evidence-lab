"""Run the bounded portable kits and verify their JSON contracts, not just exit0."""
from pathlib import Path
import argparse,hashlib,json,os,platform,subprocess,sys

ROOT=Path(__file__).resolve().parents[1]
PROJECTS={'P02':'P02_corrections','P03':'P03_verifier_reproduction','P04':'P04_cost_exposure','P05':'P05_test_dossier','P06':'P06_handoff_evidence'}
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def require(condition,message):
    if not condition:raise RuntimeError(message)
def run(pid,args):
    p=ROOT/'projects'/PROJECTS[pid]
    environment=os.environ.copy();environment['PYTHONNOUSERSITE']='1';environment['PYTHONDONTWRITEBYTECODE']='1'
    result=subprocess.run([sys.executable,'-S','-B',*map(str,args)],cwd=p,env=environment,text=True,capture_output=True,timeout=300)
    print(result.stdout)
    if result.returncode:
        print(result.stderr,file=sys.stderr)
        raise RuntimeError(f'{pid} command exited {result.returncode}')
def verify(pid,out):
    if pid in {'P02','P04'}:
        report=read(out/f'{pid}.json');require(report['status']=='PASS',pid+' summary status')
        if pid=='P02':
            suites=report['suites'];require(len(suites)==4,'P02 suite cardinality')
            require(sorted(x['recorded_cases'] for x in suites)==[3,8,12,18],'P02 cases')
            for suite in suites:
                require(suite['recorded_cases']==suite['passed']==suite['expected_cases'] and suite['failed']==0,'P02 suite result')
                require(len(suite['cases'])==suite['expected_cases'] and all(x['status']=='PASS' for x in suite['cases']),'P02 case records')
        else:
            require(report['tests_run']==23 and report['failures']==report['errors']==report['skipped']==0,'P04 counts')
            require(len(report['tests'])==23 and all(x['status']=='PASS' for x in report['tests']),'P04 method results')
            sql=report['regression_sqlite'];final=report['regression_finality']
            require(sql['status']=='PASS' and sql['exit_code']==0 and sql['cases_run']==sql['passed']==len(sql['cases'])==6 and sql['failed']==0,'P04 SQLite regression counts')
            require(all(x['expectation_met'] is True for x in sql['cases'].values()),'P04 SQLite outcomes')
            require(final['status']=='PASS' and final['exit_code']==0 and final['cases_run']==1 and final['checks_total']==len(final['checks'])==19 and final['checks_failed']==0,'P04 finality regression counts')
            require(len({x['name'] for x in final['checks']})==19 and all(x['passed'] is True for x in final['checks']),'P04 finality checks')
            current=hashlib.sha256((ROOT/'projects/P04_cost_exposure/src/exposure_ledger.py').read_bytes()).hexdigest()
            require(sql['source_sha256']==final['source_sha256']==current,'P04 regression source identity')
        return report
    if pid=='P03':
        report=read(out/'P03.json');require(len(report['cases'])==8 and report['upstream_false_positives']==2 and report['candidate_false_positives']==0,'P03 counts')
        require(all(not x['pr24']['false_positive'] for x in report['cases'].values()),'P03 strong comparator')
        for case in report['cases'].values():
            for name,arm in case.items():
                require(arm['configured_checks']==arm['executed_checks']==len(arm['oracle'])==4,'P03 checks executed')
                require(arm['retained_checks']==(3 if name=='upstream' else 4),'P03 retained checks')
                truth=all(x['passed'] for x in arm['oracle']);reported=all(x['passed'] for x in arm['retained'].values())
                require(arm['all_executed_pass']==truth and arm['reported_success']==reported and arm['false_positive']==(reported and not truth),'P03 trace recomposition')
        return {'cases':8,'main_false_successes':2,'pr24_false_successes':0,'stable_index_false_successes':0}
    if pid=='P05':
        primary=read(out/'P05_primary/summary.json');adverse=read(out/'P05_adversarial/SUMMARY.json')
        require(primary['distinct_cases']==30 and primary['program_executions']==60 and primary['candidate_expected_matches']==primary['competent_script_expected_matches']==primary['decisions_agreed']==30,'P05 primary counts')
        require(primary['material_release_true_count']==0 and primary['conservation_all_passed'],'P05 no release and preservation')
        require(adverse['distinct_cases']==22 and adverse['executions']==44 and adverse['candidate_expectations_met']==adverse['control_expectations_met']==22,'P05 adverse counts')
        require(len(adverse['rows'])==44 and all(x['expectation_met'] for x in adverse['rows']),'P05 adverse records')
        require(all(x['decision_agrees'] or x['capacity_dependent_oracle'] for x in adverse['decision_comparison']),'P05 unexplained disagreement')
        return {'primary':primary,'adversarial_counts':{k:v for k,v in adverse.items() if k not in {'rows','decision_comparison'}}}
    if pid=='P06':
        provider=read(out/'P06_provider/summary.json');parsers=read(out/'P06_parsers/result.json')
        # This is the fixed P06 matrix, independently listed from the runner.
        provider_pairs={('T01','atomic'),('T01','opaque'),('T01','contract_violating_skip'),
                        ('T02','atomic'),('T02','opaque'),('T03','atomic'),
                        ('T04','atomic'),('T04','contract_violating_skip'),
                        ('T05','atomic'),('T05','contract_violating_split')}
        expected_provider={(case,profile,mode) for case,profile in provider_pairs for mode in ('classic','adapter')}
        provider_rows=provider.get('results')
        require(isinstance(provider_rows,list) and len(provider_rows)==20,'P06 provider row count')
        provider_keys=[(r['case_id'],r['provider_profile'],r['mode']) for r in provider_rows]
        require(len(set(provider_keys))==20 and set(provider_keys)==expected_provider,'P06 provider matrix identities')
        for row in provider_rows:
            expected_unsafe=(row['case_id'],row['provider_profile']) in {('T01','contract_violating_skip'),('T05','contract_violating_split')}
            expected_meaning='EXPECTED_UNSAFE_COUNTEREXAMPLE_OBSERVED' if expected_unsafe else 'EXPECTED_BOUNDED_BEHAVIOR_OBSERVED'
            require(row['status']=='PASS' and row['meaning']==expected_meaning,'P06 provider row outcome')
            require(row['metrics']['contract_violation_observed'] is expected_unsafe,'P06 provider adverse classification')
        require(all(type(provider[k]) is int for k in ('planned_case_runs','case_runs','passed','failed','unsafe_counterexamples_observed')),'P06 provider integer counts')
        require(provider['case_runs']==len(provider_rows) and provider['passed']==sum(r['status']=='PASS' for r in provider_rows)
                and provider['failed']==sum(r['status']!='PASS' for r in provider_rows)
                and provider['unsafe_counterexamples_observed']==sum(r['meaning']=='EXPECTED_UNSAFE_COUNTEREXAMPLE_OBSERVED' for r in provider_rows),'P06 provider aggregate recomposition')
        require(provider['planned_case_runs']==provider['case_runs']==provider['passed']==20 and provider['failed']==0 and provider['unsafe_counterexamples_observed']==4,'P06 provider expectations')
        expected_parser={'actual_p06_dossier':True,'memory_name_incompatible':False,'memory_type_incompatible':False,
                         'memory_version_incompatible':False,'other_mission_id':False,'unknown_pending_obligation':False,
                         'duplicate_obligation_id':False,'forged_permission_is_only_data':True,'duplicate_mission_member':False,
                         'overflow_exponent':False,'unsafe_integer':False,'named_nan':False,'unpaired_surrogate':False,'valid_unicode':True}
        parser_rows=parsers.get('rows')
        require(isinstance(parser_rows,list) and len(parser_rows)==14,'P06 parser row count')
        parser_names=[r['name'] for r in parser_rows]
        require(len(set(parser_names))==14 and set(parser_names)==set(expected_parser),'P06 parser identities')
        protocol_path=out/'P06_parsers/protocol.json';protocol=read(protocol_path)
        require((out/'P06_parsers/protocol.sha256').read_text().strip()==hashlib.sha256(protocol_path.read_bytes()).hexdigest(),'P06 protocol digest')
        protocol_cases=protocol['cases']
        require(len(protocol_cases)==14 and len({r['name'] for r in protocol_cases})==14
                and {r['name'] for r in protocol_cases}==set(expected_parser),'P06 protocol identities')
        by_name={r['name']:r for r in protocol_cases}
        require(all(by_name[name]['expected_admitted'] is expected for name,expected in expected_parser.items()),'P06 protocol expectations')
        require(type(parsers['cases']) is int and type(parsers['expected_results']) is int,'P06 parser integer counts')
        require(parsers['cases']==parsers['expected_results']==14 and len(parsers['rows'])==14,'P06 parser counts')
        for row in parsers['rows']:
            evidence=row['byte_evidence'];data=(out/'P06_parsers'/(row['name']+'.json.txt')).read_bytes();digest=hashlib.sha256(data).hexdigest()
            require(row['expected'] is expected_parser[row['name']] and type(row['joint_admitted']) is bool,'P06 parser expected decision')
            require(row['joint_admitted']==row['expected'],'P06 parser semantic decision')
            require(by_name[row['name']]['sha256']==digest,'P06 case protocol binding')
            if row['name']=='actual_p06_dossier':require(protocol['dossier_sha256']==digest,'P06 source dossier binding')
            require(all(evidence[k]==digest for k in ['python_input_sha256','saved_file_sha256','node_stdin_sha256']),'P06 three digests')
            require(all(evidence[k]==len(data) for k in ['python_input_bytes','saved_file_bytes','node_stdin_bytes']),'P06 three sizes')
            require(row['node_raw']['received_sha256']==digest and row['node_raw']['received_bytes']==len(data),'P06 actual Node observation')
            require(row['pass'] is True and row['identical_bytes'] is True,'P06 recomposed parser result')
            if row['joint_admitted']:
                require(row['python_raw']['accepted'] is True and row['node_raw']['accepted'] is True,'P06 admitted parser acceptance')
                py_digest=row['python_raw']['bounded_canonical_sha256'];node_digest=row['node_raw']['bounded_canonical_sha256']
                require(isinstance(py_digest,str) and len(py_digest)==64 and py_digest==node_digest,'P06 admitted semantic digest')
        require(parsers['expected_results']==sum(r['pass'] is True for r in parser_rows),'P06 parser aggregate recomposition')
        return {'provider':{k:v for k,v in provider.items() if k not in {'results','metadata'}},'parser_cases':14,'byte_identity':'PASS'}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--project',choices=['all',*PROJECTS],default='all');parser.add_argument('--out',type=Path,required=True);parser.add_argument('--verify-only',action='store_true');a=parser.parse_args();out=a.out.resolve()
    if not a.verify_only:out.mkdir(parents=True,exist_ok=False)
    reports={}
    for pid in PROJECTS if a.project=='all' else [a.project]:
        if not a.verify_only:
            if pid in {'P02','P04'}:run(pid,['run_tests.py','--summary',out/f'{pid}.json'])
            elif pid=='P03':run(pid,['reproduce.py','--out',out/'P03.json'])
            elif pid=='P05':
                run(pid,['tests/run_matrix.py','--output',out/'P05_primary']);run(pid,['review/counterexamples.py','--out',out/'P05_adversarial'])
            else:
                run(pid,['provider_boundary/run.py','--out',out/'P06_provider']);run(pid,['handoff/compare_parsers.py','--out',out/'P06_parsers'])
        reports[pid]=verify(pid,out)
    summary={'status':'PASS','execution_mode':'VERIFY_EXISTING_REPORTS' if a.verify_only else 'EXECUTE_AND_VERIFY','python':platform.python_version(),'platform':platform.system(),'node':subprocess.check_output(['node','--version'],text=True).strip(),'projects':reports,'scope':'Bounded offline fixtures and expected adverse outcomes. P01 native test has separate instructions/CI. No adoption or production validity implied.'}
    (out/'SUMMARY_ALL.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':'PASS','projects':list(reports)}))
if __name__=='__main__':main()
