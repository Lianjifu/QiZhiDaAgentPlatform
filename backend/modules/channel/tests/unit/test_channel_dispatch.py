"""Unit tests for ``ChannelDispatchSubscriber``.

覆盖：入站消息还原、幂等 claim（取代旧的进程内 LRU）、渠道缺失、
服务账号物化、出站回写与失败释放。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from qzdap.modules.channel.adapter.dispatch.dispatch_subscriber import (
    INBOUND_MESSAGE_EVENT,
    ChannelDispatchSubscriber,
)
from qzdap.modules.channel.adapter.outbound.result_sink import ChannelResultSink
from qzdap_agent_runtime.gateway.facade import Gateway
from qzdap_agent_runtime.gateway.idempotency import IdempotencyGuard, InboxScope
from qzdap_agent_runtime.gateway.identity import HmacWebhookVerifier
from qzdap_agent_runtime.gateway.types import (
    ActorContext,
    ChannelType,
    IdempotencyDecision,
    IdempotencyKey,
    InboundMessage,
    KeySource,
)


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
        self.service_account = (
            _SERVICE_ACCOUNT if service_account is _UNSET else service_account
        )


class _FakeAgentRuntime:
    def __init__(self) -> None:
        self.created_sessions: list[dict] = []
        self.turns: list[dict] = []
        self.fail = False

    class _Sessions:
        def __init__(self, outer: _FakeAgentRuntime) -> None:
            self._outer = outer

        async def execute(self, **kwargs: Any) -> Any:  # type: ignore[no-untyped-def]
            session = _FakeSession(uuid4())
            self._outer.created_sessions.append({"session": session, **kwargs})
            return session

    class _Turns:
        def __init__(self, outer: _FakeAgentRuntime) -> None:
            self._outer = outer

        async def execute(self, **kwargs: Any) -> Any:  # type: ignore[no-untyped-def]
            from qzdap.modules.agent_runtime.application.use_cases.run_turn_to_completion import (
                RunTurnCompletionResult,
            )

            if self._outer.fail:
                raise RuntimeError("boom")
            self._outer.turns.append(kwargs)
            return RunTurnCompletionResult(
                final_message="hi back",
                turn_id=uuid4(),
                input_tokens=0,
                output_tokens=0,
                cache_read_tokens=0,
                cache_write_tokens=0,
            )

    def create_session(self) -> _Sessions:  # type: ignore[no-untyped-def]
        return _FakeAgentRuntime._Sessions(self)

    def run_turn_to_completion(self) -> _Turns:  # type: ignore[no-untyped-def]
        return _FakeAgentRuntime._Turns(self)


class _FakeSession:
    def __init__(self, id: UUID) -> None:
        self.id = id


class _FakeAgentRuntimeFactory:
    def __init__(self, runtime: _FakeAgentRuntime) -> None:
        self._runtime = runtime

    def for_session(self, session: Any) -> _FakeAgentRuntime:  # type: ignore[no-untyped-def]
        return self._runtime


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


class _FakeStore:
    """``IdempotencyStore`` 的内存实现 —— 认 strong 键的重复。"""

    def __init__(self) -> None:
        self.rows: dict[tuple[Any, ...], IdempotencyDecision] = {}
        self.completed: list[UUID] = []
        self.released: list[UUID] = []

    async def claim(
        self,
        scope: InboxScope,
        key: IdempotencyKey,
        *,
        payload_hash: str,
        external_message_id: str | None,
        trace_id: str,
    ) -> IdempotencyDecision:
        row_key = (scope.tenant_id, scope.workspace_id, scope.channel_id, key.value)
        existing = self.rows.get(row_key)
        if existing is not None:
            return IdempotencyDecision(
                outcome="duplicate",
                key_strength=key.strength,
                row_id=existing.row_id,
                status="completed",
            )
        decision = IdempotencyDecision(
            outcome="new",
            key_strength=key.strength,
            row_id=uuid4(),
            status="claimed",
        )
        self.rows[row_key] = decision
        return decision

    async def record_weak(
        self,
        scope: InboxScope,
        key: IdempotencyKey,
        *,
        payload_hash: str = "",
        trace_id: str = "",
    ) -> IdempotencyDecision:
        decision = IdempotencyDecision(
            outcome="new",
            key_strength="weak",
            row_id=uuid4(),
            status="claimed",
        )
        return decision

    async def mark_completed(self, row_id: UUID, *, turn_id: UUID | None = None) -> None:
        self.completed.append(row_id)

    async def release(self, row_id: UUID) -> None:
        self.released.append(row_id)


def _make_subscriber(
    *,
    channel: Any | None,
    outbound: dict | None = None,
    runtime: _FakeAgentRuntime | None = None,
) -> tuple[
    ChannelDispatchSubscriber, _FakeBus, _FakeChannelRepo, _FakeAgentRuntime, _FakeStore
]:
    repo = _FakeChannelRepo(channel)
    bus = _FakeBus()
    rt = runtime or _FakeAgentRuntime()
    factory = _FakeAgentRuntimeFactory(rt)
    session = _FakeSession(uuid4())
    store = _FakeStore()
    # ①②③ 的门面 —— 消费方只用它的 ④（claim / complete / release）。
    gateway = Gateway(
        channels=None,
        identity=HmacWebhookVerifier(),
        normalizers={},
        idempotency=IdempotencyGuard(store),
    )
    subscriber = ChannelDispatchSubscriber(
        channel_repository=repo,
        agent_runtime_factory=factory,
        sink=ChannelResultSink(outbound_registry=outbound or {}),
        clock=None,
        open_session=lambda: _CtxMgr(session),
        gateway=gateway,
    )
    return subscriber, bus, repo, rt, store


def _msg(**overrides: Any) -> InboundMessage:
    base: dict[str, Any] = {
        "actor": ActorContext(
            tenant_id=uuid4(),
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
    sub, bus, *_ = _make_subscriber(channel=None)
    await sub.install(bus)
    assert INBOUND_MESSAGE_EVENT == "InboundMessage"
    assert list(bus.subs) == ["InboundMessage"]


@pytest.mark.asyncio
async def test_duplicate_message_runs_only_one_turn() -> None:
    """同一平台消息投递两次 → **只起一轮**（旧的进程内 LRU 已被取代）。"""
    sub, bus, _, rt, store = _make_subscriber(
        channel=_FakeChannel(ChannelType.WEB, uuid4())
    )
    await sub.install(bus)
    handler = bus.subs[INBOUND_MESSAGE_EVENT][0]
    payload = _msg()._as_payload_dict()
    await handler({"payload": payload})
    await handler({"payload": payload})
    assert len(rt.created_sessions) == 1
    assert len(rt.turns) == 1
    assert len(store.completed) == 1


@pytest.mark.asyncio
async def test_a_failed_turn_releases_the_key() -> None:
    """这一轮没跑起来 → 键不该被消费（平台重投还能被受理）。"""
    rt = _FakeAgentRuntime()
    rt.fail = True
    sub, bus, _, _, store = _make_subscriber(
        channel=_FakeChannel(ChannelType.WEB, uuid4()), runtime=rt
    )
    await sub.install(bus)
    handler = bus.subs[INBOUND_MESSAGE_EVENT][0]
    await handler({"payload": _msg()._as_payload_dict()})
    assert len(store.released) == 1
    assert store.completed == []


@pytest.mark.asyncio
async def test_channel_not_found_drops_event() -> None:
    sub, bus, repo, rt, _ = _make_subscriber(channel=None)
    await sub.install(bus)
    handler = bus.subs[INBOUND_MESSAGE_EVENT][0]
    await handler({"payload": _msg()._as_payload_dict()})
    assert repo.calls == 1
    assert rt.created_sessions == []


@pytest.mark.asyncio
async def test_run_turn_uses_the_channels_service_account() -> None:
    """IM 的 actor 由**渠道登记的服务账号**物化 —— 不再是全局常量（台账 G3）。"""
    sub, bus, _, rt, _ = _make_subscriber(
        channel=_FakeChannel(ChannelType.WEB, uuid4())
    )
    await sub.install(bus)
    handler = bus.subs[INBOUND_MESSAGE_EVENT][0]
    await handler({"payload": _msg()._as_payload_dict()})
    assert len(rt.created_sessions) == 1
    owner_id = rt.created_sessions[0]["owner_id"]
    assert str(owner_id) == str(_SERVICE_USER_ID)
    agent_id = rt.created_sessions[0]["agent_id"]
    assert str(agent_id) == str(_SERVICE_AGENT_ID)
    assert rt.created_sessions[0]["agent_version"] == _SERVICE_AGENT_VERSION
    assert len(rt.turns) == 1


@pytest.mark.asyncio
async def test_a_channel_without_a_service_account_does_not_run_a_turn() -> None:
    """渠道没登记服务账号 → **不跑这一轮**（配置问题，不是请求问题）。"""
    sub, bus, _, rt, _ = _make_subscriber(
        channel=_FakeChannel(ChannelType.WEB, uuid4(), service_account=None)
    )
    await sub.install(bus)
    handler = bus.subs[INBOUND_MESSAGE_EVENT][0]
    await handler({"payload": _msg()._as_payload_dict()})
    assert rt.created_sessions == []
    assert rt.turns == []


@pytest.mark.asyncio
async def test_outbound_adapter_invoked_with_reply() -> None:
    outbound = {"web": _FakeOutboundAdapter("web")}
    sub, bus, *_ = _make_subscriber(
        channel=_FakeChannel(ChannelType.WEB, uuid4()),
        outbound=outbound,
    )
    await sub.install(bus)
    handler = bus.subs[INBOUND_MESSAGE_EVENT][0]
    await handler({"payload": _msg()._as_payload_dict()})
    adapter = outbound["web"]
    assert len(adapter.sent) == 1
    assert adapter.sent[0]["text"] == "hi back"
    assert "turn_id" in adapter.sent[0]["metadata"]


@pytest.mark.asyncio
async def test_missing_outbound_adapter_drops_reply_silently() -> None:
    sub, bus, *_ = _make_subscriber(
        channel=_FakeChannel(ChannelType.WEB, uuid4()),
        outbound={},
    )
    await sub.install(bus)
    handler = bus.subs[INBOUND_MESSAGE_EVENT][0]
    await handler({"payload": _msg()._as_payload_dict()})  # should not raise


@pytest.mark.asyncio
async def test_invalid_payload_logged_and_skipped() -> None:
    sub, bus, repo, _, _ = _make_subscriber(channel=None)
    await sub.install(bus)
    handler = bus.subs[INBOUND_MESSAGE_EVENT][0]
    await handler({"payload": {"unexpected": "shape"}})
    assert repo.calls == 0


__all__ = []
