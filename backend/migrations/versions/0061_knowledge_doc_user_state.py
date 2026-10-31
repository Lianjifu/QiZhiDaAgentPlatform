"""**建 `admin_knowledge_doc_user_state`** ✓ —— 用户对知识文档的收藏状态 ✓。

⚠️ **为什么是「按模块分表」** ✓ —— 技能 / 工作流 / 智能体各有各的一张
``*_user_state`` ✓（`admin_skill_user_state` ✓ / `admin_workflow_user_state` ✓ /
`admin_agent_user_state` ✓）—— 知识域**不读别人的表** ✓（模块边界 ✓）。

⚠️ **这个表以前根本不存在** ✓ —— 前端「用户侧知识」的收藏按钮**在开发模式下
打的是 404** ✓（`POST /api/catalog/knowledge/{id}/favorite` ✗）—— 收藏只存在
前端的本地 state 里 ✗ → 换个设备就没了 ✗。

⚠️ **回滚** ✓：``downgrade`` 把表删掉 ✓（收藏状态是可再生的派生数据 ✓）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0061_knowledge_doc_user_state"
down_revision: str | Sequence[str] | None = "0060_platform_sub_workspace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_knowledge_doc_user_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("doc_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("favorited", sa.Boolean, nullable=False, server_default=sa.text("false")),
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
            "doc_id",
            name="uq_admin_knowledge_doc_user_state",
        ),
    )
    op.create_index(
        "ix_admin_knowledge_doc_user_state_tenant_id",
        "admin_knowledge_doc_user_state",
        ["tenant_id"],
    )
    op.create_index(
        "ix_admin_knowledge_doc_user_state_workspace_id",
        "admin_knowledge_doc_user_state",
        ["workspace_id"],
    )
    op.create_index(
        "ix_admin_knowledge_doc_user_state_user_id",
        "admin_knowledge_doc_user_state",
        ["user_id"],
    )
    op.create_index(
        "ix_admin_knowledge_doc_user_state_doc_id",
        "admin_knowledge_doc_user_state",
        ["doc_id"],
    )
    op.create_index(
        "ix_admin_knowledge_doc_user_state_user_doc",
        "admin_knowledge_doc_user_state",
        ["tenant_id", "user_id", "doc_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_admin_knowledge_doc_user_state_user_doc",
        table_name="admin_knowledge_doc_user_state",
    )
    op.drop_index(
        "ix_admin_knowledge_doc_user_state_doc_id",
        table_name="admin_knowledge_doc_user_state",
    )
    op.drop_index(
        "ix_admin_knowledge_doc_user_state_user_id",
        table_name="admin_knowledge_doc_user_state",
    )
    op.drop_index(
        "ix_admin_knowledge_doc_user_state_workspace_id",
        table_name="admin_knowledge_doc_user_state",
    )
    op.drop_index(
        "ix_admin_knowledge_doc_user_state_tenant_id",
        table_name="admin_knowledge_doc_user_state",
    )
    op.drop_table("admin_knowledge_doc_user_state")
