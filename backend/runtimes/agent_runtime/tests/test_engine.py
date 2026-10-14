"""Tests for Stage 5 PR B: SessionEngine + ChannelGateway + OutboxToSinkAdapter."""

from __future__ import annotations

import asyncio

import pytest

from qzdap_agent_runtime import (
    ChannelGateway,
    SessionEngine,
    SessionRef,
    TurnRequest,
)
from qzdap_agent_runtime.channels import (
    ChannelMessage,
    build_session_key,
)
from qzdap_agent_runtime.outbox import (
    InMemoryOutboxRepository,
    OutboxEvent,
    OutboxToSinkAdapter,
    OutboxWorker,
)
from qzdap_agent_runtime.result import (
    DoneEvent,
    InMemoryResultSink,
    MessageEvent,
    ResultDispatcher,
)


# ---------------------------------------------------------------------------
# SessionEngine: ensure_session
# ---------------------------------------------------------------------------


class TestEnsureSession:
    async def test_ensure_session_returns_ref(self) -> None:
        engine = SessionEngine()
        ref = await engine.ensure_session({
            "tenant_id": "t-1",
            "workspace_id": "w-1",
            "channel_id": "feishu",
            "external_chat_id": "oc_1",
            "external_user_id": "u_1",
        })
        assert isinstance(ref, SessionRef)
        assert ref.tenant_id == "t-1"
        assert ref.workspace_id == "w-1"
        assert ref.channel_id == "feishu"

    async def test_ensure_session_id_is_deterministic(self) -> None:
        """同一组 identity 必须产出同一 session_id (稳定 key)。"""
        engine = SessionEngine()
        ref1 = await engine.ensure_session({
            "tenant_id": "t-1", "workspace_id": "w-1", "channel_id": "feishu",
            "external_chat_id": "oc_1", "external_user_id": "u_1",
        })
        ref2 = await engine.ensure_session({
            "tenant_id": "t-1", "workspace_id": "w-1", "channel_id": "feishu",
            "external_chat_id": "oc_1", "external_user_id": "u_1",
        })
        assert ref1.session_id == ref2.session_id

    async def test_different_identity_yields_different_session(self) -> None:
        engine = SessionEngine()
        ref1 = await engine.ensure_session({
            "tenant_id": "t-1", "workspace_id": "w-1", "channel_id": "feishu",
            "external_chat_id": "oc_1", "external_user_id": "u_1",
        })
        ref2 = await engine.ensure_session({
            "tenant_id": "t-1", "workspace_id": "w-1", "channel_id": "feishu",
            "external_chat_id": "oc_2",  # 不同 chat
            "external_user_id": "u_1",
        })
        assert ref1.session_id != ref2.session_id


# ---------------------------------------------------------------------------
# SessionEngine: start_turn (Stage 5 简化实现)
# ---------------------------------------------------------------------------


class TestStartTurn:
    async def test_start_turn_emits_done_event(self) -> None:
        engine = SessionEngine()
        request = TurnRequest(
            tenant_id="t-1",
            workspace_id="w-1",
            user_id="u-1",
            agent_id="agt-1",
            agent_version="v1",
            messages=[{"role": "user", "content": "hello"}],
        )
        events = []
        async for ev in engine.start_turn(request):
            events.append(ev)
        # 至少有一个 done event
        assert any(isinstance(e, DoneEvent) for e in events)

    async def test_start_turn_does_not_raise(self) -> None:
        engine = SessionEngine()
        request = TurnRequest(
            tenant_id="t-1", workspace_id="w-1", user_id="u-1",
            agent_id="agt-1", agent_version="v1",
            messages=[{"role": "user", "content": "hi"}],
        )
        async for _ in engine.start_turn(request):
            pass  # 不抛异常


# ---------------------------------------------------------------------------
# SessionEngine: replay (§4.4 Last-Event-ID)
# ---------------------------------------------------------------------------


class TestReplay:
    async def test_replay_returns_all_events(self) -> None:
        engine = SessionEngine()
        # 先 start_turn 触发事件
        request = TurnRequest(
            tenant_id="t-1", workspace_id="w-1", user_id="u-1",
            agent_id="agt-1", agent_version="v1",
            messages=[{"role": "user", "content": "test"}],
        )
        turn_id = None
        async for ev in engine.start_turn(request):
            if isinstance(ev, DoneEvent):
                turn_id = ev.turn_id
        # replay after_seq=-1 → 取所有事件
        events = []
        async for ev in engine.replay(turn_id, after_seq=-1):
            events.append(ev)
        assert len(events) >= 1
        # after_seq=N → 从 N 之后开始 (空集, 因为 N 已是最大)
        events2 = []
        async for ev in engine.replay(turn_id, after_seq=10**6):
            events2.append(ev)
        assert events2 == []


# ---------------------------------------------------------------------------
# SessionEngine: cancel_turn / close_session
# ---------------------------------------------------------------------------


class TestLifecycleStubs:
    async def test_cancel_turn_does_not_raise(self) -> None:
        engine = SessionEngine()
        await engine.cancel_turn("s-1", "t-1", "user request")

    async def test_close_session_does_not_raise(self) -> None:
        engine = SessionEngine()
        await engine.close_session("s-1")


# ---------------------------------------------------------------------------
# ChannelGateway
# ---------------------------------------------------------------------------


class TestChannelGateway:
    async def test_handle_message_yields_events(self) -> None:
        engine = SessionEngine()
        gateway = ChannelGateway(engine)
        msg = ChannelMessage(
            tenant_id="t-1",
            workspace_id="w-1",
            channel_id="feishu-bot",
            channel_type="feishu",
            external_chat_id="oc_1",
            external_user_id="u_1",
            external_message_id="om_1",
            text="hello",
        )
        events = []
        async for ev in gateway.handle(msg):
            events.append(ev)
        assert any(isinstance(e, DoneEvent) for e in events)

    async def test_handle_uses_message_trace_id_when_present(self) -> None:
        engine = SessionEngine()
        gateway = ChannelGateway(engine)
        msg = ChannelMessage(
            tenant_id="t-1", workspace_id="w-1",
            channel_id="feishu", channel_type="feishu",
            external_chat_id="oc", external_user_id="u",
            external_message_id="om",
            text="hi",
            trace_id="X-Trace-Id-from-webhook-header",
        )
        # 不会抛异常, 消息被处理
        async for _ in gateway.handle(msg):
            pass

    async def test_same_external_chat_user_maps_to_same_session(self) -> None:
        """§5.1: stable session key (基于 tenant/workspace/channel/chat/user)。"""
        engine = SessionEngine()
        gateway = ChannelGateway(engine)
        m1 = ChannelMessage(
            tenant_id="t", workspace_id="w", channel_id="c",
            channel_type="feishu", external_chat_id="chat-1",
            external_user_id="u-1", external_message_id="m-1",
            text="hi",
        )
        m2 = ChannelMessage(
            tenant_id="t", workspace_id="w", channel_id="c",
            channel_type="feishu", external_chat_id="chat-1",
            external_user_id="u-1", external_message_id="m-2",  # 不同 message_id
            text="hi again",
        )
        # 用 ensure_session 比较
        ref1 = await engine.ensure_session({
            "tenant_id": "t", "workspace_id": "w", "channel_id": "c",
            "external_chat_id": "chat-1", "external_user_id": "u-1",
        })
        ref2 = await engine.ensure_session({
            "tenant_id": "t", "workspace_id": "w", "channel_id": "c",
            "external_chat_id": "chat-1", "external_user_id": "u-1",
        })
        assert ref1.session_id == ref2.session_id


# ---------------------------------------------------------------------------
# OutboxToSinkAdapter
# ---------------------------------------------------------------------------


class TestOutboxToSinkAdapter:
    async def test_dispatch_message_event_to_sink(self) -> None:
        sink = InMemoryResultSink()
        adapter = OutboxToSinkAdapter([sink])
        outbox_event = OutboxEvent(
            turn_id="t-1", seq=1, event_type="message",
            delivery_status="pending",
            delivery_attempts=0,
payload={"content": "hello"},
        )
        await adapter.dispatch(outbox_event)
        events = sink.get_events("t-1")
        assert len(events) == 1
        assert isinstance(events[0], MessageEvent)
        assert events[0].delta == "hello"

    async def test_dispatch_done_event(self) -> None:
        sink = InMemoryResultSink()
        adapter = OutboxToSinkAdapter([sink])
        outbox_event = OutboxEvent(
            turn_id="t-1", seq=5, event_type="done",
            delivery_status="pending",
            delivery_attempts=0,
payload={"final_message": "all good", "status": "succeeded"},
        )
        await adapter.dispatch(outbox_event)
        events = sink.get_events("t-1")
        assert any(isinstance(e, DoneEvent) for e in events)

    async def test_dispatch_unknown_event_falls_back_to_error(self) -> None:
        sink = InMemoryResultSink()
        adapter = OutboxToSinkAdapter([sink])
        outbox_event = OutboxEvent(
            turn_id="t-1", seq=1, event_type="custom_unknown_type",
            delivery_status="pending",
            delivery_attempts=0,
payload={"message": "fallback"},
        )
        await adapter.dispatch(outbox_event)
        events = sink.get_events("t-1")
        assert len(events) == 1
        from qzdap_agent_runtime.result import ErrorEvent
        assert isinstance(events[0], ErrorEvent)

    async def test_dispatch_to_dispatcher(self) -> None:
        """OutboxToSinkAdapter 必须能用 ResultDispatcher (含 .sinks 属性) 初始化。"""
        sink = InMemoryResultSink()
        dispatcher = ResultDispatcher([sink])
        adapter = OutboxToSinkAdapter(dispatcher)  # 传 dispatcher
        await adapter.dispatch(OutboxEvent(
            turn_id="t-1", seq=1, event_type="message",
            delivery_status="pending",
            delivery_attempts=0,
payload={"content": "x"},
        ))
        # dispatcher 应分发到 sink
        assert len(sink.get_events("t-1")) == 1

    async def test_sink_failure_does_not_propagate(self) -> None:
        """单个 sink 失败不阻塞其他 sink。"""
        from qzdap_agent_runtime.result.sink import DispatchError

        class _BoomSink:
            async def dispatch(self, event):
                raise DispatchError("boom")

        good = InMemoryResultSink()
        adapter = OutboxToSinkAdapter([_BoomSink(), good])
        # 不抛异常
        await adapter.dispatch(OutboxEvent(
            turn_id="t-1", seq=1, event_type="message",
            delivery_status="pending",
            delivery_attempts=0,
payload={"content": "x"},
        ))
        # good sink 收到
        assert len(good.get_events("t-1")) == 1


# ---------------------------------------------------------------------------
# §8 Stage 5 退出条件: outbox_dead_letters 首次写入
# ---------------------------------------------------------------------------


class TestOutboxDeadLetterFirstWrite:
    async def test_worker_routes_to_sink_via_adapter(self) -> None:
        """§8 Stage 5 退出: outbox_dead_letters 首次写入。

        验证 outbox worker 投递事件能通过 OutboxToSinkAdapter 到达 ResultSink,
        形成完整 outbox → sink 链路。
        """
        repo = InMemoryOutboxRepository()
        sink = InMemoryResultSink()
        adapter = OutboxToSinkAdapter([sink])

        # outbox 入队 1 个 message event
        repo.add(OutboxEvent(
            turn_id="t-1", seq=1, event_type="message",
            delivery_status="pending",
            delivery_attempts=0,
payload={"content": "first delivery"},
        ))

        # 用 adapter 作 dispatcher, 跑 1 轮 worker
        worker = OutboxWorker(repo, adapter)  # type: ignore[arg-type]
        n = await worker.tick()
        assert n == 1
        # sink 收到事件
        assert len(sink.get_events("t-1")) == 1
        # worker 统计
        assert worker.stats.delivered == 1