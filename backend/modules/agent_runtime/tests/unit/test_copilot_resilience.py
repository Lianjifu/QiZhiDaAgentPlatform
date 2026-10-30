"""Resilience tests for the Copilot turn path (in-memory adapters, no DB).

Covers the guarantees the /api/sessions/{id}/turns/stream path must give:

  - a tool that raises must not kill the turn
  - a failure after the stream started must surface as an ``error`` chunk
    *and* leave the turn in ``failed`` (never stuck in ``running``)
  - a failure before the first chunk must still raise, so the HTTP layer
    can answer with a status code
  - a cancelled stream (client disconnect) must not leave a running turn
  - catalog tools the agent selects must reach the model with a real
    argument schema
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from _ar_unit_in_memory import (
    InMemoryIdempotencyStore,
    InMemorySessionJournal,
    InMemoryTurnRepository,
    make_dependencies,
    make_turn_runner,
)
from qzdap_agent_runtime.gateway.idempotency import IdempotencyGuard
from qzdap_agent_runtime.session.approval import arguments_digest
from qzdap_kernel.errors import ValidationError
from qzdap_llm.client import ChatRequest, LLMChunk, Usage
from qzdap_schema.dtos.turn import ApprovalRequiredChunk
from qzdap_schema.ids import AgentId, TenantId, UserId, WorkspaceId

from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner
from qzdap.modules.agent_runtime.adapter.turn.executor import (
    SessionGraphExecutor,
)
from qzdap.modules.agent_runtime.application.copilot import CopilotSessionService
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent
from qzdap.modules.agent_runtime.domain.errors import (
    DuplicateRequestError,
    SessionBusyError,
    SessionNotFound,
)


def _owners() -> tuple[TenantId, WorkspaceId, UserId, AgentId]:
    return TenantId(uuid4()), WorkspaceId(uuid4()), UserId(uuid4()), AgentId(uuid4())


class _Catalog:
    def __init__(self, agent: CatalogAgent) -> None:
        self._agent = agent

    async def get_published(self, agent_id):
        return self._agent


class _Messages:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def list_for_session(self, session_id):
        return self.rows

    async def append(self, **kwargs):
        self.rows.append(kwargs)

    async def next_seq(self, *, session_id):  # type: ignore[no-untyped-def]
        """下一个轮次内序号 ✓（与真实实现同语义）。"""
        return (self.rows[-1]["seq"] + 1) if self.rows else 0


class _DomainErrorLLM:
    """Yields one chunk, then fails with a **带稳定错误码**的领域异常。"""

    def __init__(self, error: Exception) -> None:
        self._error = error
        self.requests: list[ChatRequest] = []

    async def stream(self, req: ChatRequest) -> AsyncIterator[LLMChunk]:
        self.requests.append(req)
        yield LLMChunk(model=req.model, delta="partial")
        raise self._error

    async def synthetic_chunks(self, user_input, *, turn_id):
        return []


class _ExplodingLLM:
    """Yields one chunk, then blows up mid-stream."""

    def __init__(self) -> None:
        self.requests: list[ChatRequest] = []

    async def stream(self, req: ChatRequest) -> AsyncIterator[LLMChunk]:
        self.requests.append(req)
        yield LLMChunk(model=req.model, delta="partial")
        raise RuntimeError("upstream exploded")

    async def synthetic_chunks(self, user_input, *, turn_id):
        return []


class _RecordingLLM:
    def __init__(self, tool_calls: list[dict] | None = None) -> None:
        self.requests: list[ChatRequest] = []
        self._tool_calls = tool_calls

    async def stream(self, req: ChatRequest) -> AsyncIterator[LLMChunk]:
        self.requests.append(req)
        yield LLMChunk(model=req.model, delta="done")
        if self._tool_calls:
            yield LLMChunk(model=req.model, delta="", tool_calls=self._tool_calls)
        yield LLMChunk(
            model=req.model,
            delta="",
            finish_reason="stop",
            usage=Usage(input_tokens=1, output_tokens=1),
        )

    async def synthetic_chunks(self, user_input, *, turn_id):
        return []


class _SlowLLM:
    """Yields several chunks with small gaps — long enough to be cancelled."""

    def __init__(self, chunks: int = 8, gap: float = 0.02) -> None:
        self._chunks = chunks
        self._gap = gap

    async def stream(self, req: ChatRequest) -> AsyncIterator[LLMChunk]:
        for _ in range(self._chunks):
            await asyncio.sleep(self._gap)
            yield LLMChunk(model=req.model, delta="x")
        yield LLMChunk(
            model=req.model,
            delta="",
            finish_reason="stop",
            usage=Usage(input_tokens=1, output_tokens=1),
        )

    async def synthetic_chunks(self, user_input, *, turn_id):
        return []


class _PricingResolver:
    """Resolver that knows the model's price: 2.0 / 4.0 per 1K tokens."""

    def __init__(self) -> None:
        self.model_id = uuid4()

    async def resolve(self, *, tenant_id, workspace_id, upstream_model):
        return self.model_id

    async def price_of(self, *, tenant_id, workspace_id, model_id):
        return (2.0, 4.0)


class _PricingLLM:
    """LLM fake that accepts the saved-model call shape."""

    async def stream(
        self, req, *, model_id=None, route_id=None, actor=None, fallback_model_ids=None
    ):
        yield LLMChunk(model=req.model, delta="ok")
        yield LLMChunk(
            model=req.model,
            delta="",
            finish_reason="stop",
            usage=Usage(input_tokens=3, output_tokens=2),
        )

    async def synthetic_chunks(self, user_input, *, turn_id):
        return []


class _BoomToolPort:
    async def invoke(self, *, call_id, tool_name, arguments, **kwargs):
        raise RuntimeError("tool blew up")

    async def list_tools(self):
        return []


class _ScriptedLLM:
    """按脚本逐次产出 —— 审批场景需要「先要工具、后给回答」。"""

    def __init__(self, steps: list[dict]) -> None:
        self._steps = list(steps)
        self.calls = 0

    async def stream(self, req: ChatRequest) -> AsyncIterator[LLMChunk]:
        idx = min(self.calls, len(self._steps) - 1)
        self.calls += 1
        step = self._steps[idx]
        if step.get("delta"):
            yield LLMChunk(model=req.model, delta=str(step["delta"]))
        if step.get("tool_calls"):
            yield LLMChunk(
                model=req.model, delta="", tool_calls=list(step["tool_calls"])
            )
        yield LLMChunk(
            model=req.model,
            delta="",
            finish_reason="stop",
            usage=Usage(input_tokens=1, output_tokens=1),
        )

    async def synthetic_chunks(self, user_input, *, turn_id):
        return []


class _CatalogToolPort:
    def __init__(self, tools: list[dict]) -> None:
        self._tools = tools
        self.invoked: list[tuple[str, dict]] = []

    async def invoke(self, *, call_id, tool_name, arguments, **kwargs):
        self.invoked.append((tool_name, arguments))
        return {"ok": True, "output": "tool output"}

    async def list_tools(self):
        return self._tools


async def _make_service(
    *,
    llm,
    agent: CatalogAgent,
    owner_id: UserId,
    tool_port=None,
):
    deps = make_dependencies()
    messages = _Messages()
    runner = SessionGraphRunner(llm=llm, tool_port=tool_port)
    journal = InMemorySessionJournal()
    # 把 journal 也放进 deps —— 断言「审批挂起落库」要用 ✓
    deps["journal"] = journal
    # 轮次读仓库读**同一份行** ✓（停旧写后轮次只有一个落点 ✓）。
    deps["turns"] = InMemoryTurnRepository(journal)
    svc = CopilotSessionService(
        sessions=deps["sessions"],
        turns=deps["turns"],
        messages=messages,
        catalog=_Catalog(agent),
        events=deps["events"],
        graph=runner,
        idempotency=IdempotencyGuard(InMemoryIdempotencyStore()),
        journal=journal,
        claim=deps["sessions"].claim,
        turn_runner=make_turn_runner(
            graph=runner,
            journal=journal,
            events=deps["events"],
            messages=messages,
            sessions=deps["sessions"],
        ),
    )
    tid = TenantId(agent.tenant_id)
    wid = WorkspaceId(agent.workspace_id)
    detail = await svc.create_session(
        tenant_id=tid, workspace_id=wid, owner_id=owner_id, agent_id=agent.id
    )
    return svc, deps, detail["id"], tid, wid, owner_id


@pytest.mark.asyncio
async def test_tool_failure_does_not_kill_the_turn() -> None:
    tid, wid, uid, aid = _owners()
    agent = CatalogAgent.create(
        id=aid,
        tenant_id=tid,
        workspace_id=wid,
        name="t",
        category="test",
        owner="test",
        model="default",
    )
    agent.tools = [{"name": "boom_tool", "enabled": True}]
    llm = _RecordingLLM(
        tool_calls=[
            {"id": "call-1", "name": "boom_tool", "arguments": {"x": 1}},
        ]
    )
    tool_port = _BoomToolPort()
    svc, deps, sid, *_ = await _make_service(
        llm=llm, agent=agent, owner_id=uid, tool_port=tool_port
    )

    chunks = [
        chunk
        async for chunk in svc.stream_turn(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=uid,
            session_id=UUID(sid),
            user_input="hi",
        )
    ]

    kinds = [c.kind for c in chunks]
    assert "tool_result" in kinds
    assert "done" in kinds
    results = [c for c in chunks if c.kind == "tool_result"]
    assert results[0].is_error is True
    assert "tool blew up" in str(results[0].output)
    turn = await deps["turns"].latest_for_session(UUID(sid))
    assert turn is not None
    assert turn.status.value == "succeeded"


@pytest.mark.asyncio
async def test_mid_stream_failure_emits_error_chunk_and_fails_the_turn() -> None:
    tid, wid, uid, aid = _owners()
    agent = CatalogAgent.create(
        id=aid,
        tenant_id=tid,
        workspace_id=wid,
        name="t",
        category="test",
        owner="test",
        model="default",
    )
    svc, deps, sid, *_ = await _make_service(
        llm=_ExplodingLLM(), agent=agent, owner_id=uid
    )

    chunks = [
        chunk
        async for chunk in svc.stream_turn(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=uid,
            session_id=UUID(sid),
            user_input="hi",
        )
    ]

    kinds = [c.kind for c in chunks]
    assert "message" in kinds
    assert kinds[-1] == "error"
    assert "upstream exploded" in chunks[-1].message
    turn = await deps["turns"].latest_for_session(UUID(sid))
    assert turn is not None
    assert turn.status.value == "failed"
    assert turn.error_code == "TURN_FAILED"


@pytest.mark.asyncio
async def test_first_chunk_failure_raises_so_http_can_answer_with_a_status() -> None:
    tid, wid, uid, aid = _owners()
    agent = CatalogAgent.create(
        id=aid,
        tenant_id=tid,
        workspace_id=wid,
        name="t",
        category="test",
        owner="test",
        model="default",
    )
    deps = make_dependencies()
    messages = _Messages()
    runner = SessionGraphRunner(llm=deps["llm"])
    journal = InMemorySessionJournal()
    # 把 journal 也放进 deps —— 断言「审批挂起落库」要用 ✓
    deps["journal"] = journal
    # 轮次读仓库读**同一份行** ✓（停旧写后轮次只有一个落点 ✓）。
    deps["turns"] = InMemoryTurnRepository(journal)
    svc = CopilotSessionService(
        sessions=deps["sessions"],
        turns=deps["turns"],
        messages=messages,
        catalog=_Catalog(agent),
        events=deps["events"],
        graph=runner,
        idempotency=IdempotencyGuard(InMemoryIdempotencyStore()),
        journal=journal,
        claim=deps["sessions"].claim,
        turn_runner=make_turn_runner(
            graph=runner,
            journal=journal,
            events=deps["events"],
            messages=messages,
            sessions=deps["sessions"],
        ),
    )
    detail = await svc.create_session(
        tenant_id=tid, workspace_id=wid, owner_id=uid, agent_id=aid
    )

    # deps["llm"] is FakeLLM with raise_on_first_chunk unset → replace the
    # graph with one whose model fails before the first chunk.
    class _FailFast:
        async def stream(self, req):
            raise RuntimeError("no provider")
            yield  # pragma: no cover

        async def synthetic_chunks(self, user_input, *, turn_id):
            return []

    # ⚠️ 执行器在 turn_runner 里（**唯一 turn 实现** ✓）—— 换 graph 要连
    # executor 一起换，否则跑的还是旧 graph ✗。
    svc._graph = SessionGraphRunner(llm=_FailFast())
    svc._turn_runner._executor = SessionGraphExecutor(svc._graph)

    with pytest.raises(RuntimeError):
        async for _ in svc.stream_turn(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=uid,
            session_id=UUID(detail["id"]),
            user_input="hi",
        ):
            pass

    turn = await deps["turns"].latest_for_session(UUID(detail["id"]))
    assert turn is not None
    assert turn.status.value == "failed"


@pytest.mark.asyncio
async def test_cancelled_stream_does_not_leave_a_running_turn() -> None:
    tid, wid, uid, aid = _owners()
    agent = CatalogAgent.create(
        id=aid,
        tenant_id=tid,
        workspace_id=wid,
        name="t",
        category="test",
        owner="test",
        model="default",
    )
    svc, deps, sid, *_ = await _make_service(
        llm=_ExplodingLLM(), agent=agent, owner_id=uid
    )

    stream = svc.stream_turn(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        session_id=UUID(sid),
        user_input="hi",
    )
    await anext(stream)  # first chunk arrives
    await stream.aclose()  # client disconnects

    turn = await deps["turns"].latest_for_session(UUID(sid))
    assert turn is not None
    # 「被取消」在权威表 ``session_turns`` 里是 ``cancelled`` ✓ ——
    # 映射到领域枚举是 ``denied`` ✓（领域里最接近的「没跑成」✓）。
    assert turn.status.value == "denied"
    assert turn.error_code == "TURN_CANCELLED"


@pytest.mark.asyncio
async def test_catalog_tool_reaches_the_model_with_its_argument_schema() -> None:
    tid, wid, uid, aid = _owners()
    agent = CatalogAgent.create(
        id=aid,
        tenant_id=tid,
        workspace_id=wid,
        name="t",
        category="test",
        owner="test",
        model="default",
    )
    agent.tools = [{"name": "web_search", "enabled": True}]
    llm = _RecordingLLM()
    tool_port = _CatalogToolPort(
        [
            {
                "name": "web_search",
                "description": "联网搜索",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
                "risk": "medium",
                "needConfirm": False,
            }
        ]
    )
    svc, deps, sid, *_ = await _make_service(
        llm=llm, agent=agent, owner_id=uid, tool_port=tool_port
    )

    _ = [
        chunk
        async for chunk in svc.stream_turn(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=uid,
            session_id=UUID(sid),
            user_input="hi",
        )
    ]

    assert llm.requests, "the model should have been called"
    tools = llm.requests[0].tools or []
    names = [t["function"]["name"] for t in tools]
    assert "web_search" in names
    schema = next(
        t["function"]["parameters"]
        for t in tools
        if t["function"]["name"] == "web_search"
    )
    assert schema["properties"]["query"]["type"] == "string"
    assert schema["required"] == ["query"]


@pytest.mark.asyncio
async def test_unknown_session_still_raises_not_found() -> None:
    tid, wid, uid, aid = _owners()
    agent = CatalogAgent.create(
        id=aid,
        tenant_id=tid,
        workspace_id=wid,
        name="t",
        category="test",
        owner="test",
        model="default",
    )
    svc, deps, *_ = await _make_service(llm=_RecordingLLM(), agent=agent, owner_id=uid)
    with pytest.raises(SessionNotFound):
        async for _ in svc.stream_turn(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=uid,
            session_id=uuid4(),
            user_input="hi",
        ):
            pass


@pytest.mark.asyncio
async def test_second_concurrent_turn_is_rejected() -> None:
    """Two turns on one session would interleave messages and race on seq."""
    tid, wid, uid, aid = _owners()
    agent = CatalogAgent.create(
        id=aid,
        tenant_id=tid,
        workspace_id=wid,
        name="t",
        category="test",
        owner="test",
        model="default",
    )
    svc, deps, sid, *_ = await _make_service(llm=_SlowLLM(), agent=agent, owner_id=uid)

    first = svc.stream_turn(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        session_id=UUID(sid),
        user_input="one",
    )
    await anext(first)

    with pytest.raises(SessionBusyError):
        async for _ in svc.stream_turn(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=uid,
            session_id=UUID(sid),
            user_input="two",
        ):
            pass

    await first.aclose()


@pytest.mark.asyncio
async def test_cancel_request_stops_the_running_turn(monkeypatch) -> None:
    # 取消轮询的间隔现在住在**契约层**（唯一 turn 实现 ✓）
    from qzdap_agent_runtime.session import turn_runner as turn_runner_mod

    monkeypatch.setattr(turn_runner_mod, "CANCEL_POLL_SECONDS", 0.01)
    tid, wid, uid, aid = _owners()
    agent = CatalogAgent.create(
        id=aid,
        tenant_id=tid,
        workspace_id=wid,
        name="t",
        category="test",
        owner="test",
        model="default",
    )
    svc, deps, sid, *_ = await _make_service(llm=_SlowLLM(), agent=agent, owner_id=uid)

    stream = svc.stream_turn(
        tenant_id=tid,
        workspace_id=wid,
        owner_id=uid,
        session_id=UUID(sid),
        user_input="hi",
    )
    await anext(stream)
    live = await svc.request_cancel(tenant_id=tid, session_id=UUID(sid))
    assert live is True

    chunks = [chunk async for chunk in stream]
    assert chunks[-1].kind == "error"
    assert chunks[-1].code == "TURN_CANCELLED"
    turn = await deps["turns"].latest_for_session(UUID(sid))
    assert turn is not None
    # 「被取消」在权威表 ``session_turns`` 里是 ``cancelled`` ✓ ——
    # 映射到领域枚举是 ``denied`` ✓（领域里最接近的「没跑成」✓）。
    assert turn.status.value == "denied"
    assert turn.error_code == "TURN_CANCELLED"


@pytest.mark.asyncio
async def test_a_new_turn_is_not_cancelled_by_a_stale_flag(monkeypatch) -> None:
    # 取消轮询的间隔现在住在**契约层**（唯一 turn 实现 ✓）
    from qzdap_agent_runtime.session import turn_runner as turn_runner_mod

    monkeypatch.setattr(turn_runner_mod, "CANCEL_POLL_SECONDS", 0.01)
    tid, wid, uid, aid = _owners()
    agent = CatalogAgent.create(
        id=aid,
        tenant_id=tid,
        workspace_id=wid,
        name="t",
        category="test",
        owner="test",
        model="default",
    )
    svc, deps, sid, *_ = await _make_service(
        llm=_RecordingLLM(), agent=agent, owner_id=uid
    )
    await svc.request_cancel(tenant_id=tid, session_id=UUID(sid))

    chunks = [
        chunk
        async for chunk in svc.stream_turn(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=uid,
            session_id=UUID(sid),
            user_input="hi",
        )
    ]
    assert chunks[-1].kind == "done"


@pytest.mark.asyncio
async def test_a_replayed_client_request_id_does_not_start_a_second_turn() -> None:
    """Double click / network retry must not produce two conversations."""
    tid, wid, uid, aid = _owners()
    agent = CatalogAgent.create(
        id=aid,
        tenant_id=tid,
        workspace_id=wid,
        name="t",
        category="test",
        owner="test",
        model="default",
    )
    svc, deps, sid, *_ = await _make_service(
        llm=_RecordingLLM(), agent=agent, owner_id=uid
    )

    async def send(request_id: str) -> None:
        _ = [
            chunk
            async for chunk in svc.stream_turn(
                tenant_id=tid,
                workspace_id=wid,
                owner_id=uid,
                session_id=UUID(sid),
                user_input="hi",
                client_request_id=request_id,
            )
        ]

    await send("req-1")
    with pytest.raises(DuplicateRequestError):
        await send("req-1")
    # 换个 id 就是新一轮 —— 允许.
    await send("req-2")


@pytest.mark.asyncio
async def test_the_first_user_message_becomes_the_session_title() -> None:
    tid, wid, uid, aid = _owners()
    agent = CatalogAgent.create(
        id=aid,
        tenant_id=tid,
        workspace_id=wid,
        name="智能助手",
        category="test",
        owner="test",
        model="default",
    )
    svc, deps, sid, *_ = await _make_service(
        llm=_RecordingLLM(), agent=agent, owner_id=uid
    )

    _ = [
        chunk
        async for chunk in svc.stream_turn(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=uid,
            session_id=UUID(sid),
            user_input="帮我把这份季度报表整理成一页摘要",
        )
    ]
    session = await deps["sessions"].get(UUID(sid))
    assert session is not None
    assert session.metadata["title"] == "帮我把这份季度报表整理成一页摘要"
    assert session.metadata["title_auto"] is False


@pytest.mark.asyncio
async def test_usage_chunk_carries_the_cost_from_the_model_price() -> None:
    tid, wid, uid, aid = _owners()
    agent = CatalogAgent.create(
        id=aid,
        tenant_id=tid,
        workspace_id=wid,
        name="t",
        category="test",
        owner="test",
        model="default",
    )
    deps = make_dependencies()
    messages = _Messages()
    runner = SessionGraphRunner(
        llm=_PricingLLM(), catalog_model_resolver=_PricingResolver()
    )
    journal = InMemorySessionJournal()
    # 把 journal 也放进 deps —— 断言「审批挂起落库」要用 ✓
    deps["journal"] = journal
    # 轮次读仓库读**同一份行** ✓（停旧写后轮次只有一个落点 ✓）。
    deps["turns"] = InMemoryTurnRepository(journal)
    svc = CopilotSessionService(
        sessions=deps["sessions"],
        turns=deps["turns"],
        messages=messages,
        catalog=_Catalog(agent),
        events=deps["events"],
        graph=runner,
        idempotency=IdempotencyGuard(InMemoryIdempotencyStore()),
        journal=journal,
        claim=deps["sessions"].claim,
        turn_runner=make_turn_runner(
            graph=runner,
            journal=journal,
            events=deps["events"],
            messages=messages,
            sessions=deps["sessions"],
        ),
    )
    detail = await svc.create_session(
        tenant_id=tid, workspace_id=wid, owner_id=uid, agent_id=aid
    )
    chunks = [
        chunk
        async for chunk in svc.stream_turn(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=uid,
            session_id=UUID(detail["id"]),
            user_input="hi",
        )
    ]
    usage = [c for c in chunks if c.kind == "usage"]
    assert usage, "usage chunk missing"
    # FakeLLM: input 3 / output 2 tokens; price 2.0 / 4.0 per 1K
    assert usage[-1].cost_usd == round(3 / 1000 * 2.0 + 2 / 1000 * 4.0, 6)


@pytest.mark.asyncio
async def test_double_clicking_approve_executes_the_tool_only_once() -> None:
    """台账 G10 —— 连点两次「同意」, 工具只能被执行一次。

    审批恢复路径必须带幂等键：键由 ``approval_id`` 派生，因此同一次审批的
    重复点击会撞键，而下一次审批（新的 approval_id）不受影响。
    """
    tid, wid, uid, aid = _owners()
    agent = CatalogAgent.create(
        id=aid,
        tenant_id=tid,
        workspace_id=wid,
        name="t",
        category="test",
        owner="test",
        model="default",
    )
    # 目录工具只有在 agent 显式列出时才会进白名单 —— 白名单决定要不要确认.
    agent = replace(agent, tools=[{"name": "danger_tool", "enabled": True}])
    llm = _ScriptedLLM(
        [
            {
                "tool_calls": [
                    {
                        "id": str(uuid4()),
                        "name": "danger_tool",
                        "arguments": {"path": "/"},
                    }
                ]
            },
            {"delta": "已执行。"},
        ]
    )
    tool_port = _CatalogToolPort(
        [
            {
                "name": "danger_tool",
                "description": "高风险操作",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
                "risk": "high",
                "needConfirm": True,
            }
        ]
    )
    svc, _deps, sid, *_ = await _make_service(
        llm=llm, agent=agent, owner_id=uid, tool_port=tool_port
    )

    chunks = [
        chunk
        async for chunk in svc.stream_turn(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=uid,
            session_id=UUID(sid),
            user_input="清理磁盘",
            client_request_id="req-1",
        )
    ]
    approvals = [c for c in chunks if isinstance(c, ApprovalRequiredChunk)]
    assert approvals, [getattr(c, "kind", None) for c in chunks]
    approval_id = approvals[0].approval_id

    async def approve() -> list:
        return [
            chunk
            async for chunk in svc.decide_approval(
                tenant_id=tid,
                workspace_id=wid,
                owner_id=uid,
                session_id=UUID(sid),
                approval_id=approval_id,
                approved=True,
                approval_service=None,
            )
        ]

    first = await approve()
    assert any(getattr(c, "kind", None) == "tool_result" for c in first)
    assert len(tool_port.invoked) == 1

    # 连点第二次「同意」—— 必须被幂等挡下, 工具不得再执行.
    with pytest.raises(DuplicateRequestError):
        await approve()
    assert len(tool_port.invoked) == 1


@pytest.mark.asyncio
async def test_the_pending_approval_is_persisted_on_the_turn() -> None:
    """审批挂起时**落库**（Session 方案 §8 · 决策 #6）✓。

    ⚠️ 只在内存里 = 进程重启后审批永久卡死 ✗✗ —— 落库是恢复的前提 ✓。
    """
    tid, wid, uid, aid = _owners()
    agent = CatalogAgent.create(
        id=aid,
        tenant_id=tid,
        workspace_id=wid,
        name="t",
        category="test",
        owner="test",
        model="default",
    )
    agent = replace(agent, tools=[{"name": "danger_tool", "enabled": True}])
    llm = _ScriptedLLM(
        [
            {
                "tool_calls": [
                    {
                        "id": str(uuid4()),
                        "name": "danger_tool",
                        "arguments": {"path": "/"},
                    }
                ]
            },
            {"delta": "已执行。"},
        ]
    )
    tool_port = _CatalogToolPort(
        [
            {
                "name": "danger_tool",
                "description": "高风险操作",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
                "risk": "high",
                "needConfirm": True,
            }
        ]
    )
    svc, deps, sid, *_ = await _make_service(
        llm=llm, agent=agent, owner_id=uid, tool_port=tool_port
    )

    chunks = [
        chunk
        async for chunk in svc.stream_turn(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=uid,
            session_id=UUID(sid),
            user_input="清理磁盘",
            client_request_id="req-pending",
        )
    ]
    approvals = [c for c in chunks if isinstance(c, ApprovalRequiredChunk)]
    assert approvals, [getattr(c, "kind", None) for c in chunks]

    journal = deps["journal"]
    waiting = [row for row in journal.turns.values() if row.get("pending_approval")]
    assert len(waiting) == 1, journal.turns
    pending = waiting[0]["pending_approval"]
    assert pending["approval_id"] == str(approvals[0].approval_id)
    assert pending["tool_name"] == "danger_tool"
    assert pending["arguments_digest"] == arguments_digest({"path": "/"})
    assert pending["session_id"] == sid
    # 轮次状态也转成「等待」✓（由轮次表说了算）
    assert waiting[0]["status"] == "waiting"


@pytest.mark.asyncio
async def test_changed_tool_arguments_block_the_approval() -> None:
    """参数被改过 → **不执行工具**，明确错误码 ✓（Session 方案 §8 校验 5）。

    ⚠️ 比对的是「**审批记录里的参数**」（治理域的权威）—— 不是前端传回来的
    参数（那个能被改 ✗✗）。
    """
    tid, wid, uid, aid = _owners()
    agent = CatalogAgent.create(
        id=aid,
        tenant_id=tid,
        workspace_id=wid,
        name="t",
        category="test",
        owner="test",
        model="default",
    )
    agent = replace(agent, tools=[{"name": "danger_tool", "enabled": True}])
    llm = _ScriptedLLM(
        [
            {
                "tool_calls": [
                    {
                        "id": str(uuid4()),
                        "name": "danger_tool",
                        "arguments": {"path": "/"},
                    }
                ]
            },
            {"delta": "已执行。"},
        ]
    )
    tool_port = _CatalogToolPort(
        [
            {
                "name": "danger_tool",
                "description": "高风险操作",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
                "risk": "high",
                "needConfirm": True,
            }
        ]
    )
    svc, _deps, sid, *_ = await _make_service(
        llm=llm, agent=agent, owner_id=uid, tool_port=tool_port
    )

    chunks = [
        chunk
        async for chunk in svc.stream_turn(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=uid,
            session_id=UUID(sid),
            user_input="清理磁盘",
            client_request_id="req-tampered",
        )
    ]
    approvals = [c for c in chunks if isinstance(c, ApprovalRequiredChunk)]
    assert approvals, [getattr(c, "kind", None) for c in chunks]
    approval_id = approvals[0].approval_id

    class _Approval:
        status = "pending"
        expires_at = datetime.now(UTC) + timedelta(hours=1)
        # 参数与挂起时**不同** —— 模拟「审批记录里的参数被改过」
        resource = {"tool": "danger_tool", "arguments": {"path": "/etc/passwd"}}

    class _ApprovalService:
        async def get(self, *, tenant_id, approval_id):  # type: ignore[no-untyped-def]
            return _Approval()

        async def approve(self, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("参数被改过就不该批准")

    with pytest.raises(ValidationError) as excinfo:
        async for _ in svc.decide_approval(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=uid,
            session_id=UUID(sid),
            approval_id=approval_id,
            approved=True,
            approval_service=_ApprovalService(),
        ):
            pass
    assert excinfo.value.code == "TOOL_ARGUMENT_INVALID"
    assert not tool_port.invoked, "参数被改过却执行了工具 ✗✗"


@pytest.mark.asyncio
async def test_two_identical_messages_without_a_client_request_id_both_run() -> None:
    """决策 #5 —— weak 键不抑制：连发两条「好的」必须两轮都跑。

    没有 ``clientRequestId`` 时降级为内容指纹（weak）：指纹会撞，但 weak **只记录、
    不判重** —— 否则用户连发两条相同内容的消息会被静默吃掉一条。
    """
    tid, wid, uid, aid = _owners()
    agent = CatalogAgent.create(
        id=aid,
        tenant_id=tid,
        workspace_id=wid,
        name="t",
        category="test",
        owner="test",
        model="default",
    )
    svc, _deps, sid, *_ = await _make_service(
        llm=_RecordingLLM(), agent=agent, owner_id=uid
    )

    async def send() -> list:
        return [
            chunk
            async for chunk in svc.stream_turn(
                tenant_id=tid,
                workspace_id=wid,
                owner_id=uid,
                session_id=UUID(sid),
                user_input="好的",
            )
        ]

    first = await send()
    second = await send()
    assert first[-1].kind == "done"
    assert second[-1].kind == "done"


async def test_a_known_error_code_is_projected_into_the_web_copy() -> None:
    """web 投放面：错误码已知 → 气泡里是**投影文案**，不是技术细节。

    ⚠️ 轮次行里存的仍是技术细节（`str(exc)`）—— 那是给日志/运维看的 ✓；
    气泡给用户看的是人话 ✓。
    """
    from qzdap_kernel.errors import ExternalServiceError
    from qzdap_schema.dtos.errors import ErrorCode, project_error

    tid, wid, uid = TenantId(uuid4()), WorkspaceId(uuid4()), UserId(uuid4())
    agent = CatalogAgent.create(
        id=AgentId(uuid4()),
        tenant_id=tid,
        workspace_id=wid,
        name="t",
        category="test",
        owner="test",
        model="default",
    )
    svc, deps, sid, *_ = await _make_service(
        llm=_DomainErrorLLM(ExternalServiceError()), agent=agent, owner_id=uid
    )

    chunks = [
        chunk
        async for chunk in svc.stream_turn(
            tenant_id=tid,
            workspace_id=wid,
            owner_id=uid,
            session_id=UUID(sid),
            user_input="hi",
        )
    ]

    assert chunks[-1].kind == "error"
    assert chunks[-1].message == project_error(ErrorCode.EXTERNAL_SERVICE_ERROR, "web")
    # 轮次行里留的仍是技术细节（运维看这个）。
    turn = await deps["turns"].latest_for_session(UUID(sid))
    assert turn is not None
    assert turn.error_code == "TURN_FAILED"
