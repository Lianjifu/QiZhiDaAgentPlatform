#!/usr/bin/env python
"""确保目标数据库存在 —— 演示库与开发库是两个库, 不能互相污染.

Postgres 没有 ``CREATE DATABASE IF NOT EXISTS``, 所以先连到 maintenance
库 (``postgres``) 查一下, 没有再建.

用法::

    cd backend
    python scripts/ensure_database.py \\
        --url postgresql+asyncpg://postgres:postgres@127.0.0.1:9153/qzdap_demo

``--url`` 给的是**目标**库的连接串; 脚本会把它换成同一个 server 上的
``postgres`` maintenance 库去建目标库.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))


def _split_db(url: str) -> tuple[str, str]:
    """把 ``.../dbname`` 拆成 (前缀, dbname)."""
    base, _, name = url.rpartition("/")
    if not base or not name:
        raise ValueError(f"无法从连接串里解析出数据库名: {url}")
    return base, name


async def _ensure(url: str) -> str:
    base, name = _split_db(url)
    # maintenance 库 —— 目标库还没建时连不上它.
    maintenance_url = f"{base}/postgres"
    engine = create_async_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            exists = (
                await conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}
                )
            ).scalar_one_or_none()
            if exists:
                return "exists"
            # 库名来自连接串, 不是外部自由输入; 再挡一层只允许标识符字符.
            if not name.replace("_", "").isalnum():
                raise ValueError(f"数据库名不合法: {name!r}")
            await conn.execute(text(f'CREATE DATABASE "{name}"'))
            return "created"
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", required=True, help="目标库的完整连接串")
    args = parser.parse_args()
    outcome = asyncio.run(_ensure(args.url))
    print(f"database {outcome}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
