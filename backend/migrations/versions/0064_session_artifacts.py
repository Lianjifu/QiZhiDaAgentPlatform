"""**建 ``session_artifacts`` 表** ✓（产物落库 ✓）。

⚠️ **为什么要有这张表** ✓ —— 产物（报告 / 代码 / html / json）之前**只在
``/tmp/qzdap-mock-artifacts``** ✓ —— 那是 **mock 模式的临时目录** ✓（进程
一退就没了 ✓）。真实模式下**没有任何存储** ✓ → 端点一律 404 ✓ → **前端那张
产物卡片永远点不开** ✓。

⚠️ **为什么不是「复用附件表」** ✓ —— 附件（``copilot_attachments``）是
**用户上传的输入** ✓，产物是**模型生成的输出** ✓：
- 归属不同（输入 vs 输出 ✓）；
- 生命周期不同（附件绑定会话 ✓ —— 产物还绑轮次 ✓ —— 谁那一轮产出的 ✓）；
- 附件的字节由**用户**决定 ✓ —— 产物的字节由**模型**决定 ✓（大小 / 类型
  不可控 ✓ → 要有上限 ✓）。

**归属** ✓：会话层 ✓ —— 产物属于某个会话 ✓（会话没了，产物一起没 ✓ ——
外键 ``session_id → agent_sessions.id`` ON DELETE CASCADE ✓）。

⚠️ **大小上限** ✓ —— 产物进 SSE 事件流 ✓（``artifact_ready`` chunk ✓）→
**必须是有界的** ✓ —— 1 MiB ✓（与附件同口径 ✓ —— 前端的下载是整块取 ✓
—— 不是流式 ✓）。

⚠️ **回滚** ✓：``downgrade`` 删表 ✓ —— **数据回不来** ✓（要取数据从备份里取 ✓）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0064_session_artifacts"
down_revision: str | Sequence[str] | None = "0063_drop_checkpoint_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "session_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="text"),
        sa.Column("mime", sa.String(120), nullable=False, server_default="text/plain"),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False, server_default=""),
        sa.Column("content", sa.LargeBinary(), nullable=False),
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
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_session_artifacts_tenant_workspace_session",
        "session_artifacts",
        ["tenant_id", "workspace_id", "session_id"],
    )
    op.create_index("ix_session_artifacts_turn_id", "session_artifacts", ["turn_id"])


def downgrade() -> None:
    op.drop_index("ix_session_artifacts_turn_id", "session_artifacts")
    op.drop_index("ix_session_artifacts_tenant_workspace_session", "session_artifacts")
    op.drop_table("session_artifacts")
