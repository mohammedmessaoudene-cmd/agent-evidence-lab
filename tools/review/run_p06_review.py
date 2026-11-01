"""Run only the added P06 corrective probes, retaining their actual outcomes."""
from pathlib import Path
import argparse,hashlib,json,os,platform,subprocess,sys

ROOT=Path(__file__).resolve().parents[2]
KIT=ROOT/'projects/P06_handoff_evidence'
def require(condition,message):
    if not condition:raise RuntimeError(message)
def read(path):return json.loads(path.read_bytes())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def verify_unicode(unicode,metadata):
    """Recompose this fixed matrix from its rows, states and exact source pins."""
    fields=('completed_two','unknown_preserved_without_retry','atomic_reconciled_after_lost_ack','old_cli_utf8_reply_received')
    expected=set()
    for mode in ('classic','adapter'):
        expected.update((mode,'I03_TRANSPORT',fixture,encoding) for fixture,encoding in (('ascii','ASCII'),('unicode','UTF-8'),('unicode','ASCII')))
        expected.update((mode,case,'unicode','ASCII') for case in ('I03_ATOMIC_ACK','I03_OPAQUE_ACK'))
        expected.add((mode,'I03_OLD_CLI',None,None))
    rows=unicode['observations']
    keys=[(r['mode'],r['case'],r.get('fixture'),r.get('encoding_selected')) for r in rows]
    require(len(keys)==12 and len(set(keys))==12 and set(keys)==expected,'P06 exact Unicode matrix identities')
    totals={field:0 for field in fields};encodings=[]
    for row in rows:
        worker=row['worker'];result=worker.get('result') or {};state=row['state']
        statuses=[x['status'] for x in state['obligations']]
        effect_count=len(state['effects'])
        values={field:False for field in fields}
        if row['case']=='I03_TRANSPORT':
            values['completed_two']=(worker['returncode']==0 and result.get('status')=='COMPLETE' and statuses==['DONE','DONE'] and effect_count==2)
            required='completed_two'
        elif row['case']=='I03_OLD_CLI':
            values['old_cli_utf8_reply_received']=(worker['returncode']==0 and result.get('ok') is True and effect_count==1)
            required='old_cli_utf8_reply_received'
        else:
            restart=row['restart'];final=row['after_restart'];final_statuses=[x['status'] for x in final['obligations']]
            ack_lost=(worker['returncode']==2 and result.get('error')=='ACK_LOST' and 'provider exit=73;' in result.get('detail',''))
            require(row.get('provider_exit73_observed_in_rpc_error') is ack_lost,'P06 lost-ack claim recomposition')
            if row['case']=='I03_ATOMIC_ACK':
                values['atomic_reconciled_after_lost_ack']=(ack_lost and statuses==['INTENT','PENDING'] and effect_count==1 and final_statuses==['DONE','DONE'] and len(final['effects'])==2 and restart['returncode']==0 and restart['result'].get('status')=='COMPLETE')
                required='atomic_reconciled_after_lost_ack'
            else:
                values['unknown_preserved_without_retry']=(ack_lost and statuses==['UNKNOWN','PENDING'] and effect_count==1 and final_statuses==['UNKNOWN','PENDING'] and len(final['effects'])==1 and restart['returncode']==2 and restart['result'].get('error')=='UNRESOLVED_OUTCOME')
                required='unknown_preserved_without_retry'
        require(values[required] is True,'P06 required Unicode causal outcome')
        for field,value in values.items():
            require(type(row.get(field,False)) is bool and row.get(field,False) is value,'P06 Unicode flag/state contradiction: '+field)
            totals[field]+=int(value)
        actual=worker['encodings'];require(actual['no_site']==1,'P06 direct child interpreter')
        require(actual['utf8_mode']==(1 if row.get('encoding_selected')=='UTF-8' else 0),'P06 actual encoding mode')
        encodings.append({'mode':row['mode'],'case':row['case'],'selected':row.get('encoding_selected','ASCII_UTF8_DISABLED'),'actual_stdin':actual['stdin_encoding'],'actual_stdout':actual['stdout_encoding'],'utf8_mode':actual['utf8_mode']})
    for reported,field,count in (('completed_two','completed_two',6),('unknown_preserved','unknown_preserved_without_retry',2),('atomic_reconciled','atomic_reconciled_after_lost_ack',2),('old_cli_utf8_reply_received','old_cli_utf8_reply_received',2)):
        require(type(unicode[reported]) is int and unicode[reported]==totals[field]==count,'P06 Unicode aggregate recomposition')
    require(unicode['status']=='PASS' and type(unicode['case_observations']) is int and unicode['case_observations']==len(rows)==12,'P06 Unicode counts')
    source=KIT/'provider_boundary/src'
    expected_sources={p.relative_to(source).as_posix():digest(p) for p in source.rglob('*.py')}
    observed=metadata['source_sha256']
    normalized={name.replace('\\','/'):sha for name,sha in observed.items()}
    require(len(expected_sources)==len(observed)==len(normalized)==7 and normalized==expected_sources,'P06 exact seven Unicode source pins')
    require(metadata['probe_sha256']==digest(KIT/'review/check_unicode_transport.py'),'P06 Unicode probe pin')
    require(metadata['protocol_sha256']==digest(KIT/'review/UNICODE_CORRECTION_PROTOCOL.json'),'P06 Unicode protocol pin')
    return encodings

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
    def run(name,arguments):
        process=subprocess.run([sys.executable,'-S','-B',*map(str,arguments)],cwd=KIT,env=env,capture_output=True,timeout=240)
        (out/(name+'.stdout.txt')).write_bytes(process.stdout);(out/(name+'.stderr.txt')).write_bytes(process.stderr)
        require(process.returncode==0 and not process.stderr,name+' failed; inspect saved outputs')
    t05=[]
    for mode in ('classic','adapter'):
        for fault in ('ack_without_effect','none'):
            name='T05_'+mode+'_'+fault
            run(name,['review/check_t05_effect.py','--mode',mode,'--fault',fault,'--out',out/name])
            report=read(out/name/'result.json');mutant=fault!='none'
            require(report['status']=='PASS' and report['expectation_met'] is True,'T05 expectation')
            require(report['evaluator_unchanged'] is True and report['observer_unchanged'] is True,'T05 equal oracle')
            require(report['run_case_result']['status']==('FAIL' if mutant else 'PASS') and report['observed_effect_count']==(0 if mutant else 1),'T05 causal result')
            require(report['source_sha256']['run.py']==digest(KIT/'provider_boundary/run.py'),'T05 source identity')
            t05.append({'mode':mode,'fault':fault,'runner_status':report['run_case_result']['status'],'effect_count':report['observed_effect_count'],'expectation_met':True})
    run('parser_shapes',['review/check_parser_shapes.py','--include-positive-control','--out',out/'parser_shapes'])
    shapes=read(out/'parser_shapes/result.json')
    names={'actual_fixture_affected_control','empty_pending_obligation_id','pending_hash_file_without_payload','non_object_memory'}
    require(shapes['status']=='PASS' and len(shapes['rows'])==4 and {r['name'] for r in shapes['rows']}==names,'P06 shape identities')
    for row in shapes['rows']:
        raw=out/'parser_shapes'/(row['name']+'.json');expected='JOINTLY_ADMITTED' if row['name']=='actual_fixture_affected_control' else 'CONTROLLED_REFUSAL'
        require(row['outcome']==expected,'P06 shape outcome')
        require(row['input_sha256']==row['node_stdin_sha256']==digest(raw) and row['input_bytes']==row['node_stdin_bytes']==raw.stat().st_size,'P06 shape byte identity')
    run('unicode',['review/check_unicode_transport.py','--phase','after','--out',out/'unicode'])
    unicode=read(out/'unicode/summary.json');metadata=read(out/'unicode/run_metadata.json')
    encodings=verify_unicode(unicode,metadata)
    report={'schema':'p06-corrective-ci/1','status':'PASS','python':platform.python_version(),'platform':platform.system(),'t05':t05,'parser_shapes':{'observations':4,'malformed_refused':3,'positive_control':1,'byte_identity':'PASS'},'unicode':{k:unicode[k] for k in ('case_observations','completed_two','unknown_preserved','atomic_reconciled','old_cli_utf8_reply_received')},'encodings':encodings,'unicode_source_sha256':metadata['source_sha256'],'scope':'Four T05 causal observations, four shape observations and12local process observations; not independent field samples. Historical base_commit fields in probes denote lineage; effective hashes identify this execution.'}
    (out/'SUMMARY.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'PASS','t05':4,'shape_observations':4,'unicode_observations':12}))
    return 0
if __name__=='__main__':raise SystemExit(main())
