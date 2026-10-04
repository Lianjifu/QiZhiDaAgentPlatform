"""Tests for ObservabilityRecorder — event-bus routing + cost math."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from qzdap_schema.ids import TenantId, WorkspaceId

from qzdap.modules.observability_module.application.pricing import (
    DEFAULT_LLM_PRICING,
    PricingCatalog,
)
from qzdap.modules.observability_module.application.recorder import (
    ObservabilityRecorder,
    install,
)
from qzdap.modules.observability_module.domain.value_objects import (
    CostType,
    RunType,
)

from ._in_memory import (
    InMemoryCostRecordRepository,
    InMemoryRunRecordRepository,
)

# ── helpers ───────────────────────────────────────────────────────────────


def _envelope(
    event_name: str, payload: dict, *, occurred_at_ms: int | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        event_name=event_name,
        payload=payload,
        occurred_at_ms=occurred_at_ms or int(datetime.now(UTC).timestamp() * 1000),
    )


@pytest.fixture
def recorder(pricing_with_skill):
    return ObservabilityRecorder(
        run_repo=InMemoryRunRecordRepository(),
        cost_repo=InMemoryCostRecordRepository(),
        pricing=pricing_with_skill,
    )


# ── topic list ────────────────────────────────────────────────────────────


def test_topics_contains_all_subscribed_events() -> None:
    r = ObservabilityRecorder(
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
    )
    topics = r.topics()
    assert "ModelInvoked" in topics
    assert "ToolCompleted" in topics
    assert "ToolFailed" in topics
    assert "SkillInvocationCompleted" in topics
    assert "MemoryWritten" in topics
    assert "KnowledgeAssetIngested" in topics
    assert "WorkflowRunCompleted" in topics
    assert "ChannelReplySent" in topics
    assert "EvalRunCompleted" in topics
    assert "DecisionRecorded" in topics


def test_unknown_event_ignored(recorder: ObservabilityRecorder) -> None:
    awaitable = recorder.handle(_envelope("TurnStarted", {"tenant_id": uuid4()}))
    # Should be a coroutine; await it and check side effect free.
    import asyncio

    asyncio.run(awaitable)
    assert len(recorder.run_repo._store) == 0


# ── routing: each event produces correct row(s) ───────────────────────────


def _tenant_ws():
    return TenantId(uuid4()), WorkspaceId(uuid4())


def test_record_llm_produces_two_costs(recorder: ObservabilityRecorder) -> None:
    import asyncio

    tid, wid = _tenant_ws()
    asyncio.run(
        recorder.handle(
            _envelope(
                "ModelInvoked",
                {
                    "tenant_id": tid,
                    "workspace_id": wid,
                    "model_id": "gpt-4o-mini",
                    "input_tokens": 1000,
                    "output_tokens": 500,
                    "latency_ms": 120,
                    "provider": "openai",
                },
            )
        )
    )
    runs = list(recorder.run_repo._store.values())
    assert len(runs) == 1
    assert runs[0].run_type == RunType.LLM
    costs = list(recorder.cost_repo._store.values())
    assert len(costs) == 2
    types = sorted(c.cost_type for c in costs)
    assert types == [CostType.LLM_INPUT, CostType.LLM_OUTPUT]


def test_record_tool_completed(recorder: ObservabilityRecorder) -> None:
    import asyncio

    tid, wid = _tenant_ws()
    asyncio.run(
        recorder.handle(
            _envelope(
                "ToolCompleted",
                {
                    "tenant_id": tid,
                    "workspace_id": wid,
                    "tool_name": "echo",
                    "latency_ms": 5,
                },
            )
        )
    )
    runs = list(recorder.run_repo._store.values())
    assert len(runs) == 1
    assert runs[0].run_type == RunType.TOOL
    assert runs[0].status.value == "succeeded"
    costs = list(recorder.cost_repo._store.values())
    assert len(costs) == 1
    assert costs[0].cost_type == CostType.TOOL


def test_record_tool_failed(recorder: ObservabilityRecorder) -> None:
    import asyncio

    tid, wid = _tenant_ws()
    asyncio.run(
        recorder.handle(
            _envelope(
                "ToolFailed",
                {
                    "tenant_id": tid,
                    "workspace_id": wid,
                    "tool_name": "echo",
                },
            )
        )
    )
    runs = list(recorder.run_repo._store.values())
    assert runs[0].status.value == "failed"


def test_record_skill(recorder: ObservabilityRecorder) -> None:
    import asyncio

    tid, wid = _tenant_ws()
    asyncio.run(
        recorder.handle(
            _envelope(
                "SkillInvocationCompleted",
                {
                    "tenant_id": tid,
                    "workspace_id": wid,
                    "skill_id": str(uuid4()),
                    "skill_name": "echo_skill",
                    "latency_ms": 50,
                },
            )
        )
    )
    costs = list(recorder.cost_repo._store.values())
    assert costs[0].amount_usd == Decimal("0.005")
    assert costs[0].cost_type == CostType.SKILL


def test_record_memory(recorder: ObservabilityRecorder) -> None:
    import asyncio

    tid, wid = _tenant_ws()
    asyncio.run(
        recorder.handle(
            _envelope(
                "MemoryWritten",
                {
                    "tenant_id": tid,
                    "workspace_id": wid,
                    "entry_id": str(uuid4()),
                },
            )
        )
    )
    costs = list(recorder.cost_repo._store.values())
    assert costs[0].cost_type == CostType.MEMORY


def test_record_knowledge_ingested(recorder: ObservabilityRecorder) -> None:
    import asyncio

    tid, wid = _tenant_ws()
    asyncio.run(
        recorder.handle(
            _envelope(
                "KnowledgeAssetIngested",
                {
                    "tenant_id": tid,
                    "workspace_id": wid,
                    "asset_id": str(uuid4()),
                    "chunk_count": 3,
                },
            )
        )
    )
    costs = list(recorder.cost_repo._store.values())
    assert costs[0].cost_type == CostType.KNOWLEDGE
    assert costs[0].quantity == 3
    assert costs[0].amount_usd == Decimal("0.001") * 3


def test_record_workflow_completed(recorder: ObservabilityRecorder) -> None:
    import asyncio

    tid, wid = _tenant_ws()
    asyncio.run(
        recorder.handle(
            _envelope(
                "WorkflowRunCompleted",
                {
                    "tenant_id": tid,
                    "workspace_id": wid,
                    "workflow_name": "ingest",
                },
            )
        )
    )
    runs = list(recorder.run_repo._store.values())
    assert runs[0].run_type == RunType.WORKFLOW
    # No cost row.
    assert len(recorder.cost_repo._store) == 0


def test_record_channel_reply(recorder: ObservabilityRecorder) -> None:
    import asyncio

    tid, wid = _tenant_ws()
    asyncio.run(
        recorder.handle(
            _envelope(
                "ChannelReplySent",
                {
                    "tenant_id": tid,
                    "workspace_id": wid,
                    "delivery_id": str(uuid4()),
                },
            )
        )
    )
    costs = list(recorder.cost_repo._store.values())
    assert costs[0].cost_type == CostType.CHANNEL


def test_record_eval_run_completed(recorder: ObservabilityRecorder) -> None:
    import asyncio

    tid, wid = _tenant_ws()
    asyncio.run(
        recorder.handle(
            _envelope(
                "EvalRunCompleted",
                {
                    "tenant_id": tid,
                    "workspace_id": wid,
                    "template_id": str(uuid4()),
                },
            )
        )
    )
    runs = list(recorder.run_repo._store.values())
    assert runs[0].run_type == RunType.EVAL


def test_record_decision_recorded(recorder: ObservabilityRecorder) -> None:
    import asyncio

    tid, wid = _tenant_ws()
    asyncio.run(
        recorder.handle(
            _envelope(
                "DecisionRecorded",
                {
                    "tenant_id": tid,
                    "workspace_id": wid,
                    "decision_id": str(uuid4()),
                },
            )
        )
    )
    runs = list(recorder.run_repo._store.values())
    assert runs[0].run_type == RunType.GOVERNANCE


# ── error safety ──────────────────────────────────────────────────────────


def test_handle_never_raises_on_bad_payload(recorder: ObservabilityRecorder) -> None:
    import asyncio

    # Missing tenant_id — handler must swallow and log.
    async def go() -> None:
        await recorder.handle(_envelope("ModelInvoked", {"input_tokens": 10}))
        await recorder.handle(_envelope("ModelInvoked", {}))

    asyncio.run(go())
    # No runs recorded for either.
    assert len(recorder.run_repo._store) == 0


def test_handle_never_raises_when_repo_errors(recorder: ObservabilityRecorder) -> None:
    import asyncio

    class BoomRepo:
        async def add(self, _):
            raise RuntimeError("db is down")

    boom = ObservabilityRecorder(
        run_repo=BoomRepo(),
        cost_repo=BoomRepo(),
        pricing=PricingCatalog(
            llm_pricing=dict(DEFAULT_LLM_PRICING),
            tool_unit_cost={},
            skill_unit_cost={},
            memory_write_unit_cost_usd=Decimal(0),
            knowledge_ingest_unit_cost_usd=Decimal(0),
            channel_send_unit_cost_usd=Decimal(0),
        ),
    )
    tid = TenantId(uuid4())
    wid = WorkspaceId(uuid4())

    async def go() -> None:
        await boom.handle(
            _envelope(
                "ModelInvoked",
                {"tenant_id": tid, "workspace_id": wid, "model_id": "default"},
            )
        )

    asyncio.run(go())  # must not raise


def test_handle_falls_back_workspace_id(recorder: ObservabilityRecorder) -> None:
    import asyncio

    tid = TenantId(uuid4())

    # No workspace_id in envelope.
    async def go() -> None:
        await recorder.handle(
            _envelope("ToolCompleted", {"tenant_id": tid, "tool_name": "echo"})
        )

    asyncio.run(go())
    runs = list(recorder.run_repo._store.values())
    assert len(runs) == 1
    from uuid import UUID as _UUID

    assert runs[0].workspace_id == _UUID("00000000-0000-0000-0000-000000000000")


# ── install() helper ──────────────────────────────────────────────────────


def test_install_subscribes_each_topic_once() -> None:

    class FakeBus:
        def __init__(self) -> None:
            self.subs: dict[str, list] = {}

        def subscribe(self, topic, handler) -> None:
            self.subs.setdefault(topic, []).append(handler)

    r = ObservabilityRecorder(
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
    )
    bus = FakeBus()
    # install() is async so it works with both sync- and async-subscribe buses.
    asyncio.run(install(bus, r))
    assert set(bus.subs.keys()) == set(r.SUBSCRIBED_EVENTS)
    for handlers in bus.subs.values():
        assert len(handlers) == 1
