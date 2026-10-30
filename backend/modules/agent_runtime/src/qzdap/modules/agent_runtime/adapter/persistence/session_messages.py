"""``SessionMessagePort`` 的 SQL 实现 —— 消息存取（**只写新表 / 读新表** ✓）。

依据：Session 方案 §5.2 / §7（Stage 2 的 S-13 / S-15）。

**现在的形态**：

| 动作 | 落点 | 为什么 |
|---|---|---|
| 写 | **只写新表** ``session_messages``（带会话内序号 ``session_seq``）✓ | 旧表**已停写**（2026-10-30，S-15b ✓）—— 它现在只作为**只读兜底**留着 ✓，到 Stage 6 的 S-36 才 DROP ✓ |
| 读 | **新表**（2026-10-30，S-15a 切读 ✓） | 旧表的历史已由**迁移 0054** 搬进新表 ✓；对账差异为 0 是切读的前置 ✓（脚本：``scripts/verify_session_tables.py`` ✓） |

⚠️ **切读顺带修掉一个真 bug**：旧表只能按**轮次内**的 ``seq`` 排序 ✗ ——
多轮会话的历史会**交错**（第一轮的第 2 条排在第二轮的第 1 条后面 ✗✗）；
新表有会话内的 ``session_seq`` ✓ → 按它排就是**真实先后** ✓。

⚠️ **会话内序号由计数器分配**（``next_message_seq``，迁移 0052）—— 调用方
自己算 ``MAX(session_seq) + 1`` 会在并发下撞唯一索引 ✗✗。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from qzdap_agent_runtime.session.message import SessionMessagePort
from qzdap_agent_runtime.session.sequence import SessionSequencePort
from qzdap_persistence.tenant_guard import current_tenant_id
from sqlalchemy import select

from qzdap.modules.agent_runtime.adapter.persistence.models import (
    SessionMessageORM,
    SessionTurnORM,
)
from qzdap.modules.agent_runtime.adapter.persistence.session_sequence import (
    PostgresSessionSequence,
)

_log = logging.getLogger(__name__)


class PostgresSessionMessageStore(SessionMessagePort):
    """会话消息的存取 —— **只写新表、读新表** ✓（旧表已停写 S-15b ✓）。"""

    def __init__(
        self,
        session: Any,
        *,
        sequence: SessionSequencePort | None = None,
    ) -> None:
        self._s = session
        self._sequence = sequence or PostgresSessionSequence(session)

    async def list_for_session(self, session_id: UUID) -> list[dict[str, Any]]:
        """会话的消息列表 —— **读新表** ✓（切读 S-15a，2026-10-30）。

        ⚠️ **按 ``session_seq`` 排** ✓ —— 那是会话内的写入顺序 ✓（真实先后 ✓）。
        旧表只能按**轮次内**的 ``seq`` 排 ✗ → 多轮会话的历史会**交错** ✗✗。

        ⚠️ **按租户过滤** ✓ —— 新表**没有** ``tenant_id`` 列 ✓ → JOIN 轮次表
        取 ✓（与事件读同一个口径 ✓）。
        """
        result = await self._s.execute(
            select(SessionMessageORM, SessionTurnORM.tenant_id)
            .join(SessionTurnORM, SessionTurnORM.id == SessionMessageORM.turn_id)
            .where(SessionMessageORM.session_id == session_id)
            .order_by(SessionMessageORM.session_seq.asc())
        )
        bound = current_tenant_id()
        out: list[dict[str, Any]] = []
        for row, tenant_id in result.all():
            if bound is not None and tenant_id != bound:
                continue
            metadata = dict(row.metadata_ or {})
            out.append(
                {
                    # 新表没有独立的行 id ✓ —— 用「轮次 + 轮次内序号」拼一个 ✓
                    # （调用方只把它当**标识**用 ✓）。
                    "id": f"{row.turn_id}:{row.seq}",
                    "role": row.role,
                    "content": row.content,
                    # 工具名在 ``metadata_`` 里 ✓（与迁移 0054 的映射一致 ✓）。
                    "toolName": str(metadata.get("tool_name") or ""),
                    "seq": row.seq,
                    "turnId": str(row.turn_id),
                }
            )
        return out

    async def next_seq(self, *, session_id: UUID) -> int:
        """下一个轮次内消息序号 —— 读**新表**的最大序号 +1 ✓。

        ⚠️ 读的是**新表** ✓（切读 S-15a）—— 两张表同步写入 ✓，读哪张都一样 ✓。
        """
        rows = await self.list_for_session(session_id)
        return (rows[-1]["seq"] + 1) if rows else 0

    async def append(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        session_id: UUID,
        turn_id: UUID | None,
        seq: int,
        role: str,
        content: str,
        tool_name: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """追加一条消息 —— **只写新表** ✓（旧表已停写 ✓）。

        ⚠️ **``turn_id`` 不能为空**：新表的外键指向 ``session_turns.id``，
        没有轮次的消息在新表里**无处安放** ✗。这不是运行期能兜的场景 ——
        调用方（copilot）一定有轮次 ✓。
        """
        if turn_id is None:
            raise ValueError("session message requires turn_id (new table FK)")

        session_seq = await self._sequence.next_message_seq(
            tenant_id=tenant_id, session_id=session_id
        )
        # ⚠️ **工具名进 ``metadata_``** ✓ —— 新表没有独立的 tool_name 列 ✓；
        # 不带上的话，切读之后工具消息会**丢掉工具名** ✗✗（迁移 0054 的映射
        # 也是这么放的 ✓ —— 两边口径一致 ✓）。
        metadata = dict(extra or {})
        if tool_name:
            metadata["tool_name"] = tool_name
        self._s.add(
            SessionMessageORM(
                turn_id=turn_id,
                seq=seq,
                role=role,
                content=content,
                metadata_=metadata or None,
                session_id=session_id,
                session_seq=session_seq,
            )
        )
        _log.debug(
            "session_message_appended session_id=%s turn_id=%s seq=%s session_seq=%s",
            session_id,
            turn_id,
            seq,
            session_seq,
        )


__all__ = ["PostgresSessionMessageStore"]
