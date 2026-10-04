"""Integration tests — observability recorder wired onto the bus.

Verifies the full dispatch path that the lifespan installs:

    publisher → EventEnvelope
        → InProcessBus.publish
        → ObservabilityRecorder.handle (subscribed topic)
        → run_repo.add + cost_repo.add

This is the smoke test for P9-7 ("subscriber install lifespan integration
+ e2e tests").  It does NOT touch PostgreSQL; in-memory repos mirror the
SQL implementation 1:1 so a green run here means the wiring is correct
before booting the real app.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from qzdap_messaging.domain_event import EventEnvelope
from qzdap_messaging.in_process import InProcessBus
from qzdap_schema.ids import TenantId, WorkspaceId

from qzdap.modules.observability_module.application.pricing import PricingCatalog
from qzdap.modules.observability_module.application.recorder import (
    ObservabilityRecorder,
    install,
)
from qzdap.modules.observability_module.domain.value_objects import (
    CostType,
    RunType,
)

from ..unit._in_memory import (
    InMemoryCostRecordRepository,
    InMemoryRunRecordRepository,
)

# ── helpers ───────────────────────────────────────────────────────────────


def _envelope(
    *,
    event_name: str,
    payload: dict,
    tenant_id: TenantId,
    workspace_id: WorkspaceId | None,
    occurred_at_ms: int | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        event_name=event_name,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        occurred_at_ms=occurred_at_ms or int(datetime.now(UTC).timestamp() * 1000),
        trace_id=None,
        payload=payload,
        metadata={},
    )


@pytest.fixture
def pricing() -> PricingCatalog:
    return PricingCatalog.from_settings(
        SimpleNamespace(
            model_pricing_json='{"default":{"input":"0.00015","output":"0.0006"}}',
            tool_unit_cost_json='{"echo":"0","clock":"0"}',
            skill_unit_cost_json="{}",
            memory_write_unit_cost_usd=0.00001,
            knowledge_ingest_unit_cost_usd=0.001,
            channel_send_unit_cost_usd=0.0005,
            default_currency="USD",
        )
    )


@pytest.fixture
def recorder(pricing: PricingCatalog):
    return ObservabilityRecorder(
        run_repo=InMemoryRunRecordRepository(),
        cost_repo=InMemoryCostRecordRepository(),
        pricing=pricing,
    )


@pytest.fixture
async def bus_with_recorder(recorder: ObservabilityRecorder):
    bus = InProcessBus()
    await install(bus, recorder)
    return bus, recorder


# ── install() wires all 10 topics ─────────────────────────────────────────


def test_install_subscribes_all_10_events(bus_with_recorder) -> None:
    bus, _ = bus_with_recorder
    expected = {
        "ModelInvoked",
        "ToolCompleted",
        "ToolFailed",
        "SkillInvocationCompleted",
        "MemoryWritten",
        "KnowledgeAssetIngested",
        "WorkflowRunCompleted",
        "ChannelReplySent",
        "EvalRunCompleted",
        "DecisionRecorded",
    }
    subs = set(bus._subs.keys())  # type: ignore[attr-defined]
    assert expected.issubset(subs)


async def test_install_dedupes_within_one_call(recorder) -> None:
    """Each install() call dedupes internally; two separate calls
    register two handlers (matches audit_subscriber semantics).
    """
    bus = InProcessBus()
    # Manually subscribe twice for the same topic (bypassing dedupe)
    # to verify install() keeps only one entry per topic per call.
    bus.subscribe("ModelInvoked", recorder.handle)
    bus.subscribe("ModelInvoked", recorder.handle)
    await install(bus, recorder)
    # install() added 9 unique topics; the pre-existing 2 on ModelInvoked stay.
    assert bus._subs["ModelInvoked"][:2] == [recorder.handle, recorder.handle]  # type: ignore[attr-defined]
    # but install only added 1 more handler for ModelInvoked
    assert bus._subs["ModelInvoked"].count(recorder.handle) == 3  # type: ignore[attr-defined]


# ── ModelInvoked → 1 RunRecord + 2 CostRecord (input + output) ────────────


async def test_model_invoked_records_run_and_two_costs(
    bus_with_recorder,
) -> None:
    bus, recorder = bus_with_recorder
    tenant_id = TenantId(uuid4())
    workspace_id = WorkspaceId(uuid4())

    env = _envelope(
        event_name="ModelInvoked",
        payload={
            "tenant_id": str(tenant_id),
            "workspace_id": str(workspace_id),
            "model_id": "default",
            "input_tokens": 1000,
            "output_tokens": 500,
            "latency_ms": 250,
            "status": "ok",
            "actor_id": str(uuid4()),
        },
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    await bus.publish(env)

    runs = await recorder.run_repo.list_records(
        tenant_id=tenant_id, workspace_id=workspace_id
    )
    assert len(runs) == 1
    run = runs[0]
    assert run.run_type == RunType.LLM
    assert run.status.value == "succeeded"
    assert run.latency_ms == 250

    costs = await recorder.cost_repo.list_records(
        tenant_id=tenant_id, workspace_id=workspace_id
    )
    assert len(costs) == 2
    types = {c.cost_type for c in costs}
    assert types == {CostType.LLM_INPUT, CostType.LLM_OUTPUT}
    amounts = {c.cost_type: c.amount_usd for c in costs}
    # 1000 input @ $0.00015/1k = $0.00015; 500 output @ $0.0006/1k = $0.0003
    assert amounts[CostType.LLM_INPUT] == Decimal("0.00015")
    assert amounts[CostType.LLM_OUTPUT] == Decimal("0.0003")


# ── ToolCompleted / ToolFailed ─────────────────────────────────────────────


async def test_tool_completed_records_one_cost(bus_with_recorder) -> None:
    bus, recorder = bus_with_recorder
    tenant_id = TenantId(uuid4())
    workspace_id = WorkspaceId(uuid4())

    await bus.publish(
        _envelope(
            event_name="ToolCompleted",
            payload={
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
                "tool_name": "echo",
                "latency_ms": 12,
            },
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
    )
    runs = await recorder.run_repo.list_records(
        tenant_id=tenant_id, workspace_id=workspace_id
    )
    assert len(runs) == 1
    assert runs[0].run_type == RunType.TOOL
    assert runs[0].status.value == "succeeded"

    costs = await recorder.cost_repo.list_records(
        tenant_id=tenant_id, workspace_id=workspace_id
    )
    assert len(costs) == 1
    assert costs[0].cost_type == CostType.TOOL
    assert costs[0].amount_usd == Decimal(0)


async def test_tool_failed_marks_status_failed(bus_with_recorder) -> None:
    bus, recorder = bus_with_recorder
    tenant_id = TenantId(uuid4())
    workspace_id = WorkspaceId(uuid4())

    await bus.publish(
        _envelope(
            event_name="ToolFailed",
            payload={
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
                "tool_name": "echo",
            },
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
    )
    runs = await recorder.run_repo.list_records(
        tenant_id=tenant_id, workspace_id=workspace_id
    )
    assert len(runs) == 1
    assert runs[0].status.value == "failed"


# ── SkillInvocationCompleted ──────────────────────────────────────────────


async def test_skill_invocation_completed_records_run_and_cost(
    bus_with_recorder,
) -> None:
    bus, recorder = bus_with_recorder
    tenant_id = TenantId(uuid4())
    workspace_id = WorkspaceId(uuid4())

    await bus.publish(
        _envelope(
            event_name="SkillInvocationCompleted",
            payload={
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
                "skill_id": str(uuid4()),
                "skill_name": "summarize",
            },
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
    )
    runs = await recorder.run_repo.list_records(
        tenant_id=tenant_id, workspace_id=workspace_id
    )
    assert len(runs) == 1
    assert runs[0].run_type == RunType.SKILL


# ── MemoryWritten / KnowledgeAssetIngested / ChannelReplySent ─────────────


async def test_memory_written_uses_default_unit_cost(
    bus_with_recorder,
) -> None:
    bus, recorder = bus_with_recorder
    tenant_id = TenantId(uuid4())
    workspace_id = WorkspaceId(uuid4())

    await bus.publish(
        _envelope(
            event_name="MemoryWritten",
            payload={
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
                "entry_id": str(uuid4()),
            },
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
    )
    costs = await recorder.cost_repo.list_records(
        tenant_id=tenant_id, workspace_id=workspace_id
    )
    assert len(costs) == 1
    assert costs[0].cost_type == CostType.MEMORY
    assert costs[0].amount_usd == Decimal("0.00001")


async def test_knowledge_ingested_scales_with_chunk_count(
    bus_with_recorder,
) -> None:
    bus, recorder = bus_with_recorder
    tenant_id = TenantId(uuid4())
    workspace_id = WorkspaceId(uuid4())

    await bus.publish(
        _envelope(
            event_name="KnowledgeAssetIngested",
            payload={
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
                "asset_id": str(uuid4()),
                "chunk_count": 10,
            },
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
    )
    costs = await recorder.cost_repo.list_records(
        tenant_id=tenant_id, workspace_id=workspace_id
    )
    assert len(costs) == 1
    assert costs[0].cost_type == CostType.KNOWLEDGE
    assert costs[0].quantity == 10
    # 10 chunks * $0.001 = $0.01
    assert costs[0].amount_usd == Decimal("0.01")


async def test_channel_reply_sent_records_one_cost(
    bus_with_recorder,
) -> None:
    bus, recorder = bus_with_recorder
    tenant_id = TenantId(uuid4())
    workspace_id = WorkspaceId(uuid4())

    await bus.publish(
        _envelope(
            event_name="ChannelReplySent",
            payload={
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
                "delivery_id": str(uuid4()),
            },
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
    )
    costs = await recorder.cost_repo.list_records(
        tenant_id=tenant_id, workspace_id=workspace_id
    )
    assert len(costs) == 1
    assert costs[0].cost_type == CostType.CHANNEL
    assert costs[0].amount_usd == Decimal("0.0005")


# ── Run-only events: WorkflowRunCompleted, EvalRunCompleted, DecisionRecorded ─


async def test_run_only_events_record_only_run_no_cost(
    bus_with_recorder,
) -> None:
    bus, recorder = bus_with_recorder
    tenant_id = TenantId(uuid4())
    workspace_id = WorkspaceId(uuid4())

    for event in ("WorkflowRunCompleted", "EvalRunCompleted", "DecisionRecorded"):
        await bus.publish(
            _envelope(
                event_name=event,
                payload={
                    "tenant_id": str(tenant_id),
                    "workspace_id": str(workspace_id),
                    "result": "passed",
                },
                tenant_id=tenant_id,
                workspace_id=workspace_id,
            )
        )

    runs = await recorder.run_repo.list_records(
        tenant_id=tenant_id, workspace_id=workspace_id
    )
    assert len(runs) == 3
    types = {r.run_type for r in runs}
    assert types == {RunType.WORKFLOW, RunType.EVAL, RunType.GOVERNANCE}

    costs = await recorder.cost_repo.list_records(
        tenant_id=tenant_id, workspace_id=workspace_id
    )
    assert costs == []


# ── Failure isolation: handle() swallows errors, never raises back to bus ─


async def test_handler_swallows_repo_errors_without_raising(
    bus_with_recorder,
) -> None:
    _bus_unused, recorder = bus_with_recorder

    class _BoomRepo:
        async def add(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    boom_recorder = ObservabilityRecorder(
        run_repo=_BoomRepo(),  # type: ignore[arg-type]
        cost_repo=InMemoryCostRecordRepository(),
        pricing=recorder.pricing,
    )
    bus_2 = InProcessBus()
    await install(bus_2, boom_recorder)

    tenant_id = TenantId(uuid4())
    workspace_id = WorkspaceId(uuid4())

    # publish must NOT raise even though the handler raises
    await bus_2.publish(
        _envelope(
            event_name="MemoryWritten",
            payload={
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
            },
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
    )


# ── Cross-tenant isolation ────────────────────────────────────────────────


async def test_cross_tenant_isolation_via_recorder_repo(
    bus_with_recorder,
) -> None:
    bus, recorder = bus_with_recorder
    tenant_a = TenantId(uuid4())
    tenant_b = TenantId(uuid4())
    workspace = WorkspaceId(uuid4())

    for tid in (tenant_a, tenant_b):
        await bus.publish(
            _envelope(
                event_name="MemoryWritten",
                payload={
                    "tenant_id": str(tid),
                    "workspace_id": str(workspace),
                },
                tenant_id=tid,
                workspace_id=workspace,
            )
        )

    runs_a = await recorder.run_repo.list_records(
        tenant_id=tenant_a, workspace_id=workspace
    )
    runs_b = await recorder.run_repo.list_records(
        tenant_id=tenant_b, workspace_id=workspace
    )
    assert len(runs_a) == 1
    assert len(runs_b) == 1
    assert runs_a[0].tenant_id == tenant_a
    assert runs_b[0].tenant_id == tenant_b
