"""``CancelProbePort`` 的实现 —— 取消标记（跨进程可见 ✓）。

⚠️ **复用既有机制**（Session 方案 §1.7 ✓）：取消标记存在会话行的
``metadata.cancel_requested`` 里 —— 读端**直接读列**（不经过 identity map），
所以另一个 worker 写的标记这里也看得见 ✓。
"""

from __future__ import annotations

from uuid import UUID

from qzdap.modules.agent_runtime.application.ports import SessionRepository
from qzdap_agent_runtime.session.turn_runner import CancelProbePort


class SqlCancelProbe(CancelProbePort):
    """取消标记的探针 ✓。"""

    def __init__(self, sessions: SessionRepository) -> None:
        self._sessions = sessions

    async def is_cancel_requested(self, *, session_id: UUID) -> bool:
        return await self._sessions.cancel_requested(session_id)


__all__ = ["SqlCancelProbe"]
