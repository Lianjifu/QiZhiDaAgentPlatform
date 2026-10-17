"""ORM models for model quota (Phase 4).

Two tables:
- model_quotas — configuration (max_tokens, max_requests per period)
- model_quota_usage — sliding-window usage counters (per period_key)
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from qzdap_persistence.base import Base, TenantScopedMixin
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column


class ModelQuotaORM(TenantScopedMixin, Base):
    __tablename__ = "model_quotas"

    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    model_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("admin_models.id", ondelete="CASCADE"),
        nullable=False,
    )
    period: Mapped[str] = mapped_column(String(16), nullable=False)
    max_tokens_in: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    max_tokens_out: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    max_requests: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    description: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''")
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "workspace_id", "model_id", "period",
            name="uq_model_quotas_tenant_ws_model_period",
        ),
        CheckConstraint(
            "period IN ('minute','hour','day')",
            name="ck_model_quotas_period_enum",
        ),
    )


class ModelQuotaUsageORM(TenantScopedMixin, Base):
    __tablename__ = "model_quota_usage"

    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    model_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("admin_models.id", ondelete="CASCADE"),
        nullable=False,
    )
    period: Mapped[str] = mapped_column(String(16), nullable=False)
    period_key: Mapped[str] = mapped_column(String(32), nullable=False)
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    tokens_in: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    tokens_out: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    requests: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "workspace_id", "model_id", "period", "period_key",
            name="uq_model_quota_usage_window",
        ),
    )


__all__ = ["ModelQuotaORM", "ModelQuotaUsageORM"]
