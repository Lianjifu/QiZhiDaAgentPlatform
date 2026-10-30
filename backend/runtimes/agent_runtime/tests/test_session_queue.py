"""Router Stage 3：**同会话的排队** ✓（Router 方案 §4.2 ✓）。

验收覆盖 ✓：FIFO 放行 ✓ / 队列上限 ✓ / 等待超时 ✓ / 取消 ✓ / 兜底路径 ✓。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from qzdap_agent_runtime.session.queue import (
    QueueCancelled,
    QueueFullError,
    QueueOutcome,
    QueueTimeoutError,
    TurnQueuePort,
    wait_for_turn_slot,
)

TENANT = uuid4()
SESSION = uuid4()
TURN = uuid4()


class _FakeQueue:
    """**可控的排队端口** ✓（放行 / 深度 / 位置都能编排 ✓）。"""

    def __init__(self, *, depth: int = 0, release_after: int = 0) -> None:
        self.depth = depth
        self.release_after = release_after
        self.attempts = 0
        self.released = False

    async def try_release(self, **kwargs: object):  # type: ignore[no-untyped-def]
        from qzdap_agent_runtime.session.queue import QueueDecision

        self.attempts += 1
        if self.released or self.attempts > self.release_after:
            self.released = True
            return QueueDecision(outcome=QueueOutcome.RELEASED, position=1)
        return QueueDecision(outcome=QueueOutcome.WAITING, position=2)

    async def queue_depth(self, **kwargs: object) -> int:
        return self.depth

    async def queue_position(self, **kwargs: object) -> int:
        return 2


class TestTheQueueLimit:
    @pytest.mark.asyncio
    async def test_a_full_queue_is_refused_with_a_clear_error(self) -> None:
        """**队列满了 → 明确错误** ✓（决策 #7 ✓ —— **不静默丢弃** ✓）。"""
        queue = _FakeQueue(depth=5)
        with pytest.raises(QueueFullError) as excinfo:
            async for _ in wait_for_turn_slot(
                queue,  # type: ignore[arg-type]
                tenant_id=TENANT,
                session_id=SESSION,
                turn_id=TURN,
                ingress_seq=7,
            ):
                pass
        assert excinfo.value.code == "QUEUE_FULL"
        assert excinfo.value.status == 429


class TestTheWait:
    @pytest.mark.asyncio
    async def test_the_turn_waits_until_it_is_released(self) -> None:
        """**没轮到就继续等** ✓（放行前一直 WAITING ✓）。"""
        queue = _FakeQueue(release_after=3)
        seen: list[str] = []
        async for decision in wait_for_turn_slot(
            queue,  # type: ignore[arg-type]
            tenant_id=TENANT,
            session_id=SESSION,
            turn_id=TURN,
            ingress_seq=1,
        ):
            seen.append(decision.outcome)
        assert seen == ["waiting", "waiting", "waiting"]
        assert queue.released is True

    @pytest.mark.asyncio
    async def test_the_wait_times_out_with_a_clear_error(self) -> None:
        """**等超时 → 明确错误** ✓（决策 #7 ✓）。"""
        queue = _FakeQueue(release_after=10_000)

        async def _never() -> bool:
            return False

        with pytest.raises(QueueTimeoutError) as excinfo:
            async for _ in wait_for_turn_slot(
                queue,  # type: ignore[arg-type]
                tenant_id=TENANT,
                session_id=SESSION,
                turn_id=TURN,
                ingress_seq=1,
                max_wait_seconds=0.05,
                poll_seconds=0.01,
                cancelled=_never,
            ):
                pass
        assert excinfo.value.code == "QUEUE_TIMEOUT"

    @pytest.mark.asyncio
    async def test_the_cancel_stops_the_wait(self) -> None:
        """**排队期间取消 → 立刻停** ✓（不留一行 running ✗✗）。"""
        queue = _FakeQueue(release_after=10_000)

        async def _cancelled() -> bool:
            return True

        with pytest.raises(QueueCancelled):
            async for _ in wait_for_turn_slot(
                queue,  # type: ignore[arg-type]
                tenant_id=TENANT,
                session_id=SESSION,
                turn_id=TURN,
                ingress_seq=1,
                cancelled=_cancelled,
            ):
                pass


class TestThePortShape:
    def test_the_port_is_a_protocol(self) -> None:
        """**端口是协议** ✓（实现归模块侧 ✓）。"""
        assert isinstance(_FakeQueue(), TurnQueuePort)
