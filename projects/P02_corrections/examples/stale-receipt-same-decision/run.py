"""Exercise the public P02 peer on two corrections to the same decision."""
import json
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(PROJECT / "src"), str(PROJECT / ".local/deps")]
from p02.engine import Engine
from p02.fixtures import small
from p02.wire import Rejected, canonical, digest, verify


def peer(command, fixture, store, **kwargs):
    request = dict(command=command, fixture=fixture, store_path=str(store), **kwargs)
    completed = subprocess.run(["node", str(PROJECT / "src/node_peer.mjs")],
                               input=canonical(request), capture_output=True, timeout=20)
    if completed.returncode:
        raise RuntimeError((completed.stderr or completed.stdout).decode())
    return json.loads(completed.stdout)


def sql_decision(db, fixture):
    # This reference is specific to D3: mean(identity(A), C), then threshold.
    rows = db.execute("""
        WITH history(leaf, revision, value) AS (
            SELECT key, json_extract(value,'$.revision'), json_extract(value,'$.value')
            FROM json_each(:fixture,'$.leaves')
            UNION ALL
            SELECT json_extract(c.value,'$.leaf'), json_extract(c.value,'$.revision'),
                   json_extract(c.value,'$.value')
            FROM received, json_each(received.packet,'$.payload.changes') AS c
        ), ranked AS (
            SELECT *, row_number() OVER (PARTITION BY leaf ORDER BY revision DESC) AS rank
            FROM history WHERE leaf IN ('A','C')
        ), current AS (SELECT * FROM ranked WHERE rank=1),
        decision AS (SELECT sum(value)/count(*) AS score FROM current)
        SELECT leaf, revision, value, score,
               score >= json_extract(:fixture,'$.decisions.D3.threshold') AS outcome
        FROM current, decision ORDER BY leaf
    """, {"fixture": canonical(fixture).decode()}).fetchall()
    assert [row[0] for row in rows] == ["A", "C"]
    frontier = {leaf: {"revision": revision, "digest": digest(dict(leaf=leaf, revision=revision, value=value))}
                for leaf, revision, value, _, _ in rows}
    return {"score": rows[0][3], "outcome": bool(rows[0][4]), "frontier": frontier}


def run(folder):
    fixture = small()
    assert fixture["decisions"]["D3"]["node"] == "join"
    assert fixture["nodes"]["join"] == {"op": "mean", "inputs": ["a", "C"]}
    assert fixture["nodes"]["a"] == {"op": "identity", "inputs": ["A"]}
    store = folder / "peer.json"
    with closing(Engine(folder / "p02.sqlite", fixture)) as engine, closing(sqlite3.connect(":memory:")) as db:
        db.execute("CREATE TABLE received(event TEXT PRIMARY KEY, packet TEXT NOT NULL)")
        previous = peer("evaluate", fixture, store)["outputs"]["D3"]
        assert previous == sql_decision(db, fixture) == engine.outputs()["D3"]
        assert (previous["score"], previous["outcome"]) == (20, False)
        print("initial: C revision 0, score 20, decision false")
        for revision, value, expected_score in [(1, 48, 29), (2, 50, 30)]:
            event = f"C{revision}"
            change = {"leaf": "C", "revision": revision, "value": value}
            packet = engine.correction(event, fixture["leaves"]["C"]["issuer"], [change])
            assert engine.ingest(packet) == "APPLIED"
            verify(packet, engine.registry)
            with db:
                db.execute("INSERT INTO received VALUES (?,?)", (event, canonical(packet).decode()))
            expected = sql_decision(db, fixture)
            assert (expected["score"], expected["outcome"]) == (expected_score, True)
            assert engine.summary(event)["status"] == "PENDING"
            call = dict(event_id=event, decision_id="D3")
            stale = peer("receipt", fixture, store, **call)["envelope"]
            old = verify(stale, engine.registry)
            assert {k: old[k] for k in previous} == previous
            try:
                engine.accept_receipt(stale, replay=True)
            except Rejected as exc:
                assert str(exc) == "stale or incomplete causal frontier"
            else:
                raise AssertionError("the stale receipt was accepted")
            assert engine.summary(event)["status"] == "PENDING"
            assert peer("apply", fixture, store, envelope=packet, registry=engine.registry)["status"] == "APPLIED"
            fresh = peer("receipt", fixture, store, **call)["envelope"]
            result = verify(fresh, engine.registry)
            assert {k: result[k] for k in expected} == expected
            assert engine.accept_receipt(fresh, replay=True) == "LOCAL_REPLAY"
            assert engine.outputs()["D3"] == expected and engine.summary(event)["local_replay_verified"] == 1
            same = old["outcome"] == result["outcome"]
            assert same == (revision == 2)
            print(f"C revision {revision}: score {result['score']}, decision true, "
                  f"stale receipt rejected, same Boolean {str(same).lower()}")
            previous = expected


if __name__ == "__main__":
    if not __debug__:
        raise RuntimeError("Run with assertions enabled.")
    with tempfile.TemporaryDirectory(prefix="p02-example-", dir=PROJECT / ".local") as directory:
        run(Path(directory))
