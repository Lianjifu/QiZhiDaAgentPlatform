"""Stage 2 persistence: new tables + agent_sessions extensions (§8 / §14.1).

Per session-module-refactor-plan.md §8 Stage 2 and §14.1:

- 新增表: session_turns / session_messages / session_events / session_inbox
         / tool_executions / outbox_dead_letters
- agent_sessions 扩展: 新增 status 枚举值 (RUNNING / WAITING_APPROVAL /
         CANCELLED), current_revision, current_turn_id, agent_version_pinned,
         channel_session_key
- graph_state 字段保留: §4.4 双写兼容一个发布周期, 不删除
- 不引入 langgraph tables: 由 langgraph[postgres] setup 自行管理 (§14.1)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0035_session_stage2_persistence"
down_revision = "0034_identity_control"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    # ------------------------------------------------------------------
    # 1. agent_sessions 字段扩展
    # ------------------------------------------------------------------
    # 扩展 status 枚举（v1: OPEN/RUNNING/WAITING_APPROVAL/CLOSED/CANCELLED）
    op.drop_constraint("status_enum", "agent_sessions", type_="check")
    op.create_check_constraint(
        "status_enum",
        "agent_sessions",
        "status IN ('open','closed','running','waiting_approval','cancelled')",
    )

    op.add_column(
        "agent_sessions",
        sa.Column("current_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agent_sessions",
        sa.Column(
            "current_turn_id",
            uuid,
            nullable=True,
        ),
    )
    op.add_column(
        "agent_sessions",
        sa.Column(
            "agent_version_pinned", sa.String(64), nullable=True
        ),
    )
    op.add_column(
        "agent_sessions",
        sa.Column(
            "channel_session_key", sa.String(512), nullable=True
        ),
    )
    op.create_index(
        "ix_agent_sessions_channel_session_key",
        "agent_sessions",
        ["channel_session_key"],
    )

    # ------------------------------------------------------------------
    # 2. session_turns（§4.2）
    # ------------------------------------------------------------------
    op.create_table(
        "session_turns",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, nullable=False, index=True),
        sa.Column("workspace_id", uuid, nullable=False),
        sa.Column("session_id", uuid, nullable=False, index=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="running",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("agent_version", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("expected_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.CheckConstraint(
            "status IN ('running','waiting','succeeded','failed','cancelled')",
            name="session_turns_status_enum",
        ),
        sa.UniqueConstraint(
            "session_id",
            "idempotency_key",
            name="uq_session_turns_session_idem",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent_sessions.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_session_turns_tenant_session",
        "session_turns",
        ["tenant_id", "session_id"],
    )
    op.create_index(
        "ix_session_turns_status",
        "session_turns",
        ["status"],
    )

    # ------------------------------------------------------------------
    # 3. session_messages（§4.2）
    # ------------------------------------------------------------------
    op.create_table(
        "session_messages",
        sa.Column("turn_id", uuid, nullable=False, index=True),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("message_id", sa.String(64), nullable=True),
        sa.Column("metadata_", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("turn_id", "seq", name="pk_session_messages"),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["session_turns.id"],
            ondelete="CASCADE",
        ),
    )

    # ------------------------------------------------------------------
    # 4. session_events（§4.2 + §4.4 outbox 状态机）
    # ------------------------------------------------------------------
    op.create_table(
        "session_events",
        sa.Column("turn_id", uuid, nullable=False, index=True),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column(
            "delivery_status",
            sa.String(16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "delivery_attempts", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "delivery_status IN ('pending','delivered','failed','dead_letter')",
            name="session_events_status_enum",
        ),
        sa.PrimaryKeyConstraint("turn_id", "seq", name="pk_session_events"),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["session_turns.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_session_events_pending",
        "session_events",
        ["delivery_status", "created_at"],
    )

    # ------------------------------------------------------------------
    # 5. session_inbox（§4.2 channel 去重）
    # ------------------------------------------------------------------
    op.create_table(
        "session_inbox",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, nullable=False, index=True),
        sa.Column("workspace_id", uuid, nullable=False),
        sa.Column("channel_id", sa.String(128), nullable=False),
        sa.Column("external_message_id", sa.String(256), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("turn_id", uuid, nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "channel_id",
            "external_message_id",
            name="uq_session_inbox_dedup",
        ),
    )

    # ------------------------------------------------------------------
    # 6. tool_executions（§4.2 / §5.8 副作用工具幂等）
    # ------------------------------------------------------------------
    op.create_table(
        "tool_executions",
        sa.Column("tool_call_id", sa.String(64), primary_key=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("result_ref", sa.String(512), nullable=True),
        sa.Column("reconcile_endpoint", sa.String(512), nullable=True),
        sa.Column("turn_id", uuid, nullable=False, index=True),
        sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("workspace_id", uuid, nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','running','succeeded','failed','timeout')",
            name="tool_executions_status_enum",
        ),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["session_turns.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_tool_executions_tenant_status",
        "tool_executions",
        ["tenant_id", "status"],
    )

    # ------------------------------------------------------------------
    # 7. outbox_dead_letters（§4.2 / §4.4 死信）
    # ------------------------------------------------------------------
    op.create_table(
        "outbox_dead_letters",
        sa.Column("turn_id", uuid, nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "dead_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint(
            "turn_id", "seq", "attempt", name="pk_outbox_dead_letters"
        ),
    )
    op.create_index(
        "ix_outbox_dead_letters_dead_at",
        "outbox_dead_letters",
        ["dead_at"],
    )


def downgrade() -> None:
    # 删除顺序：依赖表 → 主体表
    op.drop_index("ix_outbox_dead_letters_dead_at", "outbox_dead_letters")
    op.drop_table("outbox_dead_letters")

    op.drop_index("ix_tool_executions_tenant_status", "tool_executions")
    op.drop_table("tool_executions")

    op.drop_table("session_inbox")

    op.drop_index("ix_session_events_pending", "session_events")
    op.drop_table("session_events")

    op.drop_table("session_messages")

    op.drop_index("ix_session_turns_status", "session_turns")
    op.drop_index("ix_session_turns_tenant_session", "session_turns")
    op.drop_table("session_turns")

    op.drop_index(
        "ix_agent_sessions_channel_session_key", "agent_sessions"
    )
    op.drop_column("agent_sessions", "channel_session_key")
    op.drop_column("agent_sessions", "agent_version_pinned")
    op.drop_column("agent_sessions", "current_turn_id")
    op.drop_column("agent_sessions", "current_revision")

    op.drop_constraint("status_enum", "agent_sessions", type_="check")
    op.create_check_constraint(
        "status_enum",
        "agent_sessions",
        "status IN ('open','closed')",
    )