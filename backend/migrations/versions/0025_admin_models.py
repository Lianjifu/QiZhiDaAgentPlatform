"""Replace models / credentials / routing_policies with the admin catalog.

Revision ID: 0025_admin_models
Revises: 0024_admin_workflows
Create Date: 2026-10-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_admin_models"
down_revision: str | Sequence[str] | None = "0024_admin_workflows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("quota_counters")
    op.drop_table("routing_policies")
    op.drop_table("models")
    op.drop_table("model_credentials")

    op.create_table(
        "admin_model_providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("region", sa.String(64), nullable=False, server_default=sa.text("'custom'")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'healthy'")),
        sa.Column("base_url", sa.String(512), nullable=False, server_default=sa.text("''")),
        sa.Column("api_key_masked", sa.String(64), nullable=False, server_default=sa.text("'••••'")),
        sa.Column("protocol", sa.String(32), nullable=False, server_default=sa.text("'openai'")),
        sa.Column("encrypted_payload", sa.LargeBinary(), nullable=False, server_default=sa.text("'\\x'::bytea")),
        sa.Column("error_rate", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("avg_latency_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("qps", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_admin_model_providers_tenant_ws", "admin_model_providers", ["tenant_id", "workspace_id"])
    op.create_index("ix_admin_model_providers_workspace_id", "admin_model_providers", ["workspace_id"])
    op.create_index("ix_admin_model_providers_tenant_id", "admin_model_providers", ["tenant_id"])

    op.create_table(
        "admin_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_name", sa.String(256), nullable=False, server_default=sa.text("''")),
        sa.Column("task", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("context_window", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("price_in", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("price_out", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("success_rate", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("tier", sa.String(16), nullable=False, server_default=sa.text("'balanced'")),
        sa.Column("starred", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("calls", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("trend", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("description", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_admin_models_tenant_ws_status", "admin_models", ["tenant_id", "workspace_id", "status"])
    op.create_index("ix_admin_models_workspace_id", "admin_models", ["workspace_id"])
    op.create_index("ix_admin_models_provider_id", "admin_models", ["provider_id"])
    op.create_index("ix_admin_models_tenant_id", "admin_models", ["tenant_id"])

    op.create_table(
        "admin_model_routes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("task", sa.String(32), nullable=False, server_default=sa.text("'generation'")),
        sa.Column("strategy", sa.String(32), nullable=False, server_default=sa.text("'quality-first'")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("primary_model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "fallback_model_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("description", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_admin_model_routes_tenant_ws", "admin_model_routes", ["tenant_id", "workspace_id"])
    op.create_index("ix_admin_model_routes_workspace_id", "admin_model_routes", ["workspace_id"])
    op.create_index("ix_admin_model_routes_tenant_id", "admin_model_routes", ["tenant_id"])

    op.create_table(
        "admin_model_health",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_name", sa.String(256), nullable=False, server_default=sa.text("''")),
        sa.Column("message", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("occurred_at", sa.String(32), nullable=False, server_default=sa.text("''")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_admin_model_health_tenant_ws", "admin_model_health", ["tenant_id", "workspace_id"])
    op.create_index("ix_admin_model_health_workspace_id", "admin_model_health", ["workspace_id"])
    op.create_index("ix_admin_model_health_provider_id", "admin_model_health", ["provider_id"])
    op.create_index("ix_admin_model_health_tenant_id", "admin_model_health", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("admin_model_health")
    op.drop_table("admin_model_routes")
    op.drop_table("admin_models")
    op.drop_table("admin_model_providers")
