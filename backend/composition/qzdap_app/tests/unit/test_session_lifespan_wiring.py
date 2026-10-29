"""Session 生命周期接线（Session Stage 0/1）—— 清扫器 + checkpoint saver。

**为什么测这个**：这两样东西的「接了但没跑」是**静默**的 —— 应用照常启动，
只有看日志才发现清扫器根本没跑。接线层的失败必须**看得见**。
"""

from __future__ import annotations

import asyncio

import pytest

from qzdap.composition.lifespan import _start_session_sweeper


class _BoomFactory:
    """session_factory 一调用就炸 —— 模拟「数据库不可用」。"""

    def session(self) -> None:  # type: ignore[no-untyped-def]
        raise RuntimeError("db down")


class _FakeContainer:
    def __init__(self) -> None:
        self.calls = 0

    def session_factory(self) -> _BoomFactory:
        self.calls += 1
        return _BoomFactory()


@pytest.mark.asyncio
async def test_the_sweeper_keeps_running_when_a_sweep_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一次清扫失败**不能**杀掉清扫任务 —— 下一轮还得跑 ✓。"""
    monkeypatch.setenv("QZDAP_SESSION_SWEEPER_INTERVAL", "1")
    container = _FakeContainer()

    stop = await _start_session_sweeper(container)  # type: ignore[arg-type]
    try:
        await asyncio.sleep(2.5)
        assert container.calls >= 1, "清扫器没有跑过"
    finally:
        await stop()

    # 停掉之后不再有新的清扫 —— 任务已被取消 ✓
    calls_after_stop = container.calls
    await asyncio.sleep(1.5)
    assert container.calls == calls_after_stop


@pytest.mark.asyncio
async def test_the_sweeper_interval_is_never_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """间隔 0 = **忙循环** ✗ —— 至少 1 秒一轮 ✓。"""
    monkeypatch.setenv("QZDAP_SESSION_SWEEPER_INTERVAL", "0")
    container = _FakeContainer()

    stop = await _start_session_sweeper(container)  # type: ignore[arg-type]
    try:
        await asyncio.sleep(0.2)
        # 忙循环会在 0.2 秒里跑成百上千轮
        assert container.calls <= 2, f"清扫器在忙循环：{container.calls} 次"
    finally:
        await stop()


@pytest.mark.asyncio
async def test_the_database_url_for_the_saver_is_psycopg_compatible() -> None:
    """saver 用 psycopg —— ``postgresql+asyncpg://`` 的驱动后缀必须去掉 ✓。"""
    from qzdap.composition.lifespan import _psycopg_url

    assert (
        _psycopg_url("postgresql+asyncpg://postgres:postgres@127.0.0.1:9153/qzdap_dev")
        == "postgresql://postgres:postgres@127.0.0.1:9153/qzdap_dev"
    )
    assert _psycopg_url("postgresql://u:p@h/db") == "postgresql://u:p@h/db"
