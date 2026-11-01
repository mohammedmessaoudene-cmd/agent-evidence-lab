"""Execute P05 corrective checks and archive-contract mutations, without hardware."""
from pathlib import Path
import argparse,json,os,platform,shutil,subprocess,sys

ROOT=Path(__file__).resolve().parents[2]
KIT=ROOT/'projects/P05_test_dossier'

def require(condition,message):
    if not condition:raise RuntimeError(message)

def read(path):return json.loads(path.read_bytes())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    portable=platform.system()=='Windows'
    environment=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
    def run(name,arguments):
        process=subprocess.run([sys.executable,'-S','-B',*map(str,arguments)],cwd=KIT,env=environment,capture_output=True,timeout=240)
        (out/(name+'.stdout.txt')).write_bytes(process.stdout)
        (out/(name+'.stderr.txt')).write_bytes(process.stderr)
        require(process.returncode==0 and not process.stderr,name+' failed: inspect saved outputs')
    subset=['--portable-only'] if portable else []
    run('targeted',['review/run_targeted_review.py','--out',out/'targeted',*subset])
    targeted=read(out/'targeted/TARGETED_REVIEW.json')
    require(targeted['status']=='PASS' and targeted['execution_mode']=='EXECUTE_NEW_AND_AFFECTED_ONLY','P05 execution contract')
    expected=41 if portable else 45
    require(sum(s['records'] for s in targeted['stages'])==expected and all(s['records']==s['passed'] for s in targeted['stages']),'P05 observation records')

    # A no-op source-comment mutation challenges identity only. This copy is
    # never imported or run as the business program.
    changed=out/'source_identity_mutant'
    for name in ('src/openhtf_adapter.py','control/competent_script.py','review/run_targeted_review.py'):
        destination=changed/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(KIT/name,destination)
    candidate=changed/'src/openhtf_adapter.py'
    candidate.write_bytes(candidate.read_bytes()+b'\n# SYNTHETIC_SOURCE_IDENTITY_MUTATION_ONLY\n')
    run('archive',['review/focused/probe_verifier_integrity.py','--pinned-project',KIT,'--delta-project',changed,'--evidence',out/'targeted','--out',out/'archive',*subset])
    archive=read(out/'archive/SUMMARY.json')
    require(archive['all_expectations_met'] and len(archive['rows'])==7 and all(r['expected_met'] for r in archive['rows']),'P05 archive oracle')
    require(archive['business_programs_executed']==0 and all(r['business_programs_executed']==0 for r in archive['rows']),'P05 archive execution scope')

    inputs={'status':'NOT_RUN','reason':'Windows portable profile excludes symbolic links','observations':0}
    if not portable:
        run('input_cycles',['review/focused/probe_input_cycle.py','--project',KIT,'--out',out/'input_cycles'])
        inputs=read(out/'input_cycles/SUMMARY.json')
        require(inputs['all_expectations_met'] and inputs['cli_executions']==4 and len(inputs['rows'])==4 and all(r['expected_met'] for r in inputs['rows']),'P05 input cycles')
    summary={'schema':'p05-corrective-ci/1','status':'PASS','python':platform.python_version(),'platform':platform.system(),'targeted':targeted,'archive_only':{'checks':len(archive['rows']),'expected_outcomes_met':archive['all_expectations_met'],'business_programs_executed':0},'additional_input_cycles':inputs,'scope':'Constructed software observations and archive checks. Windows uses explicit41subset; Linux45plus4input observations. No hardware, authenticity, market or human-effort proof.'}
    (out/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'PASS','targeted_observations':expected,'archive_only_checks':7,'input_cycle_observations':0 if portable else 4}))
    return 0

if __name__=='__main__':raise SystemExit(main())
