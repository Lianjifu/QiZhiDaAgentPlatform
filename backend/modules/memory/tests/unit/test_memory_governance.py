"""**记忆域的数据主体 scope** ✓（C9 ✓ —— 决策 #8 ✓）。

验收 ✓：
- **删要删干净** ✓ —— L2 行 ✓ + **向量同步删** ✓ + 会话缓冲 ✓；
- **导出给全量** ✓ —— 内容与来源 ✓；
- **缺工作区明确失败** ✓（不猜 ✓）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from qzdap.modules.memory.application.governance import MemoryDataSubjectScope
from qzdap.modules.memory.domain.entities import L2Fact
from qzdap_agent_runtime.governance.data_subject import DataSubjectRequest
from qzdap_agent_runtime.memory.refine import BufferRow

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
USER = UUID("00000000-0000-0000-0000-000000000003")
OTHER_USER = UUID("00000000-0000-0000-0000-0000000000ff")


class _Catalog:
    """**只实现这个 scope 用到的那几个方法** ✓。"""

    def __init__(self) -> None:
        self.rows: dict[UUID, L2Fact] = {}

    async def list_l2(self, workspace_id: UUID, *, user_id: UUID | None = None) -> list[L2Fact]:
        return [
            row
            for row in self.rows.values()
            if row.workspace_id == workspace_id and (user_id is None or row.user_id == user_id)
        ]

    async def delete_l2(self, ids: list[UUID]) -> int:
        victims = [item for item in ids if item in self.rows]
        for item in victims:
            del self.rows[item]
        return len(victims)


class _Vectors:
    def __init__(self) -> None:
        self.deleted: list[UUID] = []

    async def delete(self, ids: list[UUID]) -> None:
        self.deleted.extend(ids)


class _Buffer:
    def __init__(self) -> None:
        self.rows: list[BufferRow] = []
        self.deleted_users: list[tuple[UUID, UUID]] = []

    async def delete_user(self, *, workspace_id: UUID, user_id: UUID) -> int:
        self.deleted_users.append((workspace_id, user_id))
        victims = [row for row in self.rows if row.user_id == user_id]
        self.rows = [row for row in self.rows if row.user_id != user_id]
        return len(victims)


def _fact(user_id: UUID) -> L2Fact:
    now = datetime.now(UTC)
    return L2Fact(
        id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        user_name="张文佳",
        user_id=user_id,
        key="答复风格",
        value="喜欢精简答复",
        category="preference",
        source_session="s-1",
        confidence=0.9,
        status="confirmed",
        promoted_to_l3=False,
        updated_at=now,
        created_at=now,
    )


def _request(*, user_id: UUID = USER, workspace_id: UUID | None = WORKSPACE) -> DataSubjectRequest:
    return DataSubjectRequest(tenant_id=TENANT, user_id=user_id, workspace_id=workspace_id)


@pytest.mark.asyncio
async def test_the_delete_removes_the_facts_the_vectors_and_the_buffers() -> None:
    """**删干净** ✓ —— L2 ✓ + 向量 ✓ + 缓冲 ✓。"""
    catalog = _Catalog()
    vectors = _Vectors()
    buffer = _Buffer()
    fact = _fact(USER)
    catalog.rows[fact.id] = fact
    buffer.rows.append(
        BufferRow(
            id=uuid4(),
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            session_id=uuid4(),
            user_id=USER,
            turn_id=uuid4(),
            content="会议纪要要点",
            content_hash="h",
            created_at=datetime.now(UTC),
        )
    )
    scope = MemoryDataSubjectScope(catalog=catalog, vectors=vectors, buffer=buffer)  # type: ignore[arg-type]

    result = await scope.delete(_request())

    assert result["facts"] == 1
    assert catalog.rows == {}
    # ⚠️ **向量同步删** ✓ —— 不删就是**残留副本** ✗✗。
    assert vectors.deleted == [fact.id]
    assert result["buffers"] == 1
    assert buffer.rows == []


@pytest.mark.asyncio
async def test_the_delete_only_touches_that_user() -> None:
    """**别人的记忆不动** ✓（不串号 ✓ —— 决策 #11 ✓）。"""
    catalog = _Catalog()
    mine = _fact(USER)
    theirs = _fact(OTHER_USER)
    catalog.rows[mine.id] = mine
    catalog.rows[theirs.id] = theirs
    scope = MemoryDataSubjectScope(catalog=catalog)  # type: ignore[arg-type]

    await scope.delete(_request())

    assert list(catalog.rows) == [theirs.id]


@pytest.mark.asyncio
async def test_the_export_gives_the_facts_back() -> None:
    """**导出给全量** ✓ —— 内容与来源 ✓。"""
    catalog = _Catalog()
    fact = _fact(USER)
    catalog.rows[fact.id] = fact
    scope = MemoryDataSubjectScope(catalog=catalog)  # type: ignore[arg-type]

    exported = await scope.export(_request())

    assert len(exported["facts"]) == 1
    assert exported["facts"][0]["value"] == "喜欢精简答复"
    assert exported["facts"][0]["key"] == "答复风格"


@pytest.mark.asyncio
async def test_a_missing_workspace_fails_loudly() -> None:
    """**缺工作区明确失败** ✓ —— 不猜 ✓（记忆是工作区级的 ✓）。"""
    scope = MemoryDataSubjectScope(catalog=_Catalog())  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        await scope.delete(_request(workspace_id=None))
