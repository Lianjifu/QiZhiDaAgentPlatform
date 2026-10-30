#!/usr/bin/env python3
"""**新旧两表的对账** —— 切读（S-15a）与删旧表（S-36）之前的**硬判据** ✓。

⚠️ **差异必须为 0** —— 台账 §3.2 的量化判据 ✓：

- 「新旧表全量对账差异 = 0」是 **S-36（DROP 旧表）** 的前置之一 ✓；
- 差异不为 0 → **不许切读**（否则用户会看到少一半的历史 ✗✗）。

用法::

    python scripts/verify_session_tables.py            # 用 QZDAP_DATABASE_URL
    python scripts/verify_session_tables.py --url postgresql+asyncpg://...

退出码：``0`` = 无差异 ✓；``1`` = 有差异 ✗（清单打到 stdout ✓）。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

#: 消息内容比对时忽略的列 —— ``extra``/``metadata_`` 的形状两表不同 ✓
#: （旧表有 ``tool_name`` 独立列 ✓，新表把它并进了 ``metadata_`` ✓）。
_IGNORED_CONTENT_COLUMNS = ("extra", "metadata_", "tool_name")


def _queries() -> list[tuple[str, str]]:
    """要跑的对账查询 ✓（标题, SQL）。"""
    return [
        (
            "旧表有、新表没有的消息",
            """
            SELECT m.session_id::text, m.turn_id::text, m.seq, left(m.content, 60)
            FROM agent_session_messages m
            LEFT JOIN session_messages sm
              ON sm.turn_id = m.turn_id AND sm.seq = m.seq
            WHERE sm.turn_id IS NULL
            ORDER BY m.session_id, m.seq
            LIMIT 50
            """,
        ),
        (
            "新表有、旧表没有的消息（双写期之后写的 ✓，正常 ✓）",
            """
            SELECT sm.session_id::text, sm.turn_id::text, sm.seq, left(sm.content, 60)
            FROM session_messages sm
            LEFT JOIN agent_session_messages m
              ON m.turn_id = sm.turn_id AND m.seq = sm.seq
            WHERE m.id IS NULL
            ORDER BY sm.session_id, sm.session_seq
            LIMIT 50
            """,
        ),
        (
            "内容不一致的消息",
            """
            SELECT m.session_id::text, m.turn_id::text, m.seq,
                   left(m.content, 40) AS old_content,
                   left(sm.content, 40) AS new_content
            FROM agent_session_messages m
            JOIN session_messages sm
              ON sm.turn_id = m.turn_id AND sm.seq = m.seq
            WHERE m.content IS DISTINCT FROM sm.content
               OR left(m.role, 16) IS DISTINCT FROM sm.role
            ORDER BY m.session_id, m.seq
            LIMIT 50
            """,
        ),
        (
            "旧表有、新表没有的轮次",
            """
            SELECT t.session_id::text, t.id::text, t.status
            FROM agent_turns t
            LEFT JOIN session_turns st ON st.id = t.id
            WHERE st.id IS NULL
            ORDER BY t.session_id, t.created_at
            LIMIT 50
            """,
        ),
        (
            "挂不上轮次的旧消息（**搬不动** ✓ —— 切读前必须处理掉 ✗）",
            """
            SELECT m.session_id::text, m.turn_id::text, m.seq, left(m.content, 40)
            FROM agent_session_messages m
            WHERE m.turn_id IS NULL
               OR NOT EXISTS (
                   SELECT 1 FROM session_turns st WHERE st.id = m.turn_id
               )
            ORDER BY m.session_id, m.seq
            LIMIT 50
            """,
        ),
        (
            "会话内序号不连续 / 重复",
            """
            WITH ordered AS (
                SELECT session_id, session_seq,
                       row_number() OVER (
                           PARTITION BY session_id ORDER BY session_seq
                       ) AS rn
                FROM session_messages
            )
            SELECT session_id::text, session_seq, rn
            FROM ordered
            WHERE session_seq <> rn
            ORDER BY session_id, session_seq
            LIMIT 50
            """,
        ),
    ]


async def _run(url: str) -> int:
    engine = create_async_engine(url)
    problems = 0
    try:
        async with engine.connect() as conn:
            for title, sql in _queries():
                rows = (
                    await conn.execute(text(sql))
                ).all()
                # 「新表有、旧表没有」在双写期是**正常**的（新表先写 ✓）——
                # 但它说明「旧表不是完整的真相」✗ → 报出来，但不算差异 ✗。
                informational = title.startswith("新表有、旧表没有")
                if rows:
                    print(f"\n✗ {title} —— {len(rows)} 行（最多列 50 行）")
                    for row in rows:
                        print("   ", tuple(row))
                    if not informational:
                        problems += 1
                else:
                    print(f"✓ {title}")
    finally:
        await engine.dispose()

    print()
    if problems:
        print(f"✗ 对账**未通过** —— {problems} 类差异不为 0 ✗（不许切读 / 删旧表）")
        return 1
    print("✓ 对账通过 —— 差异为 0 ✓（可以进入切读 / 删旧表的下一步 ✓）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="新旧两表对账")
    parser.add_argument(
        "--url",
        default=os.environ.get("QZDAP_DATABASE_URL", ""),
        help="数据库 URL（默认取 QZDAP_DATABASE_URL ✓）",
    )
    args = parser.parse_args()
    if not args.url:
        print(
            "✗ 缺数据库 URL —— 给 --url 或设 QZDAP_DATABASE_URL ✓",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(_run(args.url))


if __name__ == "__main__":
    raise SystemExit(main())
