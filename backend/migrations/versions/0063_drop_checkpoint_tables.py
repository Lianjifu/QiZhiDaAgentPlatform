"""**DROP 四张 LangGraph checkpoint 表** ✓（Session S-14 收尾 ✓）。

⚠️ **为什么现在能删** ✓ —— 这四张表是迁移 **0046** 给
``AsyncPostgresSaver`` 建的 ✓；而 saver 已经在 **Session S-14** 退役 ✓
（它唯一的消费者是那张 19 节点的 LangGraph 图 ✓，**已随 Agent Stage 7 删除** ✓）
→ **新的循环用会话 ``metadata["resume"]`` + 轮次行续传** ✓
（不需要 LangGraph 的 checkpoint ✓）→ **lifespan 不再起 saver** ✓。

| 表 | 状态 |
|---|---|
| ``checkpoints`` | **零行** ✓ —— 没人写过 ✓ |
| ``checkpoint_blobs`` | **零行** ✓ |
| ``checkpoint_writes`` | **零行** ✓ |
| ``checkpoint_migrations`` | **1 行** ✓ —— 那是 saver 的版本标记 ✓（随表一起删 ✓） |

⚠️ **台账失真** ✓ —— `implementation-plan.md` 的 S-14 行写着「checkpoint 表
（迁移 0046）还在 ✓ → 删表归 S-36 那一批 ✓」，而 **S-36（迁移 0062）只删了
两张旧轮次表** ✓ —— 这四张表被漏掉了 ✓ → 本迁移补上 ✓。
⚠️ **README §8 第 8 条说「checkpoint 系列表不在任何迁移里」** ✓ —— **那是错的**
✓ —— 0046 恰恰建了它们 ✓ → 同一份 README 已同步改正 ✓。

⚠️ **回滚** ✓：``downgrade`` 把四张表**按原样建回来** ✓（DDL 照抄 0046 ✓
—— 含三个索引 ✓ 与 ``checkpoint_migrations`` 的版本行 ✓）。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0063_drop_checkpoint_tables"
down_revision: str | Sequence[str] | None = "0062_retire_legacy_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: saver 的版本标记 —— 0046 写进去的那一行 ✓（downgrade 要原样写回 ✓）。
_CHECKPOINT_MIGRATION_VERSION = 9


def upgrade() -> None:
    for table in (
        "checkpoint_writes",
        "checkpoint_blobs",
        "checkpoints",
        "checkpoint_migrations",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")


def downgrade() -> None:
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
    op.execute(
        sa.text(
            "INSERT INTO checkpoint_migrations (v) VALUES (:v) ON CONFLICT DO NOTHING"
        ).bindparams(v=_CHECKPOINT_MIGRATION_VERSION)
    )
