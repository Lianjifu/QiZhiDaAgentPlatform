"""Unit tests for ``ChannelTurnDispatcher``.

覆盖：入站消息还原、渠道缺失、服务账号物化、**会话粘性**（channel_session_key）、
出站回写与失败不炸总线。

⚠️ **幂等不再由这里做** —— 键由 Gateway ③ 派生、由会话层消费 ✓（同一个平台
消息重投 → 会话层判重 → 不跑第二轮 ✓）。这里只负责「把消息变成一轮」。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from qzdap.modules.channel.adapter.dispatch.channel_turn_dispatcher import (
    INBOUND_MESSAGE_EVENT,
    ChannelTurnDispatcher,
)
from qzdap.modules.channel.adapter.outbound.result_sink import ChannelResultSink
from qzdap_agent_runtime.gateway.types import (
    ActorContext,
    ChannelType,
    IdempotencyKey,
    InboundMessage,
    KeySource,
)
from qzdap_agent_runtime.session.channel_turn import ChannelTurnResult


class _FakeChannelRepo:
    def __init__(self, channel: Any | None) -> None:
        self._channel = channel
        self.calls = 0

    async def get_by_id(self, channel_id: UUID) -> Any:  # type: ignore[no-untyped-def]
        self.calls += 1
        return self._channel


# 渠道登记的服务账号（IM 的 actor 由此物化）—— 取代旧的全局常量.
_SERVICE_USER_ID = UUID("11111111-1111-1111-1111-111111111111")
_SERVICE_AGENT_ID = UUID("22222222-2222-2222-2222-222222222222")
_SERVICE_AGENT_VERSION = "channel-router-1.0.0"
_SERVICE_ACCOUNT = {
    "user_id": str(_SERVICE_USER_ID),
    "agent_id": str(_SERVICE_AGENT_ID),
    "agent_version": _SERVICE_AGENT_VERSION,
}


_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")

_UNSET = object()


class _FakeChannel:
    def __init__(
        self,
        type: ChannelType,
        workspace_id: UUID,
        service_account: dict | object | None = _UNSET,
    ) -> None:
        self.type = type
        self.workspace_id = workspace_id
        self.service_account = _SERVICE_ACCOUNT if service_account is _UNSET else service_account


class _FakeTurnService:
    """``ChannelTurnPort`` 的假实现 —— 记录它收到的那一轮 ✓。"""

    def __init__(self) -> None:
        self.requests: list[Any] = []
        self.fail = False

    async def run(self, request: Any) -> ChannelTurnResult:  # type: ignore[no-untyped-def]
        if self.fail:
            raise RuntimeError("boom")
        self.requests.append(request)
        return ChannelTurnResult(
            session_id=uuid4(),
            final_message="hi back",
            turn_id=uuid4(),
        )


class _FakeTurnFactory:
    def __init__(self, service: _FakeTurnService) -> None:
        self._service = service

    def for_session(self, session: Any) -> _FakeTurnService:  # type: ignore[no-untyped-def]
        return self._service


class _FakeBus:
    def __init__(self) -> None:
        self.subs: dict[str, list[Any]] = {}

    async def subscribe(self, topic: str, handler: Any) -> None:
        self.subs.setdefault(topic, []).append(handler)


class _FakeOutboundAdapter:
    def __init__(self, type: str) -> None:
        self.channel_type = type
        self.sent: list[dict] = []

    async def send_reply(self, **kwargs: Any) -> str | None:
        self.sent.append(kwargs)
        return None


class _CtxMgr:
    def __init__(self, session: Any) -> None:
        self._session = session

    async def __aenter__(self) -> Any:
        return self._session

    async def __aexit__(self, *exc: Any) -> None:
        return None


def _make_dispatcher(
    *,
    channel: Any | None,
    outbound: dict | None = None,
    service: _FakeTurnService | None = None,
) -> tuple[ChannelTurnDispatcher, _FakeBus, _FakeChannelRepo, _FakeTurnService]:
    repo = _FakeChannelRepo(channel)
    bus = _FakeBus()
    svc = service or _FakeTurnService()
    dispatcher = ChannelTurnDispatcher(
        channel_repository=repo,
        turn_factory=_FakeTurnFactory(svc),
        sink=ChannelResultSink(outbound_registry=outbound or {}),
        open_session=lambda: _CtxMgr(object()),
    )
    return dispatcher, bus, repo, svc


def _msg(**overrides: Any) -> InboundMessage:
    base: dict[str, Any] = {
        "actor": ActorContext(
            # ⚠️ **同一个渠道的消息属于同一个租户** ✓ —— 固定值 ✓
            # （原来每次随机 ✓ —— 那会让「同一渠道同一聊天」算出两个 key ✓✗）。
            tenant_id=_TENANT_ID,
            workspace_id=None,
            actor_id=_SERVICE_USER_ID,
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


@pytest.mark.asyncio
async def test_subscribes_by_event_class_name() -> None:
    """总线按**类名**路由 —— 按 dotted topic 订阅是旧实现的真实缺陷。"""
    dispatcher, bus, *_ = _make_dispatcher(channel=None)
    await dispatcher.install(bus)
    assert INBOUND_MESSAGE_EVENT == "InboundMessage"
    assert list(bus.subs) == ["InboundMessage"]


@pytest.mark.asyncio
async def test_the_turn_uses_the_channels_service_account() -> None:
    """IM 的 actor 由**渠道登记的服务账号**物化 —— 不再是全局常量（台账 G3）。"""
    dispatcher, bus, _, svc = _make_dispatcher(channel=_FakeChannel(ChannelType.WEB, uuid4()))
    await dispatcher.install(bus)
    handler = bus.subs[INBOUND_MESSAGE_EVENT][0]
    await handler({"payload": _msg()._as_payload_dict()})
    assert len(svc.requests) == 1
    request = svc.requests[0]
    assert str(request.owner_id) == str(_SERVICE_USER_ID)
    assert str(request.agent_id) == str(_SERVICE_AGENT_ID)
    assert request.agent_version == _SERVICE_AGENT_VERSION


@pytest.mark.asyncio
async def test_the_session_key_is_sticky_per_channel_and_chat() -> None:
    """**同一个渠道 + 同一个聊天 = 同一个会话** ✓（台账 R1）。

    ⚠️ 过去 IM 每条消息新建会话 —— 跨消息没有上下文 ✗。
    """
    channel_id = uuid4()
    dispatcher, bus, _, svc = _make_dispatcher(channel=_FakeChannel(ChannelType.WEB, uuid4()))
    await dispatcher.install(bus)
    handler = bus.subs[INBOUND_MESSAGE_EVENT][0]
    for _ in range(2):
        await handler(
            {"payload": _msg(channel_id=channel_id, external_chat_id="chat-9")._as_payload_dict()}
        )
    assert len(svc.requests) == 2
    keys = {request.channel_session_key for request in svc.requests}
    assert len(keys) == 1
    key = keys.pop()
    # ⚠️ **哈希版** ✓（Router 方案 §4.1 ✓ —— 台账 R4 ✓）—— **原文不进库**
    # ✓（渠道 ID / 群 ID 是身份 ✓ —— §12.2 的观测约束 ✓）。
    assert str(channel_id) not in key
    assert "chat-9" not in key


@pytest.mark.asyncio
async def test_different_chats_get_different_session_keys() -> None:
    """不同的聊天 → 不同的会话 ✓（粘性是**按 chat** 的，不是按渠道）。"""
    channel_id = uuid4()
    dispatcher, bus, _, svc = _make_dispatcher(channel=_FakeChannel(ChannelType.WEB, uuid4()))
    await dispatcher.install(bus)
    handler = bus.subs[INBOUND_MESSAGE_EVENT][0]
    for chat in ("chat-a", "chat-b"):
        await handler(
            {"payload": _msg(channel_id=channel_id, external_chat_id=chat)._as_payload_dict()}
        )
    keys = {request.channel_session_key for request in svc.requests}
    assert len(keys) == 2


@pytest.mark.asyncio
async def test_a_channel_without_a_service_account_does_not_run_a_turn() -> None:
    """渠道没登记服务账号 → **不跑这一轮**（配置问题，不是请求问题）。"""
    dispatcher, bus, _, svc = _make_dispatcher(
        channel=_FakeChannel(ChannelType.WEB, uuid4(), service_account=None)
    )
    await dispatcher.install(bus)
    handler = bus.subs[INBOUND_MESSAGE_EVENT][0]
    await handler({"payload": _msg()._as_payload_dict()})
    assert svc.requests == []


@pytest.mark.asyncio
async def test_channel_not_found_drops_event() -> None:
    dispatcher, bus, repo, svc = _make_dispatcher(channel=None)
    await dispatcher.install(bus)
    handler = bus.subs[INBOUND_MESSAGE_EVENT][0]
    await handler({"payload": _msg()._as_payload_dict()})
    assert repo.calls == 1
    assert svc.requests == []


@pytest.mark.asyncio
async def test_outbound_adapter_invoked_with_reply() -> None:
    outbound = {"web": _FakeOutboundAdapter("web")}
    dispatcher, bus, *_ = _make_dispatcher(
        channel=_FakeChannel(ChannelType.WEB, uuid4()),
        outbound=outbound,
    )
    await dispatcher.install(bus)
    handler = bus.subs[INBOUND_MESSAGE_EVENT][0]
    await handler({"payload": _msg()._as_payload_dict()})
    adapter = outbound["web"]
    assert len(adapter.sent) == 1
    assert adapter.sent[0]["text"] == "hi back"
    assert "turn_id" in adapter.sent[0]["metadata"]


@pytest.mark.asyncio
async def test_missing_outbound_adapter_drops_reply_silently() -> None:
    dispatcher, bus, *_ = _make_dispatcher(
        channel=_FakeChannel(ChannelType.WEB, uuid4()),
        outbound={},
    )
    await dispatcher.install(bus)
    handler = bus.subs[INBOUND_MESSAGE_EVENT][0]
    await handler({"payload": _msg()._as_payload_dict()})  # should not raise


@pytest.mark.asyncio
async def test_a_failed_turn_does_not_break_the_bus() -> None:
    """这一轮炸了 → **记日志、不炸总线** ✓（旧实现也是这个口径）。"""
    service = _FakeTurnService()
    service.fail = True
    dispatcher, bus, *_ = _make_dispatcher(
        channel=_FakeChannel(ChannelType.WEB, uuid4()), service=service
    )
    await dispatcher.install(bus)
    handler = bus.subs[INBOUND_MESSAGE_EVENT][0]
    await handler({"payload": _msg()._as_payload_dict()})  # should not raise


@pytest.mark.asyncio
async def test_invalid_payload_logged_and_skipped() -> None:
    dispatcher, bus, repo, *_ = _make_dispatcher(channel=None)
    await dispatcher.install(bus)
    handler = bus.subs[INBOUND_MESSAGE_EVENT][0]
    await handler({"payload": {"unexpected": "shape"}})
    assert repo.calls == 0


__all__ = []
