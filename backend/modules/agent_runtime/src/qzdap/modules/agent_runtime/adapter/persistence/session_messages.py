"""``SessionMessagePort`` 的 SQL 实现 —— **双写期**的消息存取。

依据：Session 方案 §5.2 / §7（Stage 2 的 S-13 / S-15）。

**双写期的形态**：

| 动作 | 落点 | 为什么 |
|---|---|---|
| 写 | **新表** ``session_messages``（带会话内序号 ``session_seq``）**+ 旧表** ``agent_session_messages`` | 旧表要留到 Stage 6（对账 + 只读窗口）✓ |
| 读 | **仍读旧表** | 切读（S-15a）要等**对账窗口**，不是本 Stage —— 提前切读 = 用户看到的历史可能缺行 ✗ |

⚠️ **会话内序号由计数器分配**（``next_message_seq``，迁移 0052）—— 调用方
自己算 ``MAX(session_seq) + 1`` 会在并发下撞唯一索引 ✗✗。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from qzdap_agent_runtime.session.message import SessionMessagePort
from qzdap_agent_runtime.session.sequence import SessionSequencePort

from qzdap.modules.agent_runtime.adapter.persistence.catalog_repositories import (
    SqlSessionMessageRepository,
)
from qzdap.modules.agent_runtime.adapter.persistence.models import SessionMessageORM
from qzdap.modules.agent_runtime.adapter.persistence.session_sequence import (
    PostgresSessionSequence,
)

_log = logging.getLogger(__name__)


class PostgresSessionMessageStore(SessionMessagePort):
    """会话消息的存取 —— **写双表、读旧表**（双写期 ✓）。"""

    def __init__(
        self,
        session: Any,
        *,
        sequence: SessionSequencePort | None = None,
    ) -> None:
        self._s = session
        self._sequence = sequence or PostgresSessionSequence(session)
        self._legacy = SqlSessionMessageRepository(session)

    async def list_for_session(self, session_id: UUID) -> list[dict[str, Any]]:
        """会话的消息列表 —— **仍读旧表**（切读在 S-15a ✓）。"""
        return await self._legacy.list_for_session(session_id)

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
        """追加一条消息 —— 新表 + 旧表**都写** ✓。

        ⚠️ **``turn_id`` 不能为空**：新表的外键指向 ``session_turns.id``，
        没有轮次的消息在新表里**无处安放** ✗。这不是运行期能兜的场景 ——
        调用方（copilot）一定有轮次 ✓。
        """
        if turn_id is None:
            raise ValueError("session message requires turn_id (new table FK)")

        session_seq = await self._sequence.next_message_seq(
            tenant_id=tenant_id, session_id=session_id
        )
        self._s.add(
            SessionMessageORM(
                turn_id=turn_id,
                seq=seq,
                role=role,
                content=content,
                metadata_=extra or None,
                session_id=session_id,
                session_seq=session_seq,
            )
        )
        # 旧表 —— **双写**（台账 X4：旧表在 Stage 6 才 DROP）
        await self._legacy.append(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            session_id=session_id,
            turn_id=turn_id,
            seq=seq,
            role=role,
            content=content,
            tool_name=tool_name,
            extra=extra,
        )
        _log.debug(
            "session_message_appended session_id=%s turn_id=%s seq=%s session_seq=%s",
            session_id,
            turn_id,
            seq,
            session_seq,
        )


__all__ = ["PostgresSessionMessageStore"]
