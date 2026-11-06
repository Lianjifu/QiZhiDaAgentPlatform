#!/usr/bin/env python
"""种**开发环境数据** —— dev 租户 + dev 账号 + 内置工具.

⚠️ **只剩开发环境这一套** ✓ —— 演示环境已退役 ✓（原来的演示租户 /
``admin@acme.com`` 演示账号 / 演示内容都没了 ✓）。

启动时 ``QZDAP_ENV=development`` 会自动跑一遍同样的逻辑 (见
``composition/qzdap_app/.../lifespan.py`` 的 ``ensure_default_resources``).
这个脚本是给「需要手动重跑」用的.

用法::

    cd backend
    python scripts/seed_dev_data.py
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from qzdap.composition.container import Container  # noqa: E402
from qzdap.composition.seeds import (  # noqa: E402
    dev_profile,
    seed_builtin_tools,
    seed_identity,
)
from qzdap.composition.settings import get_settings  # noqa: E402


async def _run() -> int:
    settings = get_settings()
    container = Container(settings)
    profile = dev_profile(settings)
    sf = container.session_factory()
    async with sf.session() as session:
        result = await seed_identity(session, container.hasher(), profile)
        added = await seed_builtin_tools(session, result["tenant_id"], result["workspace_id"])
    print(f"dev tenant     : {profile.tenant_slug} ({result['tenant_id']})")
    print(f"dev workspace  : {result['workspace_id']}")
    print(f"built-in tools : {len(added)} added")
    print("dev accounts   :")
    for email, _display, role in profile.accounts:
        print(f"  {email}  (role={role}, password={profile.password})")
    return 0


def main() -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args()
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
