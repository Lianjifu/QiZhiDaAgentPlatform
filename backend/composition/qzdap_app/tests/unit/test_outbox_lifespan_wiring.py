"""**出站队列 worker** 的接线（Session Stage 4b）✓。

**为什么测这个**：worker「接了但没跑」是**静默**的 —— IM 的回复在投递失败时
就**永远躺在队列里** ✗✗，只有看指标才发现。接线层的失败必须**看得见** ✓。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from qzdap.composition.lifespan import _start_outbox_worker
from qzdap.modules.channel.adapter.outbound.channel_outbox_dispatcher import (
    ChannelOutboxDispatcher,
)
from qzdap_agent_runtime.outbox import OutboxWorker


class _FakeRepo:
    """每轮取一条「待投递」的消息 —— 第一轮成功，之后没有 ✓。"""

    def __init__(self) -> None:
        self.ticks = 0
        self.delivered: list[tuple[str, int]] = []

    async def list_pending(self, limit: int = 100) -> list[Any]:
        self.ticks += 1
        if self.ticks > 1:
            return []
        from qzdap_agent_runtime.outbox import OutboxEvent

        return [
            OutboxEvent(
                turn_id="t1",
                seq=1,
                event_type="im_reply",
                payload={
                    "content": "你好",
                    "channel_type": "feishu",
                    "chat_id": "c1",
                },
                delivery_status="pending",
                delivery_attempts=0,
            )
        ]

    async def mark_delivered(self, turn_id: str, seq: int) -> None:
        self.delivered.append((turn_id, seq))

    async def mark_failed(self, turn_id: str, seq: int, attempts: int, last_error: str) -> None:
        return None

    async def move_to_dead_letter(
        self, turn_id: str, seq: int, attempts: int, last_error: str
    ) -> None:
        return None


class _FakeSink:
    def __init__(self) -> None:
        self.delivered: list[tuple[Any, Any]] = []

    async def deliver(self, event: Any, *, target: Any) -> Any:  # type: ignore[no-untyped-def]
        self.delivered.append((event, target))
        from qzdap_agent_runtime.gateway.outbound import DeliveryOutcome

        return DeliveryOutcome(status="sent")

    async def replay(self, turn_id: str, after_seq: int = 0):  # type: ignore[no-untyped-def]
        return
        yield  # pragma: no cover


class _FakeContainer:
    def __init__(self) -> None:
        self.repo = _FakeRepo()
        self.sink = _FakeSink()

    def session_factory(self) -> Any:  # type: ignore[no-untyped-def]
        return self.repo

    def channel_result_sink(self) -> Any:  # type: ignore[no-untyped-def]
        return self.sink


@pytest.mark.asyncio
async def test_the_worker_delivers_the_queued_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """队列里的消息**会被投出去** ✓ —— 接了但没跑 = 回复永远躺在队列里 ✗✗。"""
    monkeypatch.setenv("QZDAP_OUTBOX_INTERVAL", "1")
    container = _FakeContainer()

    stop = await _start_outbox_worker(
        container,  # type: ignore[arg-type]
        repo=container.repo,
        dispatcher=ChannelOutboxDispatcher(sink=container.sink),
    )
    try:
        await asyncio.sleep(2.5)
    finally:
        await stop()

    assert container.repo.ticks >= 1, "worker 没有跑过"
    assert container.repo.delivered == [("t1", 1)]
    assert len(container.sink.delivered) == 1


@pytest.mark.asyncio
async def test_the_worker_keeps_running_when_a_tick_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一轮失败**不能**杀掉 worker —— 下一轮还得跑 ✓。"""
    monkeypatch.setenv("QZDAP_OUTBOX_INTERVAL", "1")
    container = _FakeContainer()

    attempts: list[int] = []

    async def _boom(*args: object, **kwargs: object) -> None:
        attempts.append(1)
        raise RuntimeError("db down")

    stop = await _start_outbox_worker(
        container,  # type: ignore[arg-type]
        repo=container.repo,
        dispatcher=ChannelOutboxDispatcher(sink=container.sink),
    )
    try:
        # 把 repo 弄炸 —— worker 应当**继续**跑 ✓
        container.repo.list_pending = _boom  # type: ignore[assignment]
        await asyncio.sleep(2.5)
        # 失败的轮次**没有**杀掉 worker —— 后面还在跑 ✓。
        assert len(attempts) >= 2, "一轮失败后 worker 就不跑了"
    finally:
        await stop()


@pytest.mark.asyncio
async def test_the_worker_interval_is_never_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """间隔 0 = **忙循环** ✗ —— 至少 1 秒一轮 ✓。"""
    monkeypatch.setenv("QZDAP_OUTBOX_INTERVAL", "0")
    container = _FakeContainer()
    stop = await _start_outbox_worker(
        container,  # type: ignore[arg-type]
        repo=container.repo,
        dispatcher=ChannelOutboxDispatcher(sink=container.sink),
    )
    try:
        await asyncio.sleep(0.2)
    finally:
        await stop()
    # 不该在 0.2 秒里跑上一轮（间隔被抬到 1 秒 ✓）
    assert container.repo.ticks == 0


def test_the_worker_is_the_contract_layer_one() -> None:
    """用的是**契约层**那个 worker ✓（重试 / 退避 / 死信只有一份 ✓）。"""
    assert OutboxWorker.__module__ == "qzdap_agent_runtime.outbox"


__all__ = []
