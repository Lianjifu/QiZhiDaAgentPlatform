"""Unit tests for ``qzdap_vault.crypto.aes_gcm`` (P6 model + channel)."""

from __future__ import annotations

import pytest

from qzdap_vault import (
    CryptoError,
    InvalidCiphertext,
    InvalidKey,
    decrypt,
    derive_key,
    encrypt,
    generate_key,
)

# ── round-trip ────────────────────────────────────────────────────────────


def test_encrypt_decrypt_round_trip_bytes() -> None:
    key = generate_key()
    plaintext = b"hello world" * 17
    blob = encrypt(plaintext, key)

    assert decrypt(blob, key) == plaintext


def test_encrypt_decrypt_round_trip_empty() -> None:
    """AES-GCM allows zero-length plaintext; the auth tag still binds AAD."""
    key = generate_key()
    blob = encrypt(b"", key)
    assert decrypt(blob, key) == b""


def test_encrypt_decrypt_round_trip_all_key_sizes() -> None:
    """128/192/256-bit keys are all supported."""
    plaintext = b"ok"
    for bits in (128, 192, 256):
        key = generate_key(bits)
        blob = encrypt(plaintext, key)
        assert decrypt(blob, key) == plaintext


# ── ciphertext shape ──────────────────────────────────────────────────────


def test_ciphertext_is_nonce_12_ct_plus_tag_16() -> None:
    """12-byte nonce + AES-GCM ciphertext (plaintext length) + 16-byte tag."""
    key = generate_key()
    plaintext = b"abcde"  # 5 bytes
    blob = encrypt(plaintext, key)
    assert len(blob) == 12 + 5 + 16


def test_nonce_uniqueness_across_calls() -> None:
    """Two encryptions of the same plaintext produce different blobs."""
    key = generate_key()
    plaintext = b"same payload"
    blobs = {encrypt(plaintext, key) for _ in range(50)}
    assert len(blobs) == 50


# ── tamper / wrong key ────────────────────────────────────────────────────


def test_wrong_key_raises_invalid_ciphertext() -> None:
    key = generate_key()
    other = generate_key()
    blob = encrypt(b"payload", key)
    with pytest.raises(InvalidCiphertext) as ei:
        decrypt(blob, other)
    assert ei.value.code == "INVALID_CIPHERTEXT"


def test_tampered_ciphertext_raises_invalid_ciphertext() -> None:
    key = generate_key()
    blob = encrypt(b"payload", key)
    # Flip a bit in the ciphertext region (skip the nonce prefix)
    tampered = bytearray(blob)
    tampered[15] ^= 0x01
    with pytest.raises(InvalidCiphertext):
        decrypt(bytes(tampered), key)


def test_short_blob_raises_invalid_ciphertext() -> None:
    """A blob shorter than 12 (nonce) + 16 (tag) has no ciphertext."""
    key = generate_key()
    with pytest.raises(InvalidCiphertext) as ei:
        decrypt(b"\x00" * 20, key)
    assert ei.value.code == "INVALID_CIPHERTEXT"


# ── AAD binding ──────────────────────────────────────────────────────────


def test_aad_mismatch_raises() -> None:
    """Decrypting with the wrong AAD must fail even with the right key."""
    key = generate_key()
    blob = encrypt(b"payload", key, aad=b"tenant=acme")
    with pytest.raises(InvalidCiphertext):
        decrypt(blob, key, aad=b"tenant=other")


def test_aad_match_round_trips() -> None:
    key = generate_key()
    blob = encrypt(b"payload", key, aad=b"tenant=acme")
    assert decrypt(blob, key, aad=b"tenant=acme") == b"payload"


# ── key validation ────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad_len", [0, 8, 15, 17, 23, 25, 31, 33, 64])
def test_encrypt_rejects_invalid_key_length(bad_len: int) -> None:
    """Valid AES key lengths are 16 (128-bit), 24 (192-bit), 32 (256-bit)."""
    bad_key = b"\x00" * bad_len
    with pytest.raises(InvalidKey) as ei:
        encrypt(b"x", bad_key)
    assert ei.value.code == "INVALID_KEY"


@pytest.mark.parametrize("bad_len", [0, 8, 15, 17, 23, 25, 31, 33, 64])
def test_decrypt_rejects_invalid_key_length(bad_len: int) -> None:
    bad_key = b"\x00" * bad_len
    with pytest.raises(InvalidKey):
        decrypt(b"\x00" * 64, bad_key)


def test_generate_key_validates_bits() -> None:
    with pytest.raises(InvalidKey):
        generate_key(512)


# ── derive_key (Argon2id KDF) ────────────────────────────────────────────


def test_derive_key_is_deterministic() -> None:
    salt = b"a" * 16
    k1 = derive_key("passphrase-correct horse battery staple", salt=salt)
    k2 = derive_key("passphrase-correct horse battery staple", salt=salt)
    assert k1 == k2
    assert len(k1) == 32


def test_derive_key_changes_with_salt() -> None:
    k1 = derive_key("same-passphrase", salt=b"a" * 16)
    k2 = derive_key("same-passphrase", salt=b"b" * 16)
    assert k1 != k2


def test_derive_key_changes_with_passphrase() -> None:
    salt = b"a" * 16
    k1 = derive_key("passphrase-one", salt=salt)
    k2 = derive_key("passphrase-two", salt=salt)
    assert k1 != k2


def test_derive_key_rejects_empty_passphrase() -> None:
    with pytest.raises(InvalidKey):
        derive_key("", salt=b"a" * 16)


def test_derive_key_rejects_empty_salt() -> None:
    with pytest.raises(InvalidKey):
        derive_key("p", salt=b"")


def test_derive_key_rejects_invalid_length() -> None:
    with pytest.raises(InvalidKey):
        derive_key("p", salt=b"a" * 16, length=8)


def test_derive_key_then_encrypt_decrypt_round_trip() -> None:
    """Common pattern: passphrase + salt → AES key → encrypt."""
    passphrase = "QZDAP_MODEL_MASTER_KEY_env"
    salt = b"unique-salt-per-tenant"
    key = derive_key(passphrase, salt=salt)
    blob = encrypt(b"sk-abc1234567890", key)
    assert decrypt(blob, derive_key(passphrase, salt=salt)) == b"sk-abc1234567890"


# ── error hierarchy ──────────────────────────────────────────────────────


def test_crypto_errors_are_app_errors() -> None:
    """All crypto errors inherit ``AppError`` so the HTTP layer maps them."""
    from qzdap_kernel.errors import AppError

    assert issubclass(InvalidKey, AppError)
    assert issubclass(InvalidCiphertext, AppError)
    assert issubclass(CryptoError, AppError)
    assert issubclass(InvalidKey, CryptoError)
    assert issubclass(InvalidCiphertext, CryptoError)


def test_invalid_key_has_422_status() -> None:
    err = InvalidKey("bad", code="INVALID_KEY")
    assert err.status == 422


def test_invalid_ciphertext_has_422_status() -> None:
    err = InvalidCiphertext("bad", code="INVALID_CIPHERTEXT")
    assert err.status == 422
