"""Session 运行时：会话唯一化 + 轮次留痕列 + 消息会话内序号 + LangGraph checkpoint 表。

依据：docs/modules/agent-runtime.md

1) agent_sessions：外部会话映射唯一化 —— 部分唯一索引
   ``(tenant_id, channel_session_key) WHERE channel_session_key IS NOT NULL``。
   会话创建归 Session（Router 决策 #10：Router 只派生 key）。
   ``wait_status`` **不删** —— Stage 0 只停写不删列，物理 DROP 放在 Stage 6。

2) session_turns：审批挂起 / 取消标记 / 入站序号 / 两列路由留痕。
   ``route_decision``（Router 写）与 ``agent_decision``（Agent 写）是**两个列、
   两个写者** —— 语义不同、写入时刻不同，共用一列会互相覆盖。
   状态枚举加 ``queued``（Router 决策 #1 = S1 严格排队）。

3) session_messages：加 ``session_id`` / ``session_seq``。``session_id`` 没有
   DEFAULT，因此必须三步：可空列 → 回填 → SET NOT NULL。

4) LangGraph checkpoint 表。⚠️ 表名按**已安装的 langgraph-checkpoint-postgres
   3.1.3** 的实际 DDL 来建（``checkpoints`` / ``checkpoint_blobs`` /
   ``checkpoint_writes`` / ``checkpoint_migrations``，**无 langgraph_ 前缀、
   无 _v2 变体**）—— saver 的 ``setup()`` 用的是这组名字，带前缀的版本在
   3.x 已经不存在。建完把 ``checkpoint_migrations`` 的版本行写成 9
   （``len(MIGRATIONS) - 1``），``setup()`` 就不会再重复执行它的迁移。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0046_session_runtime"
down_revision: str | Sequence[str] | None = "0045_router_ingress_seq"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# langgraph.checkpoint.postgres.base.MIGRATIONS 的长度 - 1
_CHECKPOINT_MIGRATION_VERSION = 9


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    # ------------------------------------------------------------------
    # 1) agent_sessions：外部会话映射唯一化
    # ------------------------------------------------------------------
    op.create_index(
        "uq_agent_sessions_channel_key",
        "agent_sessions",
        ["tenant_id", "channel_session_key"],
        unique=True,
        postgresql_where=sa.text("channel_session_key IS NOT NULL"),
    )
    # 0035 建的普通索引 (channel_session_key) 已被上面这个部分唯一索引覆盖 ——
    # 当前全仓没有任何「仅按 channel_session_key」的查询（grep 确认），故 DROP；
    # 回滚脚本里重建。
    op.drop_index("ix_agent_sessions_channel_session_key", "agent_sessions")

    # ------------------------------------------------------------------
    # 2) session_turns
    # ------------------------------------------------------------------
    op.add_column("session_turns", sa.Column("pending_approval", postgresql.JSONB, nullable=True))
    op.add_column(
        "session_turns",
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("session_turns", sa.Column("ingress_seq", sa.Integer(), nullable=True))
    op.add_column("session_turns", sa.Column("route_decision", postgresql.JSONB, nullable=True))
    op.add_column("session_turns", sa.Column("agent_decision", postgresql.JSONB, nullable=True))

    op.create_index(
        "uq_session_turns_session_ingress",
        "session_turns",
        ["session_id", "ingress_seq"],
        unique=True,
        postgresql_where=sa.text("ingress_seq IS NOT NULL"),
    )

    # 轮次状态枚举加 'queued'
    op.drop_constraint("session_turns_status_enum", "session_turns", type_="check")
    op.create_check_constraint(
        "session_turns_status_enum",
        "session_turns",
        "status IN ('queued','running','waiting','succeeded','failed','cancelled')",
    )

    # ------------------------------------------------------------------
    # 3) session_messages：会话内单调序号
    # ------------------------------------------------------------------
    op.add_column("session_messages", sa.Column("session_id", uuid, nullable=True))
    op.add_column(
        "session_messages",
        sa.Column(
            "session_seq",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    # 3a) 回填 session_id —— 注意 join 键是 session_turns.**id**
    #     （0035 建的主键列名是 id，不是 turn_id）。
    op.execute(
        """
        UPDATE session_messages m
           SET session_id = t.session_id
          FROM session_turns t
         WHERE t.id = m.turn_id
           AND m.session_id IS NULL
        """
    )

    # 3b) 孤儿检查：turn_id 在 session_turns 无对应 → session_id 仍为 NULL，
    #     SET NOT NULL 会失败。FK(turn_id → session_turns.id) 保证不会有孤儿，
    #     这里仍显式检查一次，让异常在迁移阶段暴露而不是在运行期。
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM session_messages m
                 WHERE m.session_id IS NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM session_turns t WHERE t.id = m.turn_id
                   )
            ) THEN
                RAISE EXCEPTION
                    'session_messages 存在孤儿行（turn_id 在 session_turns 无对应），无法回填 session_id';
            END IF;
        END $$;
        """
    )

    # 3c) 回填会话内序号：按 (轮次开始时间, 消息 seq) 在会话内排序
    op.execute(
        """
        WITH ordered AS (
            SELECT m.turn_id,
                   m.seq,
                   ROW_NUMBER() OVER (
                       PARTITION BY t.session_id
                       ORDER BY t.started_at, m.seq
                   ) AS session_seq
              FROM session_messages m
              JOIN session_turns t ON t.id = m.turn_id
        )
        UPDATE session_messages m
           SET session_seq = o.session_seq
          FROM ordered o
         WHERE m.turn_id = o.turn_id
           AND m.seq = o.seq
        """
    )

    op.alter_column("session_messages", "session_id", nullable=False)

    op.create_index(
        "uq_session_messages_session_seq",
        "session_messages",
        ["session_id", "session_seq"],
        unique=True,
    )

    # ------------------------------------------------------------------
    # 4) LangGraph checkpoint 表（AsyncPostgresSaver 的实际 DDL）
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS checkpoint_migrations (
            v INTEGER PRIMARY KEY
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS checkpoints (
            thread_id TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            checkpoint_id TEXT NOT NULL,
            parent_checkpoint_id TEXT,
            type TEXT,
            checkpoint JSONB NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}',
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS checkpoint_blobs (
            thread_id TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            channel TEXT NOT NULL,
            version TEXT NOT NULL,
            type TEXT NOT NULL,
            blob BYTEA,
            PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS checkpoint_writes (
            thread_id TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            checkpoint_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            idx INTEGER NOT NULL,
            channel TEXT NOT NULL,
            type TEXT,
            blob BYTEA NOT NULL,
            task_path TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
        )
        """
    )
    op.create_index("checkpoints_thread_id_idx", "checkpoints", ["thread_id"])
    op.create_index("checkpoint_blobs_thread_id_idx", "checkpoint_blobs", ["thread_id"])
    op.create_index("checkpoint_writes_thread_id_idx", "checkpoint_writes", ["thread_id"])
    # 让 saver 的 setup() 认为自己已是最新版本，不再重复执行它自己的迁移。
    op.execute(
        sa.text(
            "INSERT INTO checkpoint_migrations (v) VALUES (:v) ON CONFLICT DO NOTHING"
        ).bindparams(v=_CHECKPOINT_MIGRATION_VERSION)
    )


def downgrade() -> None:
    # 1) checkpoint 表
    for table in (
        "checkpoint_writes",
        "checkpoint_blobs",
        "checkpoints",
        "checkpoint_migrations",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")

    # 2) 新增索引
    op.drop_index("uq_session_messages_session_seq", "session_messages")
    op.drop_index("uq_session_turns_session_ingress", "session_turns")
    op.drop_index("uq_agent_sessions_channel_key", "agent_sessions")

    # 3) 新增列
    op.drop_column("session_messages", "session_id")
    op.drop_column("session_messages", "session_seq")
    op.drop_column("session_turns", "agent_decision")
    op.drop_column("session_turns", "route_decision")
    op.drop_column("session_turns", "ingress_seq")
    op.drop_column("session_turns", "cancel_requested")
    op.drop_column("session_turns", "pending_approval")

    # 4) 恢复轮次状态枚举
    op.drop_constraint("session_turns_status_enum", "session_turns", type_="check")
    op.create_check_constraint(
        "session_turns_status_enum",
        "session_turns",
        "status IN ('running','waiting','succeeded','failed','cancelled')",
    )

    # 5) 重建 0035 的普通索引
    op.create_index(
        "ix_agent_sessions_channel_session_key",
        "agent_sessions",
        ["channel_session_key"],
    )
