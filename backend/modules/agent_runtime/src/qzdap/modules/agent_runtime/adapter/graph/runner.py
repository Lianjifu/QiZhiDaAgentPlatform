"""Session-layer graph: load → recall/retrieve → compact → ReAct loop → remember."""

from __future__ import annotations

import logging
import sys as _sys
from collections.abc import AsyncGenerator
from contextlib import aclosing
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

from opentelemetry import trace as _trace
from qzdap_agent_runtime.context.compressor import (
    DEFAULT_WINDOW,
    CompactionOutcome,
    ContextCompressor,
)
from qzdap_agent_runtime.context.persistence import ContextManifestStore
from qzdap_agent_runtime.context.tokens import estimate_tokens as estimate_text_tokens
from qzdap_agent_runtime.context.types import AssembledContext, ManifestEntry
from qzdap_observability.metrics import record_legacy_call, record_new_call
from qzdap_observability.tracing import get_tracer
from qzdap_schema.dtos.turn import (
    ApprovalRequiredChunk,
    ArtifactReadyChunk,
    AttachmentReadyChunk,
    ContextCompactedChunk,
    DoneChunk,
    InteractiveActionChunk,
    KnowledgeSearchChunk,
    MemoryWriteChunk,
    MessageChunk,
    PlanProposedChunk,
    SkillInvocationChunk,
    ToolCallChunk,
    ToolResultChunk,
    TurnChunk,
    UsageChunk,
    WorkflowInvocationChunk,
)
from qzdap_schema.ids import ModelId
from qzdap_vault.actor import ActorContext

from qzdap.modules.agent_runtime.adapter.context.summary_adapter import (
    LLMSummaryAdapter,
)
from qzdap.modules.agent_runtime.adapter.graph.chat_model import stream_chat
from qzdap.modules.agent_runtime.adapter.graph.loop import (
    HARD_MAX_STEPS,
    apply_stall_guard,
    compile_loop_graph,
    next_route,
)
from qzdap.modules.agent_runtime.adapter.graph.state import LoopState, estimate_tokens
from qzdap.modules.agent_runtime.adapter.graph.tools import (
    execute_tool,
    needs_confirm,
    parse_arguments,
    result_text,
)
from qzdap.modules.agent_runtime.application.ports import (
    CatalogModelResolver,
    KnowledgePort,
    LLMPort,
    MemoryPort,
    SandboxPort,
    SkillPort,
    ToolPort,
)
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent

_tracer = get_tracer("qzdap.agent_runtime")
_log = logging.getLogger(__name__)


class SessionGraphRunner:
    def __init__(
        self,
        *,
        llm: LLMPort,
        skill_port: SkillPort | None = None,
        sandbox_port: SandboxPort | None = None,
        tool_port: ToolPort | None = None,
        memory_port: MemoryPort | None = None,
        knowledge_port: KnowledgePort | None = None,
        approval_factory: Any | None = None,
        # ⚠️ **manifest 的落库口** ✓（Context Stage 4 ✓）—— 每次模型调用
        # 一条 ✓（§5.1.1 ✓）。⚠️ **没有它就不落库** ✓（测试里没有库 ✓）。
        context_manifest_store: ContextManifestStore | None = None,
        # Phase 1.5: agent.model (str) → ModelId (UUID) 解析器.
        # 让前端 chat (无 body.model) 也能在 graph 里查 admin_models.
        catalog_model_resolver: CatalogModelResolver | None = None,
    ) -> None:
        self._llm = llm
        self._skill_port = skill_port
        self._sandbox_port = sandbox_port
        self._tool_port = tool_port
        self._memory_port = memory_port
        self._knowledge_port = knowledge_port
        self._approval_factory = approval_factory
        self._catalog_model_resolver = catalog_model_resolver
        self._context_manifest_store = context_manifest_store
        record_legacy_call("X5")  # 占位图 compile_loop_graph
        self._graph = compile_loop_graph(llm_node=_passthrough_llm, tools_node=_passthrough_tools)
        self.last_loop_state: dict[str, Any] = {}

    def bind_ports(
        self,
        *,
        skill_port: SkillPort | None = None,
        sandbox_port: SandboxPort | None = None,
        tool_port: ToolPort | None = None,
    ) -> None:
        """Re-bind request-scoped ports.

        Tenant / workspace / owner are only known per request, so the
        HTTP layer replaces the ports it can scope before the turn runs.
        """
        if skill_port is not None:
            self._skill_port = skill_port
        if sandbox_port is not None:
            self._sandbox_port = sandbox_port
        if tool_port is not None:
            self._tool_port = tool_port

    async def run_turn(
        self, *, parent_span_context: Any = None, **kwargs: Any
    ) -> AsyncGenerator[TurnChunk, None]:
        """Run one turn under an ``agent.turn`` span.

        The span is the parent of the per-LLM-call and per-tool-call spans,
        so a turn reads as one trace in the APM. ``parent_span_context`` lets
        the HTTP layer put this span under the request span.
        """
        # 注意: 不能用 start_as_current_span —— 它靠 ContextVar 的 token 复位,
        # 而异步生成器的每次恢复可能跑在不同的 Context 里, 退出时会抛
        # "created in a different Context". 这里用显式的 parent/child.
        span = _tracer.start_span("agent.turn", context=parent_span_context)
        span.set_attribute("agent.tenant_id", str(kwargs.get("tenant_id")))
        span.set_attribute("agent.workspace_id", str(kwargs.get("workspace_id")))
        span.set_attribute("agent.session_id", str(kwargs.get("session_id")))
        span.set_attribute("agent.turn_id", str(kwargs.get("turn_id")))
        span.set_attribute("agent.model", str(kwargs.get("model")))
        span.set_attribute("agent.agent_id", str(getattr(kwargs.get("agent"), "id", "")))
        child_ctx = _trace.set_span_in_context(span)
        tools = 0
        try:
            async with aclosing(self._run_turn_inner(span_ctx=child_ctx, **kwargs)) as inner:
                async for chunk in inner:
                    if getattr(chunk, "kind", None) == "tool_call":
                        tools += 1
                    yield chunk
        except Exception:
            span.set_status(_trace.Status(_trace.StatusCode.ERROR))
            span.record_exception(_sys.exc_info()[1])  # type: ignore[arg-type]
            raise
        finally:
            span.set_attribute("agent.tool_calls", tools)
            span.end()

    async def _run_turn_inner(
        self,
        *,
        span_ctx: Any = None,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        turn_id: UUID,
        user_input: str,
        history: list[dict[str, Any]],
        agent: CatalogAgent | None,
        model: str,
        context_window: int = DEFAULT_WINDOW,
        rolling_summary: str = "",
        resume: dict[str, Any] | None = None,
        # Phase 12: 策略路由 ID (UUID). 优先于 model — 走 Phase 7 select_chain_for_strategy.
        route_id: ModelId | None = None,
        # Phase 14: 父 session id. delegate_to_agent 工具需要用它 spawn sub-session.
        # 默认 None — 测试 / 评估场景没有父 session.
        session_id: UUID | None = None,
    ) -> AsyncGenerator[TurnChunk, None]:
        record_legacy_call("X17")  # 旧路径的手写推理循环
        seq = 0
        max_steps = 8
        if agent is not None:
            max_steps = max(1, min(int(agent.max_steps), HARD_MAX_STEPS))
            if agent.model and not model:
                model = agent.model

        # ⚠️ **actor 只建一次** ✓ —— 摘要调用与主对话调用**同一个身份** ✓
        # （摘要也是一次模型调用 ✗ —— 用别人的身份调模型不行 ✗✗）。
        actor = ActorContext(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            principal_id=owner_id,
        )

        whitelist = await self._whitelist(agent)
        tools_schema = _openai_tools(whitelist)
        # ⚠️ **走新的 ContextBuilder** ✓（A-26 ✓）—— 旧的上下文组装
        # **已删除** ✓（Context Stage 5 ✓ —— 台账 X8 ✓）。
        assembled, knowledge_hits = await self._assemble_context(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            user_input=user_input,
            history=history,
            agent=agent,
        )
        if knowledge_hits:
            seq += 1
            yield KnowledgeSearchChunk(
                turn_id=turn_id,
                seq=seq,
                query=user_input,
                hits=[
                    {
                        "id": str(item.get("id") or ""),
                        "title": str(item.get("asset_name") or item.get("package_name") or ""),
                        "snippet": str(item.get("content") or "")[:200],
                        "score": float(item.get("score") or 0.0),
                    }
                    for item in knowledge_hits
                ],
                citations=[
                    str(item.get("package_name") or "")
                    for item in knowledge_hits
                    if item.get("package_name")
                ],
                degraded=False,
            )
        # ⚠️ **走新的 Compressor** ✓（Context Stage 4 ✓）—— 旧的
        # `compact_messages` 从此没有调用方 ✓（删它归 Context Stage 5 ✓，
        # 台账 X9 ✓）。
        outcome = await self._compact(
            messages=list(assembled.messages),
            rolling_summary=rolling_summary,
            context_window=context_window,
            model=model,
            actor=actor,
        )
        messages = list(outcome.messages)
        rolling_summary = outcome.summary
        did_compact = _did_compact(outcome)
        if did_compact:
            seq += 1
            yield ContextCompactedChunk(
                turn_id=turn_id,
                seq=seq,
                # ⚠️ **压缩前的真实 token 数** ✓ —— 之前写死 0 ✗✗（事件里的
                # 「压缩了多少」永远是 0 ✓ → 排查时看不到效果 ✓）。
                tokens_before=outcome.tokens_before,
                tokens_after=outcome.tokens_after,
                # ⚠️ **降级可见** ✓（Context 方案 §4.5 ✓）—— 摘要模型挂了
                # 走确定性窗口时前端能看见 ✓。
                degraded=outcome.degraded,
            )

        state: LoopState = {
            "messages": messages,
            "step": 0,
            "max_steps": max_steps,
            "todos": [],
            "pending_approval": None,
            "last_tool_sig": "",
            "stall_count": 0,
            "final": "",
            "compacted": did_compact,
            "tokens_est": estimate_tokens(messages),
        }
        if resume:
            state = {**state, **resume}
            pending = state.get("pending_approval")
            if pending and pending.get("decision") == "approved":
                extra, state = await self._finish_pending(
                    state, pending, turn_id, seq, whitelist,
                    session_id=session_id,
                )
                for chunk in extra:
                    seq = chunk.seq
                    yield chunk
            elif pending and pending.get("decision") == "denied":
                seq += 1
                denied = {
                    "role": "tool",
                    "name": pending.get("tool_name"),
                    "tool_call_id": pending.get("tool_call_id"),
                    "content": "SKILL_DENIED",
                }
                state["messages"] = list(state.get("messages") or []) + [denied]
                state["pending_approval"] = None
                yield ToolResultChunk(
                    turn_id=turn_id,
                    seq=seq,
                    tool_call_id=UUID(str(pending.get("call_id") or uuid4())),
                    output="SKILL_DENIED",
                    is_error=True,
                    latency_ms=0,
                )

        input_tokens = 0
        output_tokens = 0
        cost_usd = 0.0
        while True:
            # ⚠️ **每次模型调用前压缩** ✓ —— ReAct 里工具结果会不断进上下文
            # ✓（不压就会撞窗口 ✗）。⚠️ **同一个 Compressor** ✓（不是第二套
            # 实现 ✗✗）。
            outcome = await self._compact(
                messages=list(state.get("messages") or []),
                rolling_summary=rolling_summary,
                context_window=context_window,
                model=model,
                actor=actor,
            )
            messages = list(outcome.messages)
            rolling_summary = outcome.summary
            state["messages"] = messages
            if _did_compact(outcome):
                seq += 1
                yield ContextCompactedChunk(
                    turn_id=turn_id,
                    seq=seq,
                    # ⚠️ **不再恒为 0** ✓（环外那一处早就修了 ✗ —— 环内这处
                    # 漏了 ✗✗ → 事件里「压缩了多少」永远是 0 ✓）。
                    tokens_before=outcome.tokens_before,
                    tokens_after=outcome.tokens_after,
                    degraded=outcome.degraded,
                )

            # ⚠️ **manifest 先于模型落库** ✓（Context 方案 §5.2 ✓）——
            # 模型已经回答了却查不到那次的组成 ✗✗（审计与评测失去依据 ✗）。
            await self._save_manifest(
                assembled=assembled,
                messages=messages,
                turn_id=turn_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                session_id=session_id,
                step=int(state.get("step") or 0),
                compaction_degraded=outcome.degraded,
            )
            chat_stream = stream_chat(
                self._llm,
                model=model or "default",
                messages=list(state["messages"]),
                tools=tools_schema,
                model_id=ModelId(UUID(model)) if _looks_uuid(model) else None,
                # Phase 12: 策略路由. 当 route_id 提供时, 优先用它走 Phase 7.
                route_id=route_id,
                actor=actor,
                # Phase 1.5: 走 graph 路径时, 让 stream_chat 在 model 是 str 时也 resolve.
                resolve_model_id=(
                    self._catalog_model_resolver.resolve
                    if self._catalog_model_resolver is not None
                    else None
                ),
                resolve_tenant_id=tenant_id,
                resolve_workspace_id=workspace_id,
            )
            assistant: dict[str, Any] | None = None
            llm_span = _tracer.start_span("agent.llm", context=span_ctx)
            llm_span.set_attribute("llm.model", model)
            try:
                async with aclosing(chat_stream):
                    async for event in chat_stream:
                        if isinstance(event, str):
                            seq += 1
                            yield MessageChunk(turn_id=turn_id, seq=seq, content=event)
                        else:
                            assistant = event
            except Exception:
                llm_span.set_status(_trace.Status(_trace.StatusCode.ERROR))
                raise
            finally:
                llm_span.end()
            if assistant is None:
                raise RuntimeError("LLM stream ended without an assistant message")
            resolved_model_id = str(assistant.get("model_id") or "")

            # Round-7: LLM side-channel 注入 plan / artifact / workflow 事件.
            # 真 LLM 默认 []; mock LLM 按触发词返回 chunk dicts.
            synth = await self._llm.synthetic_chunks(user_input, turn_id=turn_id)
            for raw in synth:
                chunk = _build_synthetic_chunk(raw, turn_id=turn_id, seq=seq + 1)
                if chunk is None:
                    continue
                seq += 1
                yield chunk
            usage = assistant.get("usage") or {}
            step_input = int(usage.get("input_tokens") or 0)
            step_output = int(usage.get("output_tokens") or 0)
            input_tokens += step_input
            output_tokens += step_output
            step_cost = await self._price_of(
                resolved_model_id=resolved_model_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                input_tokens=step_input,
                output_tokens=step_output,
            )
            cost_usd += step_cost

            state["messages"] = list(state["messages"]) + [assistant]
            state["step"] = int(state.get("step") or 0) + 1
            state["final"] = str(assistant.get("content") or state.get("final") or "")
            state = apply_stall_guard(state, list(assistant.get("tool_calls") or []))
            if next_route(state) != "tools" or int(state.get("stall_count") or 0) >= 2:
                break

            interrupt_chunk = None
            new_messages = list(state["messages"])
            for call in assistant.get("tool_calls") or []:
                name = str(call.get("name") or (call.get("function") or {}).get("name") or "")
                arguments = parse_arguments(
                    call.get("arguments") or (call.get("function") or {}).get("arguments")
                )
                call_uuid = _as_uuid(call.get("id"))
                seq += 1
                yield ToolCallChunk(
                    turn_id=turn_id,
                    seq=seq,
                    tool_call_id=call_uuid,
                    tool_name=name,
                    arguments=arguments,
                )
                meta = whitelist.get(name) or {}
                if needs_confirm(name, tool_meta=meta) and (resume or {}).get("decision") != "approved":
                    approval_id = await self._request_approval(
                        tenant_id=tenant_id,
                        owner_id=owner_id,
                        tool_name=name,
                        arguments=arguments,
                    )
                    state["pending_approval"] = {
                        "approval_id": str(approval_id),
                        "tool_name": name,
                        "arguments": arguments,
                        "tool_call_id": str(call.get("id") or call_uuid),
                        "call_id": str(call_uuid),
                    }
                    seq += 1
                    interrupt_chunk = ApprovalRequiredChunk(
                        turn_id=turn_id,
                        seq=seq,
                        approval_id=approval_id,
                        tool_name=name,
                        arguments=arguments,
                        reason="高风险操作需要确认后才会执行",
                    )
                    break
                # Phase 14: 把 parent session_id 注入 delegate_to_agent 的 arguments,
                # 让 stub tool 知道在哪个 session 上 spawn sub-session.
                tool_arguments = dict(arguments)
                if name == "delegate_to_agent" and session_id is not None:
                    tool_arguments.setdefault("parent_session_id", str(session_id))
                is_skill = meta.get("kind") == "skill"
                if is_skill:
                    seq += 1
                    yield SkillInvocationChunk(
                        turn_id=turn_id,
                        seq=seq,
                        invocation_id=call_uuid,
                        skill_name=name,
                        status="started",
                        tool_call_id=call_uuid,
                    )
                tool_span = _tracer.start_span("agent.tool", context=span_ctx)
                tool_span.set_attribute("tool.name", name)
                tool_started = monotonic()
                try:
                    result = await execute_tool(
                        name=name,
                        arguments=tool_arguments,
                        skill_port=self._skill_port,
                        sandbox_port=self._sandbox_port,
                        tool_port=self._tool_port,
                        confirmed=False,
                    )
                    tool_span.set_attribute("tool.ok", result.get("ok") is not False)
                except Exception:
                    tool_span.set_status(_trace.Status(_trace.StatusCode.ERROR))
                    raise
                finally:
                    tool_span.set_attribute(
                        "tool.latency_ms", int((monotonic() - tool_started) * 1000)
                    )
                    tool_span.end()
                if is_skill:
                    seq += 1
                    yield SkillInvocationChunk(
                        turn_id=turn_id,
                        seq=seq,
                        invocation_id=call_uuid,
                        skill_name=name,
                        status="failed" if result.get("ok") is False else "succeeded",
                        tool_call_id=call_uuid,
                    )
                text = result_text(result)
                new_messages.append(
                    {
                        "role": "tool",
                        "name": name,
                        "tool_call_id": str(call.get("id") or call_uuid),
                        "content": text,
                    }
                )
                seq += 1
                yield ToolResultChunk(
                    turn_id=turn_id,
                    seq=seq,
                    tool_call_id=call_uuid,
                    output=text,
                    is_error=result.get("ok") is False,
                    latency_ms=int(result.get("latency_ms") or 0),
                )
            if interrupt_chunk is not None:
                self.last_loop_state = dict(state)
                yield interrupt_chunk
                return
            state["messages"] = new_messages

        self.last_loop_state = {**dict(state), "pending_approval": None, "rolling_summary": rolling_summary}
        final = str(state.get("final") or "")
        # ⚠️ **摘要写新列** ✓（Context 方案 §5.1 ✓）—— 旧的
        # `metadata['rolling_summary']` 是**旧副本** ✓（它的写入点归零 ✓
        # —— 清理归 Context Stage 5 ✓）。
        await self._save_rolling_summary(
            tenant_id=tenant_id,
            session_id=session_id,
            summary=rolling_summary,
        )
        # ⚠️ **走新的 Writer** ✓（A-26 ✓）—— 旧的 `_remember` 从此没有
        # 调用方 ✓（删它归 Memory Stage 7 ✓）。
        writes = await self._write_memories(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            agent=agent,
            user_input=user_input,
            final=final,
            session_id=session_id,
            turn_id=turn_id,
        )
        for layer, preview in writes:
            seq += 1
            yield MemoryWriteChunk(turn_id=turn_id, seq=seq, layer=layer, preview=preview)
        seq += 1
        yield UsageChunk(
            turn_id=turn_id,
            seq=seq,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=0,
            cache_write_tokens=0,
            cost_usd=round(cost_usd, 6),
        )
        seq += 1
        yield DoneChunk(turn_id=turn_id, seq=seq, final_message=final)
        _ = (self._graph, rolling_summary)

    def export_loop_state(self, pending: dict[str, Any] | None, messages: list[dict[str, Any]], step: int) -> dict[str, Any]:
        return {"pending_approval": pending, "messages": messages, "step": step}

    async def _assemble_context(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        user_input: str,
        history: list[dict[str, Any]],
        agent: CatalogAgent | None,
    ) -> tuple[AssembledContext, list[dict[str, Any]]]:
        """**用新的 ContextBuilder 装配上下文** ✓（Agent Stage 5 · A-26 ✓）。

        返回 ``(装配结果, 知识召回原始结果)`` ✓ —— 后者给 `knowledge_search`
        事件用 ✓（不必再召回一次 ✗✗）；前者带着 **manifest** ✓（落库用 ✓）。
        """
        from qzdap_agent_runtime.context.builder import ContextBuilder

        builder = ContextBuilder(
            memory_port=self._memory_port,
            knowledge_port=self._knowledge_port,
        )
        assembled = await builder.build(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            user_input=user_input,
            history=history,
            agent_prompts=dict(agent.prompts) if agent is not None else {},
            agent_version=agent.version if agent is not None else None,
            tenant_context={
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
                "user_id": str(owner_id),
            },
            # ⚠️ **agent 的知识库绑定要传下去** ✓ —— 漏了就是「agent 绑了
            # 哪些知识库」这条约束**失效** ✗✗（旧路径按 `knowledge_refs`
            # 过滤 ✓）。
            knowledge_package_ids=_knowledge_package_ids(agent),
        )
        knowledge = list(assembled.recalled.get("knowledge") or [])
        memories = list(assembled.recalled.get("memory") or [])
        record_new_call("X8")  # 新的上下文组装已接管
        if memories:
            # ⚠️ **X15 的打点跟着搬家** ✓ —— L3 内容进「相关记忆」、knowledge
            # 另进「相关知识」→ **运行时双份注入** ✗（决策 #1 归 Memory
            # Stage 7 ✓）。⚠️ **旧路径是「有记忆就记」** ✓ —— 口径保持一致
            # ✓（否则指标中途变义 ✗✗）。
            record_legacy_call("X15")
        return assembled, knowledge

    async def _save_rolling_summary(
        self,
        *,
        tenant_id: UUID,
        session_id: UUID | None,
        summary: str,
    ) -> None:
        """**摘要写进 `agent_sessions.rolling_summary`** ✓（§5.1 ✓）。

        ⚠️ **新写入只走这一列** ✓ —— 旧副本（``metadata`` 里的那个 ✓）**不再
        写** ✓（Context Stage 5 删残留 ✓）。
        """
        store = self._context_manifest_store
        if store is None or session_id is None:
            return
        await store.save_rolling_summary(
            tenant_id=tenant_id,
            session_id=session_id,
            summary=summary,
        )

    async def _save_manifest(
        self,
        *,
        assembled: AssembledContext,
        messages: list[dict[str, Any]],
        turn_id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        session_id: UUID | None,
        step: int,
        compaction_degraded: bool,
    ) -> None:
        """**每次模型调用落一条 manifest** ✓（Context 方案 §5.1.1 ✓）。

        ⚠️ **没有落库口就不落** ✓（测试与纯内存场景 ✓）。
        ⚠️ **落库失败就让这一轮失败** ✓ —— 「模型已回答但查不到上下文」
        比「这一轮失败」更糟 ✗✗（审计就失去依据了 ✗）。
        """
        store = self._context_manifest_store
        if store is None or session_id is None:
            return
        payload = self._manifest_payload(
            assembled=assembled, messages=messages
        )
        degraded = {
            "recall_degraded": bool(
                assembled.degraded_flags.get("recall_degraded")
            ),
            "compaction_degraded": bool(compaction_degraded),
        }
        await store.save_manifest(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            session_id=session_id,
            turn_id=turn_id,
            step=step,
            manifest=payload,
            tokens_total=int(payload.get("total_tokens") or 0),
            degraded=degraded,
        )

    @staticmethod
    def _manifest_payload(
        *,
        assembled: AssembledContext,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """这一轮**真正喂给模型**的上下文清单 ✓。

        ⚠️ **按「消息对象身份」对齐** ✓ —— 压缩后留下的消息**还是那些对象**
        ✓（Compressor 复用原对象 ✓）→ 能对上 Builder 的条目 ✓（来源 /
        ``ref_id`` / ``score`` 都在 ✓）；对不上的是**后来加的消息**（工具
        结果 / 助手回复 ✓）→ 现算一条 ✓（来源标 ``tool_result`` ✓）。
        """
        base: dict[int, ManifestEntry] = {}
        for message, entry in zip(assembled.messages, assembled.manifest.entries):
            base[id(message)] = entry
        entries: list[dict[str, Any]] = []
        for message in messages:
            entry = base.get(id(message))
            if entry is not None:
                entries.append(_entry_to_dict(entry))
                continue
            content = str(message.get("content") or "")
            role = str(message.get("role") or "")
            if role == "system" and content.startswith("更早轮次摘要："):
                source = "summary"
            elif role == "tool":
                source = "tool_result"
            else:
                source = "recent"
            entries.append(
                {
                    "source": source,
                    "tokens": estimate_text_tokens(content),
                    "filtered_reason": None,
                    "version": None,
                    "ref_id": None,
                    "score": None,
                    "degraded": False,
                }
            )
        return {
            "total_tokens": sum(int(item["tokens"]) for item in entries),
            "entries": entries,
        }

    async def _compact(
        self,
        *,
        messages: list[dict[str, Any]],
        rolling_summary: str,
        context_window: int,
        model: str,
        actor: ActorContext,
    ) -> CompactionOutcome:
        """**用新的 Compressor 压缩上下文** ✓（Context Stage 4 ✓）。

        ⚠️ **旧的 `compact_messages` 从此没有调用方** ✓ —— 它归 Context
        Stage 5 删除 ✓（台账 X9 ✓）。

        ⚠️ **摘要模型失败就降级** ✓（契约层的 Compressor 负责 ✓）—— 这里
        **不吞异常** ✗（吞了就没人知道降级了 ✗✗）。
        """
        compressor = ContextCompressor(
            summary_model=LLMSummaryAdapter(
                self._llm,
                model=model,
                actor=actor,
                model_id=ModelId(UUID(model)) if _looks_uuid(model) else None,
            ),
            context_window=context_window,
        )
        outcome = await compressor.compact(
            messages=messages,
            existing_summary=rolling_summary,
        )
        record_new_call("X9")  # 新的上下文压缩已接管
        return outcome

    async def _price_of(
        self,
        *,
        resolved_model_id: str,
        tenant_id: UUID,
        workspace_id: UUID,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Cost of one LLM call, in the model's own currency units.

        Prices live on the model catalog row (``price_in`` / ``price_out``,
        per 1K tokens). Unknown model → 0, never an error: cost accounting
        must not break a conversation.
        """
        if not resolved_model_id or self._catalog_model_resolver is None:
            return 0.0
        try:
            prices = await self._catalog_model_resolver.price_of(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                model_id=ModelId(UUID(resolved_model_id)),
            )
        except (RuntimeError, OSError, ValueError) as exc:  # defensive
            _log.warning("model price lookup failed: %s", exc)
            return 0.0
        if not prices:
            return 0.0
        price_in, price_out = prices
        return (input_tokens / 1000.0) * float(price_in) + (
            output_tokens / 1000.0
        ) * float(price_out)

    async def _whitelist(self, agent: CatalogAgent | None) -> dict[str, dict[str, Any]]:
        """Tools the model may call.

        ``sandbox_exec`` is always available. Skills follow the existing
        rule: when the agent doesn't pin a tool list, every executable
        skill is offered. Catalog tools (the built-in set) are only
        offered when the agent explicitly lists them — otherwise every
        agent would silently gain network/filesystem reach.
        """
        allowed: dict[str, dict[str, Any]] = {
            "sandbox_exec": {
                "name": "sandbox_exec",
                "needConfirm": True,
                "risk": "high",
                "kind": "sandbox",
            }
        }
        if self._skill_port is not None:
            try:
                for item in await self._skill_port.list_executable():
                    allowed[str(item.get("name"))] = {**item, "kind": "skill"}
            except Exception:  # noqa: BLE001
                pass
        catalog: dict[str, dict[str, Any]] = {}
        if self._tool_port is not None:
            try:
                for item in await self._tool_port.list_tools():
                    name = str(item.get("name") or "")
                    if name:
                        catalog[name] = {**item, "kind": "tool"}
            except Exception:  # noqa: BLE001
                catalog = {}
        if agent is None:
            return allowed
        named = {str(tool.get("name")) for tool in agent.tools if tool.get("enabled", True)}
        if not named:
            return allowed
        named.add("sandbox_exec")
        selected = {key: value for key, value in allowed.items() if key in named}
        selected.update({key: value for key, value in catalog.items() if key in named})
        return selected

    async def _request_approval(
        self,
        *,
        tenant_id: UUID,
        owner_id: UUID,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> UUID:
        if self._approval_factory is None:
            return uuid4()
        from qzdap_schema.ids import TenantId, UserId

        svc = self._approval_factory
        approval = await svc.create(
            tenant_id=TenantId(tenant_id),
            requester_id=UserId(owner_id),
            action=f"agent.tool.{tool_name}",
            resource={"tool": tool_name, "arguments": arguments, "owner_id": str(owner_id)},
        )
        return UUID(str(approval.id))

    async def _write_memories(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        agent: CatalogAgent | None,
        user_input: str,
        final: str,
        session_id: UUID | None = None,
        turn_id: UUID | None = None,
    ) -> list[tuple[str, str]]:
        """**用新的 Writer 沉淀记忆** ✓（Agent Stage 5 · A-26 ✓）。

        ⚠️ **旧的 `_remember` 从此没有调用方了** ✓ —— 它归 Memory Stage 7
        删除 ✓（台账 X11 ✓）。

        ⚠️ **输入只有本轮对话** ✓（**不含召回结果** ✓ —— Memory 方案 §4.6 ✓）。
        """
        policy = (
            dict(agent.memory_policy)
            if agent is not None
            else {"enabled": True}
        )
        if not policy.get("enabled", True) or self._memory_port is None:
            return []
        if not user_input.strip() and not final.strip():
            return []
        result = await self._memory_port.write_turn(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=owner_id,
            session_id=session_id or uuid4(),
            turn_id=turn_id,
            user_input=user_input,
            assistant_reply=final,
        )
        written = int(result.get("written") or 0)
        if not written:
            return []
        # ⚠️ **只报一层** ✓ —— 新 Writer 写的是 L2 ✓（旧的 L1/L2 两层报法是
        # L1 缓冲表的产物 ✓，那张表要退役 ✓）。
        return [("l2", final[:80])]

    async def _remember(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        agent: CatalogAgent | None,
        user_input: str,
        final: str,
    ) -> list[tuple[str, str]]:
        record_legacy_call("X11")  # 旧记忆写入 _remember
        policy = dict(agent.memory_policy) if agent is not None else {"enabled": True, "autoSummarize": True}
        if not policy.get("enabled", True) or self._memory_port is None or not final.strip():
            return []
        content = f"用户：{user_input}\n助手：{final}"
        meta: dict[str, Any] = {
            "scope": policy.get("scope") or "user",
            "agentName": agent.name if agent else "助手",
            "key": "会话事实",
            "category": "fact",
        }
        await self._memory_port.write(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            content=content[:4000],
            metadata=meta,
        )
        out: list[tuple[str, str]] = [("l1", final[:80])]
        if policy.get("autoSummarize"):
            out.append(("l2", final[:80]))
        return out

    async def _finish_pending(
        self,
        state: LoopState,
        pending: dict[str, Any],
        turn_id: UUID,
        seq: int,
        whitelist: dict[str, dict[str, Any]],
        *,
        session_id: UUID | None = None,
    ) -> tuple[list[Any], LoopState]:
        _ = whitelist
        pending_tool = str(pending.get("tool_name"))
        pending_args = dict(pending.get("arguments") or {})
        # Phase 14: 同上, 把 parent session_id 注入 delegate_to_agent.
        if pending_tool == "delegate_to_agent" and session_id is not None:
            pending_args.setdefault("parent_session_id", str(session_id))
        pending_meta = whitelist.get(pending_tool) or {}
        is_skill = pending_meta.get("kind") == "skill"
        out: list[Any] = []
        if is_skill:
            call_id = _as_uuid(pending.get("call_id"))
            out.append(
                SkillInvocationChunk(
                    turn_id=turn_id,
                    seq=seq + 1,
                    invocation_id=call_id,
                    skill_name=pending_tool,
                    status="started",
                    tool_call_id=call_id,
                )
            )
        result = await execute_tool(
            name=pending_tool,
            arguments=pending_args,
            skill_port=self._skill_port,
            sandbox_port=self._sandbox_port,
            tool_port=self._tool_port,
            confirmed=True,
        )
        if is_skill:
            call_id = _as_uuid(pending.get("call_id"))
            out.append(
                SkillInvocationChunk(
                    turn_id=turn_id,
                    seq=seq + 2,
                    invocation_id=call_id,
                    skill_name=pending_tool,
                    status="failed" if result.get("ok") is False else "succeeded",
                    tool_call_id=call_id,
                )
            )
        text = result_text(result)
        messages = list(state.get("messages") or [])
        messages.append(
            {
                "role": "tool",
                "name": pending.get("tool_name"),
                "tool_call_id": pending.get("tool_call_id"),
                "content": text,
            }
        )
        state = {**state, "messages": messages, "pending_approval": None}
        next_seq = seq + 1 + len(out)
        chunk = ToolResultChunk(
            turn_id=turn_id,
            seq=next_seq,
            tool_call_id=_as_uuid(pending.get("call_id")),
            output=text,
            is_error=result.get("ok") is False,
            latency_ms=0,
        )
        out.append(chunk)
        # Stub tools (frontend-coupled) carry `_pending_frontend_action` in
        # their result. Emit a sibling `interactive_action` chunk so the
        # client knows to render the matching UI (modal/toast/drawer).
        if result.get("ok") and isinstance(result.get("result"), dict):
            inner = result["result"]
            action = inner.get("_pending_frontend_action")
            if action in {
                "show_question_card", "toast", "render_plan",
                "render_todo_list", "delegate_agent",
            }:
                out.append(InteractiveActionChunk(
                    turn_id=turn_id,
                    seq=next_seq + 1,
                    call_id=str(pending.get("call_id") or ""),
                    action=action,
                    payload={k: v for k, v in inner.items()
                              if k != "_pending_frontend_action"},
                ))
        return out, state


async def _passthrough_llm(state: LoopState) -> LoopState:
    return state


async def _passthrough_tools(state: LoopState) -> LoopState:
    return state


def _openai_tools(whitelist: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    tools = []
    for name, meta in whitelist.items():
        parameters = meta.get("parameters")
        if not isinstance(parameters, dict) or not parameters.get("properties"):
            parameters = {"type": "object", "properties": {}}
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": str(meta.get("description") or name),
                    "parameters": parameters,
                },
            }
        )
    return tools


def _looks_uuid(value: str) -> bool:
    try:
        UUID(value)
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def _as_uuid(raw: Any) -> UUID:
    try:
        return UUID(str(raw))
    except (ValueError, TypeError):
        return uuid4()


def _entry_to_dict(entry: ManifestEntry) -> dict[str, Any]:
    """manifest 条目 → 落库用的 dict ✓（字段与契约层一致 ✓）。"""
    return {
        "source": entry.source,
        "tokens": entry.tokens,
        "filtered_reason": entry.filtered_reason,
        "version": entry.version,
        "ref_id": entry.ref_id,
        "score": entry.score,
        "degraded": entry.degraded,
    }


def _did_compact(outcome: CompactionOutcome) -> bool:
    """这一轮**真的压缩过**吗 ✓。

    ⚠️ **判据是「有消息被折走」** ✓（``removed_ids`` ✓）—— 「token 变少了」
    只是结果 ✓（摘要本身也可能让 token 变多 ✗）。
    """
    return bool(outcome.removed_ids) or outcome.tokens_after < outcome.tokens_before


def _knowledge_package_ids(agent: CatalogAgent | None) -> tuple[UUID, ...]:
    """agent 绑定的知识库 id ✓ —— **只取启用的** ✓（旧路径同口径 ✓）。

    ⚠️ **这是 agent 的作用域约束** ✓ —— 漏传就是「agent 绑了哪些知识库」
    这条约束**整个失效** ✗✗（它会搜到工作区里所有知识库 ✗）。
    """
    if agent is None:
        return ()
    ids: list[UUID] = []
    for ref in agent.knowledge_refs:
        if not ref.get("enabled", True):
            continue
        try:
            ids.append(UUID(str(ref.get("id"))))
        except ValueError:
            continue
    return tuple(ids)


def _build_synthetic_chunk(raw: dict[str, Any], *, turn_id: UUID, seq: int) -> TurnChunk | None:
    """把 MockLLMClient.synthetic_chunks 返回的 dict 包装为 TurnChunk.

    支持 5 类: plan_proposed / artifact_ready / attachment_ready /
    workflow_invocation / tool_call / tool_result. 后两类用于 mock
    "执行命令" 触发词, 让前端能展示一段 shell 记录.
    """
    kind = raw.get("_kind") or raw.get("kind")
    if not kind:
        return None
    try:
        if kind == "plan_proposed":
            return PlanProposedChunk(
                turn_id=turn_id,
                seq=seq,
                plan_id=UUID(str(raw["plan_id"])),
                title=str(raw.get("title") or ""),
                steps=list(raw.get("steps") or []),
                reason=str(raw.get("reason") or ""),
            )
        if kind == "artifact_ready":
            payload = dict(raw)
            payload.pop("_kind", None)
            return ArtifactReadyChunk.model_validate(
                {**payload, "turn_id": turn_id, "seq": seq}
            )
        if kind == "attachment_ready":
            return AttachmentReadyChunk(
                turn_id=turn_id,
                seq=seq,
                attachment_id=UUID(str(raw["attachment_id"])),
                name=str(raw.get("name") or ""),
                mime=str(raw.get("mime") or "application/octet-stream"),
                size_bytes=int(raw.get("size_bytes") or 0),
                download_path=str(raw.get("download_path") or ""),
            )
        if kind == "workflow_invocation":
            return WorkflowInvocationChunk(
                turn_id=turn_id,
                seq=seq,
                invocation_id=UUID(str(raw["invocation_id"])),
                workflow_name=str(raw.get("workflow_name") or ""),
                status=str(raw.get("status") or "started"),
            )
        if kind == "tool_call":
            return ToolCallChunk(
                turn_id=turn_id,
                seq=seq,
                tool_call_id=_as_uuid(raw.get("tool_call_id")),
                tool_name=str(raw.get("tool_name") or ""),
                arguments=dict(raw.get("arguments") or {}),
            )
        if kind == "tool_result":
            return ToolResultChunk(
                turn_id=turn_id,
                seq=seq,
                tool_call_id=_as_uuid(raw.get("tool_call_id")),
                output=raw.get("output"),
                is_error=bool(raw.get("is_error") or False),
                latency_ms=int(raw.get("latency_ms") or 0),
            )
        if kind == "skill_invocation":
            return SkillInvocationChunk(
                turn_id=turn_id,
                seq=seq,
                invocation_id=_as_uuid(raw.get("invocation_id")),
                skill_name=str(raw.get("skill_name") or ""),
                status=str(raw.get("status") or "started"),
            )
        if kind == "knowledge_search":
            return KnowledgeSearchChunk(
                turn_id=turn_id,
                seq=seq,
                query=str(raw.get("query") or ""),
                hits=list(raw.get("hits") or []),
                citations=list(raw.get("citations") or []),
                degraded=bool(raw.get("degraded") or False),
            )
    except Exception:  # noqa: BLE001
        return None
    return None


__all__ = ["SessionGraphRunner"]
