"""**验收样本** ✓ —— 可复现的脱敏数据 ✓（H1 / P-09 ✓）。

⚠️ **这不是演示数据** ✓ —— 演示数据在 **demo 库** ✓（`qzdap_demo` ✓）——
这里的数据**只进 dev / 预发库** ✓（**租户名带 ``qa-``** ✓ —— 一眼认得出 ✓
—— 不与 demo 混在一起 ✓）。

⚠️ **脱敏** ✓ —— **全是造出来的** ✓（没有一行真实数据 ✓ —— 连邮箱都用
``.invalid`` 顶级域 ✓（RFC 2606 ✓ —— 保证不可投递 ✓）—— 口令是本地固定值 ✓）。

⚠️ **可复现** ✓ —— id 用 ``uuid5`` 从固定命名空间派生 ✓ → **跑两次 id 一样**
✓ → 脚本**幂等** ✓。

样本覆盖六层的验收判据 ✓：

| 样本 | 验什么 |
|---|---|
| **两个租户 + 每租户两个用户** | **隔离** ✓（跨租户 / 跨用户互不可见 ✓） |
| **一条长会话**（6 轮 12 条消息 ✓） | 上下文组装与压缩 ✓ |
| **一条含工具调用的轮次** | 工具事件流 ✓（`tool_call` + `tool_result` ✓） |
| **一条含审批挂起的轮次** | 审批续传 ✓（`pending_approval` ✓） |
| **每人一条记忆** | 记忆策略与用户级隔离 ✓ |
| **agent 上绑了记忆策略** | 策略绑定（C6 ✓） |
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from qzdap.composition.seeds import SeedProfile, seed_identity

_log = logging.getLogger(__name__)

#: **样本 id 的命名空间** ✓ —— 固定 ✓ → **可复现** ✓。
QA_NAMESPACE = uuid5(NAMESPACE_URL, "qzdap-acceptance-samples/v1")

#: 样本口令 ✓ —— **本地固定值** ✓（不是生产口令 ✓ —— 也不该是 ✓）。
QA_PASSWORD = "qa-local-samples-only"  # noqa: S105 —— 样本的本地固定口令 ✓（不是生产口令 ✓）

#: **长会话的轮数** ✓ —— 够长才能验压缩 ✓。
LONG_SESSION_TURNS = 6

#: **不许种样本的环境** ✓ —— demo 库要保持干净 ✓（演示数据是另一套 ✓ ——
#: 混在一起就没法验隔离了 ✗✗）；生产库更不许 ✓（里面是真实租户 ✓）。
FORBIDDEN_ENVS = frozenset({"demo", "production"})


def assert_seedable_env(env: str) -> None:
    """**环境不许种样本** ✓ —— 明确失败 ✓（不静默跳过 ✓）。"""
    if str(env or "").lower() in FORBIDDEN_ENVS:
        raise ValueError(f"不许在 env={env} 里种验收样本（demo 库要干净 ✓ / 生产库更不许 ✓）")


def qa_id(name: str) -> UUID:
    """**从名字派生一个稳定 id** ✓（可复现 ✓）。"""
    return uuid5(QA_NAMESPACE, name)


def acceptance_profiles() -> tuple[SeedProfile, ...]:
    """**两个验收租户** ✓ —— 每租户两个用户 ✓（**验隔离** ✓）。"""
    return (
        SeedProfile(
            label="qa-a",
            tenant_id=qa_id("tenant-a"),
            tenant_slug="qa-tenant-a",
            tenant_display_name="验收租户 A",
            workspace_slug="default",
            workspace_display_name="QA Workspace A",
            accounts=(
                ("qa-a-admin@example.invalid", "QA Admin A", "admin"),
                ("qa-a-user@example.invalid", "QA User A", "member"),
            ),
            password=QA_PASSWORD,
        ),
        SeedProfile(
            label="qa-b",
            tenant_id=qa_id("tenant-b"),
            tenant_slug="qa-tenant-b",
            tenant_display_name="验收租户 B",
            workspace_slug="default",
            workspace_display_name="QA Workspace B",
            accounts=(
                ("qa-b-admin@example.invalid", "QA Admin B", "admin"),
                ("qa-b-user@example.invalid", "QA User B", "member"),
            ),
            password=QA_PASSWORD,
        ),
    )


async def seed_acceptance_samples(session: Any, hasher: Any) -> dict[str, Any]:
    """种**全套验收样本** ✓ —— 幂等 ✓。

    ⚠️ **只往 dev / 预发库种** ✓ —— 生产环境跑这个脚本是不对的 ✓（脚本自己
    拦一道 ✓ —— 见 ``scripts/seed_acceptance_samples.py`` ✓）。
    """
    from sqlalchemy import select

    from qzdap.modules.agent_runtime.adapter.persistence.catalog_repositories import (
        SqlCatalogAgentRepository,
    )
    from qzdap.modules.agent_runtime.adapter.persistence.models import SessionTurnORM
    from qzdap.modules.agent_runtime.adapter.persistence.repositories import (
        SqlSessionRepository,
    )
    from qzdap.modules.agent_runtime.adapter.persistence.session_messages import (
        PostgresSessionMessageStore,
    )
    from qzdap.modules.agent_runtime.domain.entities import Session
    from qzdap.modules.identity.adapter.persistence.models import UserORM
    from qzdap.modules.memory.adapter.persistence.models import MemoryL2ORM
    from qzdap_schema.ids import AgentId, SessionId, TenantId, UserId, WorkspaceId

    summary: dict[str, Any] = {"tenants": [], "sessions": [], "turns": 0, "memories": 0}

    for profile in acceptance_profiles():
        identity = await seed_identity(session, hasher, profile)
        tenant_id: UUID = identity["tenant_id"]
        workspace_id: UUID = identity["workspace_id"]
        summary["tenants"].append(
            {
                "slug": profile.tenant_slug,
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
            }
        )

        users = {
            str(row.email): row
            for row in (
                await session.execute(select(UserORM).where(UserORM.tenant_id == tenant_id))
            )
            .scalars()
            .all()
        }
        owner = next(
            (row for email, row in users.items() if email.endswith("admin@example.invalid")), None
        )
        if owner is None:
            _log.warning("qa sample skipped (no owner)", extra={"tenant": profile.tenant_slug})
            continue

        # ── agent（带记忆策略绑定 ✓ —— 验 C6 ✓）────────────────────
        agent_repo = SqlCatalogAgentRepository(session)
        agent = None
        for existing in await agent_repo.list_for_workspace(workspace_id):
            if existing.name == f"QA Agent {profile.label.upper()}":
                agent = existing
                break
        if agent is None:
            from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent

            agent = CatalogAgent.create(
                id=qa_id(f"agent-{profile.label}"),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                name=f"QA Agent {profile.label.upper()}",
                category="企业通用",
                owner="QA",
                description="验收样本用的 agent ✓（脱敏 ✓）",
                model="demo",
            )
            agent.memory_policy = {
                "enabled": True,
                "scope": "user",
                "policyLabel": "长期记忆",
                "retentionDays": 30,
                "autoSummarize": False,
            }
            agent.knowledge_refs = []
            await agent_repo.add(agent)

        session_repo = SqlSessionRepository(session)
        message_store = PostgresSessionMessageStore(session)

        # ── 会话样本 ✓（已存在就跳过 ✓ —— 幂等 ✓）───────────────
        if await session_repo.get(qa_id(f"session-long-{profile.label}")) is None:
            # ── 长会话 ✓（6 轮 ✓）────────────────────────────────────
            long_session = Session.create(
                id=SessionId(qa_id(f"session-long-{profile.label}")),
                tenant_id=TenantId(tenant_id),
                workspace_id=WorkspaceId(workspace_id),
                owner_id=UserId(owner.id),
                agent_id=AgentId(agent.id),
                agent_version=agent.version or "v1",
                metadata={
                    "title": f"QA 长会话 {profile.label.upper()}",
                    "preview": "验收样本：长会话",
                    "agentName": agent.name,
                    "model": agent.model,
                    "rolling_summary": "",
                    "title_auto": False,
                    "qa_sample": True,
                },
            )
            await session_repo.add(long_session)
            for index in range(LONG_SESSION_TURNS):
                turn_id = qa_id(f"turn-long-{profile.label}-{index}")
                session.add(
                    SessionTurnORM(
                        id=turn_id,
                        tenant_id=tenant_id,
                        workspace_id=workspace_id,
                        session_id=long_session.id,
                        idempotency_key=f"qa:long:{profile.label}:{index}",
                        key_strength="strong",
                        status="succeeded",
                        agent_version=long_session.agent_version or "v1",
                        model_version=agent.model or "default",
                        user_input=f"验收样本第 {index + 1} 轮",
                    )
                )
                await message_store.append(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    session_id=long_session.id,
                    turn_id=turn_id,
                    seq=0,
                    role="user",
                    content=f"验收样本第 {index + 1} 轮的问题",
                )
                await message_store.append(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    session_id=long_session.id,
                    turn_id=turn_id,
                    seq=1,
                    role="assistant",
                    content=f"验收样本第 {index + 1} 轮的回答",
                )
                summary["turns"] += 1
            summary["sessions"].append(str(long_session.id))

            # ── 含工具调用的轮次 ✓ ───────────────────────────────────
            tool_turn_id = qa_id(f"turn-tool-{profile.label}")
            tool_session = Session.create(
                id=SessionId(qa_id(f"session-tool-{profile.label}")),
                tenant_id=TenantId(tenant_id),
                workspace_id=WorkspaceId(workspace_id),
                owner_id=UserId(owner.id),
                agent_id=AgentId(agent.id),
                agent_version=agent.version or "v1",
                metadata={
                    "title": f"QA 工具会话 {profile.label.upper()}",
                    "preview": "验收样本：含工具调用",
                    "agentName": agent.name,
                    "model": agent.model,
                    "rolling_summary": "",
                    "title_auto": False,
                    "qa_sample": True,
                },
            )
            await session_repo.add(tool_session)
            session.add(
                SessionTurnORM(
                    id=tool_turn_id,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    session_id=tool_session.id,
                    idempotency_key=f"qa:tool:{profile.label}",
                    key_strength="strong",
                    status="succeeded",
                    agent_version=tool_session.agent_version or "v1",
                    model_version=agent.model or "default",
                    user_input="验收样本：跑一次工具",
                )
            )
            await message_store.append(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                session_id=tool_session.id,
                turn_id=tool_turn_id,
                seq=0,
                role="user",
                content="验收样本：跑一次工具",
            )
            await message_store.append(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                session_id=tool_session.id,
                turn_id=tool_turn_id,
                seq=1,
                role="assistant",
                content="",
                tool_name="echo",
            )
            await message_store.append(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                session_id=tool_session.id,
                turn_id=tool_turn_id,
                seq=2,
                role="tool",
                content="qa-tool-output",
                tool_name="echo",
            )
            summary["turns"] += 1
            summary["sessions"].append(str(tool_session.id))

            # ── 含审批挂起的轮次 ✓（验续传 ✓）─────────────────────────
            approval_turn_id = qa_id(f"turn-approval-{profile.label}")
            approval_session = Session.create(
                id=SessionId(qa_id(f"session-approval-{profile.label}")),
                tenant_id=TenantId(tenant_id),
                workspace_id=WorkspaceId(workspace_id),
                owner_id=UserId(owner.id),
                agent_id=AgentId(agent.id),
                agent_version=agent.version or "v1",
                metadata={
                    "title": f"QA 审批会话 {profile.label.upper()}",
                    "preview": "验收样本：审批挂起",
                    "agentName": agent.name,
                    "model": agent.model,
                    "rolling_summary": "",
                    "title_auto": False,
                    "qa_sample": True,
                },
            )
            await session_repo.add(approval_session)
            session.add(
                SessionTurnORM(
                    id=approval_turn_id,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    session_id=approval_session.id,
                    idempotency_key=f"qa:approval:{profile.label}",
                    key_strength="strong",
                    # ⚠️ **挂在审批上** ✓ —— 状态是 ``waiting`` ✓（不是 running ✓
                    # —— 那是「卡住」✓ —— 审批是**有意停住** ✓）。
                    status="waiting",
                    agent_version=approval_session.agent_version or "v1",
                    model_version=agent.model or "default",
                    user_input="验收样本：需要审批的动作",
                    pending_approval={
                        "approval_id": str(qa_id(f"approval-{profile.label}")),
                        "tool_call_id": str(qa_id(f"tool-call-{profile.label}")),
                        "tool": "danger_tool",
                        "args_preview": '{"path":"/etc/passwd"}',
                        "reason": "验收样本：高风险动作要审批",
                        "expires_at": "2099-01-01T00:00:00Z",
                    },
                )
            )
            await message_store.append(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                session_id=approval_session.id,
                turn_id=approval_turn_id,
                seq=0,
                role="user",
                content="验收样本：需要审批的动作",
            )
            summary["turns"] += 1
            summary["sessions"].append(str(approval_session.id))

        # ── 记忆样本 ✓（每用户一条 ✓ —— 验用户级隔离 ✓）───────────
        for email, row in sorted(users.items()):
            content = f"验收样本记忆 {profile.label.upper()} {email}"
            existing = (
                await session.execute(
                    select(MemoryL2ORM).where(
                        MemoryL2ORM.tenant_id == tenant_id,
                        MemoryL2ORM.key == f"qa-memory-{profile.label}-{email}",
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            session.add(
                MemoryL2ORM(
                    id=qa_id(f"memory-{profile.label}-{email}"),
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    user_id=row.id,
                    user_name=row.display_name or email,
                    key=f"qa-memory-{profile.label}-{email}",
                    value=content,
                    category="fact",
                    source_session=str(qa_id(f"session-long-{profile.label}")),
                    confidence=0.9,
                    status="confirmed",
                    promoted_to_l3=False,
                    usage_history=[],
                    content_hash=None,
                    content_hash_version=1,
                    used_count=0,
                    confidence_source="explicit",
                    version=1,
                )
            )
            summary["memories"] += 1

    await session.commit()
    _log.info(
        "seeded acceptance samples",
        extra={"tenants": len(summary["tenants"]), "sessions": len(summary["sessions"])},
    )
    return summary


__all__ = [
    "FORBIDDEN_ENVS",
    "LONG_SESSION_TURNS",
    "QA_PASSWORD",
    "acceptance_profiles",
    "assert_seedable_env",
    "qa_id",
    "seed_acceptance_samples",
]
