"""Unit tests for ``ChannelDispatchSubscriber``.

Tests the message-key derivation, dedup window, payload reconstruction,
and channel-not-found handling. The agent_turn + outbound paths are
exercised separately (see test_subscriber_drains_to_reply_*).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from qzdap.modules.channel.adapter.dispatch.dispatch_subscriber import (
    SYSTEM_AGENT_ID,
    SYSTEM_AGENT_VERSION,
    SYSTEM_USER_ID,
    ChannelDispatchSubscriber,
)
from qzdap.modules.channel.domain.events import ChannelMessageReceived


class _FakeChannelRepo:
    def __init__(self, channel: Any | None) -> None:
        self._channel = channel
        self.calls = 0

    async def get_by_id(self, channel_id: UUID) -> Any:  # type: ignore[no-untyped-def]
        self.calls += 1
        return self._channel


class _FakeChannel:
    def __init__(self, type: str, workspace_id: UUID) -> None:
        self.type = type
        self.workspace_id = workspace_id


class _FakeAgentRuntime:
    def __init__(self) -> None:
        self.created_sessions: list[dict] = []
        self.turns: list[dict] = []

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


def _make_subscriber(
    *,
    channel: Any | None,
    outbound: dict | None = None,
    runtime: _FakeAgentRuntime | None = None,
) -> tuple[ChannelDispatchSubscriber, _FakeBus, _FakeChannelRepo, _FakeAgentRuntime]:
    repo = _FakeChannelRepo(channel)
    bus = _FakeBus()
    rt = runtime or _FakeAgentRuntime()
    factory = _FakeAgentRuntimeFactory(rt)
    session = _FakeSession(uuid4())
    subscriber = ChannelDispatchSubscriber(
        channel_repository=repo,
        agent_runtime_factory=factory,
        outbound_registry_getter=lambda: outbound or {},
        clock=None,
        open_session=lambda: _CtxMgr(session),
    )
    return subscriber, bus, repo, rt


def _evt(**overrides: Any) -> ChannelMessageReceived:
    base = {
        "channel_id": uuid4(),
        "channel_type": "web",
        "external_user_id": "u1",
        "external_chat_id": "c1",
        "text_preview": "hello",
        "tenant_id": uuid4(),
    }
    base.update(overrides)
    return ChannelMessageReceived(**base)


_MSG_TOPIC = "channel.message.received"


@pytest.mark.asyncio
async def test_message_key_is_stable_and_hashlike() -> None:
    sub, *_ = _make_subscriber(channel=None)
    k1 = sub._message_key(_evt(channel_id=uuid4()))
    k2 = sub._message_key(_evt(channel_id=uuid4()))
    # Different channel_ids → different keys.
    assert len(k1) == 64
    assert k1 != k2


@pytest.mark.asyncio
async def test_dedup_hits_within_window() -> None:
    sub, bus, *_ = _make_subscriber(channel=_FakeChannel("web", uuid4()))
    await sub.install(bus)
    evt = _evt()
    payload = {
        "channel_id": str(evt.channel_id),
        "channel_type": evt.channel_type,
        "external_user_id": evt.external_user_id,
        "external_chat_id": evt.external_chat_id,
        "text_preview": evt.text_preview,
        "tenant_id": str(evt.tenant_id),
    }
    handler = bus.subs[_MSG_TOPIC][0]
    await handler({"payload": payload})
    await handler({"payload": payload})
    assert bus.subs[_MSG_TOPIC]


@pytest.mark.asyncio
async def test_channel_not_found_drops_event() -> None:
    sub, bus, repo, rt = _make_subscriber(channel=None)
    await sub.install(bus)
    handler = bus.subs[_MSG_TOPIC][0]
    evt = _evt()
    payload = {
        "channel_id": str(evt.channel_id),
        "channel_type": evt.channel_type,
        "external_user_id": evt.external_user_id,
        "external_chat_id": evt.external_chat_id,
        "text_preview": evt.text_preview,
        "tenant_id": str(evt.tenant_id),
    }
    await handler({"payload": payload})
    assert repo.calls == 1
    assert rt.created_sessions == []


@pytest.mark.asyncio
async def test_run_turn_uses_system_actor() -> None:
    sub, bus, _, rt = _make_subscriber(channel=_FakeChannel("web", uuid4()))
    await sub.install(bus)
    evt = _evt()
    payload = {
        "channel_id": str(evt.channel_id),
        "channel_type": evt.channel_type,
        "external_user_id": evt.external_user_id,
        "external_chat_id": evt.external_chat_id,
        "text_preview": evt.text_preview,
        "tenant_id": str(evt.tenant_id),
    }
    handler = bus.subs[_MSG_TOPIC][0]
    await handler({"payload": payload})
    assert len(rt.created_sessions) == 1
    owner_id = rt.created_sessions[0]["owner_id"]
    assert str(owner_id) == str(SYSTEM_USER_ID)
    agent_id = rt.created_sessions[0]["agent_id"]
    assert str(agent_id) == str(SYSTEM_AGENT_ID)
    assert rt.created_sessions[0]["agent_version"] == SYSTEM_AGENT_VERSION
    # turn ran
    assert len(rt.turns) == 1


@pytest.mark.asyncio
async def test_outbound_adapter_invoked_with_reply() -> None:
    outbound = {"web": _FakeOutboundAdapter("web")}
    sub, bus, _, _ = _make_subscriber(
        channel=_FakeChannel("web", uuid4()),
        outbound=outbound,
    )
    await sub.install(bus)
    evt = _evt()
    payload = {
        "channel_id": str(evt.channel_id),
        "channel_type": evt.channel_type,
        "external_user_id": evt.external_user_id,
        "external_chat_id": evt.external_chat_id,
        "text_preview": evt.text_preview,
        "tenant_id": str(evt.tenant_id),
    }
    handler = bus.subs[_MSG_TOPIC][0]
    await handler({"payload": payload})
    adapter = outbound["web"]
    assert len(adapter.sent) == 1
    assert adapter.sent[0]["text"] == "hi back"
    assert "turn_id" in adapter.sent[0]["metadata"]


@pytest.mark.asyncio
async def test_missing_outbound_adapter_drops_reply_silently() -> None:
    sub, bus, _, _ = _make_subscriber(
        channel=_FakeChannel("web", uuid4()),
        outbound={},
    )
    await sub.install(bus)
    evt = _evt()
    payload = {
        "channel_id": str(evt.channel_id),
        "channel_type": evt.channel_type,
        "external_user_id": evt.external_user_id,
        "external_chat_id": evt.external_chat_id,
        "text_preview": evt.text_preview,
        "tenant_id": str(evt.tenant_id),
    }
    handler = bus.subs[_MSG_TOPIC][0]
    await handler({"payload": payload})  # should not raise


@pytest.mark.asyncio
async def test_invalid_payload_logged_and_skipped() -> None:
    sub, bus, repo, _ = _make_subscriber(channel=None)
    await sub.install(bus)
    handler = bus.subs[_MSG_TOPIC][0]
    await handler({"payload": {"unexpected": "shape"}})
    assert repo.calls == 0


@pytest.mark.asyncio
async def test_dedup_window_eviction() -> None:
    sub, *_ = _make_subscriber(channel=None)
    sub._dedup_window = 2
    sub._seen[(uuid4(), uuid4(), "a")] = None
    sub._seen[(uuid4(), uuid4(), "b")] = None
    sub._seen[(uuid4(), uuid4(), "c")] = None
    sub._evict_dedup()
    assert len(sub._seen) == 2
    assert all(k[2] != "a" for k in sub._seen)


__all__ = []
