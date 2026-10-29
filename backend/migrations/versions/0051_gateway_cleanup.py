"""Gateway Stage 5：清理 —— 幂等残留键 + 孤儿索引。

依据：docs/refactor/session-architecture/gateway-refactor-plan.md §10 Stage 5
（「删 ``agent_sessions.metadata.recent_request_ids`` 残留列」+「删孤儿索引」）、
台账 **G1**。

1) ``agent_sessions.metadata`` 里的 ``recent_request_ids`` —— **代码早已不再
   读写**（Gateway Stage 1 删除 ``record_request_id`` 与它的全部读写，台账 G1
   已清理），但**历史行里还留着这个键**。留着它 = 数据面还挂着一个已废止的
   幂等实现（读它的人会以为「最近请求 id」还在起作用）。

   ⚠️ 它是 **JSONB 里的一个键**，不是一列 —— 因此清理是 ``metadata - 'key'``。

2) ``session_events`` 上 ``turn_id`` 单列索引 —— **与主键完全重复**：
   主键是 ``(turn_id, seq)``，按 ``turn_id`` 的查询能直接用主键索引的最左前缀，
   这个单列索引只增加写放大（每插一个 chunk 多写一棵树）。
   Session 方案 §10.2 已判定它为冗余（「0035 已建 PRIMARY KEY (turn_id, seq)
   —— PK 自带同组合 B-tree 索引」）。

   ⚠️ 索引名带**两次**表名（``ix_session_events_session_events_turn_id``）——
   那是 0035 建表时列名 + 命名约定的组合结果；两种写法都 DROP 掉，兼容
   「表由 ORM metadata 建」的库（那种库根本没有这个索引）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0051_gateway_cleanup"
down_revision: str | Sequence[str] | None = "0050_gateway_replay_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 幂等残留键（G1）—— 代码不再读写，只清历史行。
LEGACY_METADATA_KEY = "recent_request_ids"

#: 孤儿索引的两种可能名字（见文件说明第 2 点）。
_ORPHAN_INDEX_NAMES = (
    "ix_session_events_session_events_turn_id",
    "ix_session_events_turn_id",
)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1) 幂等残留键
    # ------------------------------------------------------------------
    op.execute(
        "UPDATE agent_sessions "
        "   SET metadata = metadata - 'recent_request_ids' "
        " WHERE metadata ? 'recent_request_ids'"
    )
    # ------------------------------------------------------------------
    # 2) 孤儿索引（与主键 (turn_id, seq) 重复）
    # ------------------------------------------------------------------
    for name in _ORPHAN_INDEX_NAMES:
        op.execute(sa.text(f"DROP INDEX IF EXISTS {name}"))


def downgrade() -> None:
    # 残留键**不可恢复** —— 它是已废止实现的历史垃圾，恢复它没有意义。
    # 孤儿索引恢复也无必要（主键已覆盖同样的查询）。
    pass
