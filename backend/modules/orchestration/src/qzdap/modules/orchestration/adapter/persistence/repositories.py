from __future__ import annotations

from uuid import UUID

from qzdap_persistence.tenant_guard import current_tenant_id
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.orchestration.adapter.persistence.models import (
    WorkflowORM,
    WorkflowRunORM,
    WorkflowUserStateORM,
)
from qzdap.modules.orchestration.application.ports import (
    WorkflowRepository,
    WorkflowRunRepository,
    WorkflowUserStateRepository,
)
from qzdap.modules.orchestration.domain.entities import FlowRun, FlowVersion, Workflow


def _cross_tenant(row: object) -> bool:
    bound = current_tenant_id()
    if bound is None:
        return False
    return getattr(row, "tenant_id", None) != bound


def workflow_to_domain(row: WorkflowORM) -> Workflow:
    return Workflow(
        id=row.id,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        name=row.name,
        description=row.description,
        owner=row.owner,
        scene=row.scene,
        trigger=row.trigger,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        call_count=row.call_count,
        inputs=row.inputs,
        outputs=row.outputs,
        created_at=row.created_at,
        updated_at=row.updated_at,
        bound_agents=list(row.bound_agents or []),
        versions=[FlowVersion.from_dict(item) for item in (row.versions or []) if isinstance(item, dict)],
        initial_nodes=list(row.initial_nodes or []),
        initial_edges=list(row.initial_edges or []),
    )


def _apply(row: WorkflowORM, flow: Workflow) -> None:
    row.name = flow.name
    row.description = flow.description
    row.owner = flow.owner
    row.scene = flow.scene
    row.trigger = flow.trigger
    row.status = flow.status
    row.call_count = flow.call_count
    row.inputs = flow.inputs
    row.outputs = flow.outputs
    row.bound_agents = list(flow.bound_agents)
    row.versions = [item.to_dict() for item in flow.versions]
    row.initial_nodes = list(flow.initial_nodes)
    row.initial_edges = list(flow.initial_edges)
    row.updated_at = flow.updated_at


class SqlWorkflowRepository(WorkflowRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, workflow: Workflow) -> None:
        row = WorkflowORM(
            id=workflow.id,
            tenant_id=workflow.tenant_id,
            workspace_id=workflow.workspace_id,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
        )
        _apply(row, workflow)
        self._s.add(row)

    async def get(self, workflow_id: UUID) -> Workflow | None:
        row = await self._s.get(WorkflowORM, workflow_id)
        if row is None or _cross_tenant(row):
            return None
        return workflow_to_domain(row)

    async def list_for_workspace(self, workspace_id: UUID) -> list[Workflow]:
        result = await self._s.execute(
            select(WorkflowORM).where(WorkflowORM.workspace_id == workspace_id)
        )
        return [workflow_to_domain(row) for row in result.scalars().all() if not _cross_tenant(row)]

    async def update(self, workflow: Workflow) -> None:
        row = await self._s.get(WorkflowORM, workflow.id)
        if row is None or _cross_tenant(row):
            return
        _apply(row, workflow)

    async def delete(self, workflow_id: UUID) -> None:
        row = await self._s.get(WorkflowORM, workflow_id)
        if row is None or _cross_tenant(row):
            return
        await self._s.delete(row)


class SqlWorkflowUserStateRepository(WorkflowUserStateRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def _row(self, *, user_id: UUID, workflow_id: UUID) -> WorkflowUserStateORM | None:
        result = await self._s.execute(
            select(WorkflowUserStateORM).where(
                WorkflowUserStateORM.user_id == user_id,
                WorkflowUserStateORM.workflow_id == workflow_id,
            )
        )
        row = result.scalars().first()
        if row is None or _cross_tenant(row):
            return None
        return row

    async def set_favorite(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        workflow_id: UUID,
        on: bool,
    ) -> None:
        row = await self._row(user_id=user_id, workflow_id=workflow_id)
        if row is None:
            self._s.add(
                WorkflowUserStateORM(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    workflow_id=workflow_id,
                    favorited=on,
                )
            )
            return
        row.favorited = on


class SqlWorkflowRunRepository(WorkflowRunRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, run: FlowRun) -> None:
        self._s.add(
            WorkflowRunORM(
                id=run.id,
                tenant_id=run.tenant_id,
                workspace_id=run.workspace_id,
                user_id=run.user_id,
                workflow_id=run.workflow_id,
                name=run.name,
                time=run.time,
                result=run.result,
                created_at=run.created_at,
                updated_at=run.created_at,
            )
        )

    async def list_for_user(
        self, *, workspace_id: UUID, user_id: UUID, limit: int = 50
    ) -> list[FlowRun]:
        result = await self._s.execute(
            select(WorkflowRunORM)
            .where(
                WorkflowRunORM.workspace_id == workspace_id,
                WorkflowRunORM.user_id == user_id,
            )
            .order_by(WorkflowRunORM.created_at.desc())
            .limit(limit)
        )
        rows: list[FlowRun] = []
        for row in result.scalars().all():
            if _cross_tenant(row):
                continue
            rows.append(
                FlowRun(
                    id=row.id,
                    tenant_id=row.tenant_id,
                    workspace_id=row.workspace_id,
                    user_id=row.user_id,
                    workflow_id=row.workflow_id,
                    name=row.name,
                    time=row.time,
                    result=row.result,
                    created_at=row.created_at,
                )
            )
        return rows
