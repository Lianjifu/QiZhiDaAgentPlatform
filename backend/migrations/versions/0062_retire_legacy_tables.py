"""**DROP `agent_turns` / `agent_session_messages`** ✓（台账 **X4** ✓ —— S-36 ✓）。

⚠️ **这是不可逆的那一步** ✓ —— 别的旧实现删掉只是删代码 ✓，**这两张表删掉
就没有了** ✓（台账 §3.4「物理不可逆，无并存期」✓）→ 所以它有**四条前置** ✓：

| 前置 | 状态 |
|---|---|
| ① 切读（新表接管读） | ✅ **已完成**（S-15a ✓ —— 2026-10-30 ✓） |
| ② 新旧表全量对账差异 = 0 | ✅ **已完成**（脚本 `scripts/verify_session_tables.py` ✓ —— dev + demo 库各跑一遍 ✓ 差异 = 0 ✓） |
| ③ 停旧写 | ✅ **已完成**（S-15b ✓ —— 旧表没人写了 ✓ —— 旧 ORM 一起删了 ✓） |
| ④ 只读窗口 ≥ 7 天 | ✅ **已满足**（2026-10-30 起算 ✓ —— **窗口由用户拍板提前结束** ✓ —— 期间新旧表差异持续为 0 ✓ 且备份恢复演练已做过 ✓） |

⚠️ **为什么窗口能提前结束** ✓ —— 用户 2026-10-31 决定**现在就做** ✓：
- 旧表**只读** ✓（③ 已达成 ✓）—— 期间没有任何写入 ✓ → 差异不可能变化 ✓；
- **备份恢复演练已做过** ✓（迁移 0061 之前 ✓ —— demo / dev / 测试库各一遍 ✓
  —— 备份 → 恢复到临时库 → 逐表核对 ✓ —— **能恢复** ✓ → 即使误删也能取回 ✓）；
- **新旧表对账差异 = 0** ✓（② ✓ —— 历史数据已由迁移 0054 全部搬进新表 ✓）。

⚠️ **回滚** ✓：``downgrade`` 把两张表**按原样建回来** ✓（列 / 索引 / 约束照抄 ✓
—— 含 0043 后加的 ``cost_usd` ✓）—— 但**数据回不来** ✓（旧数据已被搬走并删除 ✓
—— 要恢复数据得从备份里取 ✓）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0062_retire_legacy_tables"
down_revision: str | Sequence[str] | None = "0061_knowledge_doc_user_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("agent_session_messages")
    op.drop_table("agent_turns")


def downgrade() -> None:
    op.create_table(
        "agent_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_input", sa.Text, nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("final_response", sa.Text, nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('running','succeeded','failed','denied')",
            name="ck_agent_turns_status_enum",
        ),
    )
    op.create_index("ix_agent_turns_tenant_id", "agent_turns", ["tenant_id"])
    op.create_index(
        "ix_agent_turns_tenant_id_session_id_status",
        "agent_turns",
        ["tenant_id", "session_id", "status"],
    )
    op.create_index(
        "ix_agent_turns_tenant_id_session_id_created_at",
        "agent_turns",
        ["tenant_id", "session_id", "created_at"],
    )
    op.create_index(
        "ix_agent_turns_tenant_id_workspace_id",
        "agent_turns",
        ["tenant_id", "workspace_id"],
    )
    op.create_index("ix_agent_turns_session_id", "agent_turns", ["session_id"])

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
        sa.Column(
            "extra", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
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
    )
    op.create_index(
        "ix_agent_session_messages_session_seq", "agent_session_messages", ["session_id", "seq"]
    )
