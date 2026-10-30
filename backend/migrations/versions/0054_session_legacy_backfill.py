"""Session 数据迁移：把旧表的历史数据搬进新表（Stage 6「迁数据」那半）。

⚠️ **这是 S-36 的前一半** —— 另一半（DROP 旧表）还要等「切读 + 只读窗口」✓。

搬两样东西：

1. ``agent_turns`` → ``session_turns``：**缺失的轮次行**补上 ✓
   （旧表是历史轮次的唯一栖身处 ✓；不补的话，新表里的消息就**挂不上轮次**
   —— 外键指向 ``session_turns.id`` ✗✗）。
2. ``agent_session_messages`` → ``session_messages``：**缺失的消息**补上 ✓，
   并按会话内的先后顺序**重新编号**（``session_seq`` ✓）。

⚠️ **为什么必须重新编号**：新表的 ``session_seq`` 是「会话内的单调序号」✓，
切读之后历史按它排序 ✓ —— 而回填进来的历史消息在时间上**更早** ✓，
不重编号的话顺序就乱了 ✗✗（老的在前、新的在后 ✗）。

⚠️ **迁移期间应用要停** ✓（回填 + 重编号与新写入并发会撞序号 ✗）。

⚠️ **不可逆的部分**：回填进来的数据**与旧表内容相同** ✓（重复一份 ✗）——
downgrade 会按 ``idempotency_key LIKE 'legacy:%'`` 把它们删掉 ✓。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0054_session_legacy_backfill"
down_revision: str | Sequence[str] | None = "0053_session_drop_wait_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 编号时用的**高位偏移**（1_000_000）—— 先把新表已有的序号挪开 ✓（避免与
#: 回填的行撞上 ``uq_session_messages_session_seq`` 唯一索引 ✗）。
#: 第二步再整体下移（2_000_000）—— 让**所有**行都落到负数区间 ✓（最后一步
#: 统一改成正数序号时，不会与任何还在原位的行撞唯一索引 ✗✗）。
#: ⚠️ 这里写成**字面量**（不是 f-string）—— 免得扫描器把它当成「拼接出来的
#: SQL」✗（那两个数是常量 ✓，拼接没有任何风险 ✓）。


def upgrade() -> None:
    # ── 1) 补齐 session_turns（历史轮次）─────────────────────────────
    #
    # ⚠️ 状态映射：旧表的 'denied'（审批被拒）→ 新表的 'cancelled' ✓
    # （新表的枚举里没有 'denied' ✗；语义最接近的是「被取消」✓）。
    op.execute(
        sa.text(
            """
            INSERT INTO session_turns (
                id, tenant_id, workspace_id, session_id, idempotency_key,
                key_strength, status, started_at, finished_at, agent_version,
                model_version, cost_usd, error_code, created_at, updated_at
            )
            SELECT t.id,
                   t.tenant_id,
                   t.workspace_id,
                   t.session_id,
                   'legacy:' || t.id::text,
                   'strong',
                   CASE t.status
                       WHEN 'running' THEN 'running'
                       WHEN 'succeeded' THEN 'succeeded'
                       WHEN 'failed' THEN 'failed'
                       WHEN 'denied' THEN 'cancelled'
                       ELSE 'failed'
                   END,
                   t.started_at,
                   t.finished_at,
                   COALESCE(NULLIF(s.agent_version, ''), 'v1'),
                   'legacy',
                   t.cost_usd,
                   t.error_code,
                   t.created_at,
                   t.updated_at
            FROM agent_turns t
            JOIN agent_sessions s ON s.id = t.session_id
            WHERE NOT EXISTS (
                SELECT 1 FROM session_turns st WHERE st.id = t.id
            )
            """
        )
    )

    # ── 2) 把新表已有的序号挪开 ──────────────────────────────────────
    op.execute(
        sa.text(
            "UPDATE session_messages SET session_seq = session_seq + 1000000"
        )
    )

    # ── 3) 回填旧消息 ────────────────────────────────────────────────
    #
    # ⚠️ 只搬「挂得上轮次」的 ✓ —— 新表的外键指向 ``session_turns.id`` ✗
    # （第 1 步已经把历史轮次补齐了 ✓）。
    # ⚠️ ``turn_id`` 为空的消息**搬不了** ✗（新表不允许）—— 它们由对账脚本
    # 报出来 ✓（切读前必须处理掉 ✗）。
    op.execute(
        sa.text(
            """
            INSERT INTO session_messages (
                turn_id, seq, role, content, message_id, metadata_,
                session_id, session_seq, created_at
            )
            SELECT m.turn_id,
                   m.seq,
                   left(m.role, 16),
                   m.content,
                   NULL,
                   CASE
                       WHEN m.tool_name <> ''
                           THEN m.extra || jsonb_build_object('tool_name', m.tool_name)
                       ELSE m.extra
                   END,
                   m.session_id,
                   -- 占位序号：**负数** ✓（与被挪到高位的旧行不撞 ✓）；
                   -- 同一会话内互不相同 ✓（唯一索引是 (session_id, session_seq) ✓）。
                   -row_number() OVER (
                       PARTITION BY m.session_id
                       ORDER BY m.created_at, m.seq, m.id
                   ),
                   m.created_at
            FROM agent_session_messages m
            WHERE m.turn_id IS NOT NULL
              AND EXISTS (
                  SELECT 1 FROM session_turns st WHERE st.id = m.turn_id
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM session_messages sm
                  WHERE sm.turn_id = m.turn_id AND sm.seq = m.seq
              )
            """
        )
    )

    # ── 4) 重新编号（会话内按时间顺序）───────────────────────────────
    #
    # ⚠️ **先整体下移到负数区** —— 直接改成新序号会在改的过程中撞唯一索引 ✗
    # （两个行互换序号时 ✗）。负数与正数不会撞 ✓。
    op.execute(
        sa.text(
            "UPDATE session_messages SET session_seq = session_seq - 2000000"
        )
    )
    op.execute(
        sa.text(
            """
            WITH ordered AS (
                SELECT sm.turn_id,
                       sm.seq,
                       row_number() OVER (
                           PARTITION BY sm.session_id
                           ORDER BY sm.created_at, sm.seq, sm.turn_id
                       ) AS rn
                FROM session_messages sm
            )
            UPDATE session_messages sm
            SET session_seq = ordered.rn
            FROM ordered
            WHERE sm.turn_id = ordered.turn_id
              AND sm.seq = ordered.seq
            """
        )
    )

    # ── 5) 同步计数器（下一条消息从哪儿继续）─────────────────────────
    op.execute(
        sa.text(
            """
            UPDATE agent_sessions s
            SET next_message_seq = COALESCE(m.max_seq, 0)
            FROM (
                SELECT session_id, MAX(session_seq) AS max_seq
                FROM session_messages
                GROUP BY session_id
            ) m
            WHERE s.id = m.session_id
            """
        )
    )


def downgrade() -> None:
    # 回填进来的轮次（键带 'legacy:' 前缀 ✓）连同它们的消息一起删掉 ✓
    # —— 回到「旧表是唯一真相」的形态 ✓。
    op.execute(
        sa.text(
            """
            DELETE FROM session_messages
            WHERE turn_id IN (
                SELECT id FROM session_turns
                WHERE idempotency_key LIKE 'legacy:%'
            )
            """
        )
    )
    op.execute(
        sa.text("DELETE FROM session_turns WHERE idempotency_key LIKE 'legacy:%'")
    )
    # 序号恢复成「从 1 开始连续」—— 与迁移前一致 ✓（不能留洞 ✗）。
    op.execute(
        sa.text(
            """
            WITH ordered AS (
                SELECT sm.turn_id,
                       sm.seq,
                       row_number() OVER (
                           PARTITION BY sm.session_id
                           ORDER BY sm.created_at, sm.seq, sm.turn_id
                       ) AS rn
                FROM session_messages sm
            )
            UPDATE session_messages sm
            SET session_seq = ordered.rn
            FROM ordered
            WHERE sm.turn_id = ordered.turn_id
              AND sm.seq = ordered.seq
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE agent_sessions s
            SET next_message_seq = COALESCE(m.max_seq, 0)
            FROM (
                SELECT session_id, MAX(session_seq) AS max_seq
                FROM session_messages
                GROUP BY session_id
            ) m
            WHERE s.id = m.session_id
            """
        )
    )
