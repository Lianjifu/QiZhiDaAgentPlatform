"""**出站队列**在渠道侧的行为 ✓。

覆盖：
- 回复**先入队、再投递** —— 投递成功 → 标 delivered ✓；
- 投递失败 → 标 failed（**留在队列里**等 worker 重试 ✓），**不炸主链路** ✓；
- ``ChannelOutboxDispatcher``：没有投递目标 / 渠道不认识 / sink 失败 → 抛
  :class:`DispatchError` ✓（worker 据此记 FAILED / 进死信 ✓）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from qzdap.modules.channel.adapter.dispatch.channel_turn_dispatcher import (
    ChannelTurnDispatcher,
)
from qzdap.modules.channel.adapter.outbound.channel_outbox_dispatcher import (
    ChannelOutboxDispatcher,
)
from qzdap.modules.channel.adapter.outbound.result_sink import ChannelResultSink
from qzdap_agent_runtime.gateway.types import (
    ActorContext,
    ChannelType,
    IdempotencyKey,
    InboundMessage,
    KeySource,
)
from qzdap_agent_runtime.outbox import (
    IM_REPLY_EVENT_TYPE,
    DispatchError,
    OutboundMessage,
    OutboxEvent,
)
from qzdap_agent_runtime.session.channel_turn import ChannelTurnResult


class _FakeChannelRepo:
    def __init__(self, channel: Any | None) -> None:
        self._channel = channel

    async def get_by_id(self, channel_id: UUID) -> Any:  # type: ignore[no-untyped-def]
        return self._channel


class _FakeChannel:
    def __init__(self, type: ChannelType, workspace_id: UUID) -> None:
        self.type = type
        self.workspace_id = workspace_id
        self.service_account = {
            "user_id": str(uuid4()),
            "agent_id": str(uuid4()),
            "agent_version": "v1",
        }


class _FakeTurnService:
    def __init__(self, *, final_message: str = "hi back") -> None:
        self._final_message = final_message
        self.turn_id = uuid4()

    async def run(self, request: Any) -> ChannelTurnResult:  # type: ignore[no-untyped-def]
        return ChannelTurnResult(
            session_id=uuid4(),
            final_message=self._final_message,
            turn_id=self.turn_id,
        )


class _FakeTurnFactory:
    def __init__(self, service: _FakeTurnService) -> None:
        self._service = service

    def for_session(self, session: Any) -> _FakeTurnService:  # type: ignore[no-untyped-def]
        return self._service


class _FakeOutbox:
    """``OutboxRepository`` 的替身 ✓。"""

    def __init__(self) -> None:
        self.enqueued: list[dict[str, Any]] = []
        self.delivered: list[tuple[str, int]] = []
        self.failed: list[tuple[str, int, int, str]] = []

    async def enqueue(
        self, *, turn_id: str, event_type: str, payload: dict[str, Any]
    ) -> OutboundMessage:
        self.enqueued.append(
            {"turn_id": turn_id, "event_type": event_type, "payload": dict(payload)}
        )
        return OutboundMessage(turn_id=turn_id, seq=1, event_type=event_type)

    async def mark_delivered(self, turn_id: str, seq: int) -> None:
        self.delivered.append((turn_id, seq))

    async def mark_failed(
        self, turn_id: str, seq: int, attempts: int, last_error: str
    ) -> None:
        self.failed.append((turn_id, seq, attempts, last_error))


class _FakeOutboundAdapter:
    def __init__(self, channel_type: str, *, fail: bool = False) -> None:
        self.channel_type = channel_type
        self.fail = fail
        self.sent: list[dict] = []

    async def send_reply(self, **kwargs: Any) -> str | None:
        if self.fail:
            raise RuntimeError("network down")
        self.sent.append(kwargs)
        return None


class _CtxMgr:
    async def __aenter__(self) -> Any:
        return object()

    async def __aexit__(self, *exc: Any) -> None:
        return None


def _msg(**overrides: Any) -> InboundMessage:
    base: dict[str, Any] = {
        "actor": ActorContext(
            tenant_id=uuid4(),
            workspace_id=None,
            actor_id=uuid4(),
            roles=("service_account",),
            actor_kind="service_account",
        ),
        "channel_type": ChannelType.WEB,
        "channel_id": uuid4(),
        "external_chat_id": "c1",
        "external_user_id": "u1",
        "explicit_agent_id": None,
        "idempotency": IdempotencyKey(
            value="platform|msg-1",
            source=KeySource.PLATFORM_MESSAGE_ID,
            strength="strong",
            expires_at=datetime.now(UTC) + timedelta(days=7),
        ),
        "external_message_id": "msg-1",
        "payload_hash": "deadbeef",
        "trace_id": "trace-1",
        "text": "hello",
    }
    base.update(overrides)
    return InboundMessage(**base)


def _make_dispatcher(
    *,
    outbound: dict | None = None,
    outbox: _FakeOutbox | None = None,
    service: _FakeTurnService | None = None,
):
    channel = _FakeChannel(ChannelType.WEB, uuid4())
    svc = service or _FakeTurnService()
    box = outbox or _FakeOutbox()
    dispatcher = ChannelTurnDispatcher(
        channel_repository=_FakeChannelRepo(channel),
        turn_factory=_FakeTurnFactory(svc),
        sink=ChannelResultSink(outbound_registry=outbound or {}),
        open_session=lambda: _CtxMgr(),
        outbox=box,  # type: ignore[arg-type]
    )
    return dispatcher, svc, box


@pytest.mark.asyncio
async def test_the_reply_is_queued_before_it_is_delivered() -> None:
    """**入队先于投递** ✓ —— 投递失败时那一行还在 ✓。"""
    adapter = _FakeOutboundAdapter("web")
    dispatcher, svc, box = _make_dispatcher(outbound={"web": adapter})
    await dispatcher._handle_message(_msg())
    assert len(box.enqueued) == 1
    assert box.enqueued[0]["event_type"] == IM_REPLY_EVENT_TYPE
    assert box.enqueued[0]["payload"]["content"] == "hi back"
    assert box.enqueued[0]["payload"]["chat_id"] == "c1"
    # 投递成功 → 标 delivered ✓
    assert box.delivered == [(str(svc.turn_id), 1)]
    assert box.failed == []
    assert len(adapter.sent) == 1


@pytest.mark.asyncio
async def test_a_failed_delivery_stays_in_the_queue() -> None:
    """投递失败 → **留在队列里**等 worker 重试 ✓，且**不炸主链路** ✓。"""
    adapter = _FakeOutboundAdapter("web", fail=True)
    dispatcher, svc, box = _make_dispatcher(outbound={"web": adapter})
    await dispatcher._handle_message(_msg())
    assert len(box.enqueued) == 1
    assert box.delivered == []
    assert len(box.failed) == 1
    assert box.failed[0][0] == str(svc.turn_id)


@pytest.mark.asyncio
async def test_the_dispatcher_refuses_a_message_without_a_target() -> None:
    """没有投递目标（渠道 / 聊天）→ **拒绝** ✓（不猜投递到哪 ✗✗）。"""
    dispatcher = ChannelOutboxDispatcher(sink=ChannelResultSink(outbound_registry={}))
    with pytest.raises(DispatchError):
        await dispatcher.dispatch(
            OutboxEvent(
                turn_id="t1",
                seq=1,
                event_type=IM_REPLY_EVENT_TYPE,
                payload={"content": "hi"},
                delivery_status="pending",
                delivery_attempts=0,
            )
        )


@pytest.mark.asyncio
async def test_the_dispatcher_rejects_an_unknown_channel() -> None:
    dispatcher = ChannelOutboxDispatcher(sink=ChannelResultSink(outbound_registry={}))
    with pytest.raises(DispatchError):
        await dispatcher.dispatch(
            OutboxEvent(
                turn_id="t1",
                seq=1,
                event_type=IM_REPLY_EVENT_TYPE,
                payload={"content": "hi", "channel_type": "telegram", "chat_id": "c1"},
                delivery_status="pending",
                delivery_attempts=0,
            )
        )


@pytest.mark.asyncio
async def test_a_sink_failure_becomes_a_dispatch_error() -> None:
    """sink 失败 → DispatchError ✓（worker 才能记 FAILED / 进死信 ✓）。"""
    adapter = _FakeOutboundAdapter("web", fail=True)
    dispatcher = ChannelOutboxDispatcher(
        sink=ChannelResultSink(outbound_registry={"web": adapter})
    )
    with pytest.raises(DispatchError):
        await dispatcher.dispatch(
            OutboxEvent(
                turn_id="t1",
                seq=1,
                event_type=IM_REPLY_EVENT_TYPE,
                payload={"content": "hi", "channel_type": "web", "chat_id": "c1"},
                delivery_status="pending",
                delivery_attempts=0,
            )
        )


__all__ = []
