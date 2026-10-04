"""AES-GCM symmetric encryption (P6 model + channel credential storage).

Storage layout: ``nonce(12) || ciphertext || tag(16)``. ``cryptography``
library's ``AESGCM.encrypt`` returns ciphertext+tag concatenated, so the
helper stores the same on-disk shape the library accepts on decrypt.

Key handling:
- ``encrypt`` / ``decrypt`` accept a raw 128/192/256-bit key.
- ``derive_key`` is a thin wrapper over Argon2id for turning a
  passphrase (e.g. ``QZDAP_MODEL_MASTER_KEY``) into a 256-bit key.

Errors raised here come from ``qzdap_kernel.errors`` so the HTTP layer
can surface them via the standard error envelope.
"""

from __future__ import annotations

import secrets
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from qzdap_kernel.errors import AppError

_NONCE_LEN: Final = 12
_VALID_KEY_LENS: Final = frozenset({16, 24, 32})


class CryptoError(AppError):
    """Base for AES-GCM crypto failures."""

    code = "CRYPTO_ERROR"
    status = 500


class InvalidKey(CryptoError):
    code = "INVALID_KEY"
    status = 422


class InvalidCiphertext(CryptoError):
    code = "INVALID_CIPHERTEXT"
    status = 422


def generate_key(length_bits: int = 256) -> bytes:
    """Return a fresh random AES key (default 256-bit)."""
    if length_bits not in (128, 192, 256):
        raise InvalidKey(
            f"key length must be 128/192/256 bits; got {length_bits}",
            code="INVALID_KEY",
        )
    return secrets.token_bytes(length_bits // 8)


def encrypt(
    plaintext: bytes,
    key: bytes,
    *,
    aad: bytes | None = None,
) -> bytes:
    """Encrypt ``plaintext`` under ``key``; return ``nonce(12) || ct || tag(16)``.

    ``aad`` (additional authenticated data) is optional but recommended
    so an attacker cannot swap ciphertexts between different records.
    """
    if len(key) not in _VALID_KEY_LENS:
        raise InvalidKey(
            f"AES-GCM key must be 128/192/256-bit; got {len(key) * 8}-bit",
            code="INVALID_KEY",
        )
    nonce = secrets.token_bytes(_NONCE_LEN)
    aesgcm = AESGCM(key)
    ct_with_tag = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce + ct_with_tag


def decrypt(
    blob: bytes,
    key: bytes,
    *,
    aad: bytes | None = None,
) -> bytes:
    """Inverse of :func:`encrypt`. Raises ``InvalidCiphertext`` on tag mismatch."""
    if len(blob) < _NONCE_LEN + 16:
        raise InvalidCiphertext(
            "ciphertext too short",
            code="INVALID_CIPHERTEXT",
        )
    if len(key) not in _VALID_KEY_LENS:
        raise InvalidKey(
            f"AES-GCM key must be 128/192/256-bit; got {len(key) * 8}-bit",
            code="INVALID_KEY",
        )
    nonce, ct_with_tag = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
    try:
        return AESGCM(key).decrypt(nonce, ct_with_tag, aad)
    except InvalidTag as exc:
        raise InvalidCiphertext(
            "authentication tag mismatch (wrong key or tampered ciphertext)",
            code="INVALID_CIPHERTEXT",
        ) from exc


def derive_key(
    passphrase: str,
    *,
    salt: bytes,
    length: int = 32,
    iterations: int = 3,
    memory_cost: int = 64_000,
    lanes: int = 4,
) -> bytes:
    """Argon2id KDF — turn a passphrase into a symmetric key.

    Defaults are OWASP's recommended Argon2id parameters for
    interactive use (≤ 1s wall time on commodity hardware).
    """
    if not passphrase:
        raise InvalidKey(
            "passphrase must be non-empty",
            code="INVALID_KEY",
        )
    if length not in (16, 24, 32):
        raise InvalidKey(
            f"derived key length must be 16/24/32 bytes; got {length}",
            code="INVALID_KEY",
        )
    if not salt:
        raise InvalidKey(
            "salt must be non-empty",
            code="INVALID_KEY",
        )
    kdf = Argon2id(
        salt=salt,
        length=length,
        iterations=iterations,
        memory_cost=memory_cost,
        lanes=lanes,
    )
    return kdf.derive(passphrase.encode("utf-8"))


__all__ = [
    "CryptoError",
    "InvalidCiphertext",
    "InvalidKey",
    "decrypt",
    "derive_key",
    "encrypt",
    "generate_key",
]
