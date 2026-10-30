"""Real SubAgentPort — drives the agent_runtime with the agent under test.

Each call:

1. Looks up the ``AgentVersion`` via ``AgentFactoryQueryPort`` so we know
   which ``model_id`` (string) the agent was configured for.
2. Creates a fresh session and drains a single turn via the agent_runtime's
   ``OneShotTurnService`` —— **唯一 turn 实现**（旧的第二套 turn 实现，
   台账 X2，已删 ✓）。

The adapter raises ``AppError`` on agent_runtime failures so the
runner can convert them to per-case score errors.
"""

from __future__ import annotations

import asyncio
from typing import Any

from qzdap.modules.agent_runtime.application.one_shot_turn import (
    OneShotTurnService,
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
        one_shot: OneShotTurnService,
        agent_factory: AgentFactoryQueryPort,
    ) -> None:
        self._one_shot = one_shot
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

        # ── 建会话 + 跑一轮（唯一 turn 实现 ✓）────────────────────────
        # ⚠️ 会话用**显式的 agent_version**（评测跑的是被测版本 ✓）——
        # 新链路的会话由 :class:`OneShotTurnService` 建 ✓。
        turn = await asyncio.wait_for(
            self._one_shot.run(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_id=owner_id,
                agent_id=AgentId(agent_id),  # template UUID re-used as agent id
                agent_version=str(version.version_tag),
                user_input=user_input,
                model=model_id,
                metadata={"evaluation": True},
                # 关掉会话 —— 别泄漏（与旧实现同口径 ✓）。
                close_session=True,
            ),
            timeout=timeout_seconds,
        )
        completion = turn.completion

        return {
            "final_message": completion.final_message or "",
            "turn_id": str(completion.turn_id),
            "input_tokens": completion.input_tokens,
            "output_tokens": completion.output_tokens,
        }


__all__ = ["RealSubAgentPort"]