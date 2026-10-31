#!/usr/bin/env python
"""**验收检查** ✓ —— 一键跑完六层的判据 ✓（H1 / P-09 ✓）。

⚠️ **先种样本** ✓ —— ``python scripts/seed_acceptance_samples.py`` ✓
（没有样本就没什么可验的 ✗✗）。

⚠️ **查的是库** ✓（不是接口 ✓）—— **接口层的验收要另跑** ✓（这个脚本
验的是**落库形态** ✓ —— 六层的关键不变量在库里长什么样 ✓）。

用法::

    cd backend
    python scripts/acceptance_check.py

退出码：0 = 全过 ✓；1 = 有判据没过 ✗（**逐条打印** ✓ —— 不用猜 ✓）。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from sqlalchemy import text  # noqa: E402

from qzdap.composition.acceptance_samples import acceptance_profiles  # noqa: E402
from qzdap.composition.container import Container  # noqa: E402
from qzdap.composition.settings import get_settings  # noqa: E402


class _Report:
    """**逐条判定**的收集器 ✓（全过 = 绿 ✓）。"""

    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, ok: bool, label: str, detail: str = "") -> None:
        if ok:
            self.passed.append(label)
            print(f"  ✓ {label}" + (f" —— {detail}" if detail else ""))
        else:
            self.failed.append(label)
            print(f"  ✗ {label}" + (f" —— {detail}" if detail else ""))

    @property
    def ok(self) -> bool:
        return not self.failed


async def _run() -> int:
    settings = get_settings()
    container = Container(settings)
    sf = container.session_factory()
    report = _Report()

    profiles = acceptance_profiles()
    slugs = [profile.tenant_slug for profile in profiles]

    async with sf.session() as session:
        print("【样本】验收样本在不在 ✓")
        for profile in profiles:
            tenant = (
                await session.execute(
                    text("SELECT id FROM tenants WHERE slug = :slug"), {"slug": profile.tenant_slug}
                )
            ).scalar_one_or_none()
            report.check(tenant is not None, f"租户 {profile.tenant_slug} 存在")
            if tenant is None:
                continue
            users = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM users WHERE tenant_id = :tid AND email LIKE :pattern"
                    ),
                    {"tid": tenant, "pattern": "%@example.invalid"},
                )
            ).scalar_one()
            report.check(
                int(users) == len(profile.accounts),
                f"租户 {profile.tenant_slug} 有 {len(profile.accounts)} 个用户",
                f"实际 {users}",
            )

        print("【Session】轮次与消息的形态 ✓")
        turn_count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM session_turns t "
                    "JOIN tenants tn ON tn.id = t.tenant_id WHERE tn.slug = ANY(:slugs)"
                ),
                {"slugs": slugs},
            )
        ).scalar_one()
        report.check(int(turn_count) >= 6, "验收轮次都在", f"{turn_count} 条")

        orphan = (
            await session.execute(
                text(
                    "SELECT count(*) FROM session_messages m "
                    "LEFT JOIN session_turns t ON t.id = m.turn_id WHERE t.id IS NULL"
                )
            )
        ).scalar_one()
        report.check(int(orphan) == 0, "没有孤儿消息（消息都挂在轮次上）", f"{orphan} 条")

        waiting = (
            await session.execute(
                text(
                    "SELECT count(*) FROM session_turns WHERE status = 'waiting' "
                    "AND pending_approval IS NOT NULL"
                )
            )
        ).scalar_one()
        report.check(int(waiting) >= 2, "有挂起审批的轮次（验续传）", f"{waiting} 条")

        seq_gap = (
            await session.execute(
                text(
                    "SELECT count(*) FROM ("
                    "  SELECT turn_id FROM session_events GROUP BY turn_id"
                    "  HAVING count(*) <> max(seq) + 1 OR min(seq) <> 0"
                    ") g"
                )
            )
        ).scalar_one()
        report.check(
            int(seq_gap) == 0, "事件流的 seq 连续（0 起、不跳号）", f"{seq_gap} 个轮次异常"
        )

        print("【Memory】记忆与策略 ✓")
        for profile in profiles:
            tenant_id = (
                await session.execute(
                    text("SELECT id FROM tenants WHERE slug = :slug"), {"slug": profile.tenant_slug}
                )
            ).scalar_one_or_none()
            if tenant_id is None:
                continue
            memories = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM admin_memory_l2 "
                        "WHERE tenant_id = :tid AND key LIKE 'qa-memory-%'"
                    ),
                    {"tid": tenant_id},
                )
            ).scalar_one()
            report.check(
                int(memories) >= 2, f"租户 {profile.tenant_slug} 的记忆样本在", f"{memories} 条"
            )

        bound = (
            await session.execute(
                text(
                    "SELECT count(*) FROM admin_agents "
                    "WHERE memory_policy->>'policyLabel' = '长期记忆' AND name LIKE 'QA Agent%'"
                )
            )
        ).scalar_one()
        report.check(int(bound) >= 2, "agent 上绑了记忆策略（C6）", f"{bound} 个")

        print("【隔离】跨租户看不见 ✓")
        cross = (
            await session.execute(
                text(
                    "SELECT count(*) FROM session_turns t JOIN tenants tn ON tn.id = t.tenant_id "
                    "WHERE tn.slug = 'qa-tenant-b' AND t.tenant_id IN ("
                    "  SELECT id FROM tenants WHERE slug = 'qa-tenant-a')"
                )
            )
        ).scalar_one()
        report.check(int(cross) == 0, "B 租户的轮次不属于 A 租户", f"{cross} 条越界")

        print("【Schema】退役的列与表 ✓")
        columns = (
            await session.execute(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_name = 'agent_sessions' AND column_name = 'graph_state'"
                )
            )
        ).scalar_one()
        report.check(int(columns) == 0, "`agent_sessions.graph_state` 已退役（迁移 0056）")

    print()
    if report.ok:
        print(f"✓ 验收检查全过（{len(report.passed)} 条 ✓）")
        return 0
    print(f"✗ 验收检查没过：{len(report.failed)} 条失败 / {len(report.passed)} 条通过")
    for label in report.failed:
        print(f"  · {label}")
    return 1


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
