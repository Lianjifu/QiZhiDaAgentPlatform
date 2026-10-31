"""Memory Stage 4：**C6 策略绑定的运行面** ✓（Memory 方案 §7.1 ✓）。

核心验收 ✓：**后台改绑定 → 下一轮的行为可见地改变** ✓：

- ``enabled=False`` → **一条不写** ✓；
- ``scope=session`` → **只召回本会话的记忆** ✓；
- ``l3EntryIds`` → **那条 L3 一定被召回** ✓（哪怕关键词不匹配 ✓）；
- ``policyLabel`` → **保留策略被解析出来** ✓（绑定看得见 ✓）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from qzdap.modules.memory.application.services import MemoryRuntimeService
from qzdap.modules.memory.domain.entities import L2Fact, L3Entry, RetentionPolicy
from qzdap_agent_runtime.memory.policy import MemoryPolicy, MemoryRef, MemoryRefKind
from qzdap_agent_runtime.memory.refine import BufferRow
from qzdap_agent_runtime.memory.scope import MemoryScope
from tests.unit.test_memory_catalog import InMemoryCatalog

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
USER = UUID("00000000-0000-0000-0000-000000000003")


def _l2(*, session_id: UUID, value: str = "我在上海办公") -> L2Fact:
    now = datetime.now(UTC)
    return L2Fact(
        id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        user_name="用户",
        user_id=USER,
        key=value,
        value=value,
        category="fact",
        source_session=str(session_id),
        confidence=0.9,
        status="confirmed",
        promoted_to_l3=False,
        updated_at=now,
        created_at=now,
        usage_history=[],
        content_hash=None,
        version=1,
    )


def _l3(*, title: str) -> L3Entry:
    now = datetime.now(UTC)
    return L3Entry(
        id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        team="平台组",
        title=title,
        summary="团队知识摘要",
        category="policy",
        status="published",
        hits=0,
        contributor="管理员",
        updated_at=now,
        created_at=now,
    )


def _policy(*, label: str = "keep") -> RetentionPolicy:
    now = datetime.now(UTC)
    return RetentionPolicy(
        id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        layer="l2",
        label=label,
        description="测试策略",
        ttl_minutes=1440,
        max_items=100,
        storage_mb=64,
        eviction="lru",
        hit_rate=0.5,
        updated_at=now,
        created_at=now,
    )


@pytest.mark.asyncio
async def test_a_disabled_agent_writes_nothing() -> None:
    """**关掉记忆 → 一条不写** ✓（后台改绑定 → 行为立刻变 ✓）。"""
    catalog = InMemoryCatalog()
    service = MemoryRuntimeService(catalog)
    outcome = await service.write_turn(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        user_id=USER,
        session_id=uuid4(),
        user_input="记住：我在上海办公",
        policy=MemoryPolicy(enabled=False),
    )
    assert outcome.written == []
    assert outcome.skipped == "policy_disabled"
    assert catalog.l2 == {}


@pytest.mark.asyncio
async def test_the_workspace_scope_is_refused_explicitly() -> None:
    """**工作区级写不了 → 明确跳过** ✓（不静默降级 ✓）。"""
    catalog = InMemoryCatalog()
    service = MemoryRuntimeService(catalog)
    outcome = await service.write_turn(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        user_id=USER,
        session_id=uuid4(),
        user_input="记住：我在上海办公",
        policy=MemoryPolicy(scope=MemoryScope.WORKSPACE),
    )
    assert outcome.skipped == "scope_unsupported"
    assert catalog.l2 == {}


@pytest.mark.asyncio
async def test_the_policy_label_is_resolved() -> None:
    """**``policyLabel`` 解析成保留策略** ✓（绑定看得见 ✓）。"""
    catalog = InMemoryCatalog()
    retention = _policy(label="keep-forever")
    catalog.policies[retention.id] = retention
    service = MemoryRuntimeService(catalog)
    outcome = await service.write_turn(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        user_id=USER,
        session_id=uuid4(),
        user_input="记住：我在上海办公",
        policy=MemoryPolicy(policy_label="keep-forever"),
    )
    assert outcome.written
    assert outcome.retention_label == "keep-forever"


@pytest.mark.asyncio
async def test_the_session_scope_only_recalls_that_session() -> None:
    """**会话作用域真的过滤** ✓（不再只是标签 ✗✗）。"""
    catalog = InMemoryCatalog()
    mine = uuid4()
    other = uuid4()
    catalog.l2[uuid4()] = _l2(session_id=mine, value="我在上海办公")
    catalog.l2[uuid4()] = _l2(session_id=other, value="我在北京办公")
    service = MemoryRuntimeService(catalog)
    hits = await service.recall(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        user_id=USER,
        query="我在",
        session_id=mine,
        policy=MemoryPolicy(scope=MemoryScope.SESSION),
    )
    assert len(hits) == 1
    assert "上海" in hits[0].content
    assert "北京" not in hits[0].content


@pytest.mark.asyncio
async def test_the_pinned_entry_is_always_recalled() -> None:
    """**显式绑定的 L3 一定被召回** ✓（哪怕关键词不匹配 ✓）。"""
    catalog = InMemoryCatalog()
    entry = _l3(title="差旅报销标准")
    catalog.l3[entry.id] = entry
    service = MemoryRuntimeService(catalog)
    hits = await service.recall(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        user_id=USER,
        query="完全无关的问题",
        policy=MemoryPolicy(
            l3_entry_ids=(str(entry.id),),
            knowledge_refs=(MemoryRef(kind=MemoryRefKind.L3, ref_id=str(entry.id)),),
        ),
    )
    assert [hit.source_id for hit in hits] == [str(entry.id)]


@pytest.mark.asyncio
async def test_the_bound_l2_memory_is_also_recalled() -> None:
    """**引用的 L2 记忆也要被召回** ✓（§7.1 的 ``knowledge_refs`` ✓）。"""
    catalog = InMemoryCatalog()
    fact = _l2(session_id=uuid4(), value="我的生日是 3 月 1 日")
    catalog.l2[fact.id] = fact
    service = MemoryRuntimeService(catalog)
    hits = await service.recall(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        user_id=USER,
        query="完全无关的问题",
        policy=MemoryPolicy(
            knowledge_refs=(MemoryRef(kind=MemoryRefKind.MEMORY, ref_id=str(fact.id)),),
        ),
    )
    assert [hit.source_id for hit in hits] == [str(fact.id)]


@pytest.mark.asyncio
async def test_the_pinned_entry_of_another_user_is_not_leaked() -> None:
    """**绑定别人的记忆也看不见** ✓（不串号 ✓ —— 决策 #11 ✓）。"""
    catalog = InMemoryCatalog()
    fact = _l2(session_id=uuid4(), value="别人的记忆")
    fact.user_id = uuid4()
    catalog.l2[fact.id] = fact
    service = MemoryRuntimeService(catalog)
    hits = await service.recall(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        user_id=USER,
        query="完全无关的问题",
        policy=MemoryPolicy(
            knowledge_refs=(MemoryRef(kind=MemoryRefKind.MEMORY, ref_id=str(fact.id)),),
        ),
    )
    assert hits == []


class _FakeBuffer:
    """**会话缓冲**的替身 ✓。"""

    def __init__(self) -> None:
        self.rows: list[BufferRow] = []

    async def add(self, row: BufferRow) -> None:
        self.rows.append(row)

    async def list_pending(self, *, before, limit: int = 100):  # type: ignore[no-untyped-def]
        return [row for row in self.rows if row.created_at <= before][:limit]

    async def delete(self, row_ids) -> None:  # type: ignore[no-untyped-def]
        self.rows = [row for row in self.rows if row.id not in row_ids]


@pytest.mark.asyncio
async def test_the_session_scope_lands_in_the_buffer() -> None:
    """**会话级策略 → 落会话缓冲** ✓（不是 L2 ✓ —— 决策 #5 ✓）。"""
    catalog = InMemoryCatalog()
    buffer = _FakeBuffer()
    service = MemoryRuntimeService(catalog, buffer=buffer)
    outcome = await service.write_turn(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        user_id=USER,
        session_id=uuid4(),
        user_input="记住：我在上海办公",
        policy=MemoryPolicy(scope=MemoryScope.SESSION),
    )
    assert outcome.written
    # ⚠️ **L2 里没有** ✓（它还在缓冲里 ✓ —— 会话结束才提炼 ✓）。
    assert catalog.l2 == {}
    assert len(buffer.rows) == 1
    assert buffer.rows[0].content == "记住：我在上海办公"
