"""Governance application ports — repository / port Protocols.

Adapter implementations live in ``adapter/{persistence,subscribers}``.
The application layer never imports them; ``composition/container``
wires concrete adapters at startup.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from qzdap_schema.ids import (
    ApprovalId,
    PolicyId,
    TenantId,
    UserId,
)

from qzdap.modules.governance.domain.entities import (
    Approval,
    AuditLogEntry,
    DecisionEvent,
    PolicyRule,
)
from qzdap.modules.governance.domain.value_objects import ApprovalStatus


@runtime_checkable
class PolicyRepository(Protocol):
    async def add(self, rule: PolicyRule) -> None: ...

    async def get(
        self, *, tenant_id: TenantId, rule_id: PolicyId
    ) -> PolicyRule | None: ...

    async def list_records(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: UUID | None = None,
        enabled_only: bool = False,
        limit: int = 100,
        cursor: str | None = None,
    ) -> list[PolicyRule]: ...

    async def list_enabled(self, *, tenant_id: TenantId) -> list[PolicyRule]:
        """Bulk fetch the tenant's enabled rules — the evaluator hot path."""
        ...

    async def update(self, rule: PolicyRule) -> None: ...

    async def delete(self, *, tenant_id: TenantId, rule_id: PolicyId) -> bool: ...


@runtime_checkable
class ApprovalRepository(Protocol):
    async def add(self, approval: Approval) -> None: ...

    async def get(
        self, *, tenant_id: TenantId, approval_id: ApprovalId
    ) -> Approval | None: ...

    async def update(self, approval: Approval) -> None: ...

    async def list_pending(
        self, *, tenant_id: TenantId, now: datetime, limit: int = 200
    ) -> list[Approval]: ...

    async def list_by_status(
        self,
        *,
        tenant_id: TenantId,
        status: ApprovalStatus,
        limit: int = 100,
    ) -> list[Approval]: ...


@runtime_checkable
class DecisionEventRepo(Protocol):
    async def append(self, event: DecisionEvent) -> None: ...

    async def list_by_tenant(
        self,
        *,
        tenant_id: TenantId,
        limit: int = 100,
        cursor: datetime | None = None,
    ) -> list[DecisionEvent]: ...


@runtime_checkable
class AuditLogPort(Protocol):
    """Append-only audit sink — every business event ends up here."""

    async def append(
        self,
        *,
        tenant_id: TenantId,
        actor_id: UserId | None,
        event_type: str,
        payload: dict[str, Any],
    ) -> AuditLogEntry: ...

    async def list_by_tenant(
        self,
        *,
        tenant_id: TenantId,
        limit: int = 100,
        event_type_prefix: str | None = None,
    ) -> list[AuditLogEntry]: ...


@runtime_checkable
class PolicyEventPublisher(Protocol):
    """Mirrors the kernel EventBus port, narrowed to governance topics."""

    async def publish(self, topic: str, payload: dict[str, Any]) -> None: ...


@runtime_checkable
class ClockPort(Protocol):
    """Injected clock — keeps evaluator timestamps deterministic in tests."""

    def now(self) -> datetime: ...


@runtime_checkable
class IdGeneratorPort(Protocol):
    def new_id(self) -> UUID: ...


__all__ = [
    "ApprovalRepository",
    "AuditLogPort",
    "ClockPort",
    "DecisionEventRepo",
    "IdGeneratorPort",
    "PolicyEventPublisher",
    "PolicyRepository",
]
