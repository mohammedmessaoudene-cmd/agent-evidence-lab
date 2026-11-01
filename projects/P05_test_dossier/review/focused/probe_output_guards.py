"""New persistence guards and serialization probes, scoped to the CLI delta."""
import argparse
import hashlib
import importlib.util
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', type=Path, required=True)
    ap.add_argument('--program-project', type=Path, required=True)
    ap.add_argument('--published-program-project', type=Path)
    ap.add_argument('--corrected-only', action='store_true', help='Do not rerun historical before-fix observations')
    ap.add_argument('--only', nargs='+', help='Run only the named focused cases')
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    source_root = args.project.resolve()
    program_root = args.program_project.resolve()
    published_root = (args.published_program_project or args.program_project).resolve()
    scripts = {'candidate':'src/openhtf_adapter.py','control':'control/competent_script.py'}
    rows=[]
    definitions=[
        ('two_outputs_same_path','candidate','corrected'),
        ('later_output_is_contract','candidate','corrected'),
        ('existing_report','candidate','corrected'),
        ('existing_report','control','corrected'),
        ('symlink_to_source','candidate','corrected'),
        ('symlink_to_source','control','corrected'),
        ('hardlink_to_source','candidate','corrected'),
        ('hardlink_to_source','control','corrected'),
        ('two_fresh_reports_nested','candidate','corrected'),
        ('fresh_control_report','control','corrected'),
        ('later_parent_is_file','candidate','corrected'),
        ('parent_is_file','control','corrected'),
        ('escaped_surrogate_packet','candidate','published'),
        ('escaped_surrogate_packet','candidate','corrected'),
        ('review_api_packet_alias','candidate','published'),
        ('review_api_packet_alias','candidate','corrected'),
    ]
    if args.corrected_only:
        definitions = [row for row in definitions if row[2] == 'corrected']
    if args.only:
        unknown = set(args.only) - {row[0] for row in definitions}
        if unknown:
            ap.error('Unknown focused case: ' + ', '.join(sorted(unknown)))
        definitions = [row for row in definitions if row[0] in args.only]
    for case, who, version in definitions:
        folder=args.out/(case+'_'+who+'_'+version)
        inputs=folder/'input';inputs.mkdir(parents=True)
        for f in sorted((source_root/'runtime/exports/pass').glob('*.json')):
            shutil.copyfile(f,inputs/f.name)
        contract=folder/'contract.json';shutil.copyfile(source_root/'protocol/contract.json',contract)
        if case=='escaped_surrogate_packet':
            f=inputs/'P05-DEMO-001.json';obj=json.loads(f.read_bytes())
            obj['metadata']['p05_cli_inert_note']='\ud800'
            f.write_bytes((json.dumps(obj,ensure_ascii=True,indent=2)+'\n').encode())
        script=(published_root if version=='published' else program_root)/scripts[who]
        destination=folder/'report.json';packet=folder/'packet.json'
        extra=[];sentinels=[]
        if case=='two_outputs_same_path':extra=['--out',str(destination),'--packet-out',str(destination)]
        elif case=='later_output_is_contract':extra=['--out',str(destination),'--packet-out',str(contract)]
        elif case=='existing_report':
            destination.write_bytes(b'EXISTING REVIEW EVIDENCE\n');sentinels.append(destination)
            extra=['--out',str(destination)]
        elif case=='symlink_to_source':
            destination.symlink_to(inputs/'P05-DEMO-001.json');extra=['--out',str(destination)]
        elif case=='hardlink_to_source':
            os.link(inputs/'P05-DEMO-001.json',destination);extra=['--out',str(destination)]
        elif case=='two_fresh_reports_nested':
            destination=folder/'new/nested/report.json';packet=folder/'new/nested/packet.json'
            extra=['--out',str(destination),'--packet-out',str(packet)]
        elif case=='fresh_control_report':extra=['--out',str(destination)]
        elif case in ('later_parent_is_file','parent_is_file'):
            parent=folder/'not_directory';parent.write_bytes(b'EXISTING PARENT SENTINEL\n');sentinels.append(parent)
            if who=='candidate':extra=['--out',str(destination),'--packet-out',str(parent/'packet.json')]
            else:extra=['--out',str(parent/'report.json')]
        elif case=='escaped_surrogate_packet':extra=['--packet-out',str(packet)]
        protected=[contract,*inputs.glob('*.json'),*sentinels]
        original={f:f.read_bytes() for f in protected}
        if case=='review_api_packet_alias':
            spec=importlib.util.spec_from_file_location('api_'+version,script)
            mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            result=mod.review(contract,sha(contract.read_bytes()),inputs,packet_out=inputs/'P05-DEMO-001.json')
            output=json.dumps(result,ensure_ascii=True).encode();error=b'';code=None
        else:
            command=[sys.executable,'-B',str(script),'--contract',str(contract),
                     '--expected-contract-sha256',sha(contract.read_bytes()),'--input-dir',str(inputs),*extra]
            env=dict(os.environ);env.update(LC_ALL='C',PYTHONCOERCECLOCALE='0',PYTHONUTF8='0')
            proc=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,env=env)
            output,error,code=proc.stdout,proc.stderr,proc.returncode
            try:result=json.loads(output)
            except (ValueError,UnicodeError):result={}
        changed=[str(f.relative_to(folder)) for f,raw in original.items() if f.read_bytes()!=raw]
        (folder/'stdout.txt').write_bytes(output);(folder/'stderr.txt').write_bytes(error)
        good=case in ('two_fresh_reports_nested','fresh_control_report','escaped_surrogate_packet')
        expected=('READY_FOR_REVIEW','PASS') if good else ('INCOMPLETE','UNKNOWN')
        result_pair=(result.get('status'),result.get('measurement_summary'))
        row={'case':case,'program':who,'version':version,'script_sha256':sha(script.read_bytes()),
             'returncode':code,'status':result_pair[0],'measurement_summary':result_pair[1],
             'material_release_authorized':result.get('material_release_authorized'),
             'protected_files_changed':changed,'stderr_present':bool(error),
             'expected_after_fix':list(expected),'expected_met':result_pair==expected and not changed and not error and result.get('material_release_authorized') is False and (code is None or code==(0 if good else 2)),
             'new_report_exists':destination.exists() if case not in ('existing_report','symlink_to_source','hardlink_to_source') else None,
             'new_packet_exists':packet.exists()}
        if case in ('two_outputs_same_path','later_output_is_contract','later_parent_is_file'):
            row['expected_met']=row['expected_met'] and not destination.exists()
        if case=='two_fresh_reports_nested':
            row['required_files_present']=packet.is_file() and destination.is_file()
            row['expected_met'] &= row['required_files_present']
            if row['required_files_present']:
                parsed=json.loads(packet.read_bytes())
                row['packet_consistent_with_stdout']=parsed['review']==result
                row['report_consistent_with_stdout']=json.loads(destination.read_bytes())==result
                row['expected_met'] &= row['packet_consistent_with_stdout'] and row['report_consistent_with_stdout']
        if case=='fresh_control_report':
            row['required_files_present']=destination.is_file()
            row['expected_met'] &= row['required_files_present']
            if row['required_files_present']:
                row['report_consistent_with_stdout']=json.loads(destination.read_bytes())==result
                row['expected_met'] &= row['report_consistent_with_stdout']
        if case=='escaped_surrogate_packet':
            row['required_files_present']=packet.is_file()
            row['expected_met'] &= row['required_files_present']
            if row['required_files_present']:
                try:
                    parsed=json.loads(packet.read_bytes())
                    row['escaped_surrogate_preserved']=parsed['sources'][0]['raw_export']['metadata']['p05_cli_inert_note']=='\ud800'
                except (ValueError,KeyError):row['escaped_surrogate_preserved']=False
                row['expected_met'] &= row['escaped_surrogate_preserved']
        rows.append(row)
    summary={'schema':'p05-new-output-guards/1','rows':rows,
             'corrected_expectations_met':sum(r['expected_met'] for r in rows if r['version']=='corrected'),
             'corrected_records':sum(r['version']=='corrected' for r in rows),
             'new_cli_processes':sum(r['returncode'] is not None for r in rows),
             'review_api_calls':sum(r['returncode'] is None for r in rows),
             'historical_matrices_rerun':0,'symlink_hardlink_scope':'Only cases actually executed on '+platform.system()+' and this filesystem',
             'python':sys.version}
    (args.out/'SUMMARY.json').write_text(json.dumps(summary,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2,ensure_ascii=True))
    return 0 if all(r['expected_met'] for r in rows if r['version']=='corrected') else 1


if __name__=='__main__':raise SystemExit(main())
