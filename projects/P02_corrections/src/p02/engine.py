"""Real SQLite durable bounded pipeline with two impact-discovery strategies.

Both arms intentionally share wire, durability, decision code, trust, and costs.
This is a fair component comparison, not a benchmark of Temporal or DataHub.
No network service, LLM, external decision, or external organization is used.
"""
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from .wire import canonical, digest, integer, public_key, sign, verify, Rejected


class Blocked(ValueError):
    pass


class Engine:
    def __init__(self, path, fixture=None, mode="portable_graph"):
        self.path = str(path)
        self.mode = mode
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS leaves(id TEXT PRIMARY KEY,issuer TEXT,revision INTEGER,value INTEGER,digest TEXT);
        CREATE TABLE IF NOT EXISTS versions(leaf TEXT,revision INTEGER,value INTEGER,digest TEXT,PRIMARY KEY(leaf,revision));
        CREATE TABLE IF NOT EXISTS edges(parent TEXT,child TEXT,PRIMARY KEY(parent,child));
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,payload TEXT,digest TEXT,status TEXT);
        CREATE TABLE IF NOT EXISTS obligations(event TEXT,decision TEXT,status TEXT,delivered INTEGER DEFAULT 0,attempts INTEGER DEFAULT 0,receipt TEXT,PRIMARY KEY(event,decision));
        CREATE TABLE IF NOT EXISTS materializations(decision TEXT PRIMARY KEY,score INTEGER,outcome INTEGER,frontier TEXT);
        CREATE TABLE IF NOT EXISTS receipt_log(id TEXT PRIMARY KEY,event TEXT,decision TEXT,envelope TEXT,verification TEXT);
        CREATE TABLE IF NOT EXISTS artifacts(digest TEXT PRIMARY KEY,leaf TEXT,revision INTEGER,uri TEXT);
        CREATE TABLE IF NOT EXISTS conflicts(id INTEGER PRIMARY KEY,issuer TEXT,event TEXT,leaves TEXT,reason TEXT,payload_digest TEXT);
        CREATE TABLE IF NOT EXISTS tainted_leaves(leaf TEXT PRIMARY KEY,reason TEXT);
        """)
        old = self.db.execute("SELECT value FROM meta WHERE key='fixture'").fetchone()
        if old:
            self._fixture = json.loads(old[0])
            if fixture is not None and digest(fixture) != digest(self._fixture):
                raise Rejected("immutable graph snapshot mismatch")
        else:
            if fixture is None:
                raise Rejected("new store requires fixture")
            canonical(fixture)
            self._fixture = json.loads(canonical(fixture))
            self._initialize()
        self._fixture_json = canonical(self._fixture).decode()
        self.graph_digest = digest(self._fixture)
        names = {v["issuer"] for v in self._fixture["leaves"].values()}
        names |= {v["owner"] for v in self._fixture["decisions"].values()}
        self.registry = {name: public_key(name) for name in sorted(names)}

    @property
    def fixture(self):
        """Return a detached snapshot, never the live graph."""
        return json.loads(self._fixture_json)

    def _initialize(self):
        f = self._fixture
        all_ids = list(f["leaves"]) + list(f["nodes"]) + list(f["decisions"])
        if len(all_ids) != len(set(all_ids)):
            raise Rejected("identities overlap")
        with self.db:
            self.db.execute("INSERT INTO meta VALUES('fixture',?)", (canonical(f).decode(),))
            for leaf, info in f["leaves"].items():
                integer(info["value"]); integer(info["revision"])
                if info["revision"] < 0:
                    raise Rejected("negative revision")
                h = digest({"leaf": leaf, "revision": info["revision"], "value": info["value"]})
                self.db.execute("INSERT INTO leaves VALUES(?,?,?,?,?)", (leaf, info["issuer"], info["revision"], info["value"], h))
                self.db.execute("INSERT INTO versions VALUES(?,?,?,?)", (leaf, info["revision"], info["value"], h))
                blob = canonical({"leaf": leaf, "revision": info["revision"], "value": info["value"]})
                self.db.execute("INSERT INTO artifacts VALUES(?,?,?,?)", (hashlib.sha256(blob).hexdigest(), leaf, info["revision"], "fixture://" + leaf))
            for node, info in f["nodes"].items():
                for parent in info["inputs"]:
                    self.db.execute("INSERT OR IGNORE INTO edges VALUES(?,?)", (parent, node))
            for dec, info in f["decisions"].items():
                integer(info["threshold"])
                if info["policy"] != "ge-v1":
                    raise Rejected("unknown decision policy")
                self.db.execute("INSERT INTO edges VALUES(?,?)", (info["node"], dec))
                try:
                    score, frontier = self.evaluate(info["node"])
                    self.db.execute("INSERT INTO materializations VALUES(?,?,?,?)", (dec, score, int(score >= info["threshold"]), canonical(frontier).decode()))
                except Blocked:
                    pass

    def close(self):
        self.db.close()

    def state(self):
        return {r["id"]: {"revision": r["revision"], "value": r["value"], "digest": r["digest"]}
                for r in self.db.execute("SELECT * FROM leaves ORDER BY id")}

    def evaluate(self, node):
        leaves = self.state()
        tainted = {r[0] for r in self.db.execute("SELECT leaf FROM tainted_leaves")}
        cache = {}
        visiting = set()

        def calc(name):
            if name in leaves:
                if name in tainted: raise Blocked("BLOCKED_CONFLICT")
                row = leaves[name]
                return row["value"], {name: {"revision": row["revision"], "digest": row["digest"]}}
            if name in cache:
                return cache[name]
            if name in visiting:
                raise Blocked("BLOCKED_CYCLE")
            if name not in self._fixture["nodes"]:
                raise Blocked("UNKNOWN_MISSING_LINEAGE")
            visiting.add(name)
            spec = self._fixture["nodes"][name]
            if not spec["inputs"]:
                raise Blocked("UNKNOWN_EMPTY_TRANSFORM")
            computed = [calc(x) for x in spec["inputs"]]
            vals = [v for v, _ in computed]
            op = spec["op"]
            if op == "identity" and len(vals) == 1: out = vals[0]
            elif op == "sum": out = sum(vals)
            elif op == "mean": out = sum(vals) // len(vals)
            elif op == "min": out = min(vals)
            elif op == "max": out = max(vals)
            else: raise Blocked("UNKNOWN_OPERATOR")
            integer(out)
            frontier = {}
            for _, refs in computed:
                frontier.update(refs)
            visiting.remove(name)
            cache[name] = out, frontier
            return cache[name]
        return calc(node)

    def impact(self, leaf_ids):
        if not leaf_ids:
            return set()
        if self.mode == "classic_sql":
            # UNION (not UNION ALL) gives finite reachability even with cycles.
            placeholders = ",".join("(?)" for _ in leaf_ids)
            query = f"WITH RECURSIVE reach(id) AS (VALUES {placeholders} UNION SELECT edges.child FROM edges JOIN reach ON edges.parent=reach.id) SELECT id FROM reach"
            reached = {r[0] for r in self.db.execute(query, tuple(sorted(leaf_ids)))}
        elif self.mode == "portable_graph":
            adj = {}
            for parent, child in self.db.execute("SELECT parent,child FROM edges"):
                adj.setdefault(parent, []).append(child)
            reached, todo = set(), list(leaf_ids)
            while todo:
                item = todo.pop()
                if item in reached: continue
                reached.add(item)
                todo.extend(adj.get(item, []))
        else:
            raise Rejected("unknown comparator")
        return reached & self._fixture["decisions"].keys()

    def correction(self, event_id, issuer, changes):
        return sign({"schema": "p02-correction/0.1", "id": event_id, "issuer": issuer,
                     "changes": changes}, issuer)

    def _conflict(self, payload, leaves, reason):
        """Persist authoritative ambiguity; no automatic conflict resolution."""
        self.db.execute("INSERT INTO conflicts(issuer,event,leaves,reason,payload_digest) VALUES(?,?,?,?,?)", (payload["issuer"], payload["id"], canonical(sorted(leaves)).decode(), reason, digest(payload)))
        for leaf in leaves:
            self.db.execute("INSERT OR IGNORE INTO tainted_leaves VALUES(?,?)", (leaf, reason))
        for dec in self.impact(leaves):
            self.db.execute("UPDATE obligations SET status='BLOCKED_CONFLICT' WHERE decision=?", (dec,))
        self.db.commit()
        raise Rejected(reason)

    def ingest(self, envelope):
        p = verify(envelope, self.registry)
        if type(p) is not dict or set(p) != {"schema", "id", "issuer", "changes"} or p["schema"] != "p02-correction/0.1":
            raise Rejected("invalid correction schema")
        if p["issuer"] != envelope["signer"] or type(p["id"]) is not str or not p["id"]:
            raise Rejected("invalid correction identity")
        if type(p["changes"]) is not list or not p["changes"]:
            raise Rejected("empty correction")
        seen = set()
        for change in p["changes"]:
            if type(change) is not dict or set(change) != {"leaf", "revision", "value"}:
                raise Rejected("invalid full-partition replacement")
            leaf, rev = change["leaf"], integer(change["revision"])
            integer(change["value"])
            if type(leaf) is not str or leaf not in self._fixture["leaves"] or self._fixture["leaves"][leaf]["issuer"] != p["issuer"]:
                raise Rejected("issuer not authorized for partition")
            if rev < 0 or leaf in seen: raise Rejected("bad revision or duplicate partition")
            seen.add(leaf)
        h = digest(p)
        # The write lock precedes ALL revision reads and check-then-act logic.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            old = self.db.execute("SELECT digest,payload FROM events WHERE id=?", (p["id"],)).fetchone()
            if old:
                prior = json.loads(old["payload"])
                if prior["issuer"] != p["issuer"]:
                    raise Rejected("cross-issuer event ID collision")
                if old["digest"] != h:
                    self._conflict(p, seen | {c["leaf"] for c in prior["changes"]}, "event ID equivocation")
                self.db.commit()
                return "DUPLICATE"
            updates = []
            for change in p["changes"]:
                leaf, rev, val = change["leaf"], change["revision"], change["value"]
                row = self.db.execute("SELECT * FROM leaves WHERE id=?", (leaf,)).fetchone()
                vh = digest({"leaf": leaf, "revision": rev, "value": val})
                known = self.db.execute("SELECT digest FROM versions WHERE leaf=? AND revision=?", (leaf, rev)).fetchone()
                if known and known[0] != vh:
                    self._conflict(p, {leaf}, "same partition revision has conflicting content")
                updates.append((leaf, rev, val, vh, rev > row["revision"]))
            changed_leaves = {leaf for leaf, _, _, _, advance in updates if advance}
            affected = self.impact(changed_leaves)
            self.db.execute("INSERT INTO events VALUES(?,?,?,?)", (p["id"], canonical(p).decode(), h, "APPLIED" if changed_leaves else "SUPERSEDED"))
            for leaf, rev, val, vh, advance in updates:
                self.db.execute("INSERT OR IGNORE INTO versions VALUES(?,?,?,?)", (leaf, rev, val, vh))
                if advance:
                    self.db.execute("UPDATE leaves SET revision=?,value=?,digest=? WHERE id=?", (rev, val, vh, leaf))
                    self.db.execute("INSERT OR IGNORE INTO artifacts VALUES(?,?,?,?)", (vh, leaf, rev, "fixture://" + leaf))
            for dec in affected:
                self.db.execute("UPDATE obligations SET status='PENDING',receipt=NULL WHERE decision=? AND status!='BLOCKED_CONFLICT'", (dec,))
                self.db.execute("INSERT INTO obligations(event,decision,status) VALUES(?,?,'PENDING')", (p["id"], dec))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        return "APPLIED" if changed_leaves else "SUPERSEDED"

    def make_receipt(self, event_id, decision_id):
        if decision_id not in self._fixture["decisions"]:
            raise Rejected("unknown decision")
        d = self._fixture["decisions"][decision_id]
        score, frontier = self.evaluate(d["node"])
        return sign({"schema": "p02-review/0.1", "event_id": event_id,
                     "decision_id": decision_id, "graph_digest": self.graph_digest,
                     "cutoff": self._fixture["cutoff"], "policy_digest": digest(d),
                     "frontier": frontier, "score": score, "outcome": score >= d["threshold"],
                     "review": "REEXAMINED"}, d["owner"])

    def accept_receipt(self, envelope, replay=False, crash_at=None):
        p = verify(envelope, self.registry)
        required = {"schema", "event_id", "decision_id", "graph_digest", "cutoff", "policy_digest", "frontier", "score", "outcome", "review"}
        if type(p) is not dict or set(p) != required or p["schema"] != "p02-review/0.1" or p["review"] != "REEXAMINED":
            raise Rejected("invalid review schema")
        integer(p["score"])
        if type(p["outcome"]) is not bool: raise Rejected("outcome must be boolean")
        if type(p["frontier"]) is not dict:
            raise Rejected("invalid causal frontier")
        for leaf, ref in p["frontier"].items():
            if type(ref) is not dict or set(ref) != {"revision", "digest"}:
                raise Rejected("invalid frontier entry")
            integer(ref["revision"])
            if ref["revision"] < 0 or type(ref["digest"]) is not str or len(ref["digest"]) != 64:
                raise Rejected("invalid frontier revision/digest")
        d = self._fixture["decisions"].get(p["decision_id"])
        if not d or envelope["signer"] != d["owner"]: raise Rejected("reviewer not authorized for decision")
        if p["graph_digest"] != self.graph_digest or p["cutoff"] != self._fixture["cutoff"] or p["policy_digest"] != digest(d):
            raise Rejected("receipt scope or policy mismatch")
        # Lock before checking frontier and committing: no check-then-act window.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            ob = self.db.execute("SELECT status FROM obligations WHERE event=? AND decision=?", (p["event_id"], p["decision_id"])).fetchone()
            if not ob: raise Rejected("receipt has no registered obligation")
            score, frontier = self.evaluate(d["node"])
            if p["frontier"] != frontier: raise Rejected("stale or incomplete causal frontier")
            if replay and (p["score"] != score or p["outcome"] != (score >= d["threshold"])):
                raise Rejected("independently replayable statement is false")
            if p["outcome"] != (p["score"] >= d["threshold"]):
                raise Rejected("inconsistent decision rule")
            if crash_at == "before_write": os._exit(71)
            self.db.execute("INSERT OR REPLACE INTO materializations VALUES(?,?,?,?)", (p["decision_id"], p["score"], int(p["outcome"]), canonical(frontier).decode()))
            if crash_at == "during_transaction": os._exit(72)
            verification = "LOCAL_REPLAY" if replay else "ATTESTATION_ONLY"
            rid = digest(envelope)
            # Evidence is monotone for this exact signed receipt. A later local
            # replay upgrades its earlier attestation, while a weaker retry of
            # the identical bytes cannot erase an already recorded replay.
            prior = self.db.execute("SELECT verification FROM receipt_log WHERE id=?", (rid,)).fetchone()
            if prior and prior[0] == "LOCAL_REPLAY":
                verification = "LOCAL_REPLAY"
            self.db.execute("INSERT INTO receipt_log VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET verification=excluded.verification", (rid, p["event_id"], p["decision_id"], canonical(envelope).decode(), verification))
            self.db.execute("UPDATE obligations SET status=?,receipt=?,delivered=1 WHERE event=? AND decision=?", (verification, rid, p["event_id"], p["decision_id"]))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        if crash_at == "after_commit": os._exit(73)
        return verification

    def process_one(self, owner=None, crash_at=None):
        rows = self.db.execute("SELECT event,decision FROM obligations WHERE status='PENDING' ORDER BY event,decision").fetchall()
        for event, dec in rows:
            if owner and self._fixture["decisions"][dec]["owner"] != owner: continue
            with self.db:
                self.db.execute("UPDATE obligations SET delivered=1,attempts=attempts+1 WHERE event=? AND decision=?", (event, dec))
            try:
                receipt = self.make_receipt(event, dec)
                self.accept_receipt(receipt, replay=True, crash_at=crash_at)
            except Blocked as exc:
                with self.db:
                    self.db.execute("UPDATE obligations SET status=? WHERE event=? AND decision=?", (str(exc), event, dec))
            return True
        return False

    def drain(self, owner=None):
        count = 0
        while self.process_one(owner=owner): count += 1
        return count

    def summary(self, event_id):
        event = self.db.execute("SELECT status FROM events WHERE id=?", (event_id,)).fetchone()
        if not event: raise Rejected("unknown correction")
        rows = list(self.db.execute("SELECT * FROM obligations WHERE event=?", (event_id,)))
        counts = {}
        for row in rows: counts[row["status"]] = counts.get(row["status"], 0) + 1
        if not self._fixture.get("graph_complete", False): status = "UNKNOWN_GRAPH_COVERAGE"
        elif any(k.startswith("UNKNOWN") or k.startswith("BLOCKED") for k in counts): status = "BLOCKED"
        elif counts.get("PENDING", 0): status = "PENDING"
        elif event[0] == "SUPERSEDED": status = "SUPERSEDED_NO_ROLLBACK"
        elif not rows: status = "NO_REGISTERED_IMPACT"
        elif counts.get("ATTESTATION_ONLY", 0): status = "COMPLETE_REGISTERED_ATTESTATIONS"
        else: status = "COMPLETE_REGISTERED_LOCAL_REPLAY"
        done = counts.get("LOCAL_REPLAY", 0) + counts.get("ATTESTATION_ONLY", 0)
        return {"event_id": event_id, "published": True, "scope": "REGISTERED_SNAPSHOT_ONLY",
                "graph_digest": self.graph_digest, "cutoff": self._fixture["cutoff"], "status": status,
                "registered_obligations": len(rows), "delivered": sum(r["delivered"] for r in rows),
                "review_attestations": done, "local_replay_verified": counts.get("LOCAL_REPLAY", 0),
                "coverage_registered": done / len(rows) if rows else None,
                "global_consumer_coverage": "UNKNOWN", "semantic_truth_of_external_review": "UNKNOWN",
                "states": counts, "attempts": sum(r["attempts"] for r in rows)}

    def reimport(self, blob, new_uri):
        # URI is deliberately ignored for content identity; transformed copies
        # cannot be identified without a trusted provenance mapping.
        h = hashlib.sha256(blob).hexdigest()
        a = self.db.execute("SELECT * FROM artifacts WHERE digest=?", (h,)).fetchone()
        if not a: return {"status": "UNKNOWN_UNTRACKED_CONTENT", "uri": new_uri}
        latest = self.db.execute("SELECT revision FROM leaves WHERE id=?", (a["leaf"],)).fetchone()[0]
        return {"status": "QUARANTINE_STALE" if a["revision"] < latest else "CURRENT_REGISTERED_CONTENT",
                "leaf": a["leaf"], "revision": a["revision"], "latest": latest, "uri": new_uri}

    def outputs(self):
        return {r["decision"]: {"score": r["score"], "outcome": bool(r["outcome"]), "frontier": json.loads(r["frontier"])}
                for r in self.db.execute("SELECT * FROM materializations ORDER BY decision")}

    def storage(self):
        payload = self.db.execute("SELECT COALESCE(SUM(length(envelope)),0) FROM receipt_log").fetchone()[0]
        payload += self.db.execute("SELECT COALESCE(SUM(length(payload)),0) FROM events").fetchone()[0]
        return {"stored_payload_bytes": payload, "database_bytes_including_wal": sum(Path(self.path + ext).stat().st_size for ext in ["", "-wal", "-shm"] if Path(self.path + ext).exists()),
                "receipt_count": self.db.execute("SELECT COUNT(*) FROM receipt_log").fetchone()[0]}
