"""Async-SQLAlchemy implementations of the evaluation ports.

- :class:`SqlEvalDatasetRepository` — eval_datasets + eval_cases
- :class:`SqlEvalRunRepository`     — eval_runs (idempotency-aware)

A single SQL repository type covers both eval_datasets and eval_cases
because the dataset table is the parent of the case table and they
share a single transactional unit-of-work per request.  Same for runs.
"""

from __future__ import annotations

from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    EvalCaseId,
    EvalDatasetId,
    EvalRunId,
    TenantId,
    WorkspaceId,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.evaluation.adapter.persistence.mappers import (
    case_to_domain,
    case_to_orm,
    dataset_to_domain,
    dataset_to_orm,
    run_to_domain,
    run_to_orm,
)
from qzdap.modules.evaluation.adapter.persistence.models import (
    EvalCaseORM,
    EvalDatasetORM,
    EvalRunORM,
)
from qzdap.modules.evaluation.application.ports import (
    EvalDatasetRepository,
    EvalRunRepository,
)
from qzdap.modules.evaluation.domain.entities import (
    EvalCase,
    EvalDataset,
    EvalRun,
)
from qzdap.modules.evaluation.domain.errors import (
    EvalDatasetNameConflict,
    IdempotencyKeyConflict,
)

# ── EvalDatasetRepository ─────────────────────────────────────────────────


class SqlEvalDatasetRepository(EvalDatasetRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, *, tenant_id: TenantId, dataset_id: EvalDatasetId
    ) -> EvalDataset | None:
        result = await self._session.execute(
            select(EvalDatasetORM).where(
                EvalDatasetORM.tenant_id == tenant_id,
                EvalDatasetORM.id == dataset_id,
            )
        )
        row = result.scalar_one_or_none()
        return dataset_to_domain(row) if row is not None else None

    async def get_by_name(
        self, *, tenant_id: TenantId, name: str
    ) -> EvalDataset | None:
        result = await self._session.execute(
            select(EvalDatasetORM).where(
                EvalDatasetORM.tenant_id == tenant_id,
                EvalDatasetORM.name == name,
            )
        )
        row = result.scalar_one_or_none()
        return dataset_to_domain(row) if row is not None else None

    async def list_records(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EvalDataset]:
        if limit <= 0:
            raise ValueError("limit must be > 0")
        result = await self._session.execute(
            select(EvalDatasetORM)
            .where(
                EvalDatasetORM.tenant_id == tenant_id,
                EvalDatasetORM.workspace_id == workspace_id,
            )
            .order_by(EvalDatasetORM.created_at.desc())
            .limit(limit)
            .offset(max(0, offset))
        )
        return [dataset_to_domain(r) for r in result.scalars().all()]

    async def add(self, dataset: EvalDataset) -> EvalDataset:
        row = dataset_to_orm(dataset)
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise EvalDatasetNameConflict(
                f"eval dataset name {dataset.name!r} already exists in tenant"
            ) from exc
        return dataset_to_domain(row)

    async def update(self, dataset: EvalDataset) -> EvalDataset:
        existing = await self._session.get(EvalDatasetORM, dataset.id)
        if existing is None or existing.tenant_id != dataset.tenant_id:
            from qzdap.modules.evaluation.domain.errors import EvalDatasetNotFound

            raise EvalDatasetNotFound(f"eval dataset {dataset.id} not found")
        existing.name = dataset.name
        existing.description = dataset.description
        existing.kind = dataset.kind.value
        existing.status = dataset.status.value
        existing.case_count = dataset.case_count
        existing.metadata_ = dict(dataset.metadata)
        existing.updated_at = dataset.updated_at
        await self._session.flush()
        return dataset_to_domain(existing)

    async def add_case(self, case: EvalCase) -> EvalCase:
        row = case_to_orm(case)
        self._session.add(row)
        await self._session.flush()
        return case_to_domain(row)

    async def list_cases(
        self, *, tenant_id: TenantId, dataset_id: EvalDatasetId
    ) -> list[EvalCase]:
        result = await self._session.execute(
            select(EvalCaseORM)
            .where(
                EvalCaseORM.tenant_id == tenant_id,
                EvalCaseORM.dataset_id == dataset_id,
            )
            .order_by(EvalCaseORM.ordinal.asc())
        )
        return [case_to_domain(r) for r in result.scalars().all()]


# ── EvalRunRepository ─────────────────────────────────────────────────────


class SqlEvalRunRepository(EvalRunRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, tenant_id: TenantId, run_id: EvalRunId) -> EvalRun | None:
        result = await self._session.execute(
            select(EvalRunORM).where(
                EvalRunORM.tenant_id == tenant_id,
                EvalRunORM.id == run_id,
            )
        )
        row = result.scalar_one_or_none()
        return run_to_domain(row) if row is not None else None

    async def get_by_idempotency_key(
        self, *, tenant_id: TenantId, idempotency_key: str
    ) -> EvalRun | None:
        result = await self._session.execute(
            select(EvalRunORM).where(
                EvalRunORM.tenant_id == tenant_id,
                EvalRunORM.idempotency_key == idempotency_key,
            )
        )
        row = result.scalar_one_or_none()
        return run_to_domain(row) if row is not None else None

    async def list_records(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        template_id: AgentTemplateId | None = None,
        version_id: AgentVersionId | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EvalRun]:
        if limit <= 0:
            raise ValueError("limit must be > 0")
        stmt = (
            select(EvalRunORM)
            .where(
                EvalRunORM.tenant_id == tenant_id,
                EvalRunORM.workspace_id == workspace_id,
            )
            .order_by(EvalRunORM.created_at.desc())
            .limit(limit)
            .offset(max(0, offset))
        )
        if template_id is not None:
            stmt = stmt.where(EvalRunORM.template_id == template_id)
        if version_id is not None:
            stmt = stmt.where(EvalRunORM.version_id == version_id)
        result = await self._session.execute(stmt)
        return [run_to_domain(r) for r in result.scalars().all()]

    async def add(self, run: EvalRun) -> EvalRun:
        row = run_to_orm(run)
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise IdempotencyKeyConflict(
                f"idempotency_key {run.idempotency_key!r} already used"
            ) from exc
        return run_to_domain(row)

    async def update(self, run: EvalRun) -> EvalRun:
        existing = await self._session.get(EvalRunORM, run.id)
        if existing is None or existing.tenant_id != run.tenant_id:
            from qzdap.modules.evaluation.domain.errors import EvalRunNotFound

            raise EvalRunNotFound(f"eval run {run.id} not found")
        existing.status = run.status.value
        existing.mean_score = run.mean_score
        existing.case_count = run.case_count
        existing.passed_count = run.passed_count
        existing.failed_count = run.failed_count
        existing.started_at = run.started_at
        existing.completed_at = run.completed_at
        existing.error_message = run.error_message
        existing.updated_at = run.updated_at
        await self._session.flush()
        return run_to_domain(existing)


__all__ = [
    "SqlEvalDatasetRepository",
    "SqlEvalRunRepository",
]

_ = (EvalCaseId,)  # type-only reference to silence unused-import warnings
