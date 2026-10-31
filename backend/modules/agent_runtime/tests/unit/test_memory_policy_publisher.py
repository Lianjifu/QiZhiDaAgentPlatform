"""Memory Stage 7：**策略配置发布到 agent** ✓（B2 的「配置发布与生效」✓ —— M-37 ✓）。

验收覆盖 ✓：

- **只改绑了这个 label 的 agent** ✓（没绑的**不碰** ✓）；
- **发布完运行时下一次就读到** ✓（不用重启 ✓ —— 这才是「发布」✓）；
- **引用落在 ``knowledge_refs``** ✓（**唯一真相** ✓ —— 不在 policy 里存第二份 ✗✗）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from qzdap.modules.agent_runtime.adapter.memory.policy_publisher import (
    AgentMemoryPolicyPublisher,
)
from qzdap.modules.agent_runtime.application.catalog_ports import CatalogAgentRepository
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent
from qzdap_agent_runtime.memory.policy import MemoryPolicyConfig, PolicyBinding

TENANT = UUID("00000000-0000-0000-0000-000000000001")
OTHER_TENANT = UUID("00000000-0000-0000-0000-000000000009")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")


class FakeCatalogAgents(CatalogAgentRepository):
    """**内存版**的 agent 目录 ✓（只用于这个窄端口的验收 ✓）。"""

    def __init__(self, agents: list[CatalogAgent]) -> None:
        self.agents = agents

    async def add(self, agent: CatalogAgent) -> None:
        self.agents.append(agent)

    async def get(self, agent_id: UUID) -> CatalogAgent | None:
        return next((a for a in self.agents if a.id == agent_id), None)

    async def list_for_workspace(self, workspace_id: UUID) -> list[CatalogAgent]:
        return [a for a in self.agents if a.workspace_id == workspace_id]

    async def update(self, agent: CatalogAgent) -> None:
        return None

    async def delete(self, agent_id: UUID) -> None:
        return None


def _agent(*, name: str, policy: dict[str, object]) -> CatalogAgent:
    now = datetime.now(UTC)
    return CatalogAgent(
        id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        name=name,
        description="",
        category="通用",
        owner="管理员",
        status="published",
        version="1",
        updated_at=now,
        created_at=now,
        memory_policy=dict(policy),
    )


@pytest.mark.asyncio
async def test_only_the_bound_agent_is_published_to() -> None:
    """**只改绑了这个 label 的** ✓（别人的策略不碰 ✓）。"""
    bound = _agent(name="绑了的", policy={"enabled": True, "policyLabel": "长期记忆"})
    other = _agent(name="没绑的", policy={"enabled": True, "scope": "user"})
    publisher = AgentMemoryPolicyPublisher(FakeCatalogAgents([bound, other]))

    published = await publisher.publish(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        label="长期记忆",
        config=MemoryPolicyConfig(enabled=False, scope="session"),
    )

    assert published == 1
    assert bound.memory_policy["enabled"] is False
    assert bound.memory_policy["scope"] == "session"
    # ⚠️ **没绑的没被动过** ✓。
    assert other.memory_policy == {"enabled": True, "scope": "user"}


@pytest.mark.asyncio
async def test_the_published_config_takes_effect_on_the_next_turn() -> None:
    """**发布完运行时下一次就读到** ✓（生效 ✓ —— 不用重启 ✓）。"""
    bound = _agent(
        name="绑了的",
        policy={"enabled": True, "policyLabel": "长期记忆", "scope": "user"},
    )
    publisher = AgentMemoryPolicyPublisher(FakeCatalogAgents([bound]))
    await publisher.publish(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        label="长期记忆",
        config=MemoryPolicyConfig(enabled=False, scope="session", retention_days=7),
    )

    policy = PolicyBinding(raw=bound.memory_policy, refs=tuple(bound.knowledge_refs)).to_policy()
    assert policy.enabled is False
    assert policy.scope.value == "session"
    assert policy.retention_days == 7


@pytest.mark.asyncio
async def test_the_other_tenant_is_never_published_to() -> None:
    """**跨租户不碰** ✓（租户隔离 ✓）。"""
    now = datetime.now(UTC)
    foreign = CatalogAgent(
        id=uuid4(),
        tenant_id=OTHER_TENANT,
        workspace_id=WORKSPACE,
        name="别家的",
        description="",
        category="通用",
        owner="管理员",
        status="published",
        version="1",
        updated_at=now,
        created_at=now,
        memory_policy={"enabled": True, "policyLabel": "长期记忆"},
    )
    publisher = AgentMemoryPolicyPublisher(FakeCatalogAgents([foreign]))
    published = await publisher.publish(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        label="长期记忆",
        config=MemoryPolicyConfig(enabled=False),
    )
    assert published == 0
    assert foreign.memory_policy["enabled"] is True


@pytest.mark.asyncio
async def test_the_refs_land_in_their_own_field() -> None:
    """**引用落在 ``knowledge_refs``** ✓（**唯一真相** ✓）。"""
    bound = _agent(name="绑了的", policy={"enabled": True, "policyLabel": "长期记忆"})
    publisher = AgentMemoryPolicyPublisher(FakeCatalogAgents([bound]))
    await publisher.publish(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        label="长期记忆",
        config=MemoryPolicyConfig(
            knowledge_refs=({"type": "l3", "id": "l3-1"},),
        ),
    )
    assert bound.knowledge_refs == [{"type": "l3", "id": "l3-1"}]
    # ⚠️ **policy 里不存第二份** ✓。
    assert "knowledgeRefs" not in bound.memory_policy
