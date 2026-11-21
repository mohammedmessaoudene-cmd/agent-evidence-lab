"""Replay six public review submissions with the pinned P02 engine and SQLite."""
import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


HERE = Path(__file__).resolve().parent
COMMIT = 'f5af76e5935ef475c1269a447e28128bdb8e457f'
PROJECT = 'projects/P02_corrections'
TREE = 'b4918622588b3744f1bb136d520bc39722ad31cb'
STATES = {-1: 'CHANGES_REQUESTED', 0: 'NO_FORMAL_REVIEW_ON_THIS_SHA', 1: 'APPROVED'}
CODES = {state: code for code, state in STATES.items() if code}

QUERY = '''
SELECT json_extract(value, '$.id'), json_extract(value, '$.state')
FROM json_each(?, '$.reviews')
WHERE json_extract(value, '$.reviewer_id') = ? AND json_extract(value, '$.commit') = ?
  AND json_extract(value, '$.state') IN ('APPROVED', 'CHANGES_REQUESTED')
  AND (json_extract(value, '$.time'), json_extract(value, '$.id')) <= (?, ?)
ORDER BY json_extract(value, '$.time') DESC, json_extract(value, '$.id') DESC LIMIT 1
'''


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def prepare_source(repo, folder):
    tree = git(repo, 'rev-parse', f'{COMMIT}:{PROJECT}').decode().strip()
    if tree != TREE:
        raise ValueError('Unexpected P02 Git tree')
    for name in ('p02/__init__.py', 'p02/wire.py', 'p02/engine.py', 'node_peer.mjs'):
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git(repo, 'show', f'{tree}:src/{name}'))


def replay(repo, folder):
    prepare_source(repo, folder)
    sys.path.insert(0, str(folder))
    from p02.engine import Engine
    from p02.wire import canonical, digest

    raw = (HERE / 'source.json').read_bytes()
    data = json.loads(raw)
    heads = data['reviewed_commits']
    actor = data['maintainer']['id']
    fixture = {'leaves': {'review_' + head: {'issuer': 'local-public-record-projector', 'revision': 0,
                      'value': 0, 'unit': 'formal-review-state'} for head in heads}, 'nodes': {},
               'decisions': {'decision_' + head: {'node': 'review_' + head, 'owner': 'local-replay-peer',
                             'threshold': 1, 'policy': 'ge-v1'} for head in heads}, 'graph_complete': True,
               'membership_closed': False, 'cutoff': 'cmcp-575', 'data_kind': 'PUBLIC_REVIEW_PROJECTION'}

    def peer(command, **args):
        request = dict(fixture=fixture, store_path=str(folder / 'peer.json'), command=command, **args)
        result = subprocess.run(['node', str(folder / 'node_peer.mjs')], input=canonical(request), capture_output=True)
        if result.returncode:
            raise ValueError(f'P02 peer failed: {result.stdout!r} {result.stderr!r}')
        return json.loads(result.stdout)

    sql = sqlite3.connect(':memory:')
    engine = Engine(folder / 'engine.sqlite', fixture)
    rows, receipts = [], []
    try:
        for row in sorted(data['reviews'], key=lambda r: (r['time'], r['id'])):
            head, review_id = row['commit'], row['id']
            if row['state'] in CODES and row['reviewer_id'] == actor:
                event = 'public-review-' + str(review_id)
                leaf = 'review_' + head
                if review_id <= engine.state()[leaf]['revision']:
                    raise ValueError('Review IDs must advance on each SHA for this mapping')
                change = {'leaf': leaf, 'revision': review_id, 'value': CODES[row['state']]}
                packet = engine.correction(event, 'local-public-record-projector', [change])
                assert engine.ingest(packet) == 'APPLIED'
                assert peer('apply', envelope=packet, registry=engine.registry)['status'] == 'APPLIED'
                signed = peer('receipt', event_id=event, decision_id='decision_' + head)['envelope']
                assert engine.accept_receipt(signed, replay=True) == 'LOCAL_REPLAY'
                receipts.append({'review_id': review_id, 'local_p02_receipt_sha256': digest(signed)})
            at_review = []
            for candidate in heads:
                answer = engine.outputs()['decision_' + candidate]
                p02_id = answer['frontier']['review_' + candidate]['revision'] or None
                reference = sql.execute(QUERY, (raw.decode('utf-8'), actor, candidate, row['time'], review_id)).fetchone()
                reference = reference or (None, 'NO_FORMAL_REVIEW_ON_THIS_SHA')
                assert (p02_id, STATES[answer['score']]) == reference
                assert answer['outcome'] == (reference[1] == 'APPROVED')
                at_review.append(list(reference))
            rows.append({'at_review': review_id, 'by_commit_in_source_order': at_review})
    finally:
        engine.close()
        sql.close()
    return {'source_lf_sha256': hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest(), 'p02_commit': COMMIT, 'p02_tree': TREE,
            'comparisons': sum(len(row['by_commit_in_source_order']) for row in rows),
            'local_peer_receipts': receipts, 'observations': rows}


if __name__ == '__main__':
    if not __debug__:
        raise RuntimeError('Python assertions must be enabled')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=HERE.parents[2], help='Git clone containing the pinned lab commit')
    args = parser.parse_args()
    with TemporaryDirectory() as folder:
        result = replay(args.repo, Path(folder))
    expected = json.loads((HERE / 'receipt.json').read_bytes())
    if result != expected:
        raise ValueError('Replay differs from the published receipt')
    print(f"{result['comparisons']} matching (state, review ID) pairs and {len(result['local_peer_receipts'])} verified local P02 receipts")
