"""Generic Ed25519 pack signing primitives + trust-store scanner.

This library is intentionally pack-type-agnostic: it provides the
low-level primitives (``canonical_payload``, ``sign_payload``,
``verify_signature``, ``public_key_id``, PEM helpers) plus a
``scan_trust_dir`` helper that any pack vetter (Skill / Knowledge /
Plan / future Scenario / Workflow) can build on top of.

Pack-specific concerns — the *content* of the canonical payload, the
typed domain exceptions raised on verification failure, the per-pack
``image_digest`` semantics — stay in the pack module (``skill.domain``,
``knowledge.domain``, ``orchestration.domain``).  This split is what
lets three modules share the same Ed25519 plumbing without dragging
in each other's domain types.
"""

from __future__ import annotations

from qzdap_pack_signing.canonical import (
    canonical_payload,
    load_private_key_pem,
    load_public_key_pem,
    payload_digest,
    private_key_to_pem,
    public_key_id,
    public_key_to_pem,
    sign_payload,
    verify_signature,
)
from qzdap_pack_signing.trust_store import scan_trust_dir

__all__ = [
    "canonical_payload",
    "load_private_key_pem",
    "load_public_key_pem",
    "payload_digest",
    "private_key_to_pem",
    "public_key_id",
    "public_key_to_pem",
    "scan_trust_dir",
    "sign_payload",
    "verify_signature",
]
