#!/usr/bin/env python
"""种**开发测试数据** —— 与演示数据完全分开.

开发环境用的那套数据: dev 租户 + dev 管理员 + 内置工具. 名字里带
``dev``, 跟演示数据 (``demo`` 租户 / ``admin@acme.com``) 区分得开,
两者不共用账号、不共用密码, 也不共用库.

启动时 ``QZDAP_ENV=development`` 会自动跑一遍同样的逻辑 (见
``composition/qzdap_app/.../lifespan.py`` 的 ``ensure_default_resources``).
这个脚本是给「需要手动重跑 / 需要在 staging 上种」用的.

用法::

    cd backend
    python scripts/seed_dev_data.py              # 种 dev 数据
    python scripts/seed_dev_data.py --no-prune   # 不清理残留的 demo 数据
    python scripts/seed_dev_data.py --print-only # 只打印账号, 不写库

默认会**清掉**库里残留的 demo 数据 (``Demo Tenant`` 租户和 ``*@acme.com``
账号) —— 开发环境不该留着演示数据.
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
    prune_demo_data,
    seed_builtin_tools,
    seed_identity,
)
from qzdap.composition.settings import get_settings  # noqa: E402


async def _run(*, prune: bool) -> int:
    settings = get_settings()
    container = Container(settings)
    profile = dev_profile(settings)
    sf = container.session_factory()
    async with sf.session() as session:
        if prune:
            pruned = await prune_demo_data(session)
            print(
                f"pruned demo data: {pruned['tenants']} tenant(s), "
                f"{pruned['users']} user(s)"
            )
        result = await seed_identity(session, container.hasher(), profile)
        added = await seed_builtin_tools(
            session, result["tenant_id"], result["workspace_id"]
        )
    print(f"dev tenant     : {profile.tenant_slug} ({result['tenant_id']})")
    print(f"dev workspace  : {result['workspace_id']}")
    print(f"built-in tools : {len(added)} added")
    print("dev accounts   :")
    for email, _display, role in profile.accounts:
        print(f"  {email}  (role={role}, password={profile.password})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--no-prune",
        action="store_true",
        help="keep leftover demo rows (Demo Tenant / *@acme.com) in the database",
    )
    args = parser.parse_args()
    return asyncio.run(_run(prune=not args.no_prune))


if __name__ == "__main__":
    raise SystemExit(main())
