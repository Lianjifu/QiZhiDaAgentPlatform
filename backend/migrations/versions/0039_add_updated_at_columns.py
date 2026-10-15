"""补 updated_at 列: TenantScopedMixin 通过 @declared_attr 给所有子类注入
updated_at, 但 0007 (governance) + 0008 (agent_runtime) 早期 migration 给部分表
漏了该列, 导致 ORM INSERT 时 RETURNING updated_at 失败 (ProgrammingError:
column does not exist).

涉及的表 (列在 0038 之后又缺 updated_at 的):

- approvals           (governance)
- decision_events     (governance)
- audit_log           (governance)
- session_inbox       (agent_runtime)
- session_messages    (agent_runtime)
- session_turns       (agent_runtime)
- session_events      (agent_runtime)
- tool_executions     (agent_runtime)
- outbox_dead_letters (agent_runtime)
- channel_deliveries  (channel)
- channel_secrets     (channel)
- user_sessions       (user)
- cost_records        (observability)
- run_records         (observability)

补加 updated_at TIMESTAMPTZ NOT NULL DEFAULT now() 与 server_default,
保持 TenantScopedMixin 模型与 DB schema 一致.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision = "0039_add_updated_at_columns"
down_revision = "0038_data_subject_deletion_log"
branch_labels = None
depends_on = None


# (table, has_tenant_id) — 所有这些表都已存在, 仅 ADD COLUMN
_TABLES = (
    "approvals",
    "decision_events",
    "audit_log",
    "session_inbox",
    "session_messages",
    "session_turns",
    "session_events",
    "tool_executions",
    "outbox_dead_letters",
    "channel_deliveries",
    "channel_secrets",
    "user_sessions",
    "cost_records",
    "run_records",
)


def upgrade() -> None:
    for table in _TABLES:
        op.execute(
            sa.text(
                f"ALTER TABLE {table} "
                "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE "
                "NOT NULL DEFAULT now()"
            )
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN IF EXISTS updated_at"))


__all__: Sequence[str] = ()
