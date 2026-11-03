"""Verify the packaged file identities; not authenticity or scientific validity.

No network, subprocess, or execution of the source under test is performed.
New output files are permitted; all manifest-listed files must remain unchanged.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

ROOT = Path(__file__).resolve().parent


def main() -> int:
    try:
        manifest = json.loads((ROOT / 'MANIFEST.json').read_text(encoding='utf-8'))
        pin = json.loads((ROOT / 'SOURCE_PIN.json').read_text(encoding='utf-8'))
        files = manifest['files']
        if not isinstance(files, list):
            raise ValueError('invalid manifest file list')
        seen: set[str] = set()
        failures: list[str] = []
        for row in files:
            relative = row['path']
            parts = PurePosixPath(relative)
            if parts.is_absolute() or '..' in parts.parts or '\\' in relative or relative in seen:
                raise ValueError(f'unsafe or repeated manifest path: {relative!r}')
            seen.add(relative)
            target = ROOT.joinpath(*parts.parts)
            if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(ROOT):
                failures.append(f'{relative}: absent, symlink, or outside kit')
                continue
            data = target.read_bytes()
            if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
                failures.append(f'{relative}: identity mismatch')
        raw = (ROOT / 'upstream/exposure_ledger.py').read_bytes()
        git_blob = hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()
        if git_blob != pin['git_blob'] or hashlib.sha256(raw).hexdigest() != pin['sha256'] or len(raw) != pin['bytes']:
            failures.append('upstream P04 source identity mismatch')
        result = {'status': 'PASS' if not failures else 'FAIL', 'files_checked': len(files),
                  'upstream_git_blob': git_blob, 'failures': failures,
                  'scope': 'local byte consistency; not authenticity, execution evidence, or independent validation'}
        print(json.dumps(result, indent=2))
        return int(bool(failures))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'status': 'ERROR', 'error': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
