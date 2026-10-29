"""Context 运行时：rolling_summary 独立成列 + 上下文 manifest 表。

依据：docs/refactor/session-architecture/context-refactor-plan.md §7.2

⚠️ 物理顺序：本迁移在 0046 之后跑 —— Context 要读 ``session_messages.session_seq``
（0046 新增的会话内单调序号）。

1) ``agent_sessions.rolling_summary``：摘要的**唯一落点**。回填按
   ``graph_state`` 优先 → ``metadata`` 兜底（与旧路径
   ``copilot.py:379-380`` 的写入优先级一致）。

   ⚠️ **本迁移不清空 ``metadata['rolling_summary']``**：旧路径（copilot.py /
   runner.py）**仍是当前唯一写者**，直到 Context Stage 3 迁移写入点、
   Stage 4 停用旧循环。提前清空会把旧路径正在写的副本删掉。清理动作放在
   Stage 4 之后执行（见 Context 方案 §9 Stage 3 / §5.3）。

2) ``session_context_manifests``：每次模型调用一条（Context 决策 #6，
   粒度 ``(turn_id, step)``）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0047_context_runtime"
down_revision: str | Sequence[str] | None = "0046_session_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    # ------------------------------------------------------------------
    # 1) rolling_summary 独立成列
    # ------------------------------------------------------------------
    op.add_column(
        "agent_sessions",
        sa.Column(
            "rolling_summary",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )

    # 1a) graph_state 优先
    op.execute(
        """
        UPDATE agent_sessions s
           SET rolling_summary = s.graph_state->>'rolling_summary'
         WHERE s.graph_state ? 'rolling_summary'
           AND COALESCE(s.graph_state->>'rolling_summary', '') <> ''
        """
    )
    # 1b) metadata 兜底（graph_state 为空的行）
    op.execute(
        """
        UPDATE agent_sessions s
           SET rolling_summary = COALESCE(s.metadata->>'rolling_summary', '')
         WHERE COALESCE(s.graph_state->>'rolling_summary', '') = ''
           AND s.metadata ? 'rolling_summary'
        """
    )

    # ------------------------------------------------------------------
    # 2) manifest 表
    # ------------------------------------------------------------------
    op.create_table(
        "session_context_manifests",
        sa.Column("id", uuid, nullable=False),
        sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("workspace_id", uuid, nullable=False),
        sa.Column("session_id", uuid, nullable=False),
        sa.Column("turn_id", uuid, nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("manifest", postgresql.JSONB, nullable=False),
        sa.Column("tokens_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "degraded",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_session_context_manifests"),
        sa.UniqueConstraint(
            "turn_id",
            "step",
            name="uq_session_context_manifests_turn_step",
        ),
    )
    op.create_index(
        "ix_session_context_manifests_session",
        "session_context_manifests",
        ["tenant_id", "session_id", "created_at"],
    )


def downgrade() -> None:
    # 回滚前先把摘要写回 metadata —— 否则这次迁移回填出来的内容会丢。
    op.execute(
        """
        UPDATE agent_sessions
           SET metadata = metadata || jsonb_build_object(
                   'rolling_summary', rolling_summary
               )
         WHERE rolling_summary <> ''
           AND metadata->>'rolling_summary' IS DISTINCT FROM rolling_summary
        """
    )
    op.drop_index("ix_session_context_manifests_session", "session_context_manifests")
    op.drop_table("session_context_manifests")
    op.drop_column("agent_sessions", "rolling_summary")
