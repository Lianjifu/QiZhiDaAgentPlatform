"""Replace orch_plans / workflow_runs with the admin workflow catalog.

Revision ID: 0024_admin_workflows
Revises: 0023_admin_memory
Create Date: 2026-10-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_admin_workflows"
down_revision: str | Sequence[str] | None = "0023_admin_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("workflow_step_runs")
    op.drop_table("workflow_runs")
    op.drop_table("orch_plans")

    op.create_table(
        "admin_workflows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("owner", sa.String(128), nullable=False, server_default=sa.text("''")),
        sa.Column("scene", sa.String(64), nullable=False, server_default=sa.text("''")),
        sa.Column("trigger", sa.String(16), nullable=False, server_default=sa.text("'消息触发'")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("call_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("inputs", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("outputs", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "bound_agents",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "versions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "initial_nodes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "initial_edges",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "name",
            name="uq_admin_workflows_tenant_ws_name",
        ),
    )
    op.create_index(
        "ix_admin_workflows_tenant_workspace_status",
        "admin_workflows",
        ["tenant_id", "workspace_id", "status"],
    )
    op.create_index("ix_admin_workflows_workspace_id", "admin_workflows", ["workspace_id"])
    op.create_index("ix_admin_workflows_tenant_id", "admin_workflows", ["tenant_id"])

    op.create_table(
        "admin_workflow_user_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("favorited", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "workflow_id",
            name="uq_admin_workflow_user_state",
        ),
    )
    op.create_index(
        "ix_admin_workflow_user_state_user",
        "admin_workflow_user_state",
        ["tenant_id", "user_id", "workflow_id"],
    )
    op.create_index(
        "ix_admin_workflow_user_state_workspace_id",
        "admin_workflow_user_state",
        ["workspace_id"],
    )
    op.create_index(
        "ix_admin_workflow_user_state_user_id",
        "admin_workflow_user_state",
        ["user_id"],
    )
    op.create_index(
        "ix_admin_workflow_user_state_workflow_id",
        "admin_workflow_user_state",
        ["workflow_id"],
    )
    op.create_index(
        "ix_admin_workflow_user_state_tenant_id",
        "admin_workflow_user_state",
        ["tenant_id"],
    )

    op.create_table(
        "admin_workflow_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("time", sa.String(64), nullable=False, server_default=sa.text("''")),
        sa.Column("result", sa.String(128), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_admin_workflow_runs_user_created",
        "admin_workflow_runs",
        ["tenant_id", "user_id", "created_at"],
    )
    op.create_index("ix_admin_workflow_runs_workspace_id", "admin_workflow_runs", ["workspace_id"])
    op.create_index("ix_admin_workflow_runs_user_id", "admin_workflow_runs", ["user_id"])
    op.create_index("ix_admin_workflow_runs_workflow_id", "admin_workflow_runs", ["workflow_id"])
    op.create_index("ix_admin_workflow_runs_tenant_id", "admin_workflow_runs", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("admin_workflow_runs")
    op.drop_table("admin_workflow_user_state")
    op.drop_table("admin_workflows")
