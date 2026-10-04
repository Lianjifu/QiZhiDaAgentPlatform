"""Tests for RunRecord + CostRecord domain entities."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from qzdap_schema.ids import TenantId, UserId, WorkspaceId

from qzdap.modules.observability_module.domain.entities import (
    CostRecord,
    RunRecord,
)
from qzdap.modules.observability_module.domain.value_objects import (
    CostType,
    RunStatus,
    RunType,
)

# ── RunRecord ─────────────────────────────────────────────────────────────


def test_run_record_from_event_defaults() -> None:
    tid = TenantId(uuid4())
    wid = WorkspaceId(uuid4())
    completed_at = datetime.now(UTC)
    rec = RunRecord.from_event(
        tenant_id=tid,
        workspace_id=wid,
        run_type=RunType.LLM,
        source_id=None,
        completed_at=completed_at,
        status=RunStatus.SUCCEEDED,
    )
    assert rec.tenant_id == tid
    assert rec.workspace_id == wid
    assert rec.run_type == RunType.LLM
    assert rec.status == RunStatus.SUCCEEDED
    assert rec.completed_at == completed_at
    assert rec.latency_ms is None
    assert rec.actor_id is None
    assert rec.started_at is None
    assert rec.source_id is None
    assert rec.metadata == {}
    assert rec.id is not None


def test_run_record_from_event_with_actor() -> None:
    tid = TenantId(uuid4())
    wid = WorkspaceId(uuid4())
    aid = UserId(uuid4())
    sid = uuid4()
    started = datetime.now(UTC)
    rec = RunRecord.from_event(
        tenant_id=tid,
        workspace_id=wid,
        run_type=RunType.SKILL,
        source_id=sid,
        completed_at=started,
        status=RunStatus.FAILED,
        latency_ms=42,
        actor_id=aid,
        started_at=started,
        metadata={"skill": "echo_skill"},
    )
    assert rec.actor_id == aid
    assert rec.source_id == sid
    assert rec.latency_ms == 42
    assert rec.metadata == {"skill": "echo_skill"}
    assert rec.status == RunStatus.FAILED


def test_run_record_frozen() -> None:
    rec = RunRecord.from_event(
        tenant_id=TenantId(uuid4()),
        workspace_id=WorkspaceId(uuid4()),
        run_type=RunType.TOOL,
        source_id=None,
        completed_at=datetime.now(UTC),
        status=RunStatus.SUCCEEDED,
    )
    try:
        rec.status = RunStatus.FAILED  # type: ignore[misc]
    except (AttributeError, dataclasses.FrozenInstanceError):
        # RunRecord is frozen — assignment must raise. Other unexpected
        # exceptions propagate so the test fails loudly.
        pass
    else:
        raise AssertionError("RunRecord must be frozen")


def test_run_record_each_run_type_value() -> None:
    for rt in RunType:
        rec = RunRecord.from_event(
            tenant_id=TenantId(uuid4()),
            workspace_id=WorkspaceId(uuid4()),
            run_type=rt,
            source_id=None,
            completed_at=datetime.now(UTC),
            status=RunStatus.SUCCEEDED,
        )
        assert rec.run_type == rt


def test_run_status_enum_values() -> None:
    assert RunStatus.SUCCEEDED == "succeeded"
    assert RunStatus.FAILED == "failed"
    assert RunStatus.RUNNING == "running"


# ── CostRecord ────────────────────────────────────────────────────────────


def test_cost_record_create_basic() -> None:
    tid = TenantId(uuid4())
    wid = WorkspaceId(uuid4())
    rid = uuid4()
    rec = CostRecord.create(
        tenant_id=tid,
        workspace_id=wid,
        run_id=rid,
        cost_type=CostType.LLM_INPUT,
        amount_usd=Decimal("0.000123"),
        quantity=200,
        unit="token",
        model_id="gpt-4o-mini",
    )
    assert rec.tenant_id == tid
    assert rec.cost_type == CostType.LLM_INPUT
    assert rec.amount_usd == Decimal("0.000123")
    assert rec.quantity == 200
    assert rec.unit == "token"
    assert rec.model_id == "gpt-4o-mini"
    assert rec.metadata == {}


def test_cost_record_rejects_negative_amount() -> None:
    import pytest

    with pytest.raises(ValueError):
        CostRecord.create(
            tenant_id=TenantId(uuid4()),
            workspace_id=WorkspaceId(uuid4()),
            run_id=uuid4(),
            cost_type=CostType.TOOL,
            amount_usd=Decimal("-0.01"),
        )


def test_cost_record_rejects_empty_unit() -> None:
    import pytest

    with pytest.raises(ValueError):
        CostRecord.create(
            tenant_id=TenantId(uuid4()),
            workspace_id=WorkspaceId(uuid4()),
            run_id=uuid4(),
            cost_type=CostType.TOOL,
            amount_usd=Decimal(0),
            unit="",
        )


def test_cost_record_rejects_long_unit() -> None:
    import pytest

    with pytest.raises(ValueError):
        CostRecord.create(
            tenant_id=TenantId(uuid4()),
            workspace_id=WorkspaceId(uuid4()),
            run_id=uuid4(),
            cost_type=CostType.TOOL,
            amount_usd=Decimal(0),
            unit="x" * 17,
        )


def test_cost_record_rejects_long_currency() -> None:
    import pytest

    with pytest.raises(ValueError):
        CostRecord.create(
            tenant_id=TenantId(uuid4()),
            workspace_id=WorkspaceId(uuid4()),
            run_id=uuid4(),
            cost_type=CostType.TOOL,
            amount_usd=Decimal(0),
            currency="TOOLONGCC",  # 9 chars > 8
        )


def test_cost_record_each_cost_type() -> None:
    for ct in CostType:
        rec = CostRecord.create(
            tenant_id=TenantId(uuid4()),
            workspace_id=WorkspaceId(uuid4()),
            run_id=uuid4(),
            cost_type=ct,
            amount_usd=Decimal("0.001"),
        )
        assert rec.cost_type == ct


def test_cost_record_zero_amount_is_valid() -> None:
    rec = CostRecord.create(
        tenant_id=TenantId(uuid4()),
        workspace_id=WorkspaceId(uuid4()),
        run_id=uuid4(),
        cost_type=CostType.TOOL,
        amount_usd=Decimal(0),
        unit="echo",
    )
    assert rec.amount_usd == Decimal(0)


def test_cost_record_decimal_precision() -> None:
    rec = CostRecord.create(
        tenant_id=TenantId(uuid4()),
        workspace_id=WorkspaceId(uuid4()),
        run_id=uuid4(),
        cost_type=CostType.LLM_INPUT,
        amount_usd=Decimal("0.000001"),
    )
    assert rec.amount_usd == Decimal("0.000001")
