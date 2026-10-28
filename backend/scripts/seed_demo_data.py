#!/usr/bin/env python
"""种**演示数据** —— 与开发测试数据完全分开.

演示环境用的那套数据: demo 租户 + demo 账号 (``admin@acme.com`` /
``user@acme.com``) + 内置工具.

演示环境跑在**独立的 demo 库**上 (``QZDAP_DATABASE_URL`` 指向 demo 库,
``QZDAP_ENV=demo``). 演示库和开发库是两个库, 账号和密码也不共用.

启动时 ``QZDAP_ENV=demo`` 会自动跑一遍同样的逻辑 (见
``composition/qzdap_app/.../lifespan.py`` 的 ``ensure_default_resources``).
这个脚本是给「需要手动重跑 / 需要先把演示库准备好」用的.

用法::

    cd backend
    QZDAP_ENV=demo python scripts/seed_demo_data.py

注意: 这个脚本**只种演示数据**, 不会碰开发库 —— 它操作的是当前
``QZDAP_DATABASE_URL`` 指的那一个库, 所以请确认环境变量指对了.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from qzdap.composition.container import Container  # noqa: E402
from qzdap.composition.seeds import (  # noqa: E402
    demo_profile,
    seed_builtin_tools,
    seed_demo_content,
    seed_identity,
)
from qzdap.composition.settings import get_settings  # noqa: E402


async def _run() -> int:
    settings = get_settings()
    container = Container(settings)
    profile = demo_profile(settings)
    sf = container.session_factory()
    async with sf.session() as session:
        result = await seed_identity(session, container.hasher(), profile)
        added = await seed_builtin_tools(
            session, result["tenant_id"], result["workspace_id"]
        )
        content = await seed_demo_content(
            session,
            profile,
            tenant_id=result["tenant_id"],
            workspace_id=result["workspace_id"],
        )
    print(f"demo tenant    : {profile.tenant_slug} ({result['tenant_id']})")
    print(f"demo workspace : {result['workspace_id']}")
    print(f"built-in tools : {len(added)} added")
    for label, names in content.items():
        if isinstance(names, dict):
            # memory 是各层的条数, 不是名字列表
            if not names:
                print(f"demo {label:<10}: 已存在, 跳过")
                continue
            summary = ", ".join(f"{k}={v}" for k, v in names.items())
            print(f"demo {label:<10}: {summary}")
            continue
        print(f"demo {label:<10}: {len(names)} added")
        for name in names:
            print(f"  - {name}")
    print("demo accounts  :")
    for email, _display, role in profile.accounts:
        print(f"  {email}  (role={role}, password={profile.password})")
    print()
    print("聊天前还需要在 /admin/models 配一个 LLM 供应商")
    print("(上游模型 id 用 deepseek-chat, 才能对上这些演示智能体).")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
