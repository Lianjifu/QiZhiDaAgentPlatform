"""Unit tests for :mod:`qzdap_pack_signing.trust_store`.

Covers:

* Empty / missing trust dir → typed ``signer_untrusted_exc``.
* Bad PEM file → typed exception.
* Filename stem that doesn't match ``public_key_id(key)`` → typed exception.
* Happy path: returns ``{key_id: Ed25519PublicKey}`` for every valid PEM.
* Multiple keys: each filename maps to the right kid.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from qzdap_pack_signing import (
    public_key_id,
    public_key_to_pem,
    scan_trust_dir,
)


class _FakeSignerUntrusted(Exception):
    """Stand-in for a typed ``*SignerUntrusted`` exception."""


def _write_pem(path: Path, key: Ed25519PrivateKey) -> str:
    kid = public_key_id(key.public_key())
    pem = public_key_to_pem(key.public_key())
    path.write_bytes(pem)
    return kid


def test_scan_trust_dir_missing(tmp_path: Path) -> None:
    ghost = tmp_path / "nope"
    with pytest.raises(_FakeSignerUntrusted, match="does not exist"):
        scan_trust_dir(
            ghost,
            label="skill",
            signer_untrusted_exc=_FakeSignerUntrusted,
        )


def test_scan_trust_dir_empty(tmp_path: Path) -> None:
    with pytest.raises(_FakeSignerUntrusted, match="empty"):
        scan_trust_dir(
            tmp_path,
            label="knowledge",
            signer_untrusted_exc=_FakeSignerUntrusted,
        )


def test_scan_trust_dir_bad_pem(tmp_path: Path) -> None:
    (tmp_path / "abc.pub.pem").write_bytes(b"not a real pem")
    with pytest.raises(_FakeSignerUntrusted, match="not a valid Ed25519 PEM"):
        scan_trust_dir(
            tmp_path,
            label="plan",
            signer_untrusted_exc=_FakeSignerUntrusted,
        )


def test_scan_trust_dir_filename_mismatch(tmp_path: Path) -> None:
    """Filename stem must match ``public_key_id(key)``."""
    key = Ed25519PrivateKey.generate()
    # Write under the wrong filename.
    (tmp_path / "wrong-name.pub.pem").write_bytes(public_key_to_pem(key.public_key()))
    with pytest.raises(_FakeSignerUntrusted, match="filename does not match"):
        scan_trust_dir(
            tmp_path,
            label="skill",
            signer_untrusted_exc=_FakeSignerUntrusted,
        )


def test_scan_trust_dir_happy_path(tmp_path: Path) -> None:
    a = Ed25519PrivateKey.generate()
    b = Ed25519PrivateKey.generate()
    kid_a = _write_pem(tmp_path / f"{public_key_id(a.public_key())}.pub.pem", a)
    kid_b = _write_pem(tmp_path / f"{public_key_id(b.public_key())}.pub.pem", b)

    keys = scan_trust_dir(
        tmp_path,
        label="knowledge",
        signer_untrusted_exc=_FakeSignerUntrusted,
    )
    assert set(keys) == {kid_a, kid_b}
    # Ed25519PublicKey has no ``.public_key()`` — it's already public —
    # so we re-derive the kid from PEM bytes.
    assert public_key_id(keys[kid_a]) == kid_a
    assert public_key_id(keys[kid_b]) == kid_b


def test_scan_trust_dir_label_in_message(tmp_path: Path) -> None:
    """The label surfaces in the error so callers know which vetter failed."""
    with pytest.raises(_FakeSignerUntrusted, match="my-cool-label"):
        scan_trust_dir(
            tmp_path,
            label="my-cool-label",
            signer_untrusted_exc=_FakeSignerUntrusted,
        )


def test_scan_trust_dir_ignores_non_pem_files(tmp_path: Path) -> None:
    a = Ed25519PrivateKey.generate()
    kid = _write_pem(tmp_path / f"{public_key_id(a.public_key())}.pub.pem", a)
    # Non-PEM siblings should be ignored, NOT cause failure.
    (tmp_path / "README.md").write_text("hi")
    (tmp_path / "key.pem").write_text("not .pub.pem suffix")
    keys = scan_trust_dir(
        tmp_path,
        label="plan",
        signer_untrusted_exc=_FakeSignerUntrusted,
    )
    assert set(keys) == {kid}


def test_scan_trust_dir_deterministic_order(tmp_path: Path) -> None:
    a = Ed25519PrivateKey.generate()
    b = Ed25519PrivateKey.generate()
    _write_pem(tmp_path / f"{public_key_id(a.public_key())}.pub.pem", a)
    _write_pem(tmp_path / f"{public_key_id(b.public_key())}.pub.pem", b)
    keys = scan_trust_dir(
        tmp_path,
        label="skill",
        signer_untrusted_exc=_FakeSignerUntrusted,
    )
    # Returned order is sorted by filename (stable across runs).
    assert list(keys.keys()) == sorted(keys.keys())
