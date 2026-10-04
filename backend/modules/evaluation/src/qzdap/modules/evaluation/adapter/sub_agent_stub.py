"""Stub SubAgentPort for development shells without a runtime.

Returns a deterministic echo of the input — heuristic scoring will fail
most cases until the runtime wires up.  Lets lifespan boot succeed in
slim dev shells where ``agent_runtime_factory`` is not installed.
"""

from __future__ import annotations

from typing import Any

from qzdap_schema.ids import (
    AgentTemplateId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.evaluation.application.ports import SubAgentPort


class StubSubAgentPort(SubAgentPort):
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
        return {"final_message": f"[stub:{user_input}]"}


__all__ = ["StubSubAgentPort"]
