"""New malformed-profile probes against exact public source; no old corpus run."""
import argparse
import copy
import hashlib
import importlib.util
import json
import platform
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--include-positive-control', action='store_true')
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    src = args.project / 'handoff'
    parser = load(src / 'compare_parsers.py', 'reviewer2_exact_parser')
    base_bytes = (src / 'dossier.json').read_bytes()
    base = json.loads(base_bytes)
    probes = []
    if args.include_positive_control:
        probes.append(('actual_fixture_affected_control', base, 'joint admission'))
    empty_id = copy.deepcopy(base)
    empty_id['obligations'][0]['id'] = ''
    probes.append(('empty_pending_obligation_id', empty_id, 'controlled refusal'))
    no_payload = copy.deepcopy(base)
    del no_payload['obligations'][0]['payload']
    probes.append(('pending_hash_file_without_payload', no_payload, 'controlled refusal'))
    wrong_memory = copy.deepcopy(base)
    wrong_memory['memory'] = []
    probes.append(('non_object_memory', wrong_memory, 'controlled refusal'))
    rows = []
    for name, value, expectation in probes:
        wire = base_bytes if name == 'actual_fixture_affected_control' else json.dumps(value, ensure_ascii=True, separators=(',', ':')).encode('utf8')
        (args.out / (name + '.json')).write_bytes(wire)
        try:
            py = parser.describe(json.loads(wire))
        except Exception as exc:
            py = {'accepted': False, 'error': type(exc).__name__}
        node = subprocess.run(['node', str(src / 'node_parser.cjs')], input=wire,
                              capture_output=True, check=True, timeout=10)
        js = json.loads(node.stdout)
        (args.out / (name + '.node_stdout.json')).write_bytes(node.stdout)
        row = {'name': name, 'expected_review_behavior': expectation,
               'input_sha256': hashlib.sha256(wire).hexdigest(), 'input_bytes': len(wire),
               'node_stdin_sha256': js['received_sha256'],
               'node_stdin_bytes': js['received_bytes'], 'node_version': js['node'],
               'python_raw': py, 'node_raw': js}
        # The same exception classes and joint checks as the published loop.
        try:
            parsed = parser.strict_load(wire.decode('utf8'))
            meaning = parser.admit(parsed)
            if not js['accepted']:
                raise ValueError('SECOND_PARSER_REJECTED')
            if py['bounded_canonical_sha256'] != js['bounded_canonical_sha256']:
                raise ValueError('PARSER_MEANING_DISAGREEMENT')
            row.update(outcome='JOINTLY_ADMITTED', meaning=meaning)
        except (ValueError, UnicodeError, KeyError, TypeError) as exc:
            row.update(outcome='CONTROLLED_REFUSAL', error_type=type(exc).__name__, error=str(exc))
        except Exception as exc:
            row.update(outcome='UNCONTROLLED_EXCEPTION', error_type=type(exc).__name__, error=str(exc))
        rows.append(row)
    report = {'base_commit': 'da6e193a2c3290eec3876c9139719b7ec12f3013',
              'experiment': 'NEW_MALFORMED_PROFILE_PROBES_ONLY',
              'python': sys.version, 'platform': platform.platform(), 'argv': sys.argv,
              'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in [src / 'compare_parsers.py', src / 'node_parser.cjs', src / 'dossier.json']},
              'probe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'rows': rows,
              'qualification': 'No operation or permission is executed or conferred. These are shape/admission behavior observations.'}
    report['status'] = 'PASS' if all(r['outcome'] == ('JOINTLY_ADMITTED' if r['name'] == 'actual_fixture_affected_control' else 'CONTROLLED_REFUSAL') for r in rows) else 'FAIL'
    (args.out / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'new_cases': len(rows)-int(args.include_positive_control),
                      'affected_positive_controls': int(args.include_positive_control),
                      'outcomes': {r['name']: r['outcome'] for r in rows}}, indent=2))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
