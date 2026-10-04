"""In-memory fakes for evaluation unit tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from qzdap_schema.ids import (
    AgentTemplateId,
    AgentVersionId,
    EvalDatasetId,
    EvalRunId,
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.evaluation.application.ports import (
    EvalDatasetRepository,
    EvalRunRepository,
    EvaluationEventPublisher,
    SubAgentPort,
)
from qzdap.modules.evaluation.domain.entities import (
    EvalCase,
    EvalDataset,
    EvalRun,
)

# ── Datasets ─────────────────────────────────────────────────────────────


class InMemoryEvalDatasetRepository(EvalDatasetRepository):
    def __init__(self) -> None:
        self._by_id: dict[tuple[UUID, UUID], EvalDataset] = {}
        self._by_name: dict[tuple[UUID, str], UUID] = {}
        self._cases: dict[tuple[UUID, UUID], list[EvalCase]] = {}

    async def get(
        self, *, tenant_id: TenantId, dataset_id: EvalDatasetId
    ) -> EvalDataset | None:
        return self._by_id.get((tenant_id, dataset_id))

    async def get_by_name(
        self, *, tenant_id: TenantId, name: str
    ) -> EvalDataset | None:
        did = self._by_name.get((tenant_id, name))
        return self._by_id.get((tenant_id, did)) if did else None

    async def list_records(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EvalDataset]:
        rows = [
            d
            for (tid, _), d in self._by_id.items()
            if tid == tenant_id and d.workspace_id == workspace_id
        ]
        rows.sort(key=lambda d: d.created_at, reverse=True)
        return rows[offset : offset + limit]

    async def add(self, dataset: EvalDataset) -> EvalDataset:
        self._by_id[(dataset.tenant_id, dataset.id)] = dataset
        self._by_name[(dataset.tenant_id, dataset.name)] = dataset.id
        self._cases.setdefault((dataset.tenant_id, dataset.id), [])
        return dataset

    async def update(self, dataset: EvalDataset) -> EvalDataset:
        self._by_id[(dataset.tenant_id, dataset.id)] = dataset
        return dataset

    async def add_case(self, case: EvalCase) -> EvalCase:
        self._cases.setdefault((case.tenant_id, case.dataset_id), []).append(case)
        return case

    async def list_cases(
        self, *, tenant_id: TenantId, dataset_id: EvalDatasetId
    ) -> list[EvalCase]:
        return list(self._cases.get((tenant_id, dataset_id), ()))


# ── Runs ─────────────────────────────────────────────────────────────────


class InMemoryEvalRunRepository(EvalRunRepository):
    def __init__(self) -> None:
        self._by_id: dict[tuple[UUID, UUID], EvalRun] = {}
        self._by_idem: dict[tuple[UUID, str], UUID] = {}

    async def get(self, *, tenant_id: TenantId, run_id: EvalRunId) -> EvalRun | None:
        return self._by_id.get((tenant_id, run_id))

    async def get_by_idempotency_key(
        self, *, tenant_id: TenantId, idempotency_key: str
    ) -> EvalRun | None:
        rid = self._by_idem.get((tenant_id, idempotency_key))
        return self._by_id.get((tenant_id, rid)) if rid else None

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
        rows: list[EvalRun] = []
        for (tid, _), r in self._by_id.items():
            if tid != tenant_id:
                continue
            if r.workspace_id != workspace_id:
                continue
            if template_id is not None and r.template_id != template_id:
                continue
            if version_id is not None and r.version_id != version_id:
                continue
            rows.append(r)
        rows.sort(key=lambda r: r.created_at, reverse=True)
        return rows[offset : offset + limit]

    async def add(self, run: EvalRun) -> EvalRun:
        if (run.tenant_id, run.id) in self._by_id:
            raise RuntimeError("run already added")
        self._by_id[(run.tenant_id, run.id)] = run
        if run.idempotency_key is not None:
            self._by_idem[(run.tenant_id, run.idempotency_key)] = run.id
        return run

    async def update(self, run: EvalRun) -> EvalRun:
        self._by_id[(run.tenant_id, run.id)] = run
        return run


# ── SubAgent fake ────────────────────────────────────────────────────────


class FakeSubAgentPort(SubAgentPort):
    """Pre-canned per-input responses; tracks every call."""

    def __init__(self, *, responses: dict[str, str] | None = None) -> None:
        self._responses: dict[str, str] = dict(responses or {})
        self.calls: list[dict[str, Any]] = []

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
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "workspace_id": workspace_id,
                "owner_id": owner_id,
                "agent_id": agent_id,
                "agent_version": agent_version,
                "user_input": user_input,
                "timeout_seconds": timeout_seconds,
            }
        )
        output = self._responses.get(user_input, f"echo: {user_input}")
        return {"final_message": output}


# ── Recording publisher ──────────────────────────────────────────────────


class RecordingPublisher(EvaluationEventPublisher):
    def __init__(self) -> None:
        self.published: list[object] = []

    async def publish(self, event: object) -> None:
        self.published.append(event)


def make_dataset(*, name: str = "golden-default") -> EvalDataset:
    return EvalDataset.create(
        tenant_id=TenantId(uuid4()),
        workspace_id=WorkspaceId(uuid4()),
        name=name,
        description="",
        kind="builtin",  # type: ignore[arg-type]
        case_count=2,
        created_by=UserId(uuid4()),
    )


def make_case(
    *,
    dataset_id: EvalDatasetId,
    tenant_id: TenantId,
    workspace_id: WorkspaceId,
    ordinal: int,
    input: str,
    expected_keywords: tuple[str, ...] = (),
    min_hit: float = 0.6,
    max_latency_ms: int = 30_000,
) -> EvalCase:
    return EvalCase.create(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        ordinal=ordinal,
        input=input,
        expected_keywords=expected_keywords,
        min_keywords_hit_ratio=min_hit,
        max_latency_ms=max_latency_ms,
    )


__all__ = [
    "FakeSubAgentPort",
    "InMemoryEvalDatasetRepository",
    "InMemoryEvalRunRepository",
    "RecordingPublisher",
    "make_case",
    "make_dataset",
]


def _utc_now() -> datetime:
    return datetime.now(UTC)
