"""Adapter implementing ``SubAgentPort`` for agent_runtime.

The orchestration ``WorkflowExecutor`` invokes a sub-agent via this
port without importing agent_runtime directly.  Each call:

1. Opens a fresh DB session via the container's session factory.
2. Builds a :class:`OneShotTurnService` from the injected factory.
3. Creates a short-lived session for ``(agent_id, agent_version)`` and
   drains **one** turn through the **唯一 turn 实现**（契约层的
   ``TurnRunner`` —— 旧的第二套 turn 实现，台账 X2，已删 ✓）。
4. Closes the session and returns a structured :class:`SubAgentResult`.

The adapter is intentionally stateless; the only thing it carries is
references to the per-request factories and the session maker.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from qzdap_kernel.contextvars import current_trace_id
from qzdap_kernel.errors import AppError
from qzdap_schema.ids import (
    AgentId,
    SessionId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.agent_runtime.application.one_shot_turn import (
    OneShotTurnService,
)

logger = logging.getLogger(__name__)


# Type aliases for the dependencies the lifespan passes in.
OneShotFactory = Callable[[Any], OneShotTurnService]
SessionMaker = Callable[[], Any]


@dataclass(slots=True, frozen=True)
class SubAgentResult:
    final_message: str
    turn_id: UUID
    input_tokens: int = 0
    output_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class SubAgentAdapter:
    """Real drain adapter (P7-7) for :class:`SubAgentPort`."""

    def __init__(
        self,
        *,
        one_shot_factory: OneShotFactory | None,
        session_maker: SessionMaker | None,
    ) -> None:
        self._one_shot_factory = one_shot_factory
        self._maker = session_maker

    async def run_turn_to_completion(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        owner_id: UserId,
        agent_id: UUID,
        agent_version: str,
        user_input: str,
        model_override: str | None = None,
        timeout_seconds: int = 60,
    ) -> SubAgentResult:
        if self._one_shot_factory is None or self._maker is None:
            raise AppError(
                "SubAgentAdapter is not wired (one-shot factory or "
                "session maker missing)",
                code="SUB_AGENT_UNAVAILABLE",
                status=503,
            )

        import asyncio

        model = model_override or "default"
        factory = self._one_shot_factory
        maker = self._maker
        assert factory is not None
        assert maker is not None

        async def _drive() -> SubAgentResult:
            session = maker()
            try:
                turn = await factory(session).run(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_id=owner_id,
                    agent_id=AgentId(agent_id),
                    agent_version=agent_version,
                    user_input=user_input,
                    model=model,
                    metadata={
                        "origin": "orchestration:sub_agent",
                        "trace_id": current_trace_id(),
                    },
                    # 子代理的会话用完即关 ✓（与旧实现同口径 ✓）。
                    close_session=True,
                )
                completion = turn.completion
                # best-effort commit; the session is closed at the end
                # of the request anyway.
                try:
                    await session.commit()
                except Exception:
                    logger.exception(
                        "SubAgentAdapter commit failed; rolling back",
                        extra={"session_id": str(turn.session_id)},
                    )
                    await session.rollback()
                return SubAgentResult(
                    final_message=completion.final_message or "",
                    turn_id=completion.turn_id,
                    input_tokens=completion.input_tokens,
                    output_tokens=completion.output_tokens,
                    metadata={
                        "session_id": str(turn.session_id),
                        "agent_id": str(agent_id),
                        "agent_version": agent_version,
                        "finished_at": datetime.now(UTC).isoformat(),
                    },
                )
            finally:
                await session.close()

        return await asyncio.wait_for(_drive(), timeout=timeout_seconds)


__all__ = ["OneShotFactory", "SessionMaker", "SubAgentAdapter", "SubAgentResult"]
_ = (SessionId,)
