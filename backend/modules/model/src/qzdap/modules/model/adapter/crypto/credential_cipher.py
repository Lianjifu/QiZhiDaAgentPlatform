"""AES-GCM cipher wrapper for ModelCredential payloads.

Production cipher: keyed off ``QZDAP_MODEL_MASTER_KEY`` (32 raw bytes,
hex-encoded in env). For startup convenience we accept either:
- 32 raw bytes (most secure — caller's responsibility)
- 64-char hex string (decoded once at startup)
- a passphrase + salt (Argon2id derivation)

The cipher is a thin ``CredentialCipher`` Protocol implementation; the
adapter module ``credential_cipher`` is the only place that touches
``qzdap_vault.crypto.aes_gcm`` directly.
"""

from __future__ import annotations

from qzdap_vault.crypto import aes_gcm

from qzdap.modules.model.application.ports import CredentialCipher


def build_cipher_from_env(
    *,
    master_key_hex: str | None,
    master_key_raw: bytes | None = None,
    passphrase: str | None = None,
    salt: bytes | None = None,
    key_version: int = 1,
) -> CredentialCipher:
    """Build a ``CredentialCipher`` from one of three key sources."""
    if master_key_raw is not None:
        if len(master_key_raw) not in (16, 24, 32):
            raise ValueError(
                f"master_key_raw must be 16/24/32 bytes; got {len(master_key_raw)}"
            )
        return _AesGcmCipher(key=master_key_raw, key_version=key_version)
    if master_key_hex:
        raw = bytes.fromhex(master_key_hex)
        if len(raw) not in (16, 24, 32):
            raise ValueError(
                f"master_key_hex decodes to {len(raw)} bytes; expected 16/24/32"
            )
        return _AesGcmCipher(key=raw, key_version=key_version)
    if passphrase and salt:
        return _AesGcmCipher(
            key=aes_gcm.derive_key(passphrase, salt=salt),
            key_version=key_version,
        )
    raise ValueError(
        "build_cipher_from_env: provide master_key_raw, master_key_hex, "
        "or (passphrase + salt)"
    )


class _AesGcmCipher(CredentialCipher):
    """AES-GCM cipher — see ``qzdap_vault.crypto.aes_gcm``.

    ``key_version`` is stamped on the credential so master-key
    rotation can be implemented later (P10) by decrypting with the
    historical key, then re-encrypting with the new key and bumping
    the column.
    """

    __slots__ = ("_key", "_key_version")

    def __init__(self, *, key: bytes, key_version: int) -> None:
        self._key = key
        self._key_version = key_version

    @property
    def key_version(self) -> int:
        return self._key_version

    def encrypt(self, plaintext: bytes, *, aad: bytes | None = None) -> bytes:
        return aes_gcm.encrypt(plaintext, self._key, aad=aad)

    def decrypt(self, blob: bytes, *, aad: bytes | None = None) -> bytes:
        return aes_gcm.decrypt(blob, self._key, aad=aad)


__all__ = ["_AesGcmCipher", "build_cipher_from_env"]
