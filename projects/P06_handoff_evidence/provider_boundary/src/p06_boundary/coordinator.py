"""Strong classical kernel shared by both interfaces; trusted single authority."""
import json
from pathlib import Path
import time
from .common import Refusal, canonical, connect, digest, event, events_schema, sign, verify
from .contract import normalize_manifest


def initialize(path, key_file, manifest, delegation_seconds=120):
    manifest = normalize_manifest(manifest)
    db = connect(path)
    db.executescript("""
    CREATE TABLE missions(mission TEXT PRIMARY KEY, manifest TEXT NOT NULL, contract_hash TEXT NOT NULL, owner TEXT, epoch INTEGER NOT NULL DEFAULT 0, lease_until REAL NOT NULL DEFAULT 0, phase TEXT NOT NULL DEFAULT 'IDLE', delegation_until REAL NOT NULL);
    CREATE TABLE obligations(mission TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING', prepared_epoch INTEGER, receipt TEXT, PRIMARY KEY(mission,id));
    CREATE TABLE subjects(subject TEXT PRIMARY KEY, allowed INTEGER NOT NULL);
    """)
    events_schema(db)
    db.execute("INSERT INTO missions(mission,manifest,contract_hash,delegation_until) VALUES(?,?,?,?)",(manifest["mission"],canonical(manifest),digest(manifest),time.time()+delegation_seconds))
    for ob in manifest["obligations"]:
        db.execute("INSERT INTO obligations(mission,id,payload) VALUES(?,?,?)",(manifest["mission"],ob["id"],canonical(ob["payload"])))
    db.executemany("INSERT INTO subjects VALUES(?,1)",[("A",),("B",)])
    event(db,"MISSION_CREATED",mission=manifest["mission"],contract_hash=digest(manifest),required_obligations=len(manifest["obligations"]))
    db.close()


class Coordinator:
    def __init__(self, path, key_file):
        self.path, self.key = path, Path(key_file).read_bytes()

    def snapshot(self, mission):
        db=connect(self.path)
        try:
            row=db.execute("SELECT * FROM missions WHERE mission=?",(mission,)).fetchone()
            if not row: raise Refusal("NO_MISSION")
            result=dict(row)
            result["obligations"]=[dict(r) for r in db.execute("SELECT * FROM obligations WHERE mission=? ORDER BY id",(mission,))]
            return result
        finally: db.close()

    def _subject(self,db,subject):
        row=db.execute("SELECT allowed FROM subjects WHERE subject=?",(subject,)).fetchone()
        if not row or not row["allowed"]: raise Refusal("SUBJECT_UNAUTHORIZED")

    def _row(self,db,mission):
        row=db.execute("SELECT * FROM missions WHERE mission=?",(mission,)).fetchone()
        if not row: raise Refusal("NO_MISSION")
        return row

    def _live(self,row,subject,epoch,phase="ACTIVE"):
        if row["owner"] != subject or row["epoch"] != epoch or row["phase"] != phase:
            raise Refusal("OWNER_CHANGED")
        if time.time() >= row["delegation_until"]: raise Refusal("DELEGATION_EXPIRED")
        if time.time() >= row["lease_until"]: raise Refusal("LEASE_EXPIRED")

    def _grant(self,row,kind,**other):
        claims={"kind":kind,"aud":"p06-provider","mission":row["mission"],"epoch":row["epoch"],"subject":row["owner"],"contract_hash":row["contract_hash"],"nbf":0,"exp":min(row["lease_until"],row["delegation_until"]),**other}
        return sign(claims,self.key)

    def acquire(self,manifest,subject,lease_seconds=30):
        normalized=normalize_manifest(manifest)
        mission=normalized["mission"]
        if not (0 < lease_seconds <= 60): raise Refusal("LEASE_RANGE")
        db=connect(self.path)
        try:
            db.execute("BEGIN IMMEDIATE")
            self._subject(db,subject); row=self._row(db,mission)
            if digest(normalized)!=row["contract_hash"]: raise Refusal("CONTRACT_MISMATCH")
            now=time.time()
            if now>=row["delegation_until"]: raise Refusal("DELEGATION_EXPIRED")
            if row["owner"] is not None and row["lease_until"]>now:
                raise Refusal("LEASE_BUSY")
            epoch=row["epoch"]+1
            db.execute("UPDATE missions SET owner=?,epoch=?,lease_until=?,phase='PREPARING' WHERE mission=?",(subject,epoch,min(now+lease_seconds,row["delegation_until"]),mission))
            row=self._row(db,mission)
            event(db,"RESERVE_EPOCH",mission=mission,subject=subject,epoch=epoch)
            token=self._grant(row,"fence")
            db.execute("COMMIT")
            return {"mission":mission,"epoch":epoch,"grant":token,"subject":subject}
        except Exception:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
        finally:db.close()

    def activate(self,mission,subject,epoch,provider_ack):
        if not isinstance(provider_ack,str):raise Refusal("FENCE_ACK_INVALID")
        claims=verify(provider_ack,self.key,"fence_receipt")
        db=connect(self.path)
        try:
            db.execute("BEGIN IMMEDIATE")
            row=self._row(db,mission); self._subject(db,subject);self._live(row,subject,epoch,"PREPARING")
            if claims.get("mission")!=mission or claims.get("epoch")!=epoch or claims.get("subject")!=subject or claims.get("contract_hash")!=row["contract_hash"] or claims.get("provider")!="local-fixture":
                raise Refusal("FENCE_ACK_MISMATCH")
            db.execute("UPDATE missions SET phase='ACTIVE' WHERE mission=?",(mission,))
            event(db,"ACTIVATE_EPOCH",mission=mission,subject=subject,epoch=epoch)
            db.execute("COMMIT")
        except Exception:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
        finally:db.close()

    def retry_fence(self,mission,subject,epoch):
        db=connect(self.path)
        try:
            row=self._row(db,mission);self._subject(db,subject);self._live(row,subject,epoch,"PREPARING")
            return {"mission":mission,"epoch":epoch,"subject":subject,"grant":self._grant(row,"fence")}
        finally:db.close()

    def release(self,mission,subject,epoch):
        db=connect(self.path)
        try:
            db.execute("BEGIN IMMEDIATE")
            row=self._row(db,mission)
            if row["owner"]!=subject or row["epoch"]!=epoch:raise Refusal("OWNER_CHANGED")
            db.execute("UPDATE missions SET owner=NULL,lease_until=0,phase='IDLE' WHERE mission=?",(mission,))
            event(db,"RELEASE_EPOCH",mission=mission,subject=subject,epoch=epoch)
            db.execute("COMMIT")
        except Exception:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
        finally:db.close()

    def prepare(self,mission,obligation,subject,epoch):
        db=connect(self.path)
        try:
            db.execute("BEGIN IMMEDIATE")
            row=self._row(db,mission);self._subject(db,subject);self._live(row,subject,epoch)
            ob=db.execute("SELECT * FROM obligations WHERE mission=? AND id=?",(mission,obligation)).fetchone()
            if not ob:raise Refusal("NO_OBLIGATION")
            if ob["status"] == "DONE":raise Refusal("ALREADY_DONE")
            if ob["status"] == "UNKNOWN":raise Refusal("UNRESOLVED_OUTCOME")
            payload=json.loads(ob["payload"])
            idem=digest({"mission":mission,"obligation":obligation})
            prior=ob["status"]
            db.execute("UPDATE obligations SET status='INTENT',prepared_epoch=? WHERE mission=? AND id=?",(epoch,mission,obligation))
            action=self._grant(row,"execute",obligation=obligation,idempotency_key=idem,payload_hash=digest(payload))
            lookup=self._grant(row,"lookup",obligation=obligation,idempotency_key=idem)
            event(db,"INTENT",mission=mission,obligation=obligation,epoch=epoch,prior=prior,key=idem)
            db.execute("COMMIT")
            return {"op":"execute","mission":mission,"obligation":obligation,"key":idem,"payload":payload,"grant":action,"lookup_grant":lookup,"prior":prior}
        except Exception:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
        finally:db.close()

    def acknowledge(self,mission,obligation,subject,epoch,receipt):
        try:
            signed=verify(receipt["signature"],self.key,"receipt")
            record=receipt["record"]
            canonical_signed={k:v for k,v in signed.items() if k not in {"nbf","exp"}}
            expected={**record,"aud":"p06-provider"}
            if canonical_signed!=expected:raise Refusal("BAD_RECEIPT")
        except (KeyError,TypeError) as exc:raise Refusal("BAD_RECEIPT") from exc
        db=connect(self.path)
        try:
            db.execute("BEGIN IMMEDIATE")
            row=self._row(db,mission);self._subject(db,subject);self._live(row,subject,epoch)
            ob=db.execute("SELECT * FROM obligations WHERE mission=? AND id=?",(mission,obligation)).fetchone()
            if not ob:raise Refusal("NO_OBLIGATION")
            if record["mission"]!=mission or record["obligation"]!=obligation or record["payload_hash"]!=digest(json.loads(ob["payload"])) or record["idempotency_key"]!=digest({"mission":mission,"obligation":obligation}):
                raise Refusal("RECEIPT_BINDING")
            db.execute("UPDATE obligations SET status='DONE',receipt=? WHERE mission=? AND id=?",(canonical(receipt),mission,obligation))
            event(db,"ACK",mission=mission,obligation=obligation,epoch=epoch,effect_id=record["effect_id"])
            db.execute("COMMIT")
        except Exception:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
        finally:db.close()

    def mark_unknown(self,mission,obligation,subject,epoch):
        db=connect(self.path)
        try:
            db.execute("BEGIN IMMEDIATE")
            row=self._row(db,mission);self._live(row,subject,epoch)
            db.execute("UPDATE obligations SET status='UNKNOWN' WHERE mission=? AND id=? AND status!='DONE'",(mission,obligation))
            event(db,"UNKNOWN",mission=mission,obligation=obligation,epoch=epoch)
            db.execute("COMMIT")
        except Exception:
            if db.in_transaction:db.execute("ROLLBACK")
            raise
        finally:db.close()
