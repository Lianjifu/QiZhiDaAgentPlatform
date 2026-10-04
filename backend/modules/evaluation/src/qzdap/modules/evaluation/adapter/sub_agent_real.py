"""Real SubAgentPort — drives the agent_runtime with the agent under test.

Each call:

1. Looks up the ``AgentVersion`` via ``AgentFactoryQueryPort`` so we know
   which ``model_id`` (string) the agent was configured for.
2. Creates a fresh session against the agent via the agent_runtime's
   ``CreateSessionUseCase``.
3. Drains a single turn to completion via
   ``RunTurnCompletionUseCase`` and returns ``{final_message, ...}`` in
   the shape the evaluator runner expects.

The adapter raises ``AppError`` on agent_runtime failures so the
runner can convert them to per-case score errors.
"""

from __future__ import annotations

import asyncio
from typing import Any

from qzdap.modules.agent_runtime.application.services import (
    AgentRuntimeService,
)
from qzdap_kernel.errors import AppError
from qzdap_schema.ids import (
    AgentId,
    AgentTemplateId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.evaluation.application.ports import (
    AgentFactoryQueryPort,
    SubAgentPort,
)


class RealSubAgentPort(SubAgentPort):
    """Drive the real agent_runtime from inside the eval runner."""

    def __init__(
        self,
        *,
        runtime: AgentRuntimeService,
        agent_factory: AgentFactoryQueryPort,
    ) -> None:
        self._runtime = runtime
        self._agent_factory = agent_factory

    async def run_turn_to_completion(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        owner_id: UserId,
        agent_id: AgentTemplateId,
        agent_version: str,
        user_input: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        # The runner passes the ``AgentVersionId`` as a hex string; we
        # round-trip through ``AgentVersionId`` so the lookup is type-safe.
        from uuid import UUID

        from qzdap_schema.ids import AgentVersionId

        try:
            version_uuid = UUID(agent_version)
        except (TypeError, ValueError) as exc:
            raise AppError(
                f"agent_version {agent_version!r} is not a valid UUID",
                code="EVAL_INVALID_VERSION",
                status=400,
            ) from exc

        version = await self._agent_factory.get_agent_version(
            tenant_id=tenant_id,
            template_id=agent_id,
            version_id=AgentVersionId(version_uuid),
        )
        if version is None:
            raise AppError(
                f"agent version not published: template={agent_id} version={agent_version}",
                code="EVAL_VERSION_NOT_PUBLISHED",
                status=400,
            )

        model_id = version.default_model_id

        # ── create session ────────────────────────────────────────────
        session = await self._runtime.create_session().execute(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            agent_id=AgentId(agent_id),  # template UUID re-used as agent id
            agent_version=str(version.version_tag),
            metadata={"evaluation": True},
        )

        # ── drive a single turn to completion ────────────────────────
        completion = await asyncio.wait_for(
            self._runtime.run_turn_to_completion().execute(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_id=owner_id,
                session_id=session.id,
                user_input=user_input,
                model=model_id,
            ),
            timeout=timeout_seconds,
        )

        # ── close the session so we don't leak ────────────────────────
        try:
            await self._runtime.close_session().execute(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_id=owner_id,
                session_id=session.id,
            )
        except AppError:  # pragma: no cover — best-effort cleanup
            pass

        return {
            "final_message": completion.final_message or "",
            "turn_id": str(completion.turn_id),
            "input_tokens": completion.input_tokens,
            "output_tokens": completion.output_tokens,
        }


__all__ = ["RealSubAgentPort"]