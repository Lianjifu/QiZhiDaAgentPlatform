"""SQLAlchemy ORM models for the evaluation module.

Three tables:

- ``eval_datasets`` — named tenant-scoped dataset bundle; mutable status
                      (active ↔ archived); 1:N to ``eval_cases``.
- ``eval_cases``     — a single golden case: input + expected_keywords +
                      scoring thresholds; ordinal-sorted per dataset.
- ``eval_runs``      — execution record for an evaluation against a
                      ``(template_id, version_id)`` pair.  Immutable
                      once terminal.  Idempotency is enforced via a
                      partial unique index on
                      ``(tenant_id, idempotency_key) WHERE NOT NULL``.

Cascade rules:

- eval_cases → eval_datasets (CASCADE) — when a dataset is purged, its
  cases go with it; sets are not standalone audit artefacts.
- eval_runs has no FK to a dataset/template/version table because eval
  is the source-of-truth for the gate.  No cascades.

The ``status`` CheckConstraints mirror the strings stored by the domain
entities; the ORM enforces the same constraints as the migration.
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
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column


class EvalDatasetORM(TenantScopedMixin, Base):
    __tablename__ = "eval_datasets"

    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''")
    )
    kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'custom'"),
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'active'"),
    )
    case_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_by: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "kind IN ('builtin','custom')",
            name="eval_datasets_kind_enum",
        ),
        CheckConstraint(
            "status IN ('active','archived')",
            name="eval_datasets_status_enum",
        ),
        CheckConstraint(
            "case_count >= 0",
            name="eval_datasets_case_count_nonneg",
        ),
        make_composite_index("workspace_id", "status"),
    )


class EvalCaseORM(TenantScopedMixin, Base):
    __tablename__ = "eval_cases"

    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    dataset_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("eval_datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    input: Mapped[str] = mapped_column(Text, nullable=False)
    expected_keywords: Mapped[list[str]] = mapped_column(
        ARRAY(String(128)),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )
    min_keywords_hit_ratio: Mapped[float] = mapped_column(
        Numeric(4, 3),
        nullable=False,
        server_default=text("0.600"),
    )
    max_latency_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("30000")
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    __table_args__ = (
        CheckConstraint(
            "min_keywords_hit_ratio BETWEEN 0 AND 1",
            name="eval_cases_min_hit_ratio_range",
        ),
        CheckConstraint(
            "max_latency_ms BETWEEN 1 AND 600000",
            name="eval_cases_max_latency_range",
        ),
        make_composite_index("dataset_id", "ordinal"),
    )


class EvalRunORM(TenantScopedMixin, Base):
    __tablename__ = "eval_runs"

    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    dataset_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("eval_datasets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    template_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    version_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'queued'"),
    )
    mean_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    case_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    passed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    triggered_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','passed','failed','errored')",
            name="eval_runs_status_enum",
        ),
        CheckConstraint(
            "mean_score IS NULL OR mean_score BETWEEN 0 AND 1",
            name="eval_runs_mean_score_range",
        ),
        CheckConstraint(
            "case_count >= 0 AND passed_count >= 0 AND failed_count >= 0",
            name="eval_runs_counts_nonneg",
        ),
        make_composite_index("workspace_id", "template_id", "version_id"),
        Index(
            "uq_eval_runs_idempotency",
            "tenant_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )


__all__ = [
    "EvalCaseORM",
    "EvalDatasetORM",
    "EvalRunORM",
]
