"""New P05 CLI boundary probes; never run historical matrices or touch sources.

All potentially overwritten files are disposable copies under the fresh output.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--program-project', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    root = args.project.resolve()
    program_root = (args.program_project or args.project).resolve()
    scripts = {'candidate': program_root / 'src/openhtf_adapter.py',
               'control': program_root / 'control/competent_script.py'}
    definitions = [
        ('out_overwrites_export', who, 'source', False, False)
        for who in scripts
    ] + [
        ('out_overwrites_contract', who, 'contract', False, False)
        for who in scripts
    ] + [
        ('packet_overwrites_export', 'candidate', 'source', True, False),
        ('unicode_packet_ascii_locale', 'candidate', 'fresh', True, True),
        ('unicode_packet_utf8_locale', 'candidate', 'fresh', True, False),
    ]
    rows = []
    for case, who, target_kind, packet, ascii_locale in definitions:
        directory = args.out / (case + '_' + who)
        source_dir = directory / 'input'
        source_dir.mkdir(parents=True)
        for source in sorted((root / 'runtime/exports/pass').glob('*.json')):
            shutil.copyfile(source, source_dir / source.name)
        contract = directory / 'contract.json'
        shutil.copyfile(root / 'protocol/contract.json', contract)
        if case.startswith('unicode_'):
            source = source_dir / 'P05-DEMO-001.json'
            value = json.loads(source.read_bytes())
            value['metadata']['p05_cli_unicode_note'] = 'Mesure contrôlée — Δ = 0 ; 测量'
            source.write_bytes((json.dumps(value, ensure_ascii=True, indent=2)+'\n').encode('ascii'))
        protected = [contract, *sorted(source_dir.glob('*.json'))]
        before = {str(f.relative_to(directory)): f.read_bytes() for f in protected}
        target = (source_dir / 'P05-DEMO-001.json') if target_kind == 'source' else contract if target_kind == 'contract' else directory / 'packet.json'
        cmd = [sys.executable, '-B', str(scripts[who]), '--contract', str(contract),
               '--expected-contract-sha256', digest(contract.read_bytes()),
               '--input-dir', str(source_dir), '--packet-out' if packet else '--out', str(target)]
        env = dict(os.environ)
        env.update(LC_ALL='C', PYTHONCOERCECLOCALE='0', PYTHONUTF8='0' if ascii_locale else '1')
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, env=env)
        (directory/'stdout.txt').write_bytes(process.stdout)
        (directory/'stderr.txt').write_bytes(process.stderr)
        changed = []
        for name, raw in before.items():
            after = (directory/name).read_bytes()
            if after != raw:
                changed.append({'file':name,'before_bytes':len(raw),'after_bytes':len(after),
                                'before_sha256':digest(raw),'after_sha256':digest(after)})
        try:
            result = json.loads(process.stdout)
        except (ValueError, UnicodeError):
            result = None
        row = {'case':case,'program':who,'script_sha256':digest(scripts[who].read_bytes()),
               'returncode':process.returncode,'status':result.get('status') if result else None,
               'measurement_summary':result.get('measurement_summary') if result else None,
               'material_release_authorized':result.get('material_release_authorized') if result else None,
               'structured_stdout':isinstance(result,dict),'stderr':process.stderr.decode('utf-8',errors='backslashreplace'),
               'protected_files_changed':changed,'output_created':target.exists(),
               'output_bytes':target.stat().st_size if target.exists() else None,
               'locale':{'LC_ALL':'C','PYTHONCOERCECLOCALE':'0','PYTHONUTF8':env['PYTHONUTF8']},
               'command_roles':['python','-B',str(scripts[who].relative_to(program_root)),'--contract','CASE/contract.json',
                                '--expected-contract-sha256','SHA256(case contract)','--input-dir','CASE/input',
                                '--packet-out' if packet else '--out',str(target.relative_to(directory))]}
        rows.append(row)
        (directory/'observation.json').write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    summary = {'schema':'p05-new-cli-boundary-probes/1','python':sys.version,
               'scope':'Seven new interface executions on disposable original-data copies; no historical suite replay',
               'rows':rows,'historical_cases_rerun':0,'physical_tests':0,'framework_regenerations':0}
    (args.out/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'rows':[{k:r[k] for k in ['case','program','returncode','status','protected_files_changed','output_bytes']} for r in rows]},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
