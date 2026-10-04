#!/usr/bin/env python
"""Generate a development Ed25519 keypair for skill-pack signing.

Writes ``<prefix>.priv.pem`` and ``<prefix>.pub.pem`` to ``-o/--out-dir``
(default ``./.qzdap/skill-trust``) and prints the ``signer_key_id``
(= ``sha256(pub_pem).hexdigest()``) so the operator can paste it into a
trust store or update CI secrets.

This script is for dev / staging ONLY.  Production keys are managed by
``qzdap_vault`` and resolved via ``VaultBackedSkillVetter`` (Tier B).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Allow ``python scripts/dev_signing_keygen.py`` from anywhere in the repo.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "libs" / "pack_signing" / "src"))

from qzdap_pack_signing import (  # noqa: E402 — sys.path tweak above
    private_key_to_pem,
    public_key_id,
    public_key_to_pem,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "-o",
        "--out-dir",
        default="./.qzdap/skill-trust",
        help="directory to write the keypair into (created if missing)",
    )
    parser.add_argument(
        "-p",
        "--prefix",
        default="qzdap-office-dev",
        help="file prefix; writes <prefix>.priv.pem and <prefix>.pub.pem",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    key = Ed25519PrivateKey.generate()
    priv_path = out_dir / f"{args.prefix}.priv.pem"
    pub_path = out_dir / f"{args.prefix}.pub.pem"
    priv_path.write_bytes(private_key_to_pem(key))
    pub_path.write_bytes(public_key_to_pem(key.public_key()))

    key_id = public_key_id(key.public_key())
    print(f"wrote {priv_path}")
    print(f"wrote {pub_path}")
    print(f"signer_key_id={key_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
