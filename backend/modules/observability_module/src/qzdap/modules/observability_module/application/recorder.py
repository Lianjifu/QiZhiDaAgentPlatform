"""ObservabilityRecorder — subscribes to business events on the bus.

Mirrors the pattern used by ``governance.audit_subscriber`` /
``governance.audit_recorder``: the recorder is the EventBus handler,
``install(bus, recorder)`` wires subscriptions in lifespan.

Critical: ``handle()`` NEVER raises back to the bus.  A failing record
is logged at warning and dropped, since the originating business
operation has already succeeded by the time the event lands here.

Subscribed events use the EventEnvelope ``event_name`` (the dataclass
class name — e.g. ``"TurnCompleted"``).  This is the canonical topic
key in InProcessBus.  The audit recorder's dotted-string topic list is
broken (no class is published under those names today) and is being
left alone for P9 to ship the observability path first.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar

from qzdap_schema.ids import (
    TenantId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.observability_module.application.ports import (
    CostRecordRepository,
    RunRecordRepository,
)
from qzdap.modules.observability_module.application.pricing import PricingCatalog
from qzdap.modules.observability_module.domain.entities import (
    CostRecord,
    RunRecord,
)
from qzdap.modules.observability_module.domain.value_objects import (
    CostType,
    RunStatus,
    RunType,
)

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class ObservabilityRecorder:
    """Event-bus handler that writes RunRecord + CostRecord rows."""

    run_repo: RunRecordRepository
    cost_repo: CostRecordRepository
    pricing: PricingCatalog
    publisher: object | None = None
    logger: logging.Logger | None = None

    SUBSCRIBED_EVENTS: ClassVar[tuple[str, ...]] = (
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
    )

    def topics(self) -> tuple[str, ...]:
        return self.SUBSCRIBED_EVENTS

    async def handle(self, envelope: Any) -> None:
        """EventBus handler. Never raises back to the bus."""
        try:
            event_name = _event_name(envelope)
            if event_name not in self.SUBSCRIBED_EVENTS:
                return
            payload = _payload(envelope)
            tenant_id, workspace_id = _identity(envelope, payload)
            if tenant_id is None:
                _log.warning("observability dropped: no tenant_id on %s", event_name)
                return
            if workspace_id is None:
                from uuid import UUID as _UUID

                workspace_id = WorkspaceId(_UUID(_ZERO_WORKSPACE_HEX))
            await self._route(event_name, envelope, payload, tenant_id, workspace_id)
        except Exception as exc:  # noqa: BLE001 — observability must not raise
            (self.logger or _log).warning(
                "observability handle failed event=%s err=%s",
                _event_name(envelope),
                exc,
            )

    # ── routing ─────────────────────────────────────────────────────────

    async def _route(
        self,
        event_name: str,
        envelope: Any,
        payload: dict[str, Any],
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
    ) -> None:
        actor_id = _actor_id(payload)
        completed_at = _occurred_at(envelope)
        if event_name == "ModelInvoked":
            await self._record_llm(
                payload, tenant_id, workspace_id, completed_at, actor_id
            )
        elif event_name in ("ToolCompleted", "ToolFailed"):
            await self._record_tool(
                payload,
                tenant_id,
                workspace_id,
                completed_at,
                actor_id,
                failed=event_name == "ToolFailed",
            )
        elif event_name == "SkillInvocationCompleted":
            await self._record_skill(
                payload, tenant_id, workspace_id, completed_at, actor_id
            )
        elif event_name == "MemoryWritten":
            await self._record_memory(
                payload, tenant_id, workspace_id, completed_at, actor_id
            )
        elif event_name == "KnowledgeAssetIngested":
            await self._record_knowledge(
                payload, tenant_id, workspace_id, completed_at, actor_id
            )
        elif event_name == "WorkflowRunCompleted":
            await self._record_run_only(
                payload=payload,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                run_type=RunType.WORKFLOW,
                status=RunStatus.SUCCEEDED,
                completed_at=completed_at,
                actor_id=actor_id,
            )
        elif event_name == "ChannelReplySent":
            await self._record_channel(
                payload, tenant_id, workspace_id, completed_at, actor_id
            )
        elif event_name == "EvalRunCompleted":
            await self._record_run_only(
                payload=payload,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                run_type=RunType.EVAL,
                status=RunStatus.SUCCEEDED,
                completed_at=completed_at,
                actor_id=actor_id,
            )
        elif event_name == "DecisionRecorded":
            await self._record_run_only(
                payload=payload,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                run_type=RunType.GOVERNANCE,
                status=RunStatus.SUCCEEDED,
                completed_at=completed_at,
                actor_id=actor_id,
            )

    # ── per-event recorders ─────────────────────────────────────────────

    async def _record_llm(
        self,
        payload: dict[str, Any],
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        completed_at: datetime,
        actor_id: UserId | None,
    ) -> None:
        in_t = int(payload.get("input_tokens", 0) or 0)
        out_t = int(payload.get("output_tokens", 0) or 0)
        latency_ms = _maybe_int(payload.get("latency_ms"))
        model_id = str(payload.get("model_id") or payload.get("model") or "default")
        status = (
            RunStatus.FAILED
            if str(payload.get("status", "ok")).lower() == "error"
            else RunStatus.SUCCEEDED
        )
        run = RunRecord.from_event(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            run_type=RunType.LLM,
            source_id=None,
            completed_at=completed_at,
            status=status,
            latency_ms=latency_ms,
            actor_id=actor_id,
            metadata={
                "model_id": model_id,
                "input_tokens": in_t,
                "output_tokens": out_t,
                "provider": payload.get("provider"),
            },
        )
        await self.run_repo.add(run)
        in_cost, out_cost = self.pricing.llm_cost(
            model_id=model_id, input_tokens=in_t, output_tokens=out_t
        )
        await self.cost_repo.add(
            CostRecord.create(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                run_id=run.id,
                cost_type=CostType.LLM_INPUT,
                amount_usd=in_cost,
                quantity=in_t,
                unit="token",
                currency=self.pricing.currency,
                model_id=model_id,
            )
        )
        await self.cost_repo.add(
            CostRecord.create(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                run_id=run.id,
                cost_type=CostType.LLM_OUTPUT,
                amount_usd=out_cost,
                quantity=out_t,
                unit="token",
                currency=self.pricing.currency,
                model_id=model_id,
            )
        )

    async def _record_tool(
        self,
        payload: dict[str, Any],
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        completed_at: datetime,
        actor_id: UserId | None,
        *,
        failed: bool,
    ) -> None:
        tool_name = str(payload.get("tool_name") or "unknown")
        latency_ms = _maybe_int(payload.get("latency_ms"))
        run = RunRecord.from_event(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            run_type=RunType.TOOL,
            source_id=None,
            completed_at=completed_at,
            status=RunStatus.FAILED if failed else RunStatus.SUCCEEDED,
            latency_ms=latency_ms,
            actor_id=actor_id,
            metadata={"tool_name": tool_name},
        )
        await self.run_repo.add(run)
        await self.cost_repo.add(
            CostRecord.create(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                run_id=run.id,
                cost_type=CostType.TOOL,
                amount_usd=self.pricing.tool_cost(tool_name=tool_name),
                quantity=1,
                unit="call",
                currency=self.pricing.currency,
                metadata={"tool_name": tool_name},
            )
        )

    async def _record_skill(
        self,
        payload: dict[str, Any],
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        completed_at: datetime,
        actor_id: UserId | None,
    ) -> None:
        skill_id_raw = payload.get("skill_id")
        skill_name = str(payload.get("skill_name") or skill_id_raw or "unknown")
        latency_ms = _maybe_int(payload.get("latency_ms"))
        run = RunRecord.from_event(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            run_type=RunType.SKILL,
            source_id=_maybe_uuid(skill_id_raw),
            completed_at=completed_at,
            status=RunStatus.SUCCEEDED,
            latency_ms=latency_ms,
            actor_id=actor_id,
            metadata={"skill_name": skill_name},
        )
        await self.run_repo.add(run)
        await self.cost_repo.add(
            CostRecord.create(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                run_id=run.id,
                cost_type=CostType.SKILL,
                amount_usd=self.pricing.skill_cost(skill_name=skill_name),
                quantity=1,
                unit="call",
                currency=self.pricing.currency,
                metadata={"skill_name": skill_name},
            )
        )

    async def _record_memory(
        self,
        payload: dict[str, Any],
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        completed_at: datetime,
        actor_id: UserId | None,
    ) -> None:
        entry_id = _maybe_uuid(payload.get("entry_id"))
        run = RunRecord.from_event(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            run_type=RunType.MEMORY,
            source_id=entry_id,
            completed_at=completed_at,
            status=RunStatus.SUCCEEDED,
            actor_id=actor_id,
            metadata={},
        )
        await self.run_repo.add(run)
        await self.cost_repo.add(
            CostRecord.create(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                run_id=run.id,
                cost_type=CostType.MEMORY,
                amount_usd=self.pricing.memory_write_cost(),
                quantity=1,
                unit="call",
                currency=self.pricing.currency,
            )
        )

    async def _record_knowledge(
        self,
        payload: dict[str, Any],
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        completed_at: datetime,
        actor_id: UserId | None,
    ) -> None:
        asset_id = _maybe_uuid(payload.get("asset_id"))
        chunk_count = int(payload.get("chunk_count", 1) or 1)
        run = RunRecord.from_event(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            run_type=RunType.KNOWLEDGE,
            source_id=asset_id,
            completed_at=completed_at,
            status=RunStatus.SUCCEEDED,
            actor_id=actor_id,
            metadata={"chunk_count": chunk_count},
        )
        await self.run_repo.add(run)
        await self.cost_repo.add(
            CostRecord.create(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                run_id=run.id,
                cost_type=CostType.KNOWLEDGE,
                amount_usd=self.pricing.knowledge_ingest_cost(chunk_count=chunk_count),
                quantity=chunk_count,
                unit="chunk",
                currency=self.pricing.currency,
            )
        )

    async def _record_channel(
        self,
        payload: dict[str, Any],
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        completed_at: datetime,
        actor_id: UserId | None,
    ) -> None:
        delivery_id = _maybe_uuid(payload.get("delivery_id"))
        run = RunRecord.from_event(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            run_type=RunType.CHANNEL,
            source_id=delivery_id,
            completed_at=completed_at,
            status=RunStatus.SUCCEEDED,
            actor_id=actor_id,
            metadata={},
        )
        await self.run_repo.add(run)
        await self.cost_repo.add(
            CostRecord.create(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                run_id=run.id,
                cost_type=CostType.CHANNEL,
                amount_usd=self.pricing.channel_send_cost(),
                quantity=1,
                unit="call",
                currency=self.pricing.currency,
            )
        )

    async def _record_run_only(
        self,
        *,
        payload: dict[str, Any],
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        run_type: RunType,
        status: RunStatus,
        completed_at: datetime,
        actor_id: UserId | None,
    ) -> None:
        run = RunRecord.from_event(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            run_type=run_type,
            source_id=None,
            completed_at=completed_at,
            status=status,
            actor_id=actor_id,
            metadata={
                k: v
                for k, v in payload.items()
                if k not in {"tenant_id", "workspace_id"}
            },
        )
        await self.run_repo.add(run)


# ── subscriber installer ─────────────────────────────────────────────────


async def install(
    event_bus: Any,
    recorder: ObservabilityRecorder,
    *,
    logger: logging.Logger | None = None,
) -> None:
    """Subscribe recorder.handle to every topic in recorder.topics().

    Awaits ``event_bus.subscribe`` so this works with both sync-subscribe
    buses (InProcessBus — handler stored immediately) and async-subscribe
    buses (RedisStreamBus — handler registered once the awaitable resolves).
    """
    handler = recorder.handle
    seen: set[str] = set()
    for topic in recorder.topics():
        if topic in seen:
            continue
        seen.add(topic)
        result = event_bus.subscribe(topic, handler)
        if inspect.isawaitable(result):
            await result
    (logger or _log).info("observability recorder installed topics=%d", len(seen))


# ── internal pure helpers ─────────────────────────────────────────────────


# sentinel workspace for events that don't carry one — keeps the
# per-tenant aggregate correct (only tenant_id is required).
_ZERO_WORKSPACE_HEX = "00000000-0000-0000-0000-000000000000"


def _event_name(envelope: Any) -> str:
    if isinstance(envelope, dict):
        return (
            envelope.get("event_name")
            or envelope.get("topic")
            or envelope.get("payload", {}).get("event_name")
            or "unknown"
        )
    return (
        getattr(envelope, "event_name", None)
        or getattr(envelope, "topic", None)
        or "unknown"
    )


def _payload(envelope: Any) -> dict[str, Any]:
    if isinstance(envelope, dict):
        payload = envelope.get("payload")
        return payload if isinstance(payload, dict) else {}
    payload = getattr(envelope, "payload", None)
    return payload if isinstance(payload, dict) else {}


def _identity(
    envelope: Any, payload: dict[str, Any]
) -> tuple[TenantId | None, WorkspaceId | None]:
    raw_tid = payload.get("tenant_id")
    if raw_tid is None and not isinstance(envelope, dict):
        raw_tid = getattr(envelope, "tenant_id", None)
    raw_wid = payload.get("workspace_id")
    if raw_wid is None and not isinstance(envelope, dict):
        raw_wid = getattr(envelope, "workspace_id", None)
    from uuid import UUID

    def _to_uuid(raw: Any) -> UUID | None:
        if raw is None:
            return None
        if isinstance(raw, UUID):
            return raw
        try:
            return UUID(str(raw))
        except (TypeError, ValueError):
            return None

    tid = _to_uuid(raw_tid)
    wid = _to_uuid(raw_wid)
    if wid is not None and str(wid) == _ZERO_WORKSPACE_HEX:
        wid = None
    return (TenantId(tid) if tid is not None else None), (
        WorkspaceId(wid) if wid is not None else None
    )


def _actor_id(payload: dict[str, Any]) -> UserId | None:
    raw = (
        payload.get("actor_id") or payload.get("user_id") or payload.get("principal_id")
    )
    if raw is None:
        return None
    try:
        return UserId(raw)
    except (TypeError, ValueError):
        return None


def _occurred_at(envelope: Any) -> datetime:
    if isinstance(envelope, dict):
        ms = envelope.get("occurred_at_ms")
    else:
        ms = getattr(envelope, "occurred_at_ms", None)
    if isinstance(ms, (int, float)) and ms > 0:
        return datetime.fromtimestamp(int(ms) / 1000.0, tz=UTC)
    return datetime.now(UTC)


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _maybe_uuid(value: Any) -> Any:
    if value is None:
        return None
    from uuid import UUID

    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


__all__ = [
    "ObservabilityRecorder",
    "install",
]
