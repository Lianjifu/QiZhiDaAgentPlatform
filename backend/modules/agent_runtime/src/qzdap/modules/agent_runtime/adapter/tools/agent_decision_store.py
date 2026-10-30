"""``JournalAgentDecisionStore`` —— **专家选择的留痕** ✓（A-24 ✓）。

⚠️ **两处一起写** ✓：
- `session_turns.agent_decision` —— **轮次级快照** ✓（最后一个专家 ✓）；
- `session_events` 的 `agent.expert.selected` —— **追加式** ✓（完整历史 ✓）。

⚠️ **只记「用了什么」** ✓ —— 专家 id ✓ / 版本 ✓ / 任务类型 ✓ / 解析出的模型 ✓
与工具集 ✓ —— **不记「为什么挑了它」** ✓（理由会变 ✓ 用法是事实 ✓）。

⚠️ **不写 `route_decision`** ✓ —— 那是 **Router 层**的列 ✓（会话入口的策略
决策 ✓）—— **两列两写者** ✓（§4.5 ✓）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from qzdap.modules.agent_runtime.adapter.persistence.session_journal import (
    PostgresSessionJournal,
)
from qzdap.modules.agent_runtime.application.ports import AgentDecisionPort

#: **每步选择专家的事件名** ✓（方案 §12.3 ✓）。
EXPERT_SELECTED_EVENT = "agent.expert.selected"


class JournalAgentDecisionStore(AgentDecisionPort):
    """**把专家选择写进轮次与事件流** ✓。"""

    def __init__(self, journal: PostgresSessionJournal) -> None:
        self._journal = journal

    async def record(
        self,
        *,
        turn_id: UUID,
        decision: dict[str, Any],
        event_seq: int | None = None,
    ) -> None:
        """**记一次专家选择** ✓（快照 + 事件 ✓）。"""
        await self._journal.record_agent_decision(turn_id=turn_id, decision=decision)
        seq = (
            event_seq
            if event_seq is not None
            else await self._journal.next_event_seq(turn_id=turn_id)
        )
        await self._journal.append_event(
            turn_id=turn_id,
            seq=seq,
            event_type=EXPERT_SELECTED_EVENT,
            payload=decision,
        )


__all__ = ["EXPERT_SELECTED_EVENT", "JournalAgentDecisionStore"]
