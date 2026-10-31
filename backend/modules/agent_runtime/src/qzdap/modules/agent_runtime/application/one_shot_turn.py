"""「建会话 → 跑一轮 → 收结果」—— **内部**调用方的一条龙（子代理 / 评估 / 委派）。

⚠️ **它不是第二套 turn 实现** —— 轮次编排仍然只有契约层的 ``TurnRunner``
一个 ✓（Session 方案 §6）。这里只是把三步**串起来**，省得每个调用方各写一遍
（那正是旧 ``run_turn_to_completion`` 的下场 ✗）。

⚠️ **幂等是 weak 的**（内容指纹）—— 内部调用**不该被内容指纹抑制**（两次
同样内容的调用是两次真的调用 ✓；决策 #5：weak 只记录不抑制 ✓）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from qzdap.modules.agent_runtime.application.copilot import CopilotSessionService
from qzdap.modules.agent_runtime.application.use_cases.create_session import (
    CreateSessionUseCase,
)
from qzdap_agent_runtime.gateway.normalizer import resolve_idempotency_key
from qzdap_agent_runtime.gateway.types import ChannelType
from qzdap_agent_runtime.session.completion import TurnCompletion, drain_to_completion
from qzdap_schema.ids import AgentId, TenantId, UserId, WorkspaceId


@dataclass(frozen=True, slots=True)
class OneShotTurn:
    """一次「建会话 + 跑一轮」的结果 ✓。"""

    session_id: UUID
    completion: TurnCompletion


class OneShotTurnService:
    """内部调用方的「跑一轮」入口 ✓。"""

    def __init__(
        self,
        *,
        create_session: CreateSessionUseCase,
        copilot: CopilotSessionService,
    ) -> None:
        self._create_session = create_session
        self._copilot = copilot

    async def run(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        agent_id: UUID,
        agent_version: str,
        user_input: str,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
        close_session: bool = False,
    ) -> OneShotTurn:
        session = await self._create_session.execute(
            tenant_id=TenantId(tenant_id),
            workspace_id=WorkspaceId(workspace_id),
            owner_id=UserId(owner_id),
            agent_id=AgentId(agent_id),
            agent_version=agent_version,
            metadata=metadata or {},
        )
        completion = await self.run_on_session(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            session_id=session.id,
            user_input=user_input,
            model=model,
        )
        if close_session:
            await self._copilot.close_session(tenant_id=tenant_id, session_id=session.id)
        return OneShotTurn(session_id=session.id, completion=completion)

    async def run_on_session(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        session_id: UUID,
        user_input: str,
        model: str | None = None,
    ) -> TurnCompletion:
        """在**既有**会话上跑一轮 ✓（会话由调用方建 —— 委派那条路要带元数据）。"""
        # weak 键（内容指纹）—— **只记录不抑制** ✓（内部调用不该被抑制）。
        key = resolve_idempotency_key(
            channel=str(ChannelType.WEB),
            chat_id=str(session_id),
            user_id=str(owner_id),
            text=user_input,
        )
        chunks = self._copilot.stream_turn(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            session_id=session_id,
            user_input=user_input,
            model=model,
            idempotency_key=key,
        )
        return await drain_to_completion(chunks)


__all__ = ["OneShotTurn", "OneShotTurnService"]
