"""Process-separated provider fixture; every RPC executes in a new OS process.

It has its own durable DB and signed receipt. Fencing/expiry/idempotency are
checked in the transaction that inserts a real local effect row. No remote
business effect, production identity or independent organization is implied.
"""
import json
import os
from pathlib import Path
import sys
import time
from .common import Refusal, canonical, connect, digest, event, events_schema, sign, verify, strict_json_loads


def initialize(path, features=None):
    cfg = {"fencing":True,"idempotency":True,"lookup":True,"expiry":True,"fixture_enforcement":"atomic"}
    cfg.update(features or {})
    db = connect(path)
    db.executescript("""
      CREATE TABLE config(key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE fences(mission TEXT PRIMARY KEY, epoch INTEGER NOT NULL, subject TEXT NOT NULL, contract_hash TEXT NOT NULL);
      CREATE TABLE effects(id INTEGER PRIMARY KEY AUTOINCREMENT, mission TEXT NOT NULL, obligation TEXT NOT NULL, idempotency_key TEXT NOT NULL, payload_hash TEXT NOT NULL, payload TEXT NOT NULL, epoch INTEGER NOT NULL, subject TEXT NOT NULL, created REAL NOT NULL, receipt TEXT NOT NULL);
    """)
    events_schema(db)
    for key,value in cfg.items():
        db.execute("INSERT INTO config VALUES(?,?)",(key,canonical(value)))
    event(db,"PROVIDER_INITIALIZED",features=cfg)
    db.close()


def dispatch(db, request, key):
    cfg = {r["key"]:json.loads(r["value"]) for r in db.execute("SELECT * FROM config")}
    op = request.get("op")
    if op == "capabilities":
        # The faulted fixtures claim the same public powers as the reliable
        # provider. Their internal test mode is not a new client capability.
        return {"ok":True,"features":{k:cfg[k] for k in ("fencing","idempotency","lookup","expiry")}}
    if op not in {"fence", "execute", "lookup"}:
        raise Refusal("UNKNOWN_OPERATION")
    claims = verify(request.get("grant", ""), key, op, check_expiry=cfg["expiry"])
    if request.get("mission") != claims.get("mission"):
        raise Refusal("SCOPE_MISMATCH")
    mission = claims["mission"]
    if op == "fence":
        if not cfg["fencing"]:
            raise Refusal("FENCING_UNSUPPORTED")
        old = db.execute("SELECT * FROM fences WHERE mission=?",(mission,)).fetchone()
        if old and (claims["epoch"] < old["epoch"] or (claims["epoch"] == old["epoch"] and (claims["subject"] != old["subject"] or claims["contract_hash"] != old["contract_hash"]))):
            raise Refusal("STALE_FENCE")
        db.execute("INSERT INTO fences VALUES(?,?,?,?) ON CONFLICT(mission) DO UPDATE SET epoch=excluded.epoch,subject=excluded.subject,contract_hash=excluded.contract_hash",(mission,claims["epoch"],claims["subject"],claims["contract_hash"]))
        event(db,"FENCE_COMMIT",mission=mission,epoch=claims["epoch"],subject=claims["subject"])
        # Return only after COMMIT in main; replaying an old ACK cannot activate
        # a different mission/epoch/subject/contract, and expires with the lease.
        ack={"kind":"fence_receipt","aud":"p06-provider","mission":mission,"epoch":claims["epoch"],"subject":claims["subject"],"contract_hash":claims["contract_hash"],"nbf":0,"exp":claims["exp"],"provider":"local-fixture"}
        return {"ok":True,"epoch":claims["epoch"],"fence_ack":sign(ack,key)}
    row = db.execute("SELECT * FROM fences WHERE mission=?",(mission,)).fetchone()
    if cfg["fencing"] and cfg["fixture_enforcement"] != "skip_fence" and (not row or row["epoch"] != claims["epoch"] or row["subject"] != claims["subject"] or row["contract_hash"] != claims["contract_hash"]):
        raise Refusal("FENCED")
    if op == "lookup":
        if not cfg["lookup"]:
            raise Refusal("LOOKUP_UNSUPPORTED")
        if request.get("key") != claims.get("idempotency_key"):
            raise Refusal("KEY_MISMATCH")
        rows = db.execute("SELECT * FROM effects WHERE mission=? AND idempotency_key=? ORDER BY id",(mission,request["key"])).fetchall()
        if len(rows)>1:
            raise Refusal("DUPLICATE_PROVIDER_EFFECTS")
        event(db,"LOOKUP",mission=mission,key=request["key"],found=bool(rows))
        return {"ok":True,"found":bool(rows),"receipt":json.loads(rows[0]["receipt"]) if rows else None}
    payload = request.get("payload")
    payload_hash = digest(payload)
    if claims.get("payload_hash") != payload_hash or claims.get("idempotency_key") != request.get("key") or claims.get("obligation") != request.get("obligation"):
        raise Refusal("PAYLOAD_BINDING")
    if request.get("fixture_pause_after_validation"):
        gate=request["fixture_pause_after_validation"]
        event(db,"PRECHECK_OK",mission=mission,epoch=claims["epoch"],subject=claims["subject"],fixture_enforcement=cfg["fixture_enforcement"])
        if cfg["fixture_enforcement"] == "split_check":
            # Deliberately incorrect provider: release the serializing
            # transaction after checking, and fail to recheck at the effect.
            db.execute("COMMIT")
        ready=Path(gate["ready"])
        temporary=ready.with_name(ready.name+f".{os.getpid()}.tmp")
        temporary.write_text(canonical({"pid":os.getpid(),"checked_at":time.time(),"epoch":claims["epoch"]})+"\n",encoding="utf-8")
        os.replace(temporary,ready)
        until=time.monotonic()+15
        while not Path(gate["resume"]).exists():
            if time.monotonic()>=until:raise Refusal("FIXTURE_GATE_TIMEOUT")
            time.sleep(.005)
        if cfg["fixture_enforcement"] == "split_check":
            db.execute("BEGIN IMMEDIATE")
    rows = db.execute("SELECT * FROM effects WHERE mission=? AND idempotency_key=? ORDER BY id",(mission,request["key"])).fetchall()
    if rows and cfg["idempotency"]:
        if rows[0]["payload_hash"] != payload_hash:
            raise Refusal("IDEMPOTENCY_CONFLICT")
        event(db,"IDEMPOTENT_REPLAY",mission=mission,key=request["key"])
        return {"ok":True,"replayed":True,"receipt":json.loads(rows[0]["receipt"])}
    effect_id = db.execute("INSERT INTO effects(mission,obligation,idempotency_key,payload_hash,payload,epoch,subject,created,receipt) VALUES(?,?,?,?,?,?,?,?,?)",(mission,request["obligation"],request["key"],payload_hash,canonical(payload),claims["epoch"],claims["subject"],time.time(),"{}")).lastrowid
    rec = {"kind":"receipt","aud":"p06-coordinator","mission":mission,"obligation":request["obligation"],"idempotency_key":request["key"],"payload_hash":payload_hash,"effect_id":effect_id,"epoch":claims["epoch"],"provider":"local-fixture"}
    receipt = {"record":rec,"signature":sign({**rec,"kind":"receipt","aud":"p06-provider","nbf":0,"exp":10**12},key)}
    db.execute("UPDATE effects SET receipt=? WHERE id=?",(canonical(receipt),effect_id))
    event(db,"EFFECT_COMMIT",mission=mission,obligation=request["obligation"],key=request["key"],epoch=claims["epoch"],subject=claims["subject"],effect_id=effect_id,payload_hash=payload_hash)
    return {"ok":True,"replayed":False,"receipt":receipt}


def main():
    db = connect(sys.argv[1]); key = Path(sys.argv[2]).read_bytes()
    request={}
    try:
        request = strict_json_loads(sys.stdin.buffer.read())
        if not isinstance(request,dict):raise Refusal("REQUEST_OBJECT_REQUIRED")
        event(db,"RPC_RECEIVED",operation=request.get("op"),mission=request.get("mission"))
        db.execute("BEGIN IMMEDIATE")
        reply = dispatch(db,request,key)
        db.execute("COMMIT")
    except Refusal as exc:
        if db.in_transaction: db.execute("ROLLBACK")
        event(db,"REJECT",operation=request.get("op"),code=exc.code,mission=request.get("mission"))
        reply = {"ok":False,"error":exc.code,"detail":exc.detail}
    finally:
        db.close()
    if request.get("fixture_exit_after_commit") and reply.get("ok"):
        os._exit(73)
    sys.stdout.buffer.write((canonical(reply)+"\n").encode("utf-8"))
    sys.stdout.buffer.flush()


if __name__ == "__main__": main()
