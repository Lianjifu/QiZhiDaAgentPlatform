"""**向量兜底补写**（Memory 方案 §5.4 · C10）✓。

⚠️ **接线错 = 兜底补写形同虚设** ✓（2026-11-01 ✓）—— 之前组合根把
``SessionFactory``（**不可调用** ✓）传给了要「可调用会话工厂」的构造器 ✓ →
``find_missing`` **每轮都抛 TypeError** ✓ → 后台 worker 静默重试 ✓ → 只在
日志里留一条 warning ✓ → **没人知道兜底补写一直没跑** ✗✗。

所以这里锁两件事 ✓：
1. 传**可调用**的工厂 → 能正常补写 ✓；
2. 传**不可调用**的（``SessionFactory`` 本身 ✓）→ **接线期就报错** ✓
   （不静默跑到后台才炸 ✓）。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest

from qzdap.modules.memory.adapter.vectorize import MemoryVectorBackfill


class _Result:
    """空结果 ✓ —— 仓储只问「有哪些行」✓。"""

    def scalars(self) -> _Result:
        return self

    def all(self) -> list:
        return []


class _Session:
    """假会话 ✓ —— 仓储只会被调用一次 ✓（这里不验内容 ✓）。"""

    async def execute(self, stmt: object) -> _Result:
        return _Result()


def _callable_factory() -> Any:
    """**可调用**的会话工厂 ✓（像 ``async_sessionmaker`` ✓）。"""
    session = _Session()

    def factory() -> Any:
        return session

    return factory


def test_the_backfill_accepts_a_callable_factory() -> None:
    """传可调用的工厂 ✓ → 能正常开会话 ✓（不炸 ✓）。"""
    backfill = MemoryVectorBackfill(_callable_factory())
    assert backfill is not None


def test_the_backfill_rejects_a_non_callable_factory() -> None:
    """⚠️ **传 ``SessionFactory`` 本身要立刻报错** ✓ —— 不静默 ✓。

    （``SessionFactory`` 有 ``.session()`` ✓ / ``.maker`` ✓，但**不可调用** ✓。）
    """

    class _NotCallable:
        def session(self) -> Any:  # pragma: no cover - 只是长得像
            raise AssertionError("不该被调用")

    with pytest.raises(TypeError, match="callable"):
        MemoryVectorBackfill(_NotCallable())


@pytest.mark.asyncio
async def test_the_backfill_scans_within_its_window() -> None:
    """兜底补写**自己开会话** ✓（跨租户扫描 ✓ —— 不能借请求的会话 ✓）。"""
    opened: list[int] = []

    @asynccontextmanager
    async def _session_cm():  # type: ignore[no-untyped-def]
        opened.append(1)
        yield _Session()

    def factory() -> Any:
        return _session_cm()

    backfill = MemoryVectorBackfill(factory)
    # 扫的是「最近更新过的 L2」✓ —— 空库就是空 ✓（不抛 ✓）。
    requests = await backfill.find_missing(limit=10)
    assert requests == []
    assert opened, "它必须自己开会话 ✓"
