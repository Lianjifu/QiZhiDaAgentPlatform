"""Governance persistence models — SQLAlchemy ORM.

Tables map 1:1 to the ``0007_governance`` alembic migration:
- ``policies``
- ``approvals``
- ``decision_events``
- ``audit_log``

Each model carries a ``TenantScopedMixin`` (where applicable) so the
SQL repository can issue ``tenant_id == :tid`` guards on every query.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from qzdap_persistence.base import TenantScopedMixin
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class _Base(DeclarativeBase):
    pass


class PolicyORM(_Base, TenantScopedMixin):
    __tablename__ = "policies"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    action_pattern: Mapped[str] = mapped_column(String(256), nullable=False)
    effect: Mapped[str] = mapped_column(String(16), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    approval_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    quota: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    version_lock: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "effect IN ('allow','deny','approval')", name="ck_policies_effect"
        ),
        CheckConstraint(
            "subject_type IN ('role','user','agent')", name="ck_policies_subject"
        ),
        Index(
            "ix_policies_enabled_lookup",
            "tenant_id",
            "subject_type",
            "action_pattern",
            postgresql_where=("enabled = true"),
        ),
        Index("ix_policies_tenant_id", "tenant_id"),
    )


class ApprovalORM(_Base, TenantScopedMixin):
    __tablename__ = "approvals"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    requester_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    resource: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    action: Mapped[str] = mapped_column(String(256), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
    approver_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    correlation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','denied','expired')",
            name="ck_approvals_status",
        ),
        Index("ix_approvals_tenant_status", "tenant_id", "status"),
    )


class DecisionEventORM(_Base, TenantScopedMixin):
    __tablename__ = "decision_events"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    actor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(256), nullable=False)
    effect: Mapped[str] = mapped_column(String(16), nullable=False)
    resource: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    rule_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    approval_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_decision_events_tenant_created", "tenant_id", "created_at"),
    )


class AuditLogORM(_Base, TenantScopedMixin):
    __tablename__ = "audit_log"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    actor_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_audit_log_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_log_tenant_event", "tenant_id", "event_type"),
    )


__all__ = ["ApprovalORM", "AuditLogORM", "DecisionEventORM", "PolicyORM"]
