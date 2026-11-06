"""删掉三张**没人写也没人读**的表 ✓。

死代码审查（2026-11-06 ✓）发现这三张表在**整个仓库里零引用** ✓ ——
ORM 没映射 ✓、没有裸 SQL 读写 ✓、端点不碰 ✓ → 建了就没用起来 ✗✗
（典型的「建而不切」✓）：

- ``user_sessions``（迁移 0001 ✓，0039 加过 ``updated_at`` ✓）—— 登录态
  早就由 **JWT** 承担了 ✓（``libs/auth`` ✓），这张表**没人写** ✓；对应的
  ``UserSessionORM`` 模型已一并删除 ✓。
- ``cost_attribution``（迁移 0037 ✓）—— 成本归集没有实现 ✓，成本数据实际
  在 ``session_turns.cost_usd`` ✓（那条路是活的 ✓）。
- ``data_subject_deletion_log``（迁移 0038 ✓）—— 治理模块有「删除数据主体」
  端点 ✓（``/v1/data-subject/delete`` ✓），但**删除记录从没被写过** ✓ ——
  每个域各自实现 ``delete`` ✓，没人往这张表写 ✓。

⚠️ **downgrade 按原样重建空表** ✓ —— 数据本来就没有 ✓，重建出来也是空的 ✓
（列 / 约束 / 索引都照抄原迁移 ✓ —— 回滚链路保持完整 ✓）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0067_drop_dead_tables"
down_revision: str | Sequence[str] | None = "0066_admin_agent_route"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("user_sessions", "cost_attribution", "data_subject_deletion_log")


def upgrade() -> None:
    for table in _TABLES:
        op.drop_table(table)


def downgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)

    # ── user_sessions（0001 + 0039 的 updated_at）────────────────────
    op.create_table(
        "user_sessions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("user_id", uuid, nullable=False),
        sa.Column("jti", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_sessions_tenant_id", "user_sessions", ["tenant_id"])
    op.create_index("ix_user_sessions_tenant_id_user_id", "user_sessions", ["tenant_id", "user_id"])

    # ── cost_attribution（0037）───────────────────────────────────────
    op.create_table(
        "cost_attribution",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, nullable=False, index=True),
        sa.Column("workspace_id", uuid, nullable=False),
        sa.Column("user_id", uuid, nullable=False),
        sa.Column("agent_id", uuid, nullable=False),
        sa.Column("agent_version", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("period", sa.String(16), nullable=False, server_default="daily"),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cache_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column(
            "attribution_status",
            sa.String(16),
            nullable=False,
            server_default="ok",
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
            "user_id",
            "agent_id",
            "agent_version",
            "period",
            name="uq_cost_attribution_scope",
        ),
        sa.CheckConstraint(
            "attribution_status IN ('ok','degraded')",
            name="cost_attribution_status_enum",
        ),
    )
    op.create_index(
        "ix_cost_attribution_period",
        "cost_attribution",
        ["period", "tenant_id"],
    )

    # ── data_subject_deletion_log（0038）──────────────────────────────
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
