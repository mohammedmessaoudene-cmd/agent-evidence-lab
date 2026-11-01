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
            suites=report['suites'];require(len(suites)==3,'P02 suite cardinality')
            require(sorted(x['recorded_cases'] for x in suites)==[8,12,18],'P02 cases')
            for suite in suites:
                require(suite['recorded_cases']==suite['passed']==suite['expected_cases'] and suite['failed']==0,'P02 suite result')
                require(len(suite['cases'])==suite['expected_cases'] and all(x['status']=='PASS' for x in suite['cases']),'P02 case records')
        else:
            require(report['tests_run']==23 and report['failures']==report['errors']==report['skipped']==0,'P04 counts')
            require(len(report['tests'])==23 and all(x['status']=='PASS' for x in report['tests']),'P04 method results')
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
        require(provider['planned_case_runs']==provider['case_runs']==provider['passed']==20 and provider['failed']==0 and provider['unsafe_counterexamples_observed']==4,'P06 provider expectations')
        require(parsers['cases']==parsers['expected_results']==14 and len(parsers['rows'])==14,'P06 parser counts')
        require(all(x['pass'] and x['identical_bytes'] for x in parsers['rows']),'P06 parser byte identity')
        for row in parsers['rows']:
            evidence=row['byte_evidence'];data=(out/'P06_parsers'/(row['name']+'.json.txt')).read_bytes();digest=hashlib.sha256(data).hexdigest()
            require(all(evidence[k]==digest for k in ['python_input_sha256','saved_file_sha256','node_stdin_sha256']),'P06 three digests')
            require(all(evidence[k]==len(data) for k in ['python_input_bytes','saved_file_bytes','node_stdin_bytes']),'P06 three sizes')
            require(row['node_raw']['received_sha256']==digest and row['node_raw']['received_bytes']==len(data),'P06 actual Node observation')
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
