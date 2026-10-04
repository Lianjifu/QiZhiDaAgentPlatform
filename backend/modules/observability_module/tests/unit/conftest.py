"""Pytest fixtures for observability_module unit tests.

RunRecord + CostRecord factories follow the same ``from_event`` /
``create`` API the production code uses, so tests exercise the same
validation paths.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from qzdap_schema.ids import TenantId, WorkspaceId

from qzdap.modules.observability_module.application.pricing import (
    DEFAULT_LLM_PRICING,
    ModelPricing,
    PricingCatalog,
)
from qzdap.modules.observability_module.domain.entities import (
    CostRecord,
    RunRecord,
)
from qzdap.modules.observability_module.domain.value_objects import (
    CostType,
    RunStatus,
    RunType,
)

from ._in_memory import (
    FakeEvalRunQueryPort,
    InMemoryCostRecordRepository,
    InMemoryRunRecordRepository,
)


@pytest.fixture
def tenant_id() -> TenantId:
    return TenantId(uuid4())


@pytest.fixture
def workspace_id() -> TenantId:
    return WorkspaceId(uuid4())  # type: ignore[return-value]


@pytest.fixture
def now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
def run_repo() -> InMemoryRunRecordRepository:
    return InMemoryRunRecordRepository()


@pytest.fixture
def cost_repo() -> InMemoryCostRecordRepository:
    return InMemoryCostRecordRepository()


@pytest.fixture
def pricing() -> PricingCatalog:
    return PricingCatalog(
        llm_pricing=dict(DEFAULT_LLM_PRICING),
        tool_unit_cost={"echo": Decimal(0), "reverse": Decimal(0)},
        skill_unit_cost={},
        memory_write_unit_cost_usd=Decimal("0.00001"),
        knowledge_ingest_unit_cost_usd=Decimal("0.001"),
        channel_send_unit_cost_usd=Decimal("0.0005"),
        currency="USD",
    )


@pytest.fixture
def pricing_with_skill() -> PricingCatalog:
    return PricingCatalog(
        llm_pricing={"default": ModelPricing(Decimal("0.01"), Decimal("0.03"))},
        tool_unit_cost={"echo": Decimal(0)},
        skill_unit_cost={"echo_skill": Decimal("0.005")},
        memory_write_unit_cost_usd=Decimal("0.00001"),
        knowledge_ingest_unit_cost_usd=Decimal("0.001"),
        channel_send_unit_cost_usd=Decimal("0.0005"),
        currency="USD",
    )


@pytest.fixture
def eval_query() -> FakeEvalRunQueryPort:
    return FakeEvalRunQueryPort()


def make_run(
    *,
    tenant_id: TenantId,
    workspace_id: WorkspaceId,
    run_type: RunType,
    status: RunStatus = RunStatus.SUCCEEDED,
    completed_at: datetime | None = None,
    latency_ms: int | None = None,
) -> RunRecord:
    return RunRecord.from_event(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        run_type=run_type,
        source_id=None,
        completed_at=completed_at or datetime.now(UTC),
        status=status,
        latency_ms=latency_ms,
    )


def make_cost(
    *,
    tenant_id: TenantId,
    workspace_id: WorkspaceId,
    run_id,
    cost_type: CostType,
    amount_usd: Decimal = Decimal("0.001"),
    unit: str = "call",
    model_id: str | None = None,
) -> CostRecord:
    return CostRecord.create(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        run_id=run_id,
        cost_type=cost_type,
        amount_usd=amount_usd,
        unit=unit,
        model_id=model_id,
    )
