"""Generic Ed25519 pack signing primitives — pack-type-agnostic.

These helpers were originally in ``modules/skill/domain/signing.py``
but were lifted to a shared library so Knowledge / Plan / future pack
vetters can reuse them without each module re-implementing the
canonical-JSON + Ed25519 dance.

What lives here vs in the pack module:
    * Here (this file): ``canonical_payload``, ``sign_payload``,
      ``verify_signature``, ``public_key_id``, PEM helpers.
    * Pack module (e.g. ``skill/domain/signing.py``): the
      ``SkillPackPayload`` dataclass + the 12 skill-specific canonical
      field list.  The pack module imports the helpers below and
      defines ``canonical_payload(p: SkillPackPayload)`` as a thin
      adapter that calls into this library.

We use Ed25519 because (a) signatures are 64 bytes, (b) verification is
constant-time, and (c) no curve parameters to embed.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
    load_pem_public_key,
)


def canonical_payload(payload: Mapping[str, Any]) -> bytes:
    """Deterministic UTF-8 JSON encoding — same input ⇒ same bytes.

    ``sort_keys=True`` + ``separators=(",", ":")`` keeps the byte
    representation stable across Python versions and platform line
    endings.  Every pack vetter MUST call this helper before signing /
    verifying so SDKs of different versions agree byte-for-byte.
    """
    return json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def payload_digest(payload: Mapping[str, Any]) -> str:
    """``sha256:<hex>`` over :func:`canonical_payload` — useful for logging."""
    return f"sha256:{hashlib.sha256(canonical_payload(payload)).hexdigest()}"


def sign_payload(payload: Mapping[str, Any], *, private_key: Ed25519PrivateKey) -> str:
    """Sign the canonical payload; return the base64-encoded signature."""
    sig = private_key.sign(canonical_payload(payload))
    return base64.b64encode(sig).decode("ascii")


def verify_signature(
    payload: Mapping[str, Any], *, signature_b64: str, public_key: Ed25519PublicKey
) -> None:
    """Raise :class:`InvalidSignature` on any mismatch (bad sig / tampered fields)."""
    try:
        sig = base64.b64decode(signature_b64.encode("ascii"), validate=True)
    except (ValueError, TypeError) as exc:
        raise InvalidSignature("signature is not valid base64") from exc
    public_key.verify(sig, canonical_payload(payload))


# ---------------------------------------------------------------------------
# PEM helpers (PEM is the dev / staging trust-store format; production
# trusts keys via ``qzdap_vault`` refs and pins them in memory.)
# ---------------------------------------------------------------------------


def public_key_to_pem(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)


def load_public_key_pem(pem: bytes) -> Ed25519PublicKey:
    key = load_pem_public_key(pem)
    if not isinstance(key, Ed25519PublicKey):
        raise TypeError(f"expected Ed25519 public key, got {type(key).__name__}")
    return key


def private_key_to_pem(
    key: Ed25519PrivateKey, *, password: bytes | None = None
) -> bytes:
    encryption: BestAvailableEncryption | NoEncryption = (
        BestAvailableEncryption(password) if password else NoEncryption()
    )
    return key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, encryption)


def load_private_key_pem(
    pem: bytes, *, password: bytes | None = None
) -> Ed25519PrivateKey:
    key = load_pem_private_key(pem, password=password)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError(f"expected Ed25519 private key, got {type(key).__name__}")
    return key


def public_key_id(key: Ed25519PublicKey) -> str:
    """SHA-256 of the PEM bytes, hex-encoded — used as ``signer_key_id``."""
    return hashlib.sha256(public_key_to_pem(key)).hexdigest()


__all__ = [
    "canonical_payload",
    "load_private_key_pem",
    "load_public_key_pem",
    "payload_digest",
    "private_key_to_pem",
    "public_key_id",
    "public_key_to_pem",
    "sign_payload",
    "verify_signature",
]
