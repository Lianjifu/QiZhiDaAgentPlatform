"""Unit tests for :mod:`qzdap_pack_signing.canonical`.

Covers:

* ``canonical_payload`` is byte-stable across key order / repeated runs.
* ``payload_digest`` returns a deterministic ``sha256:<hex>`` prefix.
* ``sign_payload`` + ``verify_signature`` round-trip cleanly.
* Tampered payload / bad signature → ``InvalidSignature``.
* ``public_key_id`` is stable across re-encoding the same key.
* PEM helpers round-trip without leaking the wrong key type.
"""

from __future__ import annotations

import base64

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    load_pem_public_key,
)

from qzdap_pack_signing import (
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


def _priv() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def test_canonical_payload_is_byte_stable() -> None:
    p1 = {"name": "alpha", "version": "1.0.0", "tags": ["a", "b"]}
    p2 = {"tags": ["a", "b"], "version": "1.0.0", "name": "alpha"}
    assert canonical_payload(p1) == canonical_payload(p2)


def test_canonical_payload_uses_compact_separators() -> None:
    payload = {"name": "alpha", "version": "1.0.0"}
    raw = canonical_payload(payload)
    # ``separators=(",", ":")`` ⇒ no spaces; both inside objects and lists.
    assert b" " not in raw
    assert raw == b'{"name":"alpha","version":"1.0.0"}'


def test_canonical_payload_repeated_calls_match() -> None:
    payload = {"a": 1, "b": [1, 2, 3], "c": {"nested": True}}
    first = canonical_payload(payload)
    for _ in range(5):
        assert canonical_payload(payload) == first


def test_payload_digest_format() -> None:
    digest = payload_digest({"name": "alpha"})
    assert digest.startswith("sha256:")
    assert len(digest) == len("sha256:") + 64


def test_sign_and_verify_round_trip() -> None:
    priv = _priv()
    payload = {"name": "alpha", "version": "1.0.0"}
    sig = sign_payload(payload, private_key=priv)
    assert isinstance(sig, str)
    # base64 decodes to 64 bytes (Ed25519 signature length)
    assert len(base64.b64decode(sig.encode("ascii"))) == 64
    # Verification with matching key passes.
    verify_signature(payload, signature_b64=sig, public_key=priv.public_key())


def test_verify_raises_on_tampered_payload() -> None:
    priv = _priv()
    sig = sign_payload({"name": "alpha", "version": "1.0.0"}, private_key=priv)
    with pytest.raises(InvalidSignature):
        verify_signature(
            {"name": "alpha", "version": "1.0.1"},  # tampered
            signature_b64=sig,
            public_key=priv.public_key(),
        )


def test_verify_raises_on_tampered_signature() -> None:
    priv = _priv()
    sig = sign_payload({"name": "alpha"}, private_key=priv)
    # Flip the first base64 char to a different valid char.
    head = sig[0]
    alt = "A" if head != "A" else "B"
    bad_sig = alt + sig[1:]
    with pytest.raises(InvalidSignature):
        verify_signature(
            {"name": "alpha"},
            signature_b64=bad_sig,
            public_key=priv.public_key(),
        )


def test_verify_raises_on_invalid_base64() -> None:
    priv = _priv()
    with pytest.raises(InvalidSignature):
        verify_signature(
            {"name": "alpha"},
            signature_b64="not-base64-!!!",
            public_key=priv.public_key(),
        )


def test_verify_with_wrong_key_raises() -> None:
    priv = _priv()
    sig = sign_payload({"name": "alpha"}, private_key=priv)
    other = Ed25519PrivateKey.generate()
    with pytest.raises(InvalidSignature):
        verify_signature(
            {"name": "alpha"},
            signature_b64=sig,
            public_key=other.public_key(),
        )


def test_public_key_id_is_stable() -> None:
    priv = _priv()
    pub = priv.public_key()
    kid1 = public_key_id(pub)
    kid2 = public_key_id(pub)
    assert kid1 == kid2
    assert len(kid1) == 64
    assert all(c in "0123456789abcdef" for c in kid1)


def test_public_key_id_differs_between_keys() -> None:
    a = Ed25519PrivateKey.generate().public_key()
    b = Ed25519PrivateKey.generate().public_key()
    assert public_key_id(a) != public_key_id(b)


def test_pem_round_trip_public_key() -> None:
    priv = _priv()
    pem = public_key_to_pem(priv.public_key())
    assert pem.startswith(b"-----BEGIN PUBLIC KEY-----")
    loaded = load_public_key_pem(pem)
    assert isinstance(loaded, Ed25519PublicKey)
    assert public_key_id(loaded) == public_key_id(priv.public_key())


def test_pem_round_trip_private_key() -> None:
    priv = _priv()
    pem = private_key_to_pem(priv)
    assert pem.startswith(b"-----BEGIN PRIVATE KEY-----")
    loaded = load_private_key_pem(pem)
    assert isinstance(loaded, Ed25519PrivateKey)
    # Same private key ⇒ same public key ⇒ same key id.
    assert public_key_id(loaded.public_key()) == public_key_id(priv.public_key())


def test_load_public_key_pem_rejects_wrong_type() -> None:
    # Forge an RSA PEM — cryptography will load it as RSA, not Ed25519.
    from cryptography.hazmat.primitives.asymmetric import rsa

    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_pub_pem = rsa_key.public_key().public_bytes(
        encoding=__import__(
            "cryptography.hazmat.primitives.serialization",
            fromlist=["Encoding"],
        ).Encoding.PEM,
        format=__import__(
            "cryptography.hazmat.primitives.serialization",
            fromlist=["PublicFormat"],
        ).PublicFormat.SubjectPublicKeyInfo,
    )
    with pytest.raises(TypeError):
        load_public_key_pem(rsa_pub_pem)


def test_load_private_key_pem_rejects_wrong_type() -> None:
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
    )

    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_priv_pem = rsa_key.private_bytes(
        Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
    )
    with pytest.raises(TypeError):
        load_private_key_pem(rsa_priv_pem)


def test_verify_signature_with_re_encoded_pub_key() -> None:
    """Signing pipeline must work after PEM round-trip — the real
    ingestion path decodes ``.pub.pem`` then re-encodes for
    ``public_key_id``."""
    priv = _priv()
    sig = sign_payload({"k": "v"}, private_key=priv)
    # Encode + decode the pub key through PEM.
    pem = public_key_to_pem(priv.public_key())
    pub2 = load_pem_public_key(pem)
    assert isinstance(pub2, Ed25519PublicKey)
    verify_signature({"k": "v"}, signature_b64=sig, public_key=pub2)


def test_private_pem_round_trip_with_password() -> None:
    priv = _priv()
    pw = b"hunter2"
    pem = private_key_to_pem(priv, password=pw)
    loaded = load_private_key_pem(pem, password=pw)
    assert isinstance(loaded, Ed25519PrivateKey)
    # cryptography raises ``ValueError`` on a wrong password.
    with pytest.raises(ValueError):
        load_private_key_pem(pem, password=b"wrong")
