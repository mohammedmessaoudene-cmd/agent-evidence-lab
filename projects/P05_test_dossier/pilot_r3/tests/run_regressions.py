"""Eight synthetic declaration-gate CLI checks; no field or model calls."""
import argparse,copy,hashlib,json,platform,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,o):p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def full_declaration():
    data=json.loads((ROOT/'tests/complete_pair.json').read_text(encoding='utf-8'))
    data.update(evidence_kind='OBSERVED_DECLARATIONS',scope='FULL_PILOT',
                test_provenance='ALL_VALUES_FABRICATED;OBSERVED_TAG_TESTS_A_BRANCH_NOT_AUTHENTIC_OBSERVATIONS')
    original_job=copy.deepcopy(data['manifest']['missions'][0])
    original_records={r['method']:copy.deepcopy(r) for r in data['records']}
    a=data['manifest']['roles']['operator_A'];b=data['manifest']['roles']['operator_B']
    jobs=[];records=[]
    for i in range(16):
        jid=f'TEST_JOB_{i:02d}';job=copy.deepcopy(original_job)
        job.update(job_id=jid,phase='DEVELOPMENT' if i<4 else 'RESERVE',
                   family_id=f'SYNTHETIC_FAMILY_{i%3}',first_method='A0' if i%2==0 else 'A1')
        job['operators']={'A0':a if i%2==0 else b,'A1':b if i%2==0 else a}
        job['expected_attempt_ids']={m:[jid+'_'+m+'_T1'] for m in ('A0','A1')}
        jobs.append(job)
        for method in ('A0','A1'):
            r=copy.deepcopy(original_records[method])
            r.update(job_id=jid,attempt_id=job['expected_attempt_ids'][method][0],operator_id=job['operators'][method])
            ids={}
            for event in r['cost']['human_events']+r['cost']['cash_events']:
                old=event['event_id'];new=jid+':'+method+':'+old;ids[old]=new;event['event_id']=new
                if 'actor_id' in event:event['actor_id']=job['operators'][method]
            r['cost']['assistance']['event_ids']=[ids[x] for x in r['cost']['assistance']['event_ids']]
            records.append(r)
    data['manifest']['missions']=jobs;data['records']=records
    return data

def cases():
    base=full_declaration();rows=[]
    def add(name,modify,reason):
        d=copy.deepcopy(base);modify(d);rows.append((name,d,reason))
    add('positive_complete_declarations',lambda d:None,None)
    def missing_source(d):
        d['manifest']['missions'][0]['input_artifact_ids']=[]
        for r in d['records'][:2]:r['input_artifact_ids']=[]
    add('TECH001_missing_source',missing_source,'TEST_JOB_00: input evidence missing')
    def missing_contract(d):
        d['manifest']['missions'][0]['contract_ref']=None
        for r in d['records'][:2]:r['contract_ref']=None
    add('TECH001_missing_contract',missing_contract,'TEST_JOB_00: independently approved contract reference missing')
    add('TECH001_missing_approval',lambda d:d['manifest']['missions'][0].update(contract_approval_ref=None),
        'TEST_JOB_00: independently approved contract reference missing')
    add('TECH001_template',lambda d:d.update(evidence_kind='TEMPLATE_NOT_AN_OBSERVATION'),
        'template is not a completed starting dossier')
    def wrong_keys(d):
        roles=d['manifest']['roles'];d['manifest']['missions'][0]['operators']={'X':roles['operator_A'],'Y':roles['operator_B']}
        for r in d['records'][:2]:r['operator_id']=None
    add('TECH002_wrong_operator_keys_null_record',wrong_keys,'TEST_JOB_00: operator assignment')
    add('TECH002_invalid_first_method',lambda d:d['manifest']['missions'][0].update(first_method='X'),
        'TEST_JOB_00: first method missing')
    add('TECH001_invalid_currency',lambda d:d['manifest'].update(currency='eur'),'declared currency')
    return rows

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    out=parser.parse_args().out.resolve();out.mkdir(parents=True,exist_ok=False)
    calculator=ROOT/'pilot_collect.py';pin=sha(calculator);rows=[]
    fixture_cases=cases()
    if len(fixture_cases)!=8:raise ValueError('FIXED_CASE_BUDGET')
    with tempfile.TemporaryDirectory(prefix='p05-synthetic-') as temp:
        for name,data,reason in fixture_cases:
            input_path=Path(temp)/(name+'.json');save(input_path,data)
            command=[sys.executable,'-B',str(calculator),'--input',str(input_path),'--artifact-root',str(ROOT)]
            timed_out=False
            try:
                run=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=10,check=False)
                stdout,stderr,code=run.stdout,run.stderr,run.returncode
            except subprocess.TimeoutExpired as exc:
                stdout,stderr,code=exc.stdout or b'',exc.stderr or b'',None;timed_out=True
            directory=out/name;directory.mkdir()
            (directory/'stdout.json').write_bytes(stdout);(directory/'stderr.txt').write_bytes(stderr)
            report={};parse_error=None
            try:
                if len(stdout)>200_000:raise ValueError('OUTPUT_LIMIT')
                report=json.loads(stdout)
                if not isinstance(report,dict):raise ValueError('OUTPUT_NOT_OBJECT')
            except (ValueError,UnicodeError) as exc:parse_error=str(exc)
            expected='DECLARATIONS_COMPLETE_HUMAN_SIGNOFF_REQUIRED' if reason is None else 'BLOCKED_INPUTS'
            checks={'bounded':not timed_out and len(stdout)<=200_000,'json':parse_error is None,
                    'exit_zero':code==0,'stderr_empty':stderr==b'',
                    'gate':report.get('documentary_start_gate')==expected,
                    'missing_reason':reason is None or reason in report.get('start_missing',[]),
                    'input_pin':report.get('input_sha256')==sha(input_path),
                    'source_pin':report.get('calculator_sha256')==pin,
                    'never_release':report.get('material_release_authorized') is False,
                    'no_measured_gain_claim':report.get('twenty_percent_claim')=='NOT_ESTABLISHED'}
            if reason is None:checks['positive_no_errors']=report.get('errors')==[] and report.get('start_missing')==[]
            row={'id':name,'passed':all(checks.values()),'checks':checks,'expected_gate':expected,
                 'observed_gate':report.get('documentary_start_gate'),'input_sha256':sha(input_path),
                 'exit_code':code,'parse_error':parse_error,'data_kind':'SYNTHETIC_TEST_WITH_OBSERVED_TAG_NOT_FIELD_DATA'}
            save(directory/'comparison.json',row);rows.append(row)
    if sha(calculator)!=pin:raise ValueError('CALCULATOR_CHANGED')
    summary={'status':'PASS' if all(r['passed'] for r in rows) else 'FAIL','distinct_cases':8,
             'calculator_processes':len(rows),'passed_cases':sum(r['passed'] for r in rows),
             'negative_fragments':7,'field_pilot':'PREPARED_NOT_RUN','llm_calls':0,'hardware_runs':0,
             'calculator_sha256':pin,'runner_sha256':sha(Path(__file__)),
             'python':sys.version,'platform':platform.platform(),'rows':rows,
             'limits':'Finite synthetic software controls;not observations,rights,approval,economic benefit,independent validation or agent superiority'}
    save(out/'SUMMARY.json',summary)
    print(json.dumps({k:summary[k] for k in ('status','distinct_cases','calculator_processes','passed_cases','field_pilot')}))
    return 0 if summary['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
