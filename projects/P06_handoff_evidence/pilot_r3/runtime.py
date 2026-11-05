"""Trusted local fixture, not an agent runtime or a production protocol."""
import copy
import hashlib
import json
import sqlite3
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def write_json(path, value):
    Path(path).write_text(canonical(value) + "\n", encoding="utf-8")


def event(db, kind, **fields):
    return db.execute("INSERT INTO events(kind,data) VALUES(?,?)", (kind, canonical(fields))).lastrowid


def encode_view(view, representation):
    if representation == "structured":
        return canonical(view)
    if representation == "narrative":
        # Generated lossless labeled facts, not an LLM-written summary.
        return "Current observable facts.\n" + "\n".join(k + "=" + canonical(v) for k, v in view.items())
    raise ValueError("representation")


def decode_view(text, representation):
    if representation == "structured":
        return json.loads(text)
    if representation == "narrative":
        lines = text.splitlines()
        if not lines or lines[0] != "Current observable facts.":
            raise ValueError("HANDOFF_HEADER")
        decoded = {}
        for line in lines[1:]:
            key, separator, value = line.partition("=")
            if not separator or key in decoded:
                raise ValueError("HANDOFF_FIELD")
            decoded[key] = json.loads(value)
        return decoded
    raise ValueError("representation")


class Provider:
    """Real SQLite commits; single trusted process. No remote/network effects."""
    def __init__(self, path, profile, fault, defect=None):
        if profile not in ("recoverable", "opaque"):
            raise ValueError("profile")
        if fault not in ("normal", "pre_dispatch_loss", "post_commit_loss"):
            raise ValueError("fault")
        self.db = sqlite3.connect(path)
        self.db.executescript("""
        CREATE TABLE effects(id TEXT PRIMARY KEY, obligation TEXT, operation TEXT, epoch INTEGER);
        CREATE TABLE events(seq INTEGER PRIMARY KEY, kind TEXT, data TEXT);
        CREATE TABLE authority(epoch INTEGER);
        INSERT INTO authority VALUES(0);
        """)
        self.profile, self.fault, self.defect = profile, fault, defect
        self.fault_used = False
        self.db.commit()

    def fence(self, epoch):
        with self.db:
            old = self.db.execute("SELECT epoch FROM authority").fetchone()[0]
            if epoch <= old:
                raise ValueError("nonmonotone epoch")
            self.db.execute("UPDATE authority SET epoch=?", (epoch,))
            event(self.db, "AUTHORITY", epoch=epoch)

    def execute(self, obligation, operation, epoch):
        response = self._execute(obligation, operation, epoch)
        with self.db:
            event(self.db, "EXECUTE_RESPONSE", obligation=obligation, operation=operation,
                  epoch=epoch, response=response)
        return response

    def _execute(self, obligation, operation, epoch):
        with self.db:
            current = self.db.execute("SELECT epoch FROM authority").fetchone()[0]
            if epoch != current and self.defect != "skip_fence":
                event(self.db, "ADMISSION_REJECTED", epoch=epoch, obligation=obligation)
                return {"kind": "REJECTED", "reason": "FENCED"}
            fault = self.fault if obligation == "primary" and not self.fault_used else "normal"
            if fault != "normal":
                self.fault_used = True
            if fault == "pre_dispatch_loss":
                # Hidden to the controller: indistinguishable timeout, no admission/effect.
                event(self.db, "NOT_DISPATCHED", obligation=obligation, operation=operation)
                return {"kind": "UNKNOWN", "reason": "NO_CONFIRMATION"}
            event(self.db, "ADMISSION_ACCEPTED", obligation=obligation, operation=operation, epoch=epoch)
            prior = self.db.execute("SELECT id,obligation FROM effects WHERE operation=?", (operation,)).fetchone()
            if self.profile == "recoverable" and prior:
                if prior[1] != obligation:
                    return {"kind": "REJECTED", "reason": "BINDING_CONFLICT"}
                receipt = {"effect_id": prior[0], "obligation": obligation, "operation": operation}
            elif self.defect == "ack_without_effect":
                receipt = {"effect_id": "no-such-effect", "obligation": obligation, "operation": operation}
            else:
                ordinal = self.db.execute("SELECT COUNT(*) FROM effects WHERE obligation=?", (obligation,)).fetchone()[0] + 1
                eid = obligation + ":" + str(ordinal)
                self.db.execute("INSERT INTO effects(id,obligation,operation,epoch) VALUES(?,?,?,?)", (eid, obligation, operation, epoch))
                event(self.db, "EFFECT_COMMIT", effect_id=eid, obligation=obligation, operation=operation, epoch=epoch)
                receipt = {"effect_id": eid, "obligation": obligation, "operation": operation}
        if fault == "post_commit_loss":
            return {"kind": "UNKNOWN", "reason": "NO_CONFIRMATION"}
        return {"kind": "RECEIPT", "receipt": receipt}

    def lookup(self, operation):
        if self.profile != "recoverable":
            response = {"kind": "UNSUPPORTED"}
        else:
            row = self.db.execute("SELECT id,obligation FROM effects WHERE operation=?", (operation,)).fetchone()
            response = ({"kind": "ABSENT"} if not row else
                        {"kind": "RECEIPT", "receipt": {"effect_id": row[0], "obligation": row[1], "operation": operation}})
        with self.db:
            event(self.db, "LOOKUP_RESPONSE", operation=operation, response=response)
        return response

    def close(self):
        self.db.close()


class Episode:
    """Controller visible facts are a projection, never the provider database.

    Host code is trusted. This boundary is NOT an OS sandbox for arbitrary code.
    Only action objects are admitted; no external code/model is executed here.
    """
    def __init__(self, root, profile="opaque", fault="post_commit_loss", depth=1, arm="C0", defect=None):
        if type(depth) is not int or depth not in (1, 3) or arm not in ("C0", "L1", "L2", "L3"):
            raise ValueError("episode configuration")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=False)
        self.arm, self.profile, self.epoch = arm, profile, 1
        self.provider = Provider(self.root / "provider.sqlite", profile, fault, defect)
        self.provider.fence(1)
        self.obligations = ["primary", "independent"]
        self.state = {o: {"status": "PENDING", "operation": "op:" + o, "attempted": False, "receipt": None} for o in self.obligations}
        self.receiver_state = copy.deepcopy(self.state)
        self.trace, self.handoffs = [], 0
        self.config = {"schema": 1, "profile": profile, "fault": fault, "depth": depth, "arm": arm, "defect": defect,
                       "mandatory": self.obligations, "execution_kind": "DETERMINISTIC_FIXTURE", "llm_calls": 0, "max_actions": 16}
        write_json(self.root / "config.json", self.config)

    def view(self):
        return {"schema": 1, "epoch": self.epoch, "capabilities": {"fencing": True, "lookup": self.profile == "recoverable", "idempotency": self.profile == "recoverable"},
                "obligations": copy.deepcopy(self.receiver_state), "remaining_actions": 16 - len(self.trace)}

    def render_view(self, representation):
        return encode_view(self.view(), representation)

    def sync_obligation(self, ob):
        # The canonical mission ledger retains tasks omitted by a handoff.
        # Separate deep copies prevent later receiver mutation from changing it.
        self.state[ob] = copy.deepcopy(self.receiver_state[ob])

    def act(self, action):
        if len(self.trace) >= 16:
            raise ValueError("ACTION_BUDGET_EXCEEDED")
        if not isinstance(action, dict) or set(action) - {"kind", "obligation", "status", "obligations", "epoch"}:
            raise ValueError("ACTION_SHAPE")
        kind = action.get("kind")
        if kind not in {"execute", "lookup", "settle", "claim", "handoff", "abstain"}:
            raise ValueError("ACTION_KIND")
        before = self.view()
        outcome = {"kind": "RECORDED"}
        if kind in {"execute", "lookup", "settle", "claim"}:
            ob = action.get("obligation")
            if ob not in self.receiver_state:
                raise ValueError("UNKNOWN_OBLIGATION")
            state = self.receiver_state[ob]
        if kind == "execute":
            epoch = action.get("epoch", self.epoch)
            if type(epoch) is not int:
                raise ValueError("EPOCH_TYPE")
            if self.arm == "L3" and state["attempted"] and self.profile == "opaque":
                outcome = {"kind": "GATE_REJECTED", "reason": "OPAQUE_RETRY"}
            else:
                state["attempted"] = True  # durable intent represented in controller trace
                state["status"] = "UNKNOWN"
                self.sync_obligation(ob)
                # Persist pre-dispatch facts before calling provider.
                write_json(self.root / "intent.json", {"epoch": self.epoch, "obligations": self.state})
                outcome = self.provider.execute(ob, state["operation"], epoch)
                if outcome["kind"] == "RECEIPT":
                    state["receipt"] = outcome["receipt"]
                self.sync_obligation(ob)
        elif kind == "lookup":
            outcome = self.provider.lookup(state["operation"])
            if outcome["kind"] == "RECEIPT":
                state["receipt"] = outcome["receipt"]
                self.sync_obligation(ob)
        elif kind in {"settle", "claim"}:
            status = action.get("status")
            if status not in {"DONE", "UNKNOWN", "PENDING"}:
                raise ValueError("STATUS")
            if kind == "settle":
                if self.arm == "L3" and status == "DONE" and state["receipt"] is None:
                    outcome = {"kind": "GATE_REJECTED", "reason": "NO_OBSERVED_RECEIPT"}
                else:
                    state["status"] = status
                    self.sync_obligation(ob)
        elif kind == "handoff":
            obs = action.get("obligations")
            if not isinstance(obs, list) or any(type(o) is not str for o in obs) or len(obs) != len(set(obs)) or not set(obs).issubset(self.receiver_state):
                raise ValueError("HANDOFF_SHAPE")
            if self.handoffs >= self.config["depth"]:
                raise ValueError("HANDOFF_BUDGET_EXCEEDED")
            self.handoffs += 1
            self.epoch += 1
            self.provider.fence(self.epoch)
            payload = self.view()
            payload["obligations"] = {o: copy.deepcopy(self.receiver_state[o]) for o in obs}
            payload["remaining_actions"] -= 1
            representation = "narrative" if self.arm == "L1" else "structured"
            serialized = encode_view(payload, representation)
            # Consume the actual transported text. No canonical state fallback.
            received = decode_view(serialized, representation)
            self.receiver_state = copy.deepcopy(received["obligations"])
            artifact = "handoff-" + str(self.handoffs) + ".json"
            write_json(self.root / artifact, {"representation": representation, "text": serialized,
                                            "parsed_payload": received})
            outcome = {"kind": "HANDOFF", "obligations": copy.deepcopy(obs), "epoch": self.epoch,
                       "artifact": artifact}
        row = {"seq": len(self.trace) + 1, "action": copy.deepcopy(action), "before": before, "outcome": copy.deepcopy(outcome), "after": self.view()}
        row["after"]["remaining_actions"] -= 1
        self.trace.append(row)
        write_json(self.root / "trace.json", self.trace)
        return copy.deepcopy(outcome)

    def finish(self):
        write_json(self.root / "final.json", {"view": self.view(), "ledger": self.state})
        write_json(self.root / "trace.json", self.trace)
        self.provider.close()
        files = [p for p in self.root.iterdir() if p.is_file()]
        write_json(self.root / "manifest.json", {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files})


def classical(ep):
    """Uses only the same view and tool outcomes allowed in every arm."""
    ep.act({"kind": "execute", "obligation": "primary"})
    for _ in range(ep.config["depth"]):
        ep.act({"kind": "handoff", "obligations": list(ep.view()["obligations"])})
    classical_resume(ep)


def classical_resume(ep):
    """Continue using only receiver-visible tasks and authorized tool outcomes."""
    for ob in list(ep.view()["obligations"]):
        state = ep.view()["obligations"][ob]
        if state["receipt"] is None:
            if not state["attempted"]:
                ep.act({"kind": "execute", "obligation": ob})
            elif ep.view()["capabilities"]["lookup"]:
                result = ep.act({"kind": "lookup", "obligation": ob})
                if result["kind"] == "ABSENT":
                    ep.act({"kind": "execute", "obligation": ob})
        status = "DONE" if ep.view()["obligations"][ob]["receipt"] else "UNKNOWN"
        ep.act({"kind": "settle", "obligation": ob, "status": status})


def run_episode(root, **kwargs):
    ep = Episode(root, **kwargs)
    try:
        classical(ep)
    finally:
        ep.finish()
