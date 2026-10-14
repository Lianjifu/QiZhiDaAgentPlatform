"""Stage 8 PR B: data_subject_deletion_log (§14.1 / §8)。

§8 Stage 8 退出条件:
- 用户删除请求一键清理 4 处存储 (langgraph_checkpoints / langgraph_store /
  session_messages / LangSmith trace)
- 写 data_subject_deletion_log 留痕 (本 migration)
- 旧 graph_state 字段保留只读 1 个发布周期 (Stage 2 引入的双写迁移到期后)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0038_data_subject_deletion_log"
down_revision = "0037_cost_attribution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    op.create_table(
        "data_subject_deletion_log",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", uuid, nullable=False, index=True),
        sa.Column("tenant_id", uuid, nullable=False, index=True),
        sa.Column("scopes", postgresql.ARRAY(sa.String(32)), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("checkpoints_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("store_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("messages_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trace_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','partial','failed')",
            name="data_subject_status_enum",
        ),
    )
    op.create_index(
        "ix_data_subject_deletion_user_tenant",
        "data_subject_deletion_log",
        ["user_id", "tenant_id"],
    )

    # §8 Stage 8 退出条件: 旧 graph_state 字段保留只读 1 个发布周期
    # 这里通过注释标记 deprecation, 不删列 (避免影响回滚)
    # 真实下线由后续 PR (Stage 8 后) 执行
    # 仅添加 is_legacy_graph_state 索引方便审计
    op.create_index(
        "ix_agent_sessions_legacy_graph_state",
        "agent_sessions",
        ["id"],
        postgresql_where=sa.text("(graph_state IS NOT NULL)"),
    )


def downgrade() -> None:
    op.drop_index("ix_agent_sessions_legacy_graph_state", "agent_sessions")
    op.drop_index("ix_data_subject_deletion_user_tenant", "data_subject_deletion_log")
    op.drop_table("data_subject_deletion_log")