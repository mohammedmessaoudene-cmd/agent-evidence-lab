"""Two bounded Linux output-path failures, not a hostile-filesystem guarantee."""
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
    p.add_argument('--program-project',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    script=a.program_project.resolve()/'src/openhtf_adapter.py'
    rows=[]
    for name in ['cyclic_output_symlink','cyclic_output_parent']:
        d=a.out.resolve()/name;inputs=d/'input';inputs.mkdir(parents=True)
        for f in (a.project/'runtime/exports/pass').glob('*.json'):shutil.copyfile(f,inputs/f.name)
        contract=d/'contract.json';shutil.copyfile(a.project/'protocol/contract.json',contract)
        link=d/'loop';link.symlink_to('loop')
        target=link if name=='cyclic_output_symlink' else link/'report.json'
        before={f:hashlib.sha256(f.read_bytes()).hexdigest() for f in [contract,*inputs.glob('*.json')]}
        proc=subprocess.run([sys.executable,'-B',str(script),'--contract',str(contract),'--expected-contract-sha256',before[contract],'--input-dir',str(inputs),'--out',str(target)],capture_output=True,timeout=5)
        (d/'stdout.txt').write_bytes(proc.stdout);(d/'stderr.txt').write_bytes(proc.stderr)
        try:r=json.loads(proc.stdout)
        except ValueError:r={}
        unchanged=all(hashlib.sha256(f.read_bytes()).hexdigest()==h for f,h in before.items())
        row={'case':name,'returncode':proc.returncode,'status':r.get('status'),'measurement_summary':r.get('measurement_summary'),'material_release_authorized':r.get('material_release_authorized'),'stderr_present':bool(proc.stderr),'source_unchanged':unchanged,'symlink_unchanged':link.is_symlink() and link.readlink()==Path('loop')}
        row['expected_met']=proc.returncode==2 and r.get('status')=='INCOMPLETE' and r.get('measurement_summary')=='UNKNOWN' and r.get('material_release_authorized') is False and not proc.stderr and unchanged and row['symlink_unchanged']
        rows.append(row)
    s={'source_sha256':hashlib.sha256(script.read_bytes()).hexdigest(),'rows':rows,'new_cli_executions':2,'all_expectations_met':all(r['expected_met'] for r in rows),'scope':'Linux path-error guard only'}
    (a.out/'SUMMARY.json').write_text(json.dumps(s,indent=2)+'\n',encoding='utf-8');print(json.dumps(s,indent=2))


if __name__=='__main__':main()
