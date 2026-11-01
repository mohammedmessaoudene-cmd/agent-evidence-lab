"""Eight synthetic crash/restart and Python/Node checks, without datasets."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from p02.engine import Engine
from p02.fixtures import small
from p02.wire import Rejected, canonical, verify


def update(engine, event, leaf='A', value=20):
    return engine.correction(event, engine.fixture['leaves'][leaf]['issuer'],
                             [{'leaf': leaf, 'revision': 1, 'value': value}])


def worker(database, mode, stage=None):
    env = os.environ.copy()
    env['PYTHONPATH'] = os.pathsep.join([str(ROOT / 'src'), str(ROOT / '.local/deps')])
    args = [sys.executable, '-S', '-B', '-m', 'p02.worker', str(database), '--mode', mode]
    if stage:
        args += ['--crash-at', stage]
    return subprocess.run(args, env=env, capture_output=True, text=True, timeout=20)


def crash_case(folder, mode, stage):
    database = folder / 'store.sqlite'
    engine = Engine(database, small(), mode)
    try:
        engine.ingest(update(engine, 'C1'))
        before = engine.outputs()
        child = worker(database, mode, stage)
        assert child.returncode == {'before_write': 71, 'during_transaction': 72, 'after_commit': 73}[stage], child.stderr
        crashed = engine.summary('C1')
        if stage != 'after_commit':
            assert engine.outputs() == before and crashed['review_attestations'] == 0
        else:
            assert crashed['review_attestations'] == 1
        restarted = worker(database, mode)
        assert restarted.returncode == 0, restarted.stderr
        final = engine.summary('C1')
        assert final['status'] == 'COMPLETE_REGISTERED_LOCAL_REPLAY'
        outputs = engine.outputs()
        assert outputs['D1']['score'] == 20 and outputs['D1']['outcome'] is True
        assert outputs['D3']['score'] == 25 and outputs['D3']['outcome'] is False
        return {'crash_exit_code': child.returncode, 'restart_exit_code': restarted.returncode,
                'post_crash_attestations': crashed['review_attestations'],
                'final_status': final['status'], 'power_loss_durability': 'NOT_TESTED',
                'external_exactly_once': 'NOT_TESTED'}
    finally:
        engine.close()


def node(request):
    result = subprocess.run(['node', str(ROOT / 'src/node_peer.mjs')],
                            input=canonical(request).decode('ascii'), capture_output=True,
                            text=True, timeout=20)
    response = json.loads(result.stdout)
    assert result.returncode == 0, response
    return response


def interop_case(folder, mode):
    fixture = small()
    engine = Engine(folder / 'store.sqlite', fixture, mode)
    store = folder / 'node-store.json'
    try:
        first = update(engine, 'A1')
        engine.ingest(first)
        applied = node({'command': 'apply', 'fixture': fixture, 'store_path': str(store),
                        'envelope': first, 'registry': engine.registry})
        durability = applied['storage_durability']
        assert durability['file_fsync'] is True and durability['rename_completed'] is True
        if durability['directory_fsync'] == 'UNSUPPORTED_EPERM_WIN32':
            assert sys.platform == 'win32' and durability['power_loss_durability'] == 'NOT_ESTABLISHED'
        else:
            assert durability['directory_fsync'] == 'COMPLETED'
            assert durability['power_loss_durability'] == 'NOT_TESTED'
        receipt = engine.make_receipt('A1', 'D1')
        assert node({'command': 'verify', 'envelope': receipt, 'registry': engine.registry})['accepted']
        from_node = node({'command': 'receipt', 'fixture': fixture, 'store_path': str(store),
                          'event_id': 'A1', 'decision_id': 'D3'})['envelope']
        verify(from_node, engine.registry)
        assert engine.accept_receipt(from_node, replay=True) == 'LOCAL_REPLAY'
        second = update(engine, 'C1', leaf='C', value=40)
        engine.ingest(second)
        stale = node({'command': 'receipt', 'fixture': fixture, 'store_path': str(store),
                      'event_id': 'C1', 'decision_id': 'D3'})['envelope']
        try:
            engine.accept_receipt(stale, replay=True)
        except Rejected:
            stale_rejected = True
        else:
            raise AssertionError('stale Node frontier accepted')
        node({'command': 'apply', 'fixture': fixture, 'store_path': str(store),
              'envelope': second, 'registry': engine.registry})
        fresh = node({'command': 'receipt', 'fixture': fixture, 'store_path': str(store),
                      'event_id': 'C1', 'decision_id': 'D3'})['envelope']
        assert engine.accept_receipt(fresh, replay=True) == 'LOCAL_REPLAY'
        engine.drain()
        assert engine.outputs()['D3']['score'] == 30 and engine.outputs()['D3']['outcome'] is True
        return {'python_to_node_signature': True, 'node_to_python_signature_and_replay': True,
                'stale_frontier_rejected': stale_rejected, 'storage_durability': durability,
                'independent_organizations': False, 'node_writer_model': 'SINGLE_WRITER'}
    finally:
        engine.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    records = []
    for mode in ('classic_sql', 'portable_graph'):
        for name in ('before_write', 'during_transaction', 'after_commit', 'interop'):
            folder = args.out / (name + '_' + mode)
            folder.mkdir()
            row = {'case_id': name, 'mode': mode}
            try:
                row['evidence'] = interop_case(folder, mode) if name == 'interop' else crash_case(folder, mode, name)
                row['status'] = 'PASS'
            except Exception as error:
                row.update(status='FAIL', error=str(error), traceback=traceback.format_exc())
            records.append(row)
    result = {'case_records': len(records), 'passed': sum(r['status'] == 'PASS' for r in records),
              'failed': sum(r['status'] != 'PASS' for r in records), 'results': records}
    (args.out / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('case_records', 'passed', 'failed')}))
    return int(result['failed'] != 0)


if __name__ == '__main__':
    raise SystemExit(main())
