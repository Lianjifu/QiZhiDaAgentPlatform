"""SQLAlchemy ORM models for the observability_module.

Two tables:

- ``run_records`` — single observed business action (LLM invocation,
  tool call, skill invocation, memory write, etc.).  Source-of-truth
  is the originating event-bus event; the row records ``source_id``
  for cross-reference (weak FK — see migration docstring).
- ``cost_records`` — money line attached to a ``run_records`` row.
  ``amount_usd`` is NUMERIC(12, 6) — first Decimal column in the
  project.

Both inherit :class:`TenantScopedMixin` and thus get ``id`` /
``tenant_id`` / ``created_at`` from the mixin.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from qzdap_persistence.base import Base, TenantScopedMixin, make_composite_index
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column


class RunRecordORM(TenantScopedMixin, Base):
    __tablename__ = "run_records"

    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    run_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    actor_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'succeeded'"),
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    __table_args__ = (
        CheckConstraint(
            "run_type IN ('llm','tool','skill','memory','knowledge',"
            "'workflow','channel','eval','governance')",
            name="run_type_enum",
        ),
        CheckConstraint(
            "status IN ('succeeded','failed','running')",
            name="status_enum",
        ),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="latency_nonneg",
        ),
        make_composite_index("workspace_id", "run_type", "completed_at"),
    )


class CostRecordORM(TenantScopedMixin, Base):
    __tablename__ = "cost_records"

    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    run_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("run_records.id", ondelete="RESTRICT"),
        nullable=False,
    )
    cost_type: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_usd: Mapped[Any] = mapped_column(Numeric(12, 6), nullable=False)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'call'")
    )
    currency: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text("'USD'")
    )
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    __table_args__ = (
        CheckConstraint(
            "cost_type IN ('llm_input','llm_output','tool','skill','memory',"
            "'knowledge','channel')",
            name="cost_type_enum",
        ),
        CheckConstraint("amount_usd >= 0", name="amount_nonneg"),
        CheckConstraint("currency = 'USD'", name="currency_usd"),
        CheckConstraint("length(unit) BETWEEN 1 AND 16", name="unit_length"),
        CheckConstraint("quantity IS NULL OR quantity >= 0", name="quantity_nonneg"),
        make_composite_index("workspace_id", "created_at"),
        make_composite_index("run_id"),
    )


__all__ = ["CostRecordORM", "RunRecordORM"]
