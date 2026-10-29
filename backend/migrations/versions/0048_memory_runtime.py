"""Memory 运行时：L2 补用户维度与幂等列 + STM 缓冲表 + 策略约束放开 + 死表下线。

依据：docs/refactor/session-architecture/memory-refactor-plan.md §9.2

1) ``admin_memory_l2`` 补 8 列：``user_id`` / ``content_hash`` /
   ``content_hash_version`` / ``source_turn_id`` / ``last_used_at`` /
   ``used_count`` / ``confidence_source`` / ``version``。
   ⚠️ ``user_id`` **必须由写入侧持久化 owner_id** —— 决策 #11：存量自动沉淀的
   记忆**不回填**（``write()`` 过去把 owner_id 直接丢了，显示名既可能是占位符
   也可能重名，回填必串号）。下面只对**能唯一确定归属**的历史行回填。

2) ``session_memory_buffer``：STM 未提炼缓冲（带 session_id / user_id）——
   决策 #5（L1 退役）的落点。

3) ``admin_memory_promotions`` 补 from_layer / to_layer / reason，并从旧的
   ``layer = 'l1→l2'`` 单串回填。

4) ``admin_memory_policies`` 唯一约束放开到 label 维度（决策 #12）。

5) DROP 死表 ``memory_l2_embeddings``（台账 X19）：0036 建、**零代码引用**，
   与生产在用的 ``admin_memory_vec`` 职责重复。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0048_memory_runtime"
down_revision: str | Sequence[str] | None = "0047_context_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    # ------------------------------------------------------------------
    # 1) admin_memory_l2 补列
    # ------------------------------------------------------------------
    op.add_column("admin_memory_l2", sa.Column("user_id", uuid, nullable=True))
    op.add_column("admin_memory_l2", sa.Column("content_hash", sa.String(64), nullable=True))
    op.add_column(
        "admin_memory_l2",
        sa.Column(
            "content_hash_version",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column("admin_memory_l2", sa.Column("source_turn_id", uuid, nullable=True))
    op.add_column(
        "admin_memory_l2", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "admin_memory_l2",
        sa.Column("used_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "admin_memory_l2",
        sa.Column(
            "confidence_source",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'rule'"),
        ),
    )
    op.add_column(
        "admin_memory_l2",
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )

    # 1a) user_id 回填 —— 只回填「能唯一确定归属」的历史行：
    #     · user_name 是占位符 '用户'（自动沉淀）→ 一律不回填
    #     · 同租户内 display_name 重名 → 不回填（会串号）
    #     ⚠️ 表名是 users（identity 模块），没有 identity_users 这张表。
    op.execute(
        """
        UPDATE admin_memory_l2 l
           SET user_id = u.id
          FROM users u
         WHERE u.tenant_id = l.tenant_id
           AND u.display_name = l.user_name
           AND l.user_name <> '用户'
           AND l.user_name <> ''
           AND u.display_name NOT IN (
               SELECT display_name FROM users
                WHERE tenant_id = l.tenant_id
                GROUP BY display_name HAVING COUNT(*) > 1
           )
        """
    )

    # 1b) content_hash 存量**不回填**（§4.4 决策：存量不参与去重，
    #     下次被重写时再补）。

    op.create_index(
        "uq_memory_l2_content_hash",
        "admin_memory_l2",
        ["tenant_id", "workspace_id", "user_id", "content_hash"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL AND content_hash IS NOT NULL"),
    )
    op.create_index(
        "ix_memory_l2_user",
        "admin_memory_l2",
        ["tenant_id", "workspace_id", "user_id", "status"],
    )

    # 1c) 向量 payload 补 user_id（决策 #2 的落地对象）。
    #     admin_memory_vec.id 就是 L2 的 id（vector adapter 用 fact.id 做 item_id）。
    #     关联不上的行（存量自动记忆）保持没有 user_id —— 在按用户过滤时不可见，
    #     这是决策 #11 要求的方向（宁可不可见，不要串号）。
    op.execute(
        """
        UPDATE admin_memory_vec v
           SET payload = v.payload || jsonb_build_object('user_id', l.user_id::text)
          FROM admin_memory_l2 l
         WHERE l.id = v.id
           AND l.user_id IS NOT NULL
           AND NOT (v.payload ? 'user_id')
        """
    )

    # ------------------------------------------------------------------
    # 2) STM 缓冲表（决策 #5：L1 退役的落点）
    # ------------------------------------------------------------------
    op.create_table(
        "session_memory_buffer",
        sa.Column("id", uuid, nullable=False),
        sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("workspace_id", uuid, nullable=False),
        sa.Column("session_id", uuid, nullable=False),
        sa.Column("user_id", uuid, nullable=False),
        sa.Column("turn_id", uuid, nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "candidates",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'buffer'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_session_memory_buffer"),
        sa.UniqueConstraint(
            "session_id",
            "content_hash",
            name="uq_session_memory_buffer_hash",
        ),
    )

    # ------------------------------------------------------------------
    # 3) admin_memory_promotions 补字段并回填
    # ------------------------------------------------------------------
    op.add_column(
        "admin_memory_promotions",
        sa.Column("from_layer", sa.String(8), nullable=False, server_default=sa.text("'l1'")),
    )
    op.add_column(
        "admin_memory_promotions",
        sa.Column("to_layer", sa.String(8), nullable=False, server_default=sa.text("'l2'")),
    )
    op.add_column(
        "admin_memory_promotions",
        sa.Column("reason", sa.String(256), nullable=False, server_default=sa.text("''")),
    )
    op.execute(
        """
        UPDATE admin_memory_promotions
           SET from_layer = split_part(layer, '→', 1),
               to_layer   = split_part(layer, '→', 2)
         WHERE layer LIKE '%→%'
        """
    )

    # ------------------------------------------------------------------
    # 4) admin_memory_policies 放开唯一约束（决策 #12）
    # ------------------------------------------------------------------
    op.drop_constraint(
        "uq_admin_memory_policies_tenant_ws_layer",
        "admin_memory_policies",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_admin_memory_policies_tenant_ws_layer_label",
        "admin_memory_policies",
        ["tenant_id", "workspace_id", "layer", "label"],
    )

    # ------------------------------------------------------------------
    # 5) 死表下线（台账 X19）
    # ------------------------------------------------------------------
    op.execute("DROP TABLE IF EXISTS memory_l2_embeddings")


def downgrade() -> None:
    # 1) 恢复策略唯一约束
    op.drop_constraint(
        "uq_admin_memory_policies_tenant_ws_layer_label",
        "admin_memory_policies",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_admin_memory_policies_tenant_ws_layer",
        "admin_memory_policies",
        ["tenant_id", "workspace_id", "layer"],
    )

    # 2) promotions 补的列
    op.drop_column("admin_memory_promotions", "reason")
    op.drop_column("admin_memory_promotions", "to_layer")
    op.drop_column("admin_memory_promotions", "from_layer")

    # 3) STM 缓冲表
    op.drop_table("session_memory_buffer")

    # 4) L2 补的列与索引
    op.drop_index("ix_memory_l2_user", "admin_memory_l2")
    op.drop_index("uq_memory_l2_content_hash", "admin_memory_l2")
    op.drop_column("admin_memory_l2", "version")
    op.drop_column("admin_memory_l2", "confidence_source")
    op.drop_column("admin_memory_l2", "used_count")
    op.drop_column("admin_memory_l2", "last_used_at")
    op.drop_column("admin_memory_l2", "source_turn_id")
    op.drop_column("admin_memory_l2", "content_hash")
    op.drop_column("admin_memory_l2", "content_hash_version")
    op.drop_column("admin_memory_l2", "user_id")

    # 5) 向量 payload 里的 user_id 一并摘掉（回滚后按 workspace 过滤）
    op.execute(
        """
        UPDATE admin_memory_vec
           SET payload = payload - 'user_id'
         WHERE payload ? 'user_id'
        """
    )

    # 6) 死表 memory_l2_embeddings 的 DROP **不可逆** —— 它零引用，
    #    对运行时无影响；确需恢复时执行 0036_memory_l2_embeddings 的 upgrade()。
