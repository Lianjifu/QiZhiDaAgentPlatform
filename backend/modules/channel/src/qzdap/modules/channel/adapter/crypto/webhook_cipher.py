"""Webhook secret cipher — wraps qzdap_vault.crypto.aes_gcm.

Channel secrets share the AES-GCM envelope layout with model
credentials (``nonce(12) || ciphertext || tag(16)``) so the same
master key can protect both, with a ``key_version`` column to support
future rotation. P6 only ships env-mode master keys.
"""

from __future__ import annotations

from qzdap.modules.channel.application.ports import WebhookSecretCipher
from qzdap_vault.crypto.aes_gcm import decrypt as aes_gcm_decrypt
from qzdap_vault.crypto.aes_gcm import encrypt as aes_gcm_encrypt


class AesGcmWebhookCipher(WebhookSecretCipher):
    """Encrypt / decrypt webhook HMAC secrets using AES-GCM."""

    def __init__(self, *, key: bytes, key_version: int = 1) -> None:
        if not isinstance(key, (bytes, bytearray)) or len(key) not in (16, 24, 32):
            raise ValueError("AES-GCM key must be 16/24/32 bytes")
        self._key = bytes(key)
        self._key_version = key_version

    @property
    def key_version(self) -> int:
        return self._key_version

    def encrypt(self, plaintext: bytes) -> bytes:
        return aes_gcm_encrypt(plaintext, self._key)

    def decrypt(self, blob: bytes) -> bytes:
        return aes_gcm_decrypt(blob, self._key)


def build_cipher_from_env(
    *,
    master_key_raw: str | None = None,
    master_key_hex: str | None = None,
    key_version: int = 1,
) -> AesGcmWebhookCipher:
    """Build an AES-GCM cipher from a master-key env string.

    Accepts either raw bytes (``master_key_raw``) or hex-encoded
    (``master_key_hex``). Validates the key length at construction
    time so boot fails loudly on a misconfigured key.
    """
    if master_key_hex:
        try:
            key = bytes.fromhex(master_key_hex.strip())
        except ValueError as exc:
            raise ValueError(f"invalid hex master_key: {exc}") from exc
        return AesGcmWebhookCipher(key=key, key_version=key_version)
    if master_key_raw:
        key = master_key_raw.encode("utf-8")
        return AesGcmWebhookCipher(key=key, key_version=key_version)
    raise ValueError("must supply master_key_raw or master_key_hex")


__all__ = ["AesGcmWebhookCipher", "build_cipher_from_env"]
