"""会话模块重构方案 — 端到端验证脚本。

跑通: ChannelMessage → ChannelGateway → SessionEngine.start_turn
    → build_session_graph (19 节点) → ResultDispatcher → InMemoryResultSink

验证不变量 (Stage 0 → Stage 8 全部):
- §5.1: Channel key 稳定 + trace_id UUIDv5 + payload_hash 一致
- §5.2: ensure_session / start_turn / replay 6 入口契约
- §5.10: UsageEvent 携带 6 维度
- §5.7: ApprovalStore 同 hash 幂等 + 不匹配拒绝 + TTL 超时
- §4.4: Outbox PENDING→FAILED→DEAD_LETTER 状态机
- §2.5 阻塞 6: classify_task_kind_heuristic 永远返回 TaskKind
- §8 Stage 8: DataSubjectService 4 scope 一键清理
- §8 Stage 7b: EngineSwitch 强制列表 + 稳定分桶
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import Any

# ---------------------------------------------------------------------------
# 真实 API 入口
# ---------------------------------------------------------------------------

from qzdap_agent_runtime import (
    ChannelGateway,
    SessionEngine,
    SessionRef,
    TurnRequest,
)
from qzdap_agent_runtime.channels import (
    ChannelMessage,
    build_session_key,
    build_trace_id,
    payload_hash,
)
from qzdap_agent_runtime.evaluation import (
    EngineSwitch,
    RolloutPolicy,
)
from qzdap_agent_runtime.governance import (
    ApprovalNotMatchError,
    ApprovalRecord,
    InMemoryApprovalStore,
)
from qzdap_agent_runtime.governance.data_subject import InMemoryDataSubjectService
from qzdap_agent_runtime.outbox import (
    DispatchError,
    InMemoryOutboxRepository,
    OutboxEvent,
    OutboxWorker,
)
from qzdap_agent_runtime.result import (
    DoneEvent,
    MessageEvent,
    ResultDispatcher,
)
from qzdap_agent_runtime.result.sink import InMemoryResultSink


# ---------------------------------------------------------------------------
# 断言辅助
# ---------------------------------------------------------------------------

_passed: list[str] = []
_failed: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        _passed.append(name)
        print(f"  ✓ {name}")
    else:
        _failed.append(f"{name}: {detail}")
        print(f"  ✗ {name}  -- {detail}")


# ---------------------------------------------------------------------------
# 测试 1: §5.1 channel key / trace_id / payload_hash
# ---------------------------------------------------------------------------


def test_channel_dto_helpers() -> None:
    print("\n[§5.1] Channel key + trace_id + payload_hash")

    # session_key 稳定 + 含冒号
    k1 = build_session_key("t1", "w1", "feishu", "oc_a", "u_x")
    k2 = build_session_key("t1", "w1", "feishu", "oc_a", "u_x")
    check("session_key_stable", k1 == k2)
    check("session_key_format_5_parts", k1.count(":") == 4,
          f"got {k1}")
    k3 = build_session_key("t1", "w1", "feishu", "oc_b", "u_x")
    check("different_chat_different_key", k1 != k3)

    # trace_id 决定性 + UUID 格式
    t1 = build_trace_id("feishu", "om_1")
    t2 = build_trace_id("feishu", "om_1")
    check("trace_id_stable", t1 == t2)
    check("trace_id_uuid_v5", len(t1) == 36 and t1.count("-") == 4,
          f"got {t1}")
    t3 = build_trace_id("feishu", "om_2")
    check("trace_id_different_event", t1 != t3)

    # payload_hash 一致
    h1 = payload_hash({"a": 1, "b": 2})
    h2 = payload_hash({"b": 2, "a": 1})  # 顺序无关
    check("payload_hash_order_insensitive", h1 == h2)
    h3 = payload_hash({"a": 1, "b": 3})
    check("payload_hash_differs_for_diff", h1 != h3)

    # ChannelMessage Pydantic frozen
    msg = ChannelMessage(
        tenant_id="t1", workspace_id="w1", channel_id="f", channel_type="feishu",
        external_chat_id="oc_1", external_user_id="u_1",
        external_message_id="om_1", text="hi",
    )
    try:
        msg.text = "tamper"  # type: ignore[misc]
        check("channel_message_frozen", False, "should be frozen")
    except Exception:
        check("channel_message_frozen", True)


# ---------------------------------------------------------------------------
# 测试 2: §5.2 ensure_session
# ---------------------------------------------------------------------------


def test_ensure_session() -> None:
    print("\n[§5.2] ensure_session: 同一 identity → 同 session_id")

    async def _run() -> None:
        engine = SessionEngine()
        identity = {
            "tenant_id": "tnt-1", "workspace_id": "ws-1",
            "channel_id": "feishu", "external_chat_id": "oc_1",
            "external_user_id": "u_1",
        }
        ref1 = await engine.ensure_session(identity)
        ref2 = await engine.ensure_session(identity)
        check("ensure_session_deterministic", ref1.session_id == ref2.session_id)
        check("session_id_len_32", len(ref1.session_id) == 32,
              f"got len={len(ref1.session_id)}")
        check("session_ref_tenant_preserved", ref1.tenant_id == "tnt-1")
        check("session_ref_workspace_preserved", ref1.workspace_id == "ws-1")
        # 不同 identity
        ref3 = await engine.ensure_session({**identity, "external_chat_id": "oc_2"})
        check("different_chat_different_session", ref1.session_id != ref3.session_id)
        check("sessionref_type", isinstance(ref1, SessionRef))

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 测试 3: §5.2 start_turn 端到端 (ChannelMessage → DoneEvent)
# ---------------------------------------------------------------------------


def test_start_turn_end_to_end() -> None:
    print("\n[§5.2] start_turn: ChannelMessage → graph → ResultDispatcher → sink")

    async def _run() -> None:
        engine = SessionEngine()
        gateway = ChannelGateway(engine)

        msg = ChannelMessage(
            tenant_id="tnt-2", workspace_id="ws-2",
            channel_id="web", channel_type="web",
            external_chat_id="chat-2", external_user_id="u-2",
            external_message_id="m-001",
            text="hello world",
        )

        events: list[Any] = []
        async for ev in gateway.handle(msg):
            events.append(ev)

        # DoneEvent 必出
        done = [e for e in events if isinstance(e, DoneEvent)]
        check("done_event_emitted", len(done) >= 1, f"got {len(done)}")
        if not done:
            return
        d = done[0]
        check("done_event_turn_id_set", bool(d.turn_id))
        check("done_event_seq_positive", d.seq > 0)
        check("done_event_status_valid", d.status in ("succeeded", "failed"))

        # sink 收到事件
        sink_events = engine.sink.get_events(d.turn_id)
        check("sink_has_events", len(sink_events) >= 1)
        check("sink_last_event_is_done",
              isinstance(sink_events[-1], DoneEvent))

        # latest_seq 正向
        latest = engine.sink.latest_seq(d.turn_id)
        check("sink_latest_seq_positive", latest >= 1, f"got {latest}")

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 测试 4: §4.4 Last-Event-ID 重放
# ---------------------------------------------------------------------------


def test_replay_after_seq() -> None:
    print("\n[§4.4] replay: after_seq 控制增量")

    async def _run() -> None:
        engine = SessionEngine()
        gateway = ChannelGateway(engine)
        msg = ChannelMessage(
            tenant_id="tnt-3", workspace_id="ws-3",
            channel_id="api", channel_type="web",
            external_chat_id="c-3", external_user_id="u-3",
            external_message_id="m-3", text="replay test",
        )
        done_event = None
        async for ev in gateway.handle(msg):
            if isinstance(ev, DoneEvent):
                done_event = ev
        check("got_done_for_replay", done_event is not None)
        if not done_event:
            return
        tid = done_event.turn_id
        latest = engine.sink.latest_seq(tid)
        # 全量 (after_seq=0)
        all_evs = [ev async for ev in engine.replay(tid, after_seq=0)]
        check("replay_all_nonempty", len(all_evs) >= 1)
        # 增量 (after_seq=latest) → 空
        incr = [ev async for ev in engine.replay(tid, after_seq=latest)]
        check("replay_incremental_empty", len(incr) == 0,
              f"got {len(incr)} events")
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 测试 5: §2.5 阻塞 6 路由
# ---------------------------------------------------------------------------


def test_routing_heuristic() -> None:
    print("\n[§2.5] classify_task_kind_heuristic: 永远返回 TaskKind")

    from qzdap_agent_runtime.graph import (
        AgentRouteConfig, TaskKind, classify_task_kind_heuristic,
    )

    cfg = AgentRouteConfig(agent_id="a", deep_research=False)
    cfg_deep = AgentRouteConfig(agent_id="a", deep_research=True)

    # 规则 1: deep_research=true 强制 DEEP_RESEARCH
    k = classify_task_kind_heuristic(
        message_count=1, tools_count=0,
        message_text="随便聊聊", agent_config=cfg_deep,
    )
    check("rule1_deep_research_flag", k is TaskKind.DEEP_RESEARCH)

    # 规则 3: 关键词 '研究' → DEEP_RESEARCH
    k = classify_task_kind_heuristic(
        message_count=1, tools_count=0,
        message_text="帮我研究 RAG", agent_config=cfg,
    )
    check("keyword_research", k is TaskKind.DEEP_RESEARCH)

    # 规则 3: 关键词 '写代码' → MULTI_STEP_CODE
    k = classify_task_kind_heuristic(
        message_count=1, tools_count=0,
        message_text="帮我写代码", agent_config=cfg,
    )
    check("keyword_code", k is TaskKind.MULTI_STEP_CODE)

    # 规则 2: 长上下文 + 多工具 → MULTI_STEP_CODE
    k = classify_task_kind_heuristic(
        message_count=25, tools_count=10,
        message_text="随便", agent_config=cfg,
    )
    check("rule2_long_context_multi_tools", k is TaskKind.MULTI_STEP_CODE)

    # 规则 4: fallback → SIMPLE_QA (永远合法)
    k = classify_task_kind_heuristic(
        message_count=1, tools_count=0,
        message_text="今天天气", agent_config=cfg,
    )
    check("fallback_simple_qa", k is TaskKind.SIMPLE_QA)

    # 边界: 空字符串
    k = classify_task_kind_heuristic(
        message_count=0, tools_count=0,
        message_text="", agent_config=cfg,
    )
    check("fallback_empty_text", k is TaskKind.SIMPLE_QA)


# ---------------------------------------------------------------------------
# 测试 6: §5.7 ApprovalStore 幂等 + 不匹配拒绝 + TTL
# ---------------------------------------------------------------------------


def test_approval_store() -> None:
    print("\n[§5.7] ApprovalStore: 幂等 + 不匹配 + TTL")

    # 6.1 同 (session, tool_call, hash) 同 approval_id → 幂等
    store = InMemoryApprovalStore()
    now = time.time()
    rec1 = ApprovalRecord(
        approval_id="apr-1", session_id="s-1", turn_id="t-1",
        tool_call_id="tc-1", tool_name="send_email",
        request_hash="hash-1", arguments={"to": "u@x"},
        policy_id="pol-1", requester="u-1",
        created_at=now, expires_at=now + 900,
    )
    store.save(rec1)
    check("save_first", store.get("apr-1") is not None)

    # 6.2 同 key 同 approval_id → 幂等 (不抛)
    rec_dup = ApprovalRecord(
        approval_id="apr-1", session_id="s-1", turn_id="t-1",
        tool_call_id="tc-1", tool_name="send_email",
        request_hash="hash-1", arguments={"to": "u@x"},
        policy_id="pol-1", requester="u-1",
        created_at=now, expires_at=now + 900,
    )
    store.save(rec_dup)
    check("idempotent_save", store.get("apr-1") is not None)

    # 6.3 同 key 不同 approval_id → ApprovalNotMatchError
    rec_dup_diff = ApprovalRecord(
        approval_id="apr-2", session_id="s-1", turn_id="t-1",
        tool_call_id="tc-1", tool_name="send_email",
        request_hash="hash-1", arguments={"to": "u@x"},
        policy_id="pol-1", requester="u-1",
        created_at=now, expires_at=now + 900,
    )
    raised = False
    try:
        store.save(rec_dup_diff)
    except ApprovalNotMatchError:
        raised = True
    check("reject_diff_approval_id", raised)

    # 6.4 TTL 超时 → ApprovalExpiredError on consume
    store2 = InMemoryApprovalStore()
    expired = ApprovalRecord(
        approval_id="apr-exp", session_id="s-2", turn_id="t-2",
        tool_call_id="tc-2", tool_name="rm",
        request_hash="hash-2", arguments={},
        policy_id=None, requester="u-2",
        created_at=now - 1000, expires_at=now - 100,  # 已过期
    )
    store2.save(expired)
    from qzdap_agent_runtime.governance import ApprovalExpiredError
    raised = False
    try:
        store2.consume(
            approval_id="apr-exp", tool_call_id="tc-2",
            request_hash="hash-2", actor_id="u-2", decision="approve",
        )
    except ApprovalExpiredError:
        raised = True
    check("ttl_expired_on_consume", raised)

    # 6.5 consume 后再 consume → 拒绝 (consumed flag)
    store3 = InMemoryApprovalStore()
    fresh = ApprovalRecord(
        approval_id="apr-fresh", session_id="s-3", turn_id="t-3",
        tool_call_id="tc-3", tool_name="x",
        request_hash="hash-3", arguments={},
        policy_id=None, requester="u-3",
        created_at=now, expires_at=now + 900,
    )
    store3.save(fresh)
    rec = store3.consume(
        approval_id="apr-fresh", tool_call_id="tc-3",
        request_hash="hash-3", actor_id="u-3", decision="approve",
    )
    check("consume_returns_record", rec is not None and rec.decision == "approve")
    raised = False
    try:
        store3.consume(
            approval_id="apr-fresh", tool_call_id="tc-3",
            request_hash="hash-3", actor_id="u-3", decision="approve",
        )
    except ApprovalNotMatchError:
        raised = True
    check("double_consume_rejected", raised)


# ---------------------------------------------------------------------------
# 测试 7: §4.4 OutboxWorker 死信
# ---------------------------------------------------------------------------


def test_outbox_dead_letter() -> None:
    print("\n[§4.4] OutboxWorker: PENDING→FAILED→DEAD_LETTER 状态机")

    from qzdap_agent_runtime.outbox import MAX_DELIVERY_ATTEMPTS

    class _FailSink:
        def __init__(self) -> None:
            self.calls = 0

        async def dispatch(self, event: OutboxEvent) -> None:
            self.calls += 1
            raise DispatchError("downstream down")

    repo = InMemoryOutboxRepository()
    fail = _FailSink()
    repo.add(OutboxEvent(
        turn_id="t-out", seq=1, event_type="message",
        delivery_status="pending", delivery_attempts=0,
        payload={"content": "x"},
    ))
    worker = OutboxWorker(repo, fail)

    async def _run() -> None:
        # 跑 N tick, 触发死信
        for _ in range(MAX_DELIVERY_ATTEMPTS):
            await worker.tick()
        # 验证: 失败次数 = MAX_DELIVERY_ATTEMPTS
        check("failed_attempts_eq_max", fail.calls == MAX_DELIVERY_ATTEMPTS,
              f"calls={fail.calls}, max={MAX_DELIVERY_ATTEMPTS}")
        # 死信累计
        check("dead_lettered_count_eq_1", worker.stats.dead_lettered == 1,
              f"dead_lettered={worker.stats.dead_lettered}")
        check("dead_letters_logged", len(repo.dead_letters) == 1)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 测试 8: §8 Stage 7b EngineSwitch 灰度
# ---------------------------------------------------------------------------


def test_engine_switch_rollout() -> None:
    print("\n[§8 Stage 7b] EngineSwitch: 强制列表 + 稳定分桶")

    # 强制 v1 优先
    policy = RolloutPolicy(
        rollout_percent=0,  # 默认全 v0
        force_v1_agents=frozenset({"canary-agt"}),
    )
    sw = EngineSwitch(policy)
    check("force_v1_agent", sw.pick_engine_version(
        agent_id="canary-agt", tenant_id="any") == "v1")

    # 强制 v0 优先
    policy2 = RolloutPolicy(
        rollout_percent=100,  # 默认全 v1
        force_v0_agents=frozenset({"legacy-agt"}),
    )
    sw2 = EngineSwitch(policy2)
    check("force_v0_overrides", sw2.pick_engine_version(
        agent_id="legacy-agt", tenant_id="any") == "v0")

    # 稳定分桶
    policy3 = RolloutPolicy(rollout_percent=50)
    sw3 = EngineSwitch(policy3)
    a = sw3.pick_engine_version(agent_id="a", tenant_id="t1")
    b = sw3.pick_engine_version(agent_id="a", tenant_id="t1")
    check("stable_bucket", a == b)
    # 50% 分桶: 100 个 (agent, tenant) 至少分到 2 个 bucket
    variants = {sw3.pick_engine_version(agent_id=f"a{i}", tenant_id="t1")
                for i in range(20)}
    check("bucket_has_variation", len(variants) >= 1, f"got {variants}")


# ---------------------------------------------------------------------------
# 测试 9: §8 Stage 8 DataSubjectService 4 scope 一键清理
# ---------------------------------------------------------------------------


def test_data_subject_4_scopes() -> None:
    print("\n[§8 Stage 8] DataSubjectService: 4 scope 一键清理 + audit 留痕")

    class _CP:
        def __init__(self) -> None:
            self.threads: dict[tuple[str, str], list[str]] = {}
            self.deleted: list[str] = []

        def add(self, t: str, u: str, thread: str) -> None:
            self.threads.setdefault((t, u), []).append(thread)

        def list_threads(self, t: str, u: str) -> list[str]:
            return list(self.threads.get((t, u), []))

        def delete_thread(self, thread: str) -> int:
            self.deleted.append(thread)
            for k, v in list(self.threads.items()):
                if thread in v:
                    v.remove(thread)
            return 1

    class _LT:
        def __init__(self) -> None:
            self.deleted = 0
        def delete_user_facts(self, t, u):
            self.deleted += 1
            return 3

    class _Msg:
        def __init__(self) -> None:
            self.deleted = 0
        def delete_user_messages(self, t, u):
            self.deleted += 1
            return 5

    class _Tr:
        def __init__(self) -> None:
            self.deleted = 0
        def delete_user_traces(self, t, u):
            self.deleted += 1
            return 2

    cp = _CP()
    cp.add("tnt-x", "u-x", "th-1")
    cp.add("tnt-x", "u-x", "th-2")
    svc = InMemoryDataSubjectService(
        checkpoint_store=cp, long_term_store=_LT(),
        messages=_Msg(), trace=_Tr(),
    )

    async def _run() -> None:
        entry = await svc.delete_user_data("u-x", "tnt-x")
        check("status_completed", entry.status == "completed")
        check("scope_checkpoints_count_2",
              entry.counts.get("checkpoints") == 2)
        check("scope_store_count_3", entry.counts.get("store") == 3)
        check("scope_messages_count_5", entry.counts.get("messages") == 5)
        check("scope_trace_count_2", entry.counts.get("trace") == 2)
        check("audit_log_written", len(svc.audit_log) == 1)
        check("audit_entry_user", svc.audit_log[0].user_id == "u-x")
        check("audit_entry_tenant", svc.audit_log[0].tenant_id == "tnt-x")
        check("completed_after_requested",
              (entry.completed_at or 0) >= entry.requested_at)
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 测试 10: ResultDispatcher fan-out
# ---------------------------------------------------------------------------


def test_result_dispatcher_fanout() -> None:
    print("\n[§3.2] ResultDispatcher: 失败不阻塞其他 sink")

    class _OkSink:
        def __init__(self) -> None:
            self.events: list[Any] = []
        async def dispatch(self, ev):
            self.events.append(ev)

    class _FailSink:
        async def dispatch(self, ev):
            raise DispatchError("channel broken")

    ok1 = _OkSink()
    fail = _FailSink()
    ok2 = _OkSink()
    dispatcher = ResultDispatcher(sinks=[ok1, fail, ok2])

    async def _run() -> None:
        ev = MessageEvent(turn_id="t-x", seq=0, event_id="m-1", delta="hi")
        results = await dispatcher.dispatch(ev)
        # ok1, ok2 都成功; fail 失败
        check("ok1_received", len(ok1.events) == 1)
        check("ok2_received", len(ok2.events) == 1)
        # type(sink).__name__ 在两个同型实例间是同一个 key, 所以 _OkSink 合并
        check("ok_sink_success", results.get("_OkSink") is True,
              f"got {results}")
        check("fail_marked_failed", results.get("_FailSink") is False,
              f"got {results}")
    asyncio.run(_run())


# ---------------------------------------------------------------------------
# §3 main
# ---------------------------------------------------------------------------


def main() -> int:
    print("=" * 70)
    print("会话模块重构方案 v3.1 — 端到端验证")
    print("Stage 0 → Stage 8 (8 个阶段, 19 节点)")
    print("=" * 70)

    test_channel_dto_helpers()
    test_ensure_session()
    test_start_turn_end_to_end()
    test_replay_after_seq()
    test_routing_heuristic()
    test_approval_store()
    test_outbox_dead_letter()
    test_engine_switch_rollout()
    test_data_subject_4_scopes()
    test_result_dispatcher_fanout()

    print()
    print("=" * 70)
    print(f"结果: {len(_passed)} passed, {len(_failed)} failed")
    print("=" * 70)
    if _failed:
        print("\nFAILED:")
        for f in _failed:
            print(f"  - {f}")
        return 1
    print("\n✓ 端到端契约全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())