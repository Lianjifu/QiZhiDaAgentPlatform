"""SQLAlchemy ORM models for the agent_factory module.

Three tables:

- ``agent_templates``  — named tenant-scoped templates; mutable status
                         (active ↔ archived); default prompt + model
                         inherited by new versions.
- ``agent_versions``   — typed-columns snapshot of an agent's runtime
                         config.  IMMUTABLE once ``status != 'draft'``.
                         Uniqueness enforced by
                         ``(tenant_id, template_id, version_tag)``.
- ``releases``         — record of a successful gate-passed release.
                         Carries eval_run_id + eval_score snapshot.

Cascade rules:

- agent_versions → agent_templates (RESTRICT) — historical versions
  must outlive template deletion; archival must be explicit.
- releases → agent_templates (RESTRICT), → agent_versions (RESTRICT) —
  release rows are an audit artefact and never cascade.

The ``status`` CheckConstraints mirror the strings stored by the
domain entities; the ORM enforces the same constraints as the
migration.
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
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column


class AgentTemplateORM(TenantScopedMixin, Base):
    __tablename__ = "agent_templates"

    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''")
    )
    default_model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    default_system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'active'"),
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
            "status IN ('active','archived')",
            name="agent_templates_status_enum",
        ),
        make_composite_index("workspace_id", "status"),
    )


class AgentVersionORM(TenantScopedMixin, Base):
    __tablename__ = "agent_versions"

    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    template_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("agent_templates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_tag: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'draft'"),
    )
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    allowed_tools: Mapped[list[str]] = mapped_column(
        ARRAY(String(128)),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )
    allowed_skills: Mapped[list[str]] = mapped_column(
        ARRAY(String(128)),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )
    knowledge_package_ids: Mapped[list[str]] = mapped_column(
        ARRAY(String(128)),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )
    plan_dsl_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    max_total_steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    release_notes: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''")
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
            "status IN ('draft','published','released','retired')",
            name="agent_versions_status_enum",
        ),
        CheckConstraint(
            "max_total_steps IS NULL OR (max_total_steps BETWEEN 1 AND 256)",
            name="agent_versions_max_total_steps_range",
        ),
        make_composite_index("workspace_id", "template_id", "status"),
    )


class ReleaseORM(TenantScopedMixin, Base):
    __tablename__ = "releases"

    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    template_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("agent_templates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("agent_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    eval_run_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    eval_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'released'"),
    )
    released_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    released_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))

    __table_args__ = (
        CheckConstraint(
            "status IN ('released')",
            name="releases_status_enum",
        ),
        make_composite_index("workspace_id", "template_id", "released_at"),
    )


__all__ = [
    "AgentTemplateORM",
    "AgentVersionORM",
    "ReleaseORM",
]
