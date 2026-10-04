"""Self-evolution ORM model — EvolveCandidate.

Maps 1:1 to the ``0015_self_evolution`` alembic migration. Uses the
shared ``TenantScopedMixin`` so the SQL repo can always issue
``tenant_id == :tid`` guards.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from qzdap_persistence.base import TenantScopedMixin
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class _Base(DeclarativeBase):
    pass


class EvolveCandidateORM(_Base, TenantScopedMixin):
    __tablename__ = "evolve_candidates"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    trigger_reason: Mapped[str] = mapped_column(
        String(256), nullable=False, server_default=""
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
    requester_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    approver_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    correlation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
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
        UniqueConstraint(
            "tenant_id", "fingerprint", name="uq_evolve_candidates_fingerprint"
        ),
        CheckConstraint(
            "status IN ('pending','approved','rejected','applied')",
            name="ck_evolve_candidates_status",
        ),
        CheckConstraint(
            "kind IN ('memory_promote','skill_patch','routing_hint','dream')",
            name="ck_evolve_candidates_kind",
        ),
        Index(
            "ix_evolve_candidates_tenant_status",
            "tenant_id",
            "status",
        ),
        Index(
            "ix_evolve_candidates_tenant_created",
            "tenant_id",
            "created_at",
        ),
    )


__all__ = ["EvolveCandidateORM"]
