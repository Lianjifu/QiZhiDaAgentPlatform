"""Gateway 幂等键分层：session_inbox 加列 + 唯一约束换成只覆盖 strong 的部分唯一索引。

依据：docs/architecture/session-lifecycle.md（决策 #3 / #5）

- ``external_message_id`` 放开 NOT NULL —— web / api 的幂等键来自 clientRequestId，
  没有平台消息 ID 的语义。
- 新增 ``idempotency_key`` / ``key_source`` / ``key_strength`` / ``status`` /
  ``claimed_at`` / ``expires_at`` 六列。
- 旧唯一约束 ``(tenant_id, channel_id, external_message_id)`` 换成
  **只覆盖 strong 的部分唯一索引** —— 决策 #5 要求 weak 键「不抑制」，若普通唯一
  约束覆盖全部行，两条内容相同、落在同一 time_bucket 的 weak 消息会互相冲突，
  第二条被误判为重复。
- ``workspace_id`` / ``channel_id`` 保持 NOT NULL：PostgreSQL 的 UNIQUE 约束里
  NULL 互不相等，改 nullable 会让「workspace 为空」的消息被反复插入。

注意：``ADD COLUMN ... NOT NULL`` 在非空表上会失败，因此这里先带 server_default
加上列、再 DROP DEFAULT —— 这样在有数据的库上也能跑通（存量行会拿到默认值，
之后由 claim 分支判定为过期行清理掉）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0044_gateway_inbox_idempotency"
down_revision: str | Sequence[str] | None = "0043_turn_cost_usd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "session_inbox",
        "external_message_id",
        existing_type=sa.String(256),
        nullable=True,
    )

    op.add_column(
        "session_inbox",
        sa.Column(
            "idempotency_key",
            sa.String(128),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )
    op.add_column(
        "session_inbox",
        sa.Column(
            "key_source",
            sa.String(32),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )
    op.add_column(
        "session_inbox",
        sa.Column(
            "key_strength",
            sa.String(8),
            nullable=False,
            server_default=sa.text("'strong'"),
        ),
    )
    op.add_column(
        "session_inbox",
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'received'"),
        ),
    )
    op.add_column(
        "session_inbox",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "session_inbox",
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # 新写入必须显式给值 —— 去掉 server_default，避免上游漏传时被静默写成 ''。
    op.alter_column("session_inbox", "idempotency_key", server_default=None)
    op.alter_column("session_inbox", "key_source", server_default=None)
    op.alter_column("session_inbox", "expires_at", server_default=None)

    # 旧唯一约束换成「只覆盖 strong 的部分唯一索引」。
    op.drop_constraint("uq_session_inbox_dedup", "session_inbox", type_="unique")
    op.create_index(
        "uq_session_inbox_idem_strong",
        "session_inbox",
        ["tenant_id", "workspace_id", "channel_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("key_strength = 'strong'"),
    )
    # 过期行清理（Session 的 sweeper 第四类清扫）靠这个索引。
    op.create_index("ix_session_inbox_expires", "session_inbox", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_session_inbox_expires", "session_inbox")
    op.drop_index("uq_session_inbox_idem_strong", "session_inbox")

    op.drop_column("session_inbox", "expires_at")
    op.drop_column("session_inbox", "claimed_at")
    op.drop_column("session_inbox", "status")
    op.drop_column("session_inbox", "key_strength")
    op.drop_column("session_inbox", "key_source")
    op.drop_column("session_inbox", "idempotency_key")

    op.create_unique_constraint(
        "uq_session_inbox_dedup",
        "session_inbox",
        ["tenant_id", "channel_id", "external_message_id"],
    )
    op.alter_column(
        "session_inbox",
        "external_message_id",
        existing_type=sa.String(256),
        nullable=False,
    )
