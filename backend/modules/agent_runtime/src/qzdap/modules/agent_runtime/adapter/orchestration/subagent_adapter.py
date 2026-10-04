"""Adapter implementing ``SubAgentPort`` for agent_runtime.

The orchestration ``WorkflowExecutor`` invokes a sub-agent via this
port without importing agent_runtime directly.  Each call:

1. Opens a fresh DB session via the container's session factory.
2. Builds an :class:`AgentRuntimeService` from the injected factory.
3. Creates a short-lived :class:`Session` for ``(agent_id, agent_version)``.
4. Drains the new ``RunTurnCompletionUseCase`` to a structured
   :class:`SubAgentResult`.
5. Closes the session (best-effort) and returns the result.

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

from qzdap.modules.agent_runtime.application.services import AgentRuntimeService

logger = logging.getLogger(__name__)


# Type aliases for the dependencies the lifespan passes in.
AgentRuntimeFactory = Callable[[Any], AgentRuntimeService]
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
        agent_runtime_factory: AgentRuntimeFactory | None,
        session_maker: SessionMaker | None,
    ) -> None:
        self._factory = agent_runtime_factory
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
        if self._factory is None or self._maker is None:
            raise AppError(
                "SubAgentAdapter is not wired (agent_runtime factory or "
                "session maker missing)",
                code="SUB_AGENT_UNAVAILABLE",
                status=503,
            )

        import asyncio

        model = model_override or "default"
        factory = self._factory
        maker = self._maker
        assert factory is not None
        assert maker is not None

        async def _drive() -> SubAgentResult:
            session = maker()
            try:
                ar_service: AgentRuntimeService = factory(session)
                session_row = await ar_service.create_session().execute(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_id=owner_id,
                    agent_id=AgentId(agent_id),
                    agent_version=agent_version,
                    metadata={
                        "origin": "orchestration:sub_agent",
                        "trace_id": current_trace_id(),
                    },
                )
                completion = await ar_service.run_turn_to_completion().execute(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_id=owner_id,
                    session_id=session_row.id,
                    user_input=user_input,
                    model=model,
                )
                await ar_service.close_session().execute(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    session_id=session_row.id,
                )
                # best-effort commit; the session is closed at the end
                # of the request anyway.
                try:
                    await session.commit()
                except Exception:
                    logger.exception(
                        "SubAgentAdapter commit failed; rolling back",
                        extra={"session_id": str(session_row.id)},
                    )
                    await session.rollback()
                return SubAgentResult(
                    final_message=completion.final_message or "",
                    turn_id=completion.turn_id,
                    input_tokens=completion.input_tokens,
                    output_tokens=completion.output_tokens,
                    metadata={
                        "session_id": str(session_row.id),
                        "agent_id": str(agent_id),
                        "agent_version": agent_version,
                        "finished_at": datetime.now(UTC).isoformat(),
                    },
                )
            finally:
                await session.close()

        return await asyncio.wait_for(_drive(), timeout=timeout_seconds)


__all__ = ["AgentRuntimeFactory", "SessionMaker", "SubAgentAdapter", "SubAgentResult"]
_ = (SessionId,)
