"""Canonical bytes, fixture grants, durable SQLite events and local RPC."""
import base64
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time


class Refusal(Exception):
    def __init__(self, code, detail=""):
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def strict_json_loads(value):
    def object_pairs(pairs):
        obj={}
        for key,item in pairs:
            if key in obj:raise Refusal("JSON_DUPLICATE_MEMBER",key)
            obj[key]=item
        return obj
    def invalid_constant(value):raise Refusal("JSON_NONFINITE",value)
    try:
        obj=json.loads(value,object_pairs_hook=object_pairs,parse_constant=invalid_constant)
        def valid_unicode(v):
            if isinstance(v,str):v.encode("utf-8")
            elif isinstance(v,float) and not math.isfinite(v):raise Refusal("JSON_NONFINITE","overflowing number")
            elif isinstance(v,dict):
                for k,item in v.items():valid_unicode(k);valid_unicode(item)
            elif isinstance(v,list):
                for item in v:valid_unicode(item)
        valid_unicode(obj)
        return obj
    except Refusal:raise
    except UnicodeError as exc:raise Refusal("JSON_UNICODE",str(exc)) from exc
    except (ValueError,TypeError) as exc:raise Refusal("JSON_INVALID",str(exc)) from exc


def connect(path):
    db = sqlite3.connect(str(path), timeout=20, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def events_schema(db):
    db.execute("CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, wall_ns INTEGER, pid INTEGER, event TEXT, detail TEXT)")


def event(db, name, **detail):
    db.execute("INSERT INTO events(wall_ns,pid,event,detail) VALUES(?,?,?,?)", (time.time_ns(), os.getpid(), name, canonical(detail)))


def encode64(data):
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def decode64(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def sign(claims, key):
    body = encode64(canonical(claims).encode())
    return body + "." + encode64(hmac.new(key, body.encode(), hashlib.sha256).digest())


def verify(token, key, kind, *, check_expiry=True):
    try:
        if not isinstance(token,str):raise ValueError("token type")
        body, sig = token.split(".")
        expected = hmac.new(key, body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(decode64(sig), expected):
            raise ValueError("signature")
        claims = strict_json_loads(decode64(body))
        if claims["kind"] != kind or claims["aud"] != "p06-provider":
            raise ValueError("kind/audience")
        if check_expiry and (time.time() < claims["nbf"] or time.time() >= claims["exp"]):
            raise Refusal("GRANT_EXPIRED")
        return claims
    except Refusal:
        raise
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise Refusal("BAD_GRANT", str(exc)) from exc


def rpc(provider_db, key_file, request, *, partition=False, lose_ack=False):
    started=time.time_ns(); outcome="UNEXPECTED_ERROR"; launched=False
    try:
        if partition:
            raise Refusal("TRANSPORT_UNAVAILABLE", "injected before subprocess dispatch")
        req = dict(request)
        if lose_ack:
            req["fixture_exit_after_commit"] = True
        launched=True
        result = subprocess.run([sys.executable, "-m", "p06_boundary.provider", str(provider_db), str(key_file)], input=canonical(req), text=True, capture_output=True, timeout=20)
        if result.returncode != 0:
            raise Refusal("ACK_LOST", f"provider exit={result.returncode}; stderr={result.stderr[-500:]}")
        try:
            reply = json.loads(result.stdout)
        except ValueError as exc:
            raise Refusal("ACK_LOST", "invalid or missing stdout") from exc
        if not reply.get("ok"):
            raise Refusal(reply.get("error", "PROVIDER_ERROR"), reply.get("detail", ""))
        outcome="OK"
        return reply
    except Refusal as exc:
        outcome=exc.code;raise
    except subprocess.TimeoutExpired as exc:
        outcome="ACK_LOST";raise Refusal("ACK_LOST","provider subprocess timeout; effect may have committed") from exc
    finally:
        entry={"started_ns":started,"finished_ns":time.time_ns(),"caller_pid":os.getpid(),"operation":request.get("op"),"mission":request.get("mission"),"provider_launched":launched,"outcome":outcome}
        # Each caller has its own log: portable, no interprocess file lock.
        with (Path(provider_db).parent/f"rpc_attempts-{os.getpid()}.jsonl").open("a", encoding="utf-8") as f:
            f.write(canonical(entry)+"\n")


def read_json(path):
    return strict_json_loads(Path(path).read_text(encoding="utf-8"))
