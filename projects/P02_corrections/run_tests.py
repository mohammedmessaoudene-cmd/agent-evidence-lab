"""Run only this public package; leave raw artifacts under ignored .local/."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--summary', type=Path, help='Optional sanitized public summary destination')
    args = parser.parse_args()
    if not sys.flags.no_site:
        parser.error('Use a direct Python 3.11/3.12 executable with -S; see README.md')
    if not (ROOT / '.local/deps/cryptography').is_dir():
        parser.error('Install the pinned requirements into .local/deps first; see README.md')
    env = os.environ.copy()
    env.pop('PYTHONHOME', None)
    env['PYTHONPATH'] = os.pathsep.join([str(ROOT / '.local/deps'), str(ROOT / 'src')])
    env['PYTHONNOUSERSITE'] = '1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    start = datetime.now(timezone.utc)
    raw = ROOT / '.local/runs' / start.strftime('%Y%m%dT%H%M%S%fZ')
    raw.mkdir(parents=True, exist_ok=False)
    suites = [
        ('scope', 'review/r2_scope_tests.py', 18),
        ('records', 'review/r2_audit_record_probes.py', 12),
        ('recovery_interop', 'tests/test_recovery_interop.py', 8),
        ('receipt_identity', 'tests/test_receipt_identity.py', 3),
    ]
    results = []
    overall = True
    for name, script, expected in suites:
        command = [sys.executable, '-S', '-B', str(ROOT / script), '--out', str(raw / name)]
        completed = subprocess.run(command, env=env, cwd=ROOT, capture_output=True, text=True, timeout=120)
        (raw / (name + '.stdout')).write_text(completed.stdout, encoding='utf-8')
        (raw / (name + '.stderr')).write_text(completed.stderr, encoding='utf-8')
        output = raw / name / 'results.json'
        report = json.loads(output.read_text(encoding='utf-8')) if output.exists() else {}
        passed = completed.returncode == 0 and report.get('case_records') == expected and report.get('failed') == 0 and report.get('passed') == expected
        overall &= passed
        records = []
        for case in report.get('results', []):
            item = {key: case[key] for key in ('case_id', 'mode', 'status')}
            evidence = case.get('evidence', {})
            fields = ('known_obligations_closed', 'actual_decision_coverage', 'semantic_truth',
                      'without_observation_gap_discovery', 'external_action_performed',
                      'negative_limit', 'storage_durability', 'stale_frontier_rejected',
                      'python_to_node_signature', 'node_to_python_signature_and_replay',
                      'crash_exit_code', 'restart_exit_code', 'final_status',
                      'signature_valid_in_test_registry', 'receipt_event_id_type',
                      'expected_acceptance', 'receipt_accepted', 'logical_store_unchanged',
                      'admission_sql_statements', 'engine_status', 'audit_closure',
                      'audit_finding_codes')
            item['observations'] = {key: evidence[key] for key in fields if key in evidence}
            records.append(item)
        results.append({'suite': name, 'status': 'PASS' if passed else 'FAIL_OR_INCOMPLETE',
                        'exit_code': completed.returncode, 'expected_cases': expected,
                        'recorded_cases': report.get('case_records', 0), 'passed': report.get('passed', 0),
                        'failed': report.get('failed', 0), 'cases': records})
        print(name, results[-1]['status'], f"{report.get('passed', 0)}/{expected}", flush=True)
    source_files = [p for p in ROOT.rglob('*') if p.is_file() and '.local' not in p.parts
                    and p.suffix in ('.py', '.mjs')]
    dependencies = {d.metadata['Name']: d.version for d in importlib.metadata.distributions(path=[str(ROOT / '.local/deps')])}
    summary = {
        'project': 'P02', 'kind': 'fresh_execution_of_public_copy', 'started_utc': start.isoformat(),
        'status': 'PASS' if overall else 'FAIL_OR_INCOMPLETE', 'external_review': 'PENDING',
        'python': platform.python_version(), 'platform': platform.system(), 'sqlite': sqlite3.sqlite_version,
        'node': subprocess.run(['node', '--version'], capture_output=True, text=True, check=True).stdout.strip(),
        'python_site_import_disabled': bool(sys.flags.no_site), 'explicit_dependency_target': '.local/deps',
        'dependencies': dependencies, 'suites': results,
        'source_sha256': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source_files)},
        'limits': ['Synthetic local fixtures; no NASA or other dataset.',
                   'Known obligations may close while actual decision coverage remains UNKNOWN.',
                   'Signatures use deterministic test identities; they do not prove computation or business action.',
                   'Shared engine across the two modes; no independent algorithm or superiority comparison.',
                   'Node is single-writer. Windows EPERM directory sync does not establish power-loss durability.',
                   'No real provider, organization, network service, LLM, human-time measurement or upstream adoption.'],
        'raw_artifact_directory': raw.relative_to(ROOT).as_posix(),
    }
    (raw / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return 0 if overall else 1


if __name__ == '__main__':
    raise SystemExit(main())
