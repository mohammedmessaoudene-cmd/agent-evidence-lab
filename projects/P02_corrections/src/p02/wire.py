"""Restricted canonical JSON and Ed25519 test identities.

ASCII strings and safe integers only. This is NOT RFC 8785/JCS, COSE, SCITT,
production PKI, or evidence that an enrolled organization is honest.
"""
import hashlib
import json
import re
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

LIMIT = 2**53 - 1


class Rejected(ValueError):
    pass


def integer(value):
    if type(value) is not int or abs(value) > LIMIT:
        raise Rejected("not a safe integer")
    return value


def _validate(obj, depth=0):
    if depth > 40:
        raise Rejected("excessive nesting")
    if obj is None or type(obj) is bool:
        return
    if type(obj) is int:
        integer(obj)
    elif type(obj) is str:
        if not obj.isascii():
            raise Rejected("research wire profile requires ASCII strings")
    elif type(obj) is list:
        for item in obj:
            _validate(item, depth + 1)
    elif type(obj) is dict:
        for key, val in obj.items():
            if type(key) is not str:
                raise Rejected("non-string key")
            _validate(key, depth + 1)
            _validate(val, depth + 1)
    else:
        raise Rejected("floats or unsupported wire type")


def canonical(obj):
    _validate(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def strict_loads(text):
    def pairs(items):
        out = {}
        for key, val in items:
            if key in out:
                raise Rejected("duplicate JSON key")
            out[key] = val
        return out
    out = json.loads(text, object_pairs_hook=pairs,
                     parse_constant=lambda x: (_ for _ in ()).throw(Rejected("nonfinite number")))
    _validate(out)
    return out


def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def test_key(name):
    # PUBLIC, DETERMINISTIC TEST KEYS. NEVER USE TO IDENTIFY REAL ACTORS.
    seed = hashlib.sha256(("P02-INSECURE-TEST-KEY:" + name).encode("ascii")).digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def public_key(name):
    return test_key(name).public_key().public_bytes(serialization.Encoding.Raw,
                                                   serialization.PublicFormat.Raw).hex()


def sign(payload, signer):
    signed = {"payload": payload, "signer": signer}
    return dict(signed, signature=test_key(signer).sign(canonical(signed)).hex())


def verify(envelope, registry):
    if type(envelope) is not dict or set(envelope) != {"payload", "signer", "signature"}:
        raise Rejected("invalid envelope shape")
    _validate(envelope)
    signer = envelope["signer"]
    if type(signer) is not str or signer not in registry:
        raise Rejected("unenrolled signer")
    if type(envelope["signature"]) is not str or not re.fullmatch(r"[0-9a-f]{128}", envelope["signature"]):
        raise Rejected("signature must be 128 lowercase hexadecimal characters")
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(registry[signer])).verify(
            bytes.fromhex(envelope["signature"]), canonical({"payload": envelope["payload"], "signer": signer}))
    except Exception as exc:
        raise Rejected("invalid signature") from exc
    return envelope["payload"]
