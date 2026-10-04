"""Workflow catalog service — admin CRUD + user projection + run records."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from qzdap.modules.orchestration.application.ports import (
    WorkflowRepository,
    WorkflowRunRepository,
    WorkflowUserStateRepository,
)
from qzdap.modules.orchestration.domain.entities import (
    FLOW_STATUSES,
    TRIGGER_TYPES,
    FlowRun,
    FlowVersion,
    Workflow,
)
from qzdap.modules.orchestration.domain.errors import (
    WorkflowNotFound,
    WorkflowUnavailable,
)


class OrchestrationService:
    def __init__(
        self,
        workflows: WorkflowRepository,
        user_state: WorkflowUserStateRepository,
        runs: WorkflowRunRepository,
    ) -> None:
        self._workflows = workflows
        self._user_state = user_state
        self._runs = runs

    async def list_admin(
        self,
        *,
        workspace_id: UUID,
        status_filter: str = "all",
        q: str = "",
    ) -> list[dict[str, Any]]:
        items = await self._workflows.list_for_workspace(workspace_id)
        query = q.strip().lower()
        filtered: list[Workflow] = []
        for flow in items:
            if status_filter not in ("all", "", None) and flow.status != status_filter:
                continue
            hay = f"{flow.name} {flow.description} {flow.owner} {flow.scene}".lower()
            if query and query not in hay:
                continue
            filtered.append(flow)
        filtered.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_admin_dict() for item in filtered]

    async def get_admin(self, workflow_id: UUID) -> dict[str, Any]:
        return (await self._require(workflow_id)).to_admin_dict()

    async def create(self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]) -> dict[str, Any]:
        trigger = body.get("trigger") if body.get("trigger") in TRIGGER_TYPES else "消息触发"
        status = body.get("status") if body.get("status") in FLOW_STATUSES else "draft"
        nodes = body.get("initialNodes") if isinstance(body.get("initialNodes"), list) else None
        edges = body.get("initialEdges") if isinstance(body.get("initialEdges"), list) else None
        agents = body.get("boundAgents") if isinstance(body.get("boundAgents"), list) else None
        flow = Workflow.create(
            id=_parse_id(body.get("id")),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=str(body.get("name") or "未命名工作流"),
            description=str(body.get("description") or ""),
            owner=str(body.get("owner") or "当前管理员"),
            scene=str(body.get("scene") or "团队协作"),
            trigger=trigger,
            initial_nodes=[item for item in (nodes or []) if isinstance(item, dict)] or None,
            initial_edges=[item for item in (edges or []) if isinstance(item, dict)] or None,
            bound_agents=[str(item) for item in (agents or [])],
            status=status,
            call_count=int(body.get("callCount") or 0),
        )
        if isinstance(body.get("versions"), list) and body["versions"]:
            flow.versions = [
                FlowVersion.from_dict(item) for item in body["versions"] if isinstance(item, dict)
            ]
        await self._workflows.add(flow)
        return flow.to_admin_dict()

    async def update(self, *, workflow_id: UUID, body: dict[str, Any], actor: str) -> dict[str, Any]:
        flow = await self._require(workflow_id)
        patch = body.get("patch") if isinstance(body.get("patch"), dict) else body
        updated = flow.apply_patch(patch, actor=actor)
        await self._workflows.update(updated)
        return updated.to_admin_dict()

    async def delete(self, workflow_id: UUID) -> dict[str, Any]:
        await self._require(workflow_id)
        await self._workflows.delete(workflow_id)
        return {"ok": True, "id": str(workflow_id)}

    async def list_catalog(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._workflows.list_for_workspace(workspace_id)
        return [
            flow.to_catalog_dict()
            for flow in items
            if flow.status == "published"
        ]

    async def set_favorite(self, *, workflow_id: UUID, user_id: UUID, on: bool) -> dict[str, Any]:
        flow = await self._require(workflow_id)
        await self._user_state.set_favorite(
            tenant_id=flow.tenant_id,
            workspace_id=flow.workspace_id,
            user_id=user_id,
            workflow_id=workflow_id,
            on=on,
        )
        return {"id": str(workflow_id), "on": on}

    async def record_run(
        self, *, workflow_id: UUID, user_id: UUID, note: str | None = None
    ) -> dict[str, Any]:
        flow = await self._require(workflow_id)
        if flow.status != "published":
            raise WorkflowUnavailable("workflow unavailable")
        updated = flow.bump_call()
        await self._workflows.update(updated)
        trimmed = (note or "").strip()
        run = FlowRun(
            id=uuid4(),
            tenant_id=flow.tenant_id,
            workspace_id=flow.workspace_id,
            user_id=user_id,
            workflow_id=flow.id,
            name=flow.name,
            time="刚刚",
            result="已记录使用说明" if trimmed else "演示完成",
        )
        await self._runs.add(run)
        return run.to_catalog_dict()

    async def list_runs(self, *, workspace_id: UUID, user_id: UUID) -> list[dict[str, Any]]:
        rows = await self._runs.list_for_user(workspace_id=workspace_id, user_id=user_id)
        return [row.to_catalog_dict() for row in rows]

    async def _require(self, workflow_id: UUID) -> Workflow:
        flow = await self._workflows.get(workflow_id)
        if flow is None:
            raise WorkflowNotFound(f"workflow {workflow_id} not found")
        return flow


def _parse_id(raw: Any) -> UUID:
    if raw:
        try:
            return UUID(str(raw))
        except ValueError:
            pass
    return uuid4()


__all__ = ["OrchestrationService"]
