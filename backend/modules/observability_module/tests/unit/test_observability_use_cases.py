"""Tests for ObservabilityService + use cases."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from qzdap_kernel.errors import BusinessRuleError
from qzdap_schema.ids import TenantId, WorkspaceId

from qzdap.modules.observability_module.application.pricing import (
    DEFAULT_LLM_PRICING,
    PricingCatalog,
)
from qzdap.modules.observability_module.application.services import (
    ObservabilityService,
)
from qzdap.modules.observability_module.application.use_cases.get_quality_score import (
    QualityScore,
)
from qzdap.modules.observability_module.domain.entities import (
    CostRecord,
    RunRecord,
)
from qzdap.modules.observability_module.domain.value_objects import (
    CostType,
    RunType,
)

from ._in_memory import (
    FakeEvalRunQueryPort,
    InMemoryCostRecordRepository,
    InMemoryRunRecordRepository,
)


@pytest.fixture
def service(pricing):
    return ObservabilityService.from_parts(
        run_repo=InMemoryRunRecordRepository(),
        cost_repo=InMemoryCostRecordRepository(),
        pricing=pricing,
        eval_query=FakeEvalRunQueryPort(),
    )


# ── record_run ────────────────────────────────────────────────────────────


def test_record_run_creates_row(service: ObservabilityService) -> None:
    tid = TenantId(uuid4())
    wid = WorkspaceId(uuid4())
    rec = asyncio.run(
        service.record_run(
            cmd={
                "tenant_id": tid,
                "workspace_id": wid,
                "run_type": "llm",
                "status": "succeeded",
                "completed_at": datetime.now(UTC),
                "latency_ms": 100,
            }
        )
    )
    assert isinstance(rec, RunRecord)
    assert rec.tenant_id == tid
    assert rec.run_type == RunType.LLM


def test_record_run_rejects_bad_run_type(service: ObservabilityService) -> None:
    with pytest.raises(BusinessRuleError):
        asyncio.run(
            service.record_run(
                cmd={
                    "tenant_id": TenantId(uuid4()),
                    "workspace_id": WorkspaceId(uuid4()),
                    "run_type": "bogus",
                }
            )
        )


# ── record_cost ───────────────────────────────────────────────────────────


def test_record_cost_creates_row(service: ObservabilityService) -> None:
    tid = TenantId(uuid4())
    wid = WorkspaceId(uuid4())
    rid = uuid4()
    rec = asyncio.run(
        service.record_cost(
            cmd={
                "tenant_id": tid,
                "workspace_id": wid,
                "run_id": rid,
                "cost_type": "tool",
                "amount_usd": Decimal("0.01"),
            }
        )
    )
    assert isinstance(rec, CostRecord)
    assert rec.cost_type == CostType.TOOL
    assert rec.amount_usd == Decimal("0.01")


def test_record_cost_rejects_negative(service: ObservabilityService) -> None:
    with pytest.raises(BusinessRuleError):
        asyncio.run(
            service.record_cost(
                cmd={
                    "tenant_id": TenantId(uuid4()),
                    "workspace_id": WorkspaceId(uuid4()),
                    "run_id": uuid4(),
                    "cost_type": "tool",
                    "amount_usd": Decimal(-1),
                }
            )
        )


# ── list_runs / list_costs ────────────────────────────────────────────────


def test_list_runs_filters_by_workspace(service: ObservabilityService) -> None:
    tid = TenantId(uuid4())
    wid_a = WorkspaceId(uuid4())
    wid_b = WorkspaceId(uuid4())
    for wid in (wid_a, wid_a, wid_b):
        asyncio.run(
            service.record_run(
                cmd={
                    "tenant_id": tid,
                    "workspace_id": wid,
                    "run_type": "llm",
                    "completed_at": datetime.now(UTC),
                }
            )
        )
    rows = asyncio.run(service.list_runs(tenant_id=tid, workspace_id=wid_a))
    assert len(rows) == 2


def test_list_costs_tenant_isolation(service: ObservabilityService) -> None:
    tid_a = TenantId(uuid4())
    tid_b = TenantId(uuid4())
    wid = WorkspaceId(uuid4())
    rid = uuid4()
    for tid in (tid_a, tid_b):
        asyncio.run(
            service.record_cost(
                cmd={
                    "tenant_id": tid,
                    "workspace_id": wid,
                    "run_id": rid,
                    "cost_type": "tool",
                    "amount_usd": Decimal("0.01"),
                }
            )
        )
    rows_a = asyncio.run(service.list_costs(tenant_id=tid_a, workspace_id=wid))
    rows_b = asyncio.run(service.list_costs(tenant_id=tid_b, workspace_id=wid))
    assert len(rows_a) == 1
    assert len(rows_b) == 1
    assert rows_a[0].tenant_id == tid_a
    assert rows_b[0].tenant_id == tid_b


# ── aggregate_costs ───────────────────────────────────────────────────────


def test_aggregate_by_cost_type(service: ObservabilityService) -> None:
    tid = TenantId(uuid4())
    wid = WorkspaceId(uuid4())
    rid = uuid4()
    for ct, amount in [
        (CostType.LLM_INPUT, Decimal("0.01")),
        (CostType.LLM_INPUT, Decimal("0.02")),
        (CostType.TOOL, Decimal("0.005")),
    ]:
        asyncio.run(
            service.record_cost(
                cmd={
                    "tenant_id": tid,
                    "workspace_id": wid,
                    "run_id": rid,
                    "cost_type": ct.value,
                    "amount_usd": amount,
                }
            )
        )
    rows = asyncio.run(service.aggregate_costs(tenant_id=tid, group_by="cost_type"))
    by_type = {r["cost_type"]: r["total_usd"] for r in rows}
    assert by_type["llm_input"] == "0.03"
    assert by_type["tool"] == "0.005"


def test_aggregate_by_workspace(service: ObservabilityService) -> None:
    tid = TenantId(uuid4())
    wid_a = WorkspaceId(uuid4())
    wid_b = WorkspaceId(uuid4())
    rid = uuid4()
    for wid, amount in [
        (wid_a, Decimal("0.01")),
        (wid_a, Decimal("0.02")),
        (wid_b, Decimal("0.05")),
    ]:
        asyncio.run(
            service.record_cost(
                cmd={
                    "tenant_id": tid,
                    "workspace_id": wid,
                    "run_id": rid,
                    "cost_type": "tool",
                    "amount_usd": amount,
                }
            )
        )
    rows = asyncio.run(service.aggregate_costs(tenant_id=tid, group_by="workspace"))
    by_ws = {r["workspace_id"]: r["total_usd"] for r in rows}
    assert by_ws[str(wid_a)] == "0.03"
    assert by_ws[str(wid_b)] == "0.05"


def test_aggregate_by_model(service: ObservabilityService) -> None:
    tid = TenantId(uuid4())
    wid = WorkspaceId(uuid4())
    rid = uuid4()
    for mid, amount in [
        ("gpt-4o", Decimal("0.01")),
        ("gpt-4o", Decimal("0.02")),
        ("other", Decimal("0.005")),
    ]:
        asyncio.run(
            service.record_cost(
                cmd={
                    "tenant_id": tid,
                    "workspace_id": wid,
                    "run_id": rid,
                    "cost_type": "llm_input",
                    "amount_usd": amount,
                    "model_id": mid,
                }
            )
        )
    rows = asyncio.run(service.aggregate_costs(tenant_id=tid, group_by="model"))
    by_mid = {r["model_id"]: r["total_usd"] for r in rows}
    assert by_mid["gpt-4o"] == "0.03"
    assert by_mid["other"] == "0.005"


def test_aggregate_rejects_invalid_group_by(service: ObservabilityService) -> None:
    with pytest.raises(BusinessRuleError):
        asyncio.run(
            service.aggregate_costs(tenant_id=TenantId(uuid4()), group_by="nonsense")
        )


# ── get_quality_score ─────────────────────────────────────────────────────


def test_quality_score_returns_none_for_missing(service: dict) -> None:
    tid = TenantId(uuid4())
    score = asyncio.run(
        service.get_quality_score(
            tenant_id=tid,
            template_id=uuid4(),
            version_id=uuid4(),
        )
    )
    assert score is None


def test_quality_score_returns_aggregate(service: ObservabilityService) -> None:
    tid = TenantId(uuid4())
    tpl = uuid4()
    ver = uuid4()
    completed = datetime.now(UTC)
    fake_run = SimpleNamespace(
        id=uuid4(), mean_score=0.85, completed_at=completed, sample_count=12
    )
    service.eval_query = FakeEvalRunQueryPort(
        runs={(str(tid), str(tpl), str(ver)): fake_run}
    )
    score = asyncio.run(
        service.get_quality_score(tenant_id=tid, template_id=tpl, version_id=ver)
    )
    assert isinstance(score, QualityScore)
    assert score.mean_score == 0.85
    assert score.sample_count == 12
    assert score.latest_eval_run_id == fake_run.id


def test_quality_score_no_port_returns_none() -> None:
    svc = ObservabilityService.from_parts(
        run_repo=InMemoryRunRecordRepository(),
        cost_repo=InMemoryCostRecordRepository(),
        pricing=PricingCatalog(
            llm_pricing=dict(DEFAULT_LLM_PRICING),
            tool_unit_cost={},
            skill_unit_cost={},
            memory_write_unit_cost_usd=Decimal(0),
            knowledge_ingest_unit_cost_usd=Decimal(0),
            channel_send_unit_cost_usd=Decimal(0),
        ),
        eval_query=None,
    )
    score = asyncio.run(
        svc.get_quality_score(
            tenant_id=TenantId(uuid4()),
            template_id=uuid4(),
            version_id=uuid4(),
        )
    )
    assert score is None
