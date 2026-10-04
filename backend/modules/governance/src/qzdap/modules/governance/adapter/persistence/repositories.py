"""SQL repository implementations for the four governance tables.

Each class implements the matching application-layer Protocol
(``PolicyRepository`` / ``ApprovalRepository`` / ``DecisionEventRepo`` /
``AuditLogPort``).  Repositories hold an ``AsyncSession`` factory — the
use case layer is responsible for transaction boundaries.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from qzdap.modules.governance.adapter.persistence.mappers import (
    approval_to_domain,
    approval_to_orm,
    audit_to_domain,
    audit_to_orm,
    decision_event_to_domain,
    decision_event_to_orm,
    policy_to_domain,
    policy_to_orm,
)
from qzdap.modules.governance.adapter.persistence.models import (
    ApprovalORM,
    AuditLogORM,
    DecisionEventORM,
    PolicyORM,
)
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


class SqlPolicyRepository(PolicyRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, rule: PolicyRule) -> None:
        async with self._sf() as session:
            session.add(policy_to_orm(rule))
            await session.commit()

    async def get(self, *, tenant_id: UUID, rule_id: UUID) -> PolicyRule | None:
        async with self._sf() as session:
            row = await session.get(PolicyORM, rule_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return policy_to_domain(row)

    async def list_records(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID | None = None,
        enabled_only: bool = False,
        limit: int = 100,
        cursor: str | None = None,
    ) -> list[PolicyRule]:
        async with self._sf() as session:
            stmt = select(PolicyORM).where(PolicyORM.tenant_id == tenant_id)
            if workspace_id is not None:
                stmt = stmt.where(PolicyORM.workspace_id == workspace_id)
            if enabled_only:
                stmt = stmt.where(PolicyORM.enabled.is_(True))
            stmt = stmt.order_by(PolicyORM.priority.asc(), PolicyORM.created_at.asc())
            stmt = stmt.limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [policy_to_domain(r) for r in rows]

    async def list_enabled(self, *, tenant_id: UUID) -> list[PolicyRule]:
        async with self._sf() as session:
            stmt = (
                select(PolicyORM)
                .where(PolicyORM.tenant_id == tenant_id)
                .where(PolicyORM.enabled.is_(True))
                .order_by(PolicyORM.priority.asc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [policy_to_domain(r) for r in rows]

    async def update(self, rule: PolicyRule) -> None:
        async with self._sf() as session:
            stmt = (
                update(PolicyORM)
                .where(PolicyORM.id == UUID(str(rule.id)))
                .where(PolicyORM.tenant_id == UUID(str(rule.tenant_id)))
                .values(
                    subject_type=rule.subject_type.value,
                    subject_ref=rule.subject_ref,
                    action_pattern=rule.action_pattern,
                    effect=rule.effect.value,
                    priority=rule.priority,
                    approval_required=rule.approval_required,
                    quota=dict(rule.quota) if rule.quota else None,
                    enabled=rule.enabled,
                    version_lock=rule.version_lock,
                    updated_at=rule.updated_at,
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def delete(self, *, tenant_id: UUID, rule_id: UUID) -> bool:
        async with self._sf() as session:
            row = await session.get(PolicyORM, rule_id)
            if row is None or row.tenant_id != tenant_id:
                return False
            await session.delete(row)
            await session.commit()
            return True


class SqlApprovalRepository(ApprovalRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, approval: Approval) -> None:
        async with self._sf() as session:
            session.add(approval_to_orm(approval))
            await session.commit()

    async def get(self, *, tenant_id: UUID, approval_id: UUID) -> Approval | None:
        async with self._sf() as session:
            row = await session.get(ApprovalORM, approval_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return approval_to_domain(row)

    async def update(self, approval: Approval) -> None:
        async with self._sf() as session:
            stmt = (
                update(ApprovalORM)
                .where(ApprovalORM.id == UUID(str(approval.id)))
                .where(ApprovalORM.tenant_id == UUID(str(approval.tenant_id)))
                .values(
                    status=approval.status.value,
                    approver_id=UUID(str(approval.approver_id))
                    if approval.approver_id
                    else None,
                    decided_at=approval.decided_at,
                    payload=dict(approval.payload),
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def list_pending(
        self, *, tenant_id: UUID, now: datetime, limit: int = 200
    ) -> list[Approval]:
        async with self._sf() as session:
            stmt = (
                select(ApprovalORM)
                .where(ApprovalORM.tenant_id == tenant_id)
                .where(ApprovalORM.status == ApprovalStatus.PENDING.value)
                .order_by(ApprovalORM.created_at.asc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [approval_to_domain(r) for r in rows]

    async def list_by_status(
        self,
        *,
        tenant_id: UUID,
        status: ApprovalStatus,
        limit: int = 100,
    ) -> list[Approval]:
        async with self._sf() as session:
            stmt = (
                select(ApprovalORM)
                .where(ApprovalORM.tenant_id == tenant_id)
                .where(ApprovalORM.status == status.value)
                .order_by(ApprovalORM.created_at.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [approval_to_domain(r) for r in rows]


class SqlDecisionEventRepo(DecisionEventRepo):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def append(self, event: DecisionEvent) -> None:
        async with self._sf() as session:
            session.add(decision_event_to_orm(event))
            await session.commit()

    async def list_by_tenant(
        self,
        *,
        tenant_id: UUID,
        limit: int = 100,
        cursor: datetime | None = None,
    ) -> list[DecisionEvent]:
        async with self._sf() as session:
            stmt = (
                select(DecisionEventORM)
                .where(DecisionEventORM.tenant_id == tenant_id)
                .order_by(DecisionEventORM.created_at.desc())
                .limit(limit)
            )
            if cursor is not None:
                stmt = stmt.where(DecisionEventORM.created_at < cursor)
            rows = (await session.execute(stmt)).scalars().all()
            return [decision_event_to_domain(r) for r in rows]


class SqlAuditLogAdapter(AuditLogPort):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def append(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID | None,
        event_type: str,
        payload: dict[str, Any],
    ) -> AuditLogEntry:
        from uuid import uuid4

        entry = AuditLogEntry(
            id=uuid4(),
            tenant_id=tenant_id,  # type: ignore[arg-type]
            actor_id=actor_id,  # type: ignore[arg-type]
            event_type=event_type,
            payload=payload,
            created_at=datetime.now(UTC),
        )
        async with self._sf() as session:
            session.add(audit_to_orm(entry))
            await session.commit()
        return entry

    async def list_by_tenant(
        self,
        *,
        tenant_id: UUID,
        limit: int = 100,
        event_type_prefix: str | None = None,
    ) -> list[AuditLogEntry]:
        async with self._sf() as session:
            stmt = (
                select(AuditLogORM)
                .where(AuditLogORM.tenant_id == tenant_id)
                .order_by(AuditLogORM.created_at.desc())
                .limit(limit)
            )
            if event_type_prefix is not None:
                stmt = stmt.where(AuditLogORM.event_type.like(f"{event_type_prefix}%"))
            rows = (await session.execute(stmt)).scalars().all()
            return [audit_to_domain(r) for r in rows]


__all__ = [
    "SqlApprovalRepository",
    "SqlAuditLogAdapter",
    "SqlDecisionEventRepo",
    "SqlPolicyRepository",
]
