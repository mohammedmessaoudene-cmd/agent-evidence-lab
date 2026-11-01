"""One new inaccessible-input case for both programs, with bounded execution."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--project',type=Path,required=True)
    p.add_argument('--program-project',type=Path)
    p.add_argument('--only',nargs='+',choices=['cyclic_input_directory','cyclic_source_file'])
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    project=a.project.resolve();program=(a.program_project or a.project).resolve()
    contract=project/'protocol/contract.json';pin=hashlib.sha256(contract.read_bytes()).hexdigest()
    rows=[]
    cases=a.only or ['cyclic_input_directory','cyclic_source_file']
    for case in cases:
        for name,rel in [('candidate','src/openhtf_adapter.py'),('control','control/competent_script.py')]:
            d=a.out.resolve()/case/name;d.mkdir(parents=True)
            protected={}
            if case=='cyclic_input_directory':
                loop=d/'loop';loop.symlink_to('loop');inputs=loop
            else:
                inputs=d/'input';inputs.mkdir()
                for f in (project/'runtime/exports/pass').glob('*.json'):
                    target=inputs/f.name;shutil.copyfile(f,target);protected[target]=target.read_bytes()
                loop=inputs/'loop.json';loop.symlink_to('loop.json')
            script=program/rel
            proc=subprocess.run([sys.executable,'-B',str(script),'--contract',str(contract),'--expected-contract-sha256',pin,'--input-dir',str(inputs)],capture_output=True,timeout=5)
            (d/'stdout.txt').write_bytes(proc.stdout);(d/'stderr.txt').write_bytes(proc.stderr)
            try:r=json.loads(proc.stdout)
            except ValueError:r={}
            expected_issue=('INPUT_DIRECTORY' if name=='candidate' else 'CONTRACT_OR_INPUT_INVALID') if case=='cyclic_input_directory' else ('SOURCE_REJECTED' if name=='candidate' else 'NATIVE_EXPORT_INVALID')
            row={'case':case,'program':name,'script_sha256':hashlib.sha256(script.read_bytes()).hexdigest(),'returncode':proc.returncode,'status':r.get('status'),'measurement_summary':r.get('measurement_summary'),'material_release_authorized':r.get('material_release_authorized'),'stderr_present':bool(proc.stderr),'contract_unchanged':hashlib.sha256(contract.read_bytes()).hexdigest()==pin,'input_link_unchanged':loop.is_symlink() and loop.readlink()==Path(loop.name),'exports_unchanged':all(f.read_bytes()==raw for f,raw in protected.items()),'expected_issue_present':any(x.get('code')==expected_issue for x in r.get('issues',[]))}
            row['expected_met']=proc.returncode==2 and row['status']=='INCOMPLETE' and row['measurement_summary']=='UNKNOWN' and row['material_release_authorized'] is False and not proc.stderr and row['contract_unchanged'] and row['input_link_unchanged'] and row['exports_unchanged'] and row['expected_issue_present']
            rows.append(row)
    s={'schema':'p05-inaccessible-input-probe/1','new_case_count':len(cases),'cli_executions':len(rows),'rows':rows,'all_expectations_met':all(r['expected_met'] for r in rows),'scope':'Current Linux symlink-cycle path errors; no hostile filesystem sandbox claim'}
    (a.out/'SUMMARY.json').write_text(json.dumps(s,indent=2)+'\n',encoding='utf-8');print(json.dumps(s,indent=2))
    return 0 if s['all_expectations_met'] else 1


if __name__=='__main__':raise SystemExit(main())
