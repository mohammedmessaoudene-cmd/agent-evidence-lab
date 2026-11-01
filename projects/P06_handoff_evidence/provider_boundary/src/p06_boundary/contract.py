"""Bounded, explicit memory schema conversion. Not general semantic portability."""
import copy
from .common import Refusal, digest


def normalized_memory(mem):
    if not isinstance(mem, dict) or set(mem) != {"schema", "distance", "unit", "subject"}:
        raise Refusal("MEMORY_FIELDS")
    version = mem["schema"]
    if version == "ticket-memory/1" and mem["unit"] == "m":
        scale = 1000
    elif version == "ticket-memory/2" and mem["unit"] == "mm":
        scale = 1
    else:
        raise Refusal("MEMORY_SCHEMA")
    if type(mem["distance"]) is not int or not (0 <= mem["distance"] <= 10**9):
        raise Refusal("MEMORY_VALUE")
    if not isinstance(mem["subject"], str) or not mem["subject"] or len(mem["subject"]) > 256:
        raise Refusal("MEMORY_SUBJECT")
    val = mem["distance"] * scale
    if val > 10**9:
        raise Refusal("MEMORY_OVERFLOW")
    return {"schema":"ticket-memory/2", "distance":val, "unit":"mm", "subject":mem["subject"]}


def normalize_manifest(manifest):
    if not isinstance(manifest, dict) or set(manifest) != {"mission", "obligations", "memory"}:
        raise Refusal("MANIFEST_FIELDS")
    if not isinstance(manifest["mission"], str) or not manifest["mission"] or len(manifest["mission"]) > 100:
        raise Refusal("MISSION_ID")
    memory = normalized_memory(manifest["memory"])
    obs = manifest["obligations"]
    if not isinstance(obs, list) or not obs or len(obs) > 20:
        raise Refusal("OBLIGATIONS")
    result, ids = [], set()
    for ob in obs:
        if not isinstance(ob, dict) or set(ob) != {"id", "kind", "required", "payload"}:
            raise Refusal("OBLIGATION_FIELDS")
        if not isinstance(ob["id"], str) or not ob["id"] or ob["id"] in ids:
            raise Refusal("OBLIGATION_ID")
        ids.add(ob["id"])
        if ob["kind"] != "create_ticket" or ob["required"] is not True:
            raise Refusal("OBLIGATION_TYPE")
        p = ob["payload"]
        if not isinstance(p, dict) or set(p) != {"subject", "distance_mm", "label"}:
            raise Refusal("PAYLOAD_FIELDS")
        if p["subject"] != memory["subject"] or type(p["distance_mm"]) is not int or p["distance_mm"] != memory["distance"]:
            raise Refusal("MEMORY_PAYLOAD_MISMATCH")
        if not isinstance(p["label"], str) or not p["label"]:
            raise Refusal("PAYLOAD_LABEL")
        result.append(copy.deepcopy(ob))
    return {"mission":manifest["mission"], "obligations":sorted(result,key=lambda x:x["id"]), "memory":memory}


def envelope(manifest):
    normalized = normalize_manifest(manifest)
    return {"schema":"p06-envelope/1", "manifest":copy.deepcopy(manifest), "contract_sha256":digest(normalized), "authority":"obtain-from-coordinator", "effect_policy":"reconcile-before-retry"}


def import_envelope(bundle):
    if not isinstance(bundle, dict) or set(bundle) != {"schema", "manifest", "contract_sha256", "authority", "effect_policy"}:
        raise Refusal("ENVELOPE_FIELDS")
    if bundle["schema"] != "p06-envelope/1" or bundle["authority"] != "obtain-from-coordinator" or bundle["effect_policy"] != "reconcile-before-retry":
        raise Refusal("ENVELOPE_SCHEMA")
    normalized = normalize_manifest(bundle["manifest"])
    if digest(normalized) != bundle["contract_sha256"]:
        raise Refusal("ENVELOPE_HASH")
    return normalized


def example_manifest(mission="M1", version=1):
    memory = {"schema":f"ticket-memory/{version}","distance":1200 if version == 1 else 1200000,"unit":"m" if version == 1 else "mm","subject":"synthetic-service"}
    return {"mission":mission,"memory":memory,"obligations":[{"id":name,"kind":"create_ticket","required":True,"payload":{"subject":"synthetic-service","distance_mm":1200000,"label":name}} for name in ["01-reserve", "02-follow-up"]]}
