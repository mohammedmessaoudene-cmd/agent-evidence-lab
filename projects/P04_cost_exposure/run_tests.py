"""Run the 23 local ledger tests using a direct Python interpreter, without site."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
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
    start = datetime.now(timezone.utc)
    raw = ROOT / '.local/runs' / start.strftime('%Y%m%dT%H%M%S%fZ')
    raw.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env.pop('PYTHONHOME', None)
    env['PYTHONPATH'] = str(ROOT / 'src')
    env['PYTHONNOUSERSITE'] = '1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    command = [sys.executable, '-S', '-B', str(ROOT / 'tests/test_exposure_ledger.py'),
               '--report', str(raw / 'full_report.json')]
    completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    (raw / 'stdout.txt').write_text(completed.stdout, encoding='utf-8')
    (raw / 'stderr.txt').write_text(completed.stderr, encoding='utf-8')
    report_file = raw / 'full_report.json'
    report = json.loads(report_file.read_text(encoding='utf-8')) if report_file.exists() else {}
    passed = (completed.returncode == 0 and report.get('tests_run') == 23
              and report.get('failures') == report.get('errors') == report.get('skipped') == 0
              and len(report.get('tests', [])) == 23)
    source_files = [ROOT / 'src/exposure_ledger.py', ROOT / 'tests/test_exposure_ledger.py', Path(__file__)]
    summary = {
        'project': 'P04', 'kind': 'fresh_execution_of_public_copy', 'started_utc': start.isoformat(),
        'status': 'PASS' if passed else 'FAIL_OR_INCOMPLETE', 'external_review': 'PENDING',
        'exit_code': completed.returncode, 'python': platform.python_version(), 'platform': platform.system(),
        'sqlite': sqlite3.sqlite_version, 'python_site_import_disabled': bool(sys.flags.no_site),
        'third_party_dependencies': [],
        'tests_run': report.get('tests_run', 0), 'failures': report.get('failures'),
        'errors': report.get('errors'), 'skipped': report.get('skipped'), 'tests': report.get('tests', []),
        'source_sha256': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files},
        'limits': ['One-account SQLite fixture with cooperative local writers and synthetic evidence.',
                   'Tests use real local child processes and abrupt termination; no remote provider or paid calls.',
                   'Source-role and evidence-kind checks are not cryptographic or provider-bill authentication.',
                   'No real enforced provider ceiling, power-loss proof, network filesystem or multi-host deployment.',
                   'No end-to-end exactly-once external effects and no superior budget optimizer claim.',
                   'The historical 23-method run had one cleanup error; only its affected method was rerun then. This is a separate fresh full run of the public copy.'],
        'raw_artifact_directory': raw.relative_to(ROOT).as_posix(),
    }
    (raw / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(summary['status'], summary['tests_run'], 'tests', flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
