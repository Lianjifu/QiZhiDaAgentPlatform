"""**会话缓冲的管理视图** ✓（M-46 ✓ —— L1 表退役后的唯一来源 ✓）。

验收 ✓：

- 管理端的「L1」**读的是会话缓冲** ✓（不是那张退役的表 ✓）；
- **形状不变** ✓（前端那套 `L1Session` ✓ —— 契约没变 ✓）；
- **冲掉** = 缓冲条目被丢弃 ✓；
- **名字由窄端口补** ✓（Memory 不查会话表 ✓）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from qzdap.modules.memory.application.admin_service import MemoryAdminService
from qzdap.modules.memory.domain.errors import MemoryNotFound
from qzdap_agent_runtime.memory.refine import BufferRow, SessionBufferView
from qzdap_agent_runtime.memory.session_info import SessionInfo

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-0000000000ff")
USER = UUID("00000000-0000-0000-0000-000000000003")


class _Buffer:
    """**内存版**的会话缓冲 ✓（只实现管理面要用的那几个方法 ✓）。"""

    def __init__(self) -> None:
        self.rows: list[BufferRow] = []

    async def add(self, row: BufferRow) -> None:
        self.rows.append(row)

    async def list_pending(self, *, before: datetime, limit: int = 100) -> list[BufferRow]:
        _ = before
        return self.rows[:limit]

    async def delete(self, row_ids: tuple[UUID, ...]) -> None:
        self.rows = [row for row in self.rows if row.id not in row_ids]

    async def list_workspace_views(self, *, workspace_id: UUID) -> list[SessionBufferView]:
        rows = [row for row in self.rows if row.workspace_id == workspace_id]
        if not rows:
            return []
        return [
            SessionBufferView(
                session_id=rows[0].session_id,
                workspace_id=workspace_id,
                user_id=rows[0].user_id,
                items=len(rows),
                total_chars=sum(len(row.content) for row in rows),
                created_at=min(row.created_at for row in rows),
                last_write_at=max(row.created_at for row in rows),
            )
        ]

    async def list_session_rows(self, *, session_id: UUID) -> list[BufferRow]:
        return [row for row in self.rows if row.session_id == session_id]

    async def delete_session(self, *, session_id: UUID) -> int:
        victims = [row for row in self.rows if row.session_id == session_id]
        await self.delete(tuple(row.id for row in victims))
        return len(victims)


class _SessionInfo:
    """**窄端口**的假实现 ✓（会话的展示信息 ✓）。"""

    def __init__(self) -> None:
        self.asked: list[tuple[UUID, ...]] = []

    async def describe(self, session_ids: tuple[UUID, ...]) -> dict[UUID, SessionInfo]:
        self.asked.append(session_ids)
        return {
            session_id: SessionInfo(
                session_id=session_id,
                owner_id=USER,
                agent_name="客服应答助手",
            )
            for session_id in session_ids
        }


class _Catalog:
    """**管理服务用不到目录** ✓（这次的四个方法只碰缓冲 ✓）—— 空的实现 ✓。"""


async def _seed(buffer: _Buffer, *, content: str = "会议纪要要点", session_id: UUID | None = None):
    row = BufferRow(
        id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        session_id=session_id or uuid4(),
        user_id=USER,
        turn_id=uuid4(),
        content=content,
        content_hash=content,
        created_at=datetime.now(UTC),
    )
    await buffer.add(row)
    return row


def _service(buffer: _Buffer, session_info: _SessionInfo | None = None) -> MemoryAdminService:
    return MemoryAdminService(_Catalog(), buffer=buffer, session_info=session_info)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_the_l1_view_reads_the_session_buffer() -> None:
    """**「L1」现在读的是会话缓冲** ✓（L1 表退役了 ✓）。"""
    buffer = _Buffer()
    await _seed(buffer)
    admin = _service(buffer)
    items = await admin.list_l1(workspace_id=WORKSPACE)
    assert len(items) == 1
    assert items[0]["bufferSize"] == len("会议纪要要点")
    assert items[0]["status"] == "active"


@pytest.mark.asyncio
async def test_the_l1_view_keeps_the_frontend_shape() -> None:
    """**形状不变** ✓（前端那套 `L1Session` ✓ —— 契约没变 ✓）。"""
    buffer = _Buffer()
    await _seed(buffer)
    admin = _service(buffer)
    item = (await admin.list_l1(workspace_id=WORKSPACE))[0]
    for field in (
        "id",
        "userName",
        "agentName",
        "bufferSize",
        "tokensUsed",
        "ttlMinutes",
        "ttlRemainMin",
        "status",
        "lastFlush",
        "startedAt",
    ):
        assert field in item, f"缺字段 {field}"


@pytest.mark.asyncio
async def test_the_names_come_from_the_narrow_port() -> None:
    """**名字由窄端口补** ✓（Memory 不查会话表 ✓）。"""
    buffer = _Buffer()
    row = await _seed(buffer)
    session_info = _SessionInfo()
    admin = _service(buffer, session_info)
    item = (await admin.list_l1(workspace_id=WORKSPACE))[0]
    assert item["agentName"] == "客服应答助手"
    assert item["userName"] == str(USER)
    assert session_info.asked == [(row.session_id,)]


@pytest.mark.asyncio
async def test_the_flush_drops_the_buffer_rows() -> None:
    """**冲掉 = 缓冲条目被丢弃** ✓。"""
    buffer = _Buffer()
    row = await _seed(buffer)
    admin = _service(buffer)
    flushed = await admin.flush_l1(row.session_id, workspace_id=WORKSPACE)
    assert flushed["flushed"] == 1
    assert await admin.list_l1(workspace_id=WORKSPACE) == []


@pytest.mark.asyncio
async def test_the_flush_refuses_another_workspace() -> None:
    """**别人的会话冲不掉** ✓。"""
    buffer = _Buffer()
    row = await _seed(buffer)
    admin = _service(buffer)
    with pytest.raises(MemoryNotFound):
        await admin.flush_l1(row.session_id, workspace_id=OTHER_WORKSPACE)


@pytest.mark.asyncio
async def test_a_missing_session_raises() -> None:
    """**没有缓冲就是 404** ✓（不是空壳 ✓）。"""
    admin = _service(_Buffer())
    with pytest.raises(MemoryNotFound):
        await admin.get_l1(uuid4())
