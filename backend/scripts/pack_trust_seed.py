#!/usr/bin/env python
"""Install a public key into the local skill-pack trust store.

The trust store consumed by :class:`LocalTrustStoreSkillVetter` is a
directory of ``<key_id>.pub.pem`` files where ``key_id`` =
``sha256(pem_bytes).hexdigest()``.  This script computes the
canonical ``key_id`` from the supplied PEM and copies it into the
trust directory with the right filename.  Overwrites any existing file
with the same ``key_id``.

Usage::

    python scripts/pack_trust_seed.py \\
        .qzdap/skill-trust/qzdap-office-dev.pub.pem \\
        .qzdap/skill-trust

The trust directory is created if missing.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "libs" / "pack_signing" / "src"))

from qzdap_pack_signing import (  # noqa: E402
    load_public_key_pem,
    public_key_id,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "pub_pem",
        type=Path,
        help="path to a PEM-encoded Ed25519 public key",
    )
    parser.add_argument(
        "trust_dir",
        type=Path,
        help="trust store directory (created if missing)",
    )
    args = parser.parse_args()

    pub_pem_path: Path = args.pub_pem.expanduser().resolve()
    trust_dir: Path = args.trust_dir.expanduser().resolve()

    if not pub_pem_path.is_file():
        print(f"error: pub key {pub_pem_path} not found", file=sys.stderr)
        return 2

    pem_bytes = pub_pem_path.read_bytes()
    pub_key = load_public_key_pem(pem_bytes)
    key_id = public_key_id(pub_key)

    trust_dir.mkdir(parents=True, exist_ok=True)
    target = trust_dir / f"{key_id}.pub.pem"
    shutil.copyfile(pub_pem_path, target)
    print(f"installed {target} (signer_key_id={key_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
