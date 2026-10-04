#!/usr/bin/env python
"""Retired: sandbox pack signing is no longer used.

Catalog items are managed via ``/api/admin/skills``, ``/api/admin/knowledge``,
and ``/api/admin/workflows``.
"""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "pack_sign.py is retired; use the admin catalog APIs instead.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
