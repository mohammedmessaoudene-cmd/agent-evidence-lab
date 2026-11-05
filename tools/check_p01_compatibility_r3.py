"""Bounded hosted qualification of two selected P01 tests, normal and mutant.

Use only a disposable upstream checkout. This is synthetic, in-process recovery.
"""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys,xml.etree.ElementTree as ET

PIN='d44704ec72744e4fc0bd5a3d5dd877462a24da5b'
CANDIDATE='742edc61b5e5a4107a6807ec06520b34e496c47f5e8df07a0540f093f46e576f'
BACKEND='40ecc9172df886f7d4988978b00425eac11ca26758ff4e98296b35001cdcfc13'
FAKE='1e84660ac8be15fda685226b05c20428308a0fc3f29b162243d66f831cf3aedc'
IDENTITIES={
 ('tests.harness.memory.test_dbos_recovery.TestMemoryDBOSRecovery','test_recovery_restores_snapshot_after_compaction'),
 ('tests.harness.memory.test_memory','test_snapshot_load_dispatches_as_durable_operation')}


def require(value,message):
    if not value:raise RuntimeError(message)


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream',type=Path,required=True)
    parser.add_argument('--kit',type=Path,required=True)
    parser.add_argument('--dbos',choices=['2.29.0','3.4.0'],required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();root=args.upstream.resolve();kit=args.kit.resolve();out=args.out.resolve()
    require(os.environ.get('DBOS__CLOUD')=='false','Set DBOS__CLOUD=false before any SDK import')
    require(not out.exists(),'Fresh output directory required');out.mkdir(parents=True)
    python=root/('.venv/Scripts/python.exe' if os.name=='nt' else '.venv/bin/python')
    backend=root/'pydantic_ai_slim/pydantic_ai/durable_exec/dbos/_operation_backend.py'
    target=root/'tests/harness/memory/test_dbos_recovery.py'
    fake=root/'tests/harness/memory/test_memory.py'
    require(digest(backend)==BACKEND and digest(fake)==FAKE,'Upstream selected source bytes')
    require(digest(kit/'candidate/test_dbos_recovery.py')==CANDIDATE,'Candidate byte identity')
    require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==PIN,'Upstream commit')
    shutil.copyfile(kit/'candidate/test_dbos_recovery.py',target)
    env=os.environ.copy();env.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTEST_ADDOPTS='',PYTEST_PLUGINS='')
    commands=[]
    def run(label,argv,expected=0,timeout=120):
        result=subprocess.run([str(x) for x in argv],cwd=root,env=env,capture_output=True,timeout=timeout)
        (out/(label+'.stdout.txt')).write_bytes(result.stdout)
        (out/(label+'.stderr.txt')).write_bytes(result.stderr)
        commands.append({'label':label,'returncode':result.returncode,'expected_returncode':expected})
        (out/'COMMANDS.json').write_text(json.dumps(commands,indent=2)+'\n',encoding='utf-8')
        require(result.returncode==expected,'Unexpected process result: '+label)
        return result
    versions=run('versions',[python,'-c','import importlib.metadata as m,json,platform; print(json.dumps({"python":platform.python_version(),"dbos":m.version("dbos"),"pytest":m.version("pytest")}))'])
    observed=json.loads(versions.stdout);require(observed['dbos']==args.dbos,'Executed SDK version')
    run('ruff-check',[python,'-m','ruff','check',target])
    run('ruff-format',[python,'-m','ruff','format','--check',target])
    checked=run('pyright',[python,'-m','pyright','--project','pyproject.toml','--outputjson',target])
    require(json.loads(checked.stdout)['summary']['errorCount']==0,'Targeted Pyright errors')
    original=backend.read_bytes();rows=[]
    try:
        for mode in ('normal','mutant'):
            if mode=='mutant':
                run('patch-check',['git','apply','--check',kit/'candidate/capability_step_bypass.patch'])
                run('patch',['git','apply',kit/'candidate/capability_step_bypass.patch'])
            junit=out/(mode+'.xml')
            argv=[python,'-m','pytest','-p','no:cacheprovider','-p','anyio.pytest_plugin',
                  '-p','cassetter.pytest_plugin','-p','inline_snapshot.pytest_plugin','-p','pytest_mock','-p','xdist.plugin',
                  'tests/harness/memory/test_dbos_recovery.py::TestMemoryDBOSRecovery::test_recovery_restores_snapshot_after_compaction',
                  'tests/harness/memory/test_memory.py::test_snapshot_load_dispatches_as_durable_operation',
                  '-q','-rA','--tb=short','--color=no','--junitxml='+str(junit),'--basetemp='+str(out/(mode+'-temp'))]
            run(mode,argv,0 if mode=='normal' else 1,timeout=90)
            cases=ET.parse(junit).getroot().findall('.//testcase')
            require(len(cases)==2 and {(c.get('classname'),c.get('name')) for c in cases}==IDENTITIES,'Two exact executed identities')
            require(all(c.find('error') is None and c.find('skipped') is None for c in cases),'No skips/errors')
            failed=[c for c in cases if c.find('failure') is not None]
            if mode=='normal':require(not failed,'Normal tests must pass')
            else:
                require(len(failed)==1 and failed[0].get('classname').endswith('TestMemoryDBOSRecovery'),'Native fails; fake comparator passes')
                failure=failed[0].find('failure')
                message=failure.get('message','')
                traceback=(failure.text or '').replace('\\','/')
                require(message.startswith('AssertionError: assert ')
                        and 'At index 1 diff:' in message and 'version A' in message and 'version B' in message,
                        'Expected snapshot equality assertion, not unrelated failure or timeout')
                require('test_dbos_recovery.py:157: in test_recovery_restores_snapshot_after_compaction' in traceback
                        and 'assert sent == [[snapshot]] * 5' in traceback,
                        'Failure must bind the pinned snapshot-equality assertion')
            rows.append({'mode':mode,'executed':2,'failed':len(failed),'backend_sha256':digest(backend),'junit_sha256':digest(junit)})
    finally:
        backend.write_bytes(original)
    require(digest(backend)==BACKEND,'Backend restored exactly')
    summary={'status':'PASS','upstream':PIN,'candidate_sha256':digest(target),'dbos':args.dbos,
             'runtime':observed,'pytest_processes':2,'selected_test_identities':2,'rows':rows,'backend_restored':True,
             'scope':'Same-team hosted synthetic local nonCloud in-process recovery. Reused test identities; no new independent scenarios, provider calls, Cloud or adoption proof.'}
    (out/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
