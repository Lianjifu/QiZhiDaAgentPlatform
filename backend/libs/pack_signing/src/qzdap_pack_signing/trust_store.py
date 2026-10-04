"""File-based trust-store scanner — shared by every pack vetter's
``LocalTrustStore*Vetter``.

A trust store is a directory containing ``<key_id>.pub.pem`` files.
``key_id`` is the SHA-256 of the PEM, hex-encoded (see
:func:`qzdap_pack_signing.canonical.public_key_id`); the filename stem
MUST match the key content or the vetter refuses the key (catches
copy/paste errors at boot instead of at signature time).

This helper is pack-type-agnostic: it returns
``dict[key_id, Ed25519PublicKey]`` and never raises pack-specific
exceptions.  The caller passes in the typed ``SignerUntrusted``
exception class so each pack can surface its own error family
(``SkillSignerUntrusted``, ``KnowledgeSignerUntrusted``,
``PlanSignerUntrusted``).
"""

from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from qzdap_pack_signing.canonical import load_public_key_pem, public_key_id


def scan_trust_dir(
    trust_dir: Path,
    *,
    label: str,
    signer_untrusted_exc: type[Exception],
) -> dict[str, Ed25519PublicKey]:
    """Scan ``<trust_dir>/*.pub.pem`` → ``{key_id: pub_key}``.

    Empty / missing directory → ``signer_untrusted_exc``.  Filename
    stem must equal ``public_key_id(key)`` (catches stale
    ``<old_key_id>.pub.pem`` left over after a key rotation).

    Parameters
    ----------
    trust_dir:
        Directory holding ``<key_id>.pub.pem`` files.
    label:
        Human-readable pack label used in error messages (e.g.
        ``"skill"``, ``"knowledge"``, ``"plan"``).
    signer_untrusted_exc:
        Typed exception class to raise on any structural problem
        (missing dir, empty dir, bad PEM, filename mismatch).
    """
    if not trust_dir.is_dir():
        raise signer_untrusted_exc(
            f"{label} trust dir {trust_dir} does not exist or is not a directory"
        )
    keys: dict[str, Ed25519PublicKey] = {}
    for path in sorted(trust_dir.glob("*.pub.pem")):
        pem = path.read_bytes()
        try:
            key = load_public_key_pem(pem)
        except (TypeError, ValueError) as exc:
            raise signer_untrusted_exc(
                f"{label} trust store key {path.name!r} is not a valid Ed25519 PEM"
            ) from exc
        expected_id = public_key_id(key)
        # Filename: <key_id>.pub.pem → stem = "<key_id>.pub" → strip the suffix
        if path.stem.endswith(".pub"):
            stem_id = path.stem[: -len(".pub")]
        else:
            stem_id = path.stem
        if stem_id != expected_id:
            raise signer_untrusted_exc(
                f"{label} trust store key {path.name!r} filename does not match "
                f"key content (expected {expected_id}.pub.pem)"
            )
        keys[expected_id] = key
    if not keys:
        raise signer_untrusted_exc(
            f"{label} trust dir {trust_dir} is empty — refusing to run with "
            f"zero trusted keys"
        )
    return keys


__all__ = ["scan_trust_dir"]
