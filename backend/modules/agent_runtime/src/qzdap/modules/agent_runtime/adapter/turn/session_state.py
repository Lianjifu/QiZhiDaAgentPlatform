"""``SessionStatePort`` 的实现 —— 会话行的读改（合并，不是覆盖 ✓）。

⚠️ **不再写** ``wait_status`` —— 那列**整体退役**（台账 X6 ✅）：互斥职责
迁到了 ``current_turn_id``（台账 R3），审批挂起落到了
``session_turns.pending_approval``（Session 方案 §8）✓。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from qzdap_agent_runtime.session.turn_runner import SessionStatePort

from qzdap.modules.agent_runtime.application.ports import SessionRepository


class SqlSessionState(SessionStatePort):
    """会话状态的读改 ✓。"""

    def __init__(self, sessions: SessionRepository) -> None:
        self._sessions = sessions

    async def patch_session(
        self,
        *,
        session_id: UUID,
        metadata: Mapping[str, Any] | None = None,
        resume_state: Mapping[str, Any] | None = None,
    ) -> None:
        """改会话的元数据 / 续传状态 ✓。

        ⚠️ **metadata 是「替换」而不是「逐字段合并」** —— 调用方传的是
        **快照 + 本轮的修改**（契约层维护累加器 ✓），这样并发下别的请求
        改了 metadata 也会被覆盖 —— 与旧实现**同语义** ✓（不引入新行为）。

        ⚠️ **续传状态归 ``metadata["resume"]``** ✓（台账 **X3** ✓ ——
        旧的续传状态列**退役** ✓ —— 新的循环不写它 ✓）。
        """
        session = await self._sessions.get(session_id)
        if session is None:
            return
        updated = session
        if metadata is not None:
            updated = updated.with_runtime(metadata=dict(metadata))
        if resume_state is not None:
            merged = dict(updated.metadata or {})
            merged["resume"] = dict(resume_state)
            updated = updated.with_runtime(metadata=merged)
        await self._sessions.update(updated)


__all__ = ["SqlSessionState"]
