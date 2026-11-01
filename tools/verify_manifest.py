"""Verify published bytes. Integrity is not scientific validity or provenance."""
from pathlib import Path,PurePosixPath,PureWindowsPath
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
manifest=json.loads((ROOT/'MANIFEST_PUBLIC.json').read_text(encoding='utf-8'))
seen=set()
for entry in manifest['files']:
    name=entry['path'];p=PurePosixPath(name)
    if p.is_absolute() or PureWindowsPath(name).drive or '\\' in name or ':' in name or '..' in p.parts or name.casefold() in seen:raise SystemExit('Invalid/duplicate manifest path')
    seen.add(name.casefold());unresolved=ROOT
    for part in p.parts:
        unresolved=unresolved/part
        if unresolved.is_symlink():raise SystemExit('Manifest symlink component')
    path=unresolved.resolve()
    if not path.is_relative_to(ROOT.resolve()):raise SystemExit('Manifest escape')
    raw=path.read_bytes()
    if len(raw)!=entry['bytes'] or hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise SystemExit('Source mismatch: '+name)
tracked=subprocess.run(['git','ls-files','-z'],cwd=ROOT,capture_output=True)
if tracked.returncode==0 and tracked.stdout:
    names={n.decode('utf-8') for n in tracked.stdout.split(b'\0') if n}
    expected={e['path'] for e in manifest['files']}|{'MANIFEST_PUBLIC.json'}
    if names!=expected:raise SystemExit('Tracked path set differs from manifest')
print(json.dumps({'status':'PASS','verified_files':len(manifest['files']),'meaning':'Published byte identity only; not external attestation'}))
