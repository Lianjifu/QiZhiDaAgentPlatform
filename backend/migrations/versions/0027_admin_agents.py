"""Admin agents catalog + session graph_state / messages.

Revision ID: 0027_admin_agents
Revises: 0026_skill_runtime
Create Date: 2026-10-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_admin_agents"
down_revision: str | Sequence[str] | None = "0026_skill_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("category", sa.String(64), nullable=False, server_default=sa.text("''")),
        sa.Column("owner", sa.String(128), nullable=False, server_default=sa.text("''")),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("version", sa.String(32), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("tone", sa.String(16), nullable=False, server_default=sa.text("'brand'")),
        sa.Column("calls", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("success_rate", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_rate", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("avg_latency_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rating", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("starred", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("visible_scope", postgresql.JSONB(), nullable=False, server_default=sa.text("'[\"部门\"]'::jsonb")),
        sa.Column("data_access", sa.String(256), nullable=False, server_default=sa.text("''")),
        sa.Column("model", sa.String(128), nullable=False, server_default=sa.text("''")),
        sa.Column("max_steps", sa.Integer(), nullable=False, server_default=sa.text("8")),
        sa.Column("tools", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("versions", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("evaluation_pass_rate", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("evaluation_runs", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("evaluation_failed_cases", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("trend", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("prompts", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("custom_prompts", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("knowledge_refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("memory_policy", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("flow_refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_admin_agents_tenant_workspace_status",
        "admin_agents",
        ["tenant_id", "workspace_id", "status"],
    )
    op.create_unique_constraint(
        "uq_admin_agents_tenant_ws_name", "admin_agents", ["tenant_id", "workspace_id", "name"]
    )

    op.create_table(
        "admin_agent_user_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("favorited", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "user_id", "agent_id", name="uq_admin_agent_user_state"),
    )

    op.create_table(
        "agent_session_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("seq", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("tool_name", sa.String(128), nullable=False, server_default=sa.text("''")),
        sa.Column("extra", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_agent_session_messages_session_seq", "agent_session_messages", ["session_id", "seq"])

    op.add_column(
        "agent_sessions",
        sa.Column("graph_state", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "agent_sessions",
        sa.Column("wait_status", sa.String(32), nullable=False, server_default=sa.text("'idle'")),
    )


def downgrade() -> None:
    op.drop_column("agent_sessions", "wait_status")
    op.drop_column("agent_sessions", "graph_state")
    op.drop_table("agent_session_messages")
    op.drop_table("admin_agent_user_state")
    op.drop_table("admin_agents")
