#!/usr/bin/env python
"""种**验收样本** ✓ —— 可复现的脱敏数据 ✓（H1 / P-09 ✓）。

⚠️ **只往开发 / 测试库种** ✓ —— 验收样本是**独立租户** ✓（``qa-`` 前缀 ✓）
—— 不与开发库里管理员自己建的内容混在一起 ✓。

用法::

    cd backend
    python scripts/seed_acceptance_samples.py            # 种样本
    python scripts/seed_acceptance_samples.py --dry-run  # 只说会种什么

样本内容见 ``composition/qzdap_app/.../acceptance_samples.py`` ✓。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from qzdap.composition.acceptance_samples import (  # noqa: E402
    acceptance_profiles,
    assert_seedable_env,
    seed_acceptance_samples,
)
from qzdap.composition.container import Container  # noqa: E402
from qzdap.composition.settings import get_settings  # noqa: E402

#: **不许种样本的环境** ✓ —— demo 库要保持干净 ✓（演示数据是另一套 ✓）——
#: 生产库更不许 ✓（里面是真实租户 ✓）。
_FORBIDDEN_ENVS = {"demo", "production"}


async def _run(*, dry_run: bool) -> int:
    settings = get_settings()
    env = str(getattr(settings, "env", "development")).lower()
    try:
        assert_seedable_env(env)
    except ValueError as exc:
        print(f"✗ {exc}")
        return 1
    profiles = acceptance_profiles()
    if dry_run:
        print(f"env={env} —— 会种 {len(profiles)} 个验收租户：")
        for profile in profiles:
            print(f"  {profile.tenant_slug}  id={profile.tenant_id}")
            for email, display, role in profile.accounts:
                print(f"    {email}  ({display}, role={role})")
        return 0

    container = Container(settings)
    sf = container.session_factory()
    async with sf.session() as session:
        summary = await seed_acceptance_samples(session, container.hasher())
    print(f"验收租户 : {len(summary['tenants'])}（复用已有的 ✓）")
    for tenant in summary["tenants"]:
        print(
            f"  {tenant['slug']}  tenant={tenant['tenant_id']}  workspace={tenant['workspace_id']}"
        )
    print(f"新建会话 : {len(summary['sessions'])}（已存在就跳过 ✓ —— 幂等 ✓）")
    print(f"新建轮次 : {summary['turns']}")
    print(f"新建记忆 : {summary['memories']}")
    print("下一步：python scripts/acceptance_check.py")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="只说要种什么，不写库 ✓")
    args = parser.parse_args()
    return asyncio.run(_run(dry_run=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
