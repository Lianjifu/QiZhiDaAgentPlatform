"""In-memory fakes for the governance application ports.

Implementations of ``PolicyRepository`` / ``ApprovalRepository`` /
``DecisionEventRepo`` / ``AuditLogPort`` plus ``ClockPort`` /
``IdGeneratorPort`` / ``PolicyEventPublisher``.  No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from qzdap.modules.governance.application.ports import (
    ApprovalRepository,
    AuditLogPort,
    DecisionEventRepo,
    PolicyRepository,
)
from qzdap.modules.governance.domain.entities import (
    Approval,
    AuditLogEntry,
    DecisionEvent,
    PolicyRule,
)
from qzdap.modules.governance.domain.value_objects import ApprovalStatus

# ── PolicyRepository ────────────────────────────────────────────────────────


class InMemoryPolicyRepository(PolicyRepository):
    def __init__(self) -> None:
        self._rows: dict[UUID, PolicyRule] = {}

    async def add(self, rule: PolicyRule) -> None:
        self._rows[rule.id] = rule

    async def get(self, *, tenant_id, rule_id):  # type: ignore[no-untyped-def]
        row = self._rows.get(rule_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return row

    async def list_records(
        self,
        *,
        tenant_id,
        workspace_id=None,
        enabled_only: bool = False,
        limit: int = 100,
        cursor=None,
    ):  # type: ignore[no-untyped-def]
        out: list[PolicyRule] = []
        for r in self._rows.values():
            if r.tenant_id != tenant_id:
                continue
            if workspace_id is not None and r.workspace_id != workspace_id:
                continue
            if enabled_only and not r.enabled:
                continue
            out.append(r)
        out.sort(key=lambda r: (r.priority, str(r.id)))
        return out[:limit]

    async def list_enabled(self, *, tenant_id):  # type: ignore[no-untyped-def]
        return await self.list_records(
            tenant_id=tenant_id, workspace_id=None, enabled_only=True, limit=10_000
        )

    async def update(self, rule: PolicyRule) -> None:
        self._rows[rule.id] = rule

    async def delete(self, *, tenant_id, rule_id) -> bool:  # type: ignore[no-untyped-def]
        row = self._rows.get(rule_id)
        if row is None or row.tenant_id != tenant_id:
            return False
        del self._rows[rule_id]
        return True


# ── ApprovalRepository ──────────────────────────────────────────────────────


class InMemoryApprovalRepository(ApprovalRepository):
    def __init__(self) -> None:
        self._rows: dict[UUID, Approval] = {}

    async def add(self, approval: Approval) -> None:
        self._rows[approval.id] = approval

    async def get(self, *, tenant_id, approval_id):  # type: ignore[no-untyped-def]
        row = self._rows.get(approval_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return row

    async def update(self, approval: Approval) -> None:
        self._rows[approval.id] = approval

    async def list_pending(self, *, tenant_id, now: datetime, limit: int = 200):
        out = [
            a
            for a in self._rows.values()
            if a.tenant_id == tenant_id
            and a.status is ApprovalStatus.PENDING
            and a.expires_at > now
        ]
        out.sort(key=lambda a: a.created_at)
        return out[:limit]

    async def list_by_status(
        self, *, tenant_id, status: ApprovalStatus, limit: int = 100
    ):
        return [
            a
            for a in self._rows.values()
            if a.tenant_id == tenant_id and a.status is status
        ][:limit]


# ── DecisionEventRepo ───────────────────────────────────────────────────────


class InMemoryDecisionEventRepo(DecisionEventRepo):
    def __init__(self) -> None:
        self.events: list[DecisionEvent] = []

    async def append(self, event: DecisionEvent) -> None:
        self.events.append(event)

    async def list_by_tenant(self, *, tenant_id, limit: int = 100, cursor=None):
        out = [e for e in self.events if e.tenant_id == tenant_id]
        out.sort(key=lambda e: e.created_at, reverse=True)
        return out[:limit]


# ── AuditLogPort ────────────────────────────────────────────────────────────


class InMemoryAuditLog(AuditLogPort):
    def __init__(self) -> None:
        self.rows: list[AuditLogEntry] = []

    async def append(self, *, tenant_id, actor_id, event_type, payload):
        entry = AuditLogEntry(
            id=uuid4(),
            tenant_id=tenant_id,
            actor_id=actor_id,
            event_type=event_type,
            payload=dict(payload),
            created_at=datetime.now(UTC),
        )
        self.rows.append(entry)
        return entry

    async def list_by_tenant(
        self, *, tenant_id, limit: int = 100, event_type_prefix: str | None = None
    ):
        out = [e for e in self.rows if e.tenant_id == tenant_id]
        if event_type_prefix is not None:
            out = [e for e in out if e.event_type.startswith(event_type_prefix)]
        out.sort(key=lambda e: e.created_at, reverse=True)
        return out[:limit]


# ── Clock + Id + Publisher ──────────────────────────────────────────────────


class FixedClock:
    """Returns a configurable timestamp; bump via ``advance()``."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 1, 1, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float = 0.0) -> None:
        from datetime import timedelta

        self._now = self._now + timedelta(seconds=seconds)


class SequenceIds:
    def __init__(self) -> None:
        self._n = 0

    def new_id(self) -> UUID:
        self._n += 1
        # deterministic-but-unique id per test run
        return UUID(int=self._n)


@dataclass
class RecordingPublisher:
    """Captures published topics + payloads."""

    published: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self.published.append((topic, dict(payload)))
