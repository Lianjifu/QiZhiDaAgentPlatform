"""Workflow catalog unit tests — admin CRUD + user projection + runs."""

from __future__ import annotations

from uuid import UUID

import pytest

from qzdap.modules.orchestration.application.ports import (
    WorkflowRepository,
    WorkflowRunRepository,
    WorkflowUserStateRepository,
)
from qzdap.modules.orchestration.application.services import OrchestrationService
from qzdap.modules.orchestration.domain.entities import FlowRun, Workflow
from qzdap.modules.orchestration.domain.errors import (
    WorkflowNotFound,
    WorkflowUnavailable,
)

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
USER = UUID("00000000-0000-0000-0000-000000000010")


class InMemoryWorkflowRepository(WorkflowRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, Workflow] = {}

    async def add(self, workflow: Workflow) -> None:
        self._by_id[workflow.id] = workflow

    async def get(self, workflow_id: UUID) -> Workflow | None:
        return self._by_id.get(workflow_id)

    async def list_for_workspace(self, workspace_id: UUID) -> list[Workflow]:
        return [item for item in self._by_id.values() if item.workspace_id == workspace_id]

    async def update(self, workflow: Workflow) -> None:
        self._by_id[workflow.id] = workflow

    async def delete(self, workflow_id: UUID) -> None:
        self._by_id.pop(workflow_id, None)


class InMemoryWorkflowUserStateRepository(WorkflowUserStateRepository):
    def __init__(self) -> None:
        self.favorites: dict[tuple[UUID, UUID], bool] = {}

    async def set_favorite(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        workflow_id: UUID,
        on: bool,
    ) -> None:
        _ = (tenant_id, workspace_id)
        self.favorites[(user_id, workflow_id)] = on


class InMemoryWorkflowRunRepository(WorkflowRunRepository):
    def __init__(self) -> None:
        self.rows: list[FlowRun] = []

    async def add(self, run: FlowRun) -> None:
        self.rows.insert(0, run)

    async def list_for_user(
        self, *, workspace_id: UUID, user_id: UUID, limit: int = 50
    ) -> list[FlowRun]:
        return [
            row
            for row in self.rows
            if row.workspace_id == workspace_id and row.user_id == user_id
        ][:limit]


def _svc() -> OrchestrationService:
    return OrchestrationService(
        InMemoryWorkflowRepository(),
        InMemoryWorkflowUserStateRepository(),
        InMemoryWorkflowRunRepository(),
    )


@pytest.mark.asyncio
async def test_create_list_and_catalog_visibility() -> None:
    svc = _svc()
    created = await svc.create(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "销售周报自动整理", "scene": "销售支持", "trigger": "定时触发"},
    )
    assert created["status"] == "draft"
    assert created["trigger"] == "定时触发"
    catalog = await svc.list_catalog(workspace_id=WORKSPACE)
    assert catalog == []

    flow_id = UUID(created["id"])
    published = await svc.update(
        workflow_id=flow_id, body={"status": "published"}, actor="管理员"
    )
    assert published["status"] == "published"
    catalog = await svc.list_catalog(workspace_id=WORKSPACE)
    assert len(catalog) == 1
    assert catalog[0]["name"] == "销售周报自动整理"
    assert catalog[0]["availability"] == "available"
    assert catalog[0]["cadence"] == "按计划自动运行"
    assert catalog[0]["steps"]


@pytest.mark.asyncio
async def test_run_requires_published_and_records() -> None:
    svc = _svc()
    created = await svc.create(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "客户投诉自动分流", "trigger": "消息触发"},
    )
    flow_id = UUID(created["id"])
    with pytest.raises(WorkflowUnavailable):
        await svc.record_run(workflow_id=flow_id, user_id=USER)
    await svc.update(workflow_id=flow_id, body={"status": "published"}, actor="客服")
    run = await svc.record_run(workflow_id=flow_id, user_id=USER, note="加急")
    assert run["result"] == "已记录使用说明"
    assert run["time"] == "刚刚"
    runs = await svc.list_runs(workspace_id=WORKSPACE, user_id=USER)
    assert len(runs) == 1
    admin = await svc.get_admin(flow_id)
    assert admin["callCount"] == 1


@pytest.mark.asyncio
async def test_delete_and_not_found() -> None:
    svc = _svc()
    created = await svc.create(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "临时流程"},
    )
    flow_id = UUID(created["id"])
    deleted = await svc.delete(flow_id)
    assert deleted == {"ok": True, "id": str(flow_id)}
    with pytest.raises(WorkflowNotFound):
        await svc.get_admin(flow_id)


@pytest.mark.asyncio
async def test_favorite() -> None:
    svc = _svc()
    created = await svc.create(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "线索分发"},
    )
    flow_id = UUID(created["id"])
    fav = await svc.set_favorite(workflow_id=flow_id, user_id=USER, on=True)
    assert fav == {"id": str(flow_id), "on": True}
