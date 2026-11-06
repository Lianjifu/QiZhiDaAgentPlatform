"""种子数据 —— **只有开发环境这一套**。

⚠️ **演示环境已退役** ✓（2026-11-06 ✓）—— 演示 / 预发 / 生产环境都删了 ✓，
所以这里只剩一套租户、一套账号、一个库 ✓：

============================  ==========================  =========================
环境                            QZDAP_ENV                 种子
============================  ==========================  =========================
开发                            ``development``            dev 租户 + admin@dev.qzdap.dev / user@dev.qzdap.dev
============================  ==========================  =========================

规则:

* **开发环境不种任何内容数据** ✓ —— 智能体 / 技能 / 工作流 / 知识库 / 对话
  这些**演示内容全部删掉了** ✓（原来的 ``DEMO_*`` 规格 + ``seed_demo_*``
  函数一并退役 ✓）—— 目录页开箱是空态 ✓，内容由管理员在管理台自己建 ✓。
* 只有**租户 / 工作区 / 账号**由种子提供 ✓（不然登录不了 ✓），
  以及**内置工具** (``echo`` / ``bash`` / …) —— 内置工具是**平台参考数据**
  而不是内容 ✓，每个租户都需要一份 ✓。
  名字与参数契约的单一来源是
  ``qzdap.modules.tool.application.tool_catalog.BUILTIN_TOOL_SPECS``.
* ``test`` / ``ci`` 是跑测试的取值 ✓ —— ``test`` 与开发环境同源 ✓，
  ``ci`` 不种任何租户/账号 ✓（CI 自己建隔离库 ✓）。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SeedProfile:
    """一套种子数据的身份 —— 租户 / 工作区 / 账号 / 密码."""

    #: ``dev`` —— 只用于日志和 metadata, 决定数据"长什么样".
    label: str
    tenant_id: UUID
    tenant_slug: str
    tenant_display_name: str
    workspace_slug: str
    workspace_display_name: str
    #: (email, display_name, role) —— role 是 workspace 角色.
    accounts: tuple[tuple[str, str, str], ...]
    password: str
    #: **按账号覆盖口令** ✓（email → password ✓）—— 默认都用 ``password`` ✓。
    #: **管理员与成员分开** ✓（成员不该拿到管理员口令 ✓）。
    passwords: Mapping[str, str] = field(default_factory=dict)


def dev_profile(settings: Any) -> SeedProfile:
    """开发环境用的那套数据."""
    return SeedProfile(
        label="dev",
        tenant_id=uuid4(),
        tenant_slug=settings.dev_tenant_slug,
        tenant_display_name=settings.dev_tenant_display_name,
        workspace_slug="default",
        workspace_display_name="Default Workspace",
        accounts=(
            (settings.dev_admin_email, "Dev Admin", "admin"),
            # ⚠️ **用户侧账号** ✓（2026-11-01 ✓）—— 管理员只进管理台 ✓
            # （前端按角色分流 ✓）→ 用户侧那套页面要另有一个成员账号 ✓。
            (settings.dev_user_email, "Dev User", "member"),
        ),
        password=settings.dev_admin_password,
        passwords={settings.dev_user_email: settings.dev_user_password},
    )


def profile_for_env(settings: Any) -> SeedProfile | None:
    """按 ``QZDAP_ENV`` 选那套种子.

    ⚠️ **只有一个开发环境了** ✓ —— 演示 / 预发 / 生产环境都已退役 ✓。
    ``development`` / ``test`` 用 dev 那套 ✓；``ci`` 不种任何租户/账号
    ✓（CI 自己建隔离库 ✓）。
    """
    env = str(getattr(settings, "env", "development"))
    if env in {"development", "test"}:
        return dev_profile(settings)
    return None


async def seed_identity(
    session: Any,
    hasher: Any,
    profile: SeedProfile,
) -> dict[str, Any]:
    """种租户 / 工作区 / 账号 / 工作区成员关系. 幂等.

    已经有同名租户时**复用**它而不是新建 —— 免得重复跑种子脚本把库里
    塞满同名租户.
    """
    from sqlalchemy import select

    from qzdap.modules.identity.adapter.persistence.models import (
        TenantORM,
        UserWorkspaceORM,
        WorkspaceORM,
    )
    from qzdap.modules.identity.adapter.persistence.repositories import (
        SqlTenantRepository,
        SqlUserRepository,
        SqlWorkspaceRepository,
    )
    from qzdap.modules.identity.domain import Tenant, User, Workspace

    existing_tenant = (
        await session.execute(
            select(TenantORM).where(TenantORM.slug == profile.tenant_slug).limit(1)
        )
    ).scalar_one_or_none()
    if existing_tenant is not None:
        tenant_id = existing_tenant.id
        workspace_id = (
            (
                await session.execute(
                    select(WorkspaceORM.id)
                    .where(
                        WorkspaceORM.tenant_id == tenant_id,
                        WorkspaceORM.status == "active",
                    )
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        created_tenant = False
    else:
        tenant_id = profile.tenant_id
        tenant = Tenant.create(
            id=tenant_id,
            slug=profile.tenant_slug,
            display_name=profile.tenant_display_name,
            metadata={"seeded": True, "seed_profile": profile.label},
        )
        workspace = Workspace.create(
            id=uuid4(),
            tenant_id=tenant_id,
            slug=profile.workspace_slug,
            display_name=profile.workspace_display_name,
        )
        await SqlTenantRepository(session).add(tenant)
        await SqlWorkspaceRepository(session).add(workspace)
        await session.commit()
        workspace_id = workspace.id
        created_tenant = True
        _log.info(
            "seeded %s tenant/workspace",
            profile.label,
            extra={
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
                "slug": profile.tenant_slug,
            },
        )

    users_repo = SqlUserRepository(session)
    seeded_logins: list[str] = []
    seeded_memberships: list[str] = []
    for email, display_name, role in profile.accounts:
        # ⚠️ **按账号取口令** ✓（默认共用 ``profile.password`` ✓）。
        hashed = hasher.hash(profile.passwords.get(email, profile.password))
        user = await users_repo.get_by_email_global(email)
        if user is None:
            user = User.create(
                id=uuid4(),
                tenant_id=tenant_id,
                email=email,
                display_name=display_name,
                hashed_password=hashed,
            )
            await users_repo.add(user)
            seeded_logins.append(email)
        # 工作区成员关系 —— 没有这行, 需要 workspace_access 的端点会 403.
        if workspace_id is not None:
            membership = await session.scalar(
                select(UserWorkspaceORM).where(
                    UserWorkspaceORM.user_id == user.id,
                    UserWorkspaceORM.workspace_id == workspace_id,
                )
            )
            if membership is None:
                session.add(
                    UserWorkspaceORM(
                        tenant_id=tenant_id,
                        user_id=user.id,
                        workspace_id=workspace_id,
                        role=role,
                    )
                )
                seeded_memberships.append(email)
    if seeded_logins:
        await session.commit()
        _log.info("seeded %s login accounts", profile.label, extra={"emails": seeded_logins})
    if seeded_memberships:
        await session.commit()
        _log.info(
            "seeded %s workspace memberships",
            profile.label,
            extra={"emails": seeded_memberships, "workspace_id": str(workspace_id)},
        )
    return {
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "created_tenant": created_tenant,
        "seeded_logins": seeded_logins,
    }


async def seed_builtin_tools(
    session: Any,
    tenant_id: UUID,
    workspace_id: UUID | None,
) -> list[str]:
    """给租户注册内置工具. 幂等 —— 已存在的名字直接跳过.

    内置工具是**平台参考数据**（每个租户都要一份, 才能让模型调得到）,
    不是内容数据 —— 每个租户都需要一份, 所以开发种子会注册它.
    """
    from sqlalchemy import select

    from qzdap.modules.tool.adapter.persistence.models import ToolORM
    from qzdap.modules.tool.application.tool_catalog import BUILTIN_TOOL_SPECS

    existing = {
        str(name)
        for (name,) in (
            await session.execute(select(ToolORM.name).where(ToolORM.tenant_id == tenant_id))
        ).all()
    }
    added: list[str] = []
    for name, spec in sorted(BUILTIN_TOOL_SPECS.items()):
        if name in existing:
            continue
        session.add(
            ToolORM(
                id=uuid4(),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                name=name,
                description=spec["description"],
                protocol="custom",
                spec={},
                spec_operations=[],
                auth_config=None,
                rate_limit_per_minute=None,
                enabled=True,
                version=1,
            )
        )
        added.append(name)
    if added:
        await session.commit()
        _log.info("seeded built-in tools", extra={"tenant_id": str(tenant_id), "count": len(added)})
    return added


__all__ = [
    "SeedProfile",
    "dev_profile",
    "profile_for_env",
    "seed_builtin_tools",
    "seed_identity",
]
