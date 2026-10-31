"""Memory Stage 5：**会话缓冲的提炼** ✓（M-29 ✓）。

验收覆盖 ✓：

- **会话还在跑 → 不动** ✓（不把进行中的对话提炼掉 ✓）；
- **会话结束了 → 提炼成 L2** ✓；
- **过期 → 丢弃** ✓（不留垃圾 ✓）；
- **提炼完的行被删掉** ✓。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from qzdap_agent_runtime.memory.refine import (
    BufferRefiner,
    BufferRow,
)
from qzdap_agent_runtime.memory.writer import WriteOutcome


class _Buffer:
    def __init__(self, rows: list[BufferRow] | None = None) -> None:
        self.rows = rows or []
        self.deleted: list[tuple] = []

    async def add(self, row: BufferRow) -> None:
        self.rows.append(row)

    async def list_pending(self, *, before: datetime, limit: int = 100) -> list[BufferRow]:
        return [row for row in self.rows if row.created_at <= before][:limit]

    async def delete(self, row_ids: tuple) -> None:
        self.deleted.append(row_ids)
        self.rows = [row for row in self.rows if row.id not in row_ids]


class _Activity:
    def __init__(self, active: set | None = None) -> None:
        self.active = active or set()

    async def active_session_ids(self, *, session_ids: tuple) -> set:
        return {sid for sid in session_ids if sid in self.active}


class _Writer:
    def __init__(self) -> None:
        self.written: list[str] = []

    async def write_fact(self, **kwargs) -> WriteOutcome:  # type: ignore[no-untyped-def]
        self.written.append(str(kwargs["content"]))
        return WriteOutcome(written=[{"id": str(uuid4())}])


def _row(*, session_id, content: str, age_hours: float = 0.0) -> BufferRow:
    return BufferRow(
        id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        session_id=session_id,
        user_id=uuid4(),
        turn_id=None,
        content=content,
        content_hash=content,
        created_at=datetime.now(UTC) - timedelta(hours=age_hours),
    )


class TestTheRefinement:
    @pytest.mark.asyncio
    async def test_a_finished_session_is_promoted(self) -> None:
        """**会话结束了 → 提炼成 L2** ✓。"""
        session_id = uuid4()
        buffer = _Buffer([_row(session_id=session_id, content="我在上海办公")])
        writer = _Writer()
        refiner = BufferRefiner(buffer=buffer, activity=_Activity(), writer=writer)
        report = await refiner.refine(now=datetime.now(UTC))
        assert report.promoted == 1
        assert writer.written == ["我在上海办公"]
        # ⚠️ **处理完的行被删掉** ✓（不留垃圾 ✓）。
        assert buffer.rows == []

    @pytest.mark.asyncio
    async def test_a_running_session_is_left_alone(self) -> None:
        """**会话还在跑 → 不动** ✓（不提炼进行中的对话 ✓）。"""
        session_id = uuid4()
        buffer = _Buffer([_row(session_id=session_id, content="我在上海办公")])
        writer = _Writer()
        refiner = BufferRefiner(buffer=buffer, activity=_Activity({session_id}), writer=writer)
        report = await refiner.refine(now=datetime.now(UTC))
        assert report.promoted == 0
        assert writer.written == []
        assert len(buffer.rows) == 1

    @pytest.mark.asyncio
    async def test_expired_rows_are_discarded(self) -> None:
        """**过期 → 丢弃** ✓（不留垃圾 ✓）。"""
        session_id = uuid4()
        buffer = _Buffer([_row(session_id=session_id, content="很久以前的事", age_hours=48)])
        writer = _Writer()
        refiner = BufferRefiner(
            buffer=buffer,
            activity=_Activity(),
            writer=writer,
            ttl=timedelta(hours=24),
        )
        report = await refiner.refine(now=datetime.now(UTC))
        assert report.discarded == 1
        assert report.promoted == 0
        assert writer.written == []
        assert buffer.rows == []
