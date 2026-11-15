"""Ed25519 signing, AES-256-GCM encryption at rest, SHA-256 hash chain."""
import base64
import hashlib
import json
import os

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .. import config

KEYDIR = config.DATA / "keys"
KEYDIR.mkdir(parents=True, exist_ok=True)
GENESIS = "0" * 64


def canonical(d: dict) -> bytes:
    return json.dumps(d, sort_keys=True, separators=(",", ":")).encode()


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def unb64(s: str) -> bytes:
    return base64.b64decode(s.encode())


def device_key(astro_id: str) -> Ed25519PrivateKey:
    """Load (or provision) the private key that lives on the wearable."""
    p = KEYDIR / f"{astro_id}.key"
    if p.exists():
        return Ed25519PrivateKey.from_private_bytes(p.read_bytes())
    k = Ed25519PrivateKey.generate()
    p.write_bytes(
        k.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
    )
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return k


def public_b64(priv: Ed25519PrivateKey) -> str:
    return b64(
        priv.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    )


def registry(crew) -> dict:
    """Public-key registry the gateway trusts (provisioned out of band)."""
    return {a: public_b64(device_key(a)) for a in crew}


def sign(priv: Ed25519PrivateKey, payload: dict) -> str:
    return b64(priv.sign(canonical(payload)))


def verify(pub_b64: str, payload: dict, sig_b64: str) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(unb64(pub_b64)).verify(
            unb64(sig_b64), canonical(payload)
        )
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def master_key() -> bytes:
    env = os.environ.get("CIPHERPULSE_MASTER_KEY")
    if env:
        return bytes.fromhex(env)
    p = config.DATA / "master.key"
    if not p.exists():
        p.write_bytes(AESGCM.generate_key(bit_length=256))
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
    return p.read_bytes()


def encrypt(key: bytes, plaintext: bytes, aad: bytes) -> str:
    nonce = os.urandom(12)
    return b64(nonce + AESGCM(key).encrypt(nonce, plaintext, aad))


def decrypt(key: bytes, blob: str, aad: bytes) -> bytes:
    raw = unb64(blob)
    return AESGCM(key).decrypt(raw[:12], raw[12:], aad)


def chain_hash(prev_hash: str, enc_payload: str, meta: str) -> str:
    return hashlib.sha256(f"{prev_hash}|{meta}|{enc_payload}".encode()).hexdigest()
