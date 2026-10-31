"""Session-layer graph: load → recall/retrieve → compact → ReAct loop → remember."""

from __future__ import annotations

import json
import logging
import sys as _sys
from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import Any, cast
from uuid import UUID, uuid4

from opentelemetry import context as _otel_context
from opentelemetry import trace as _trace

from qzdap.modules.agent_runtime.adapter.context.summary_adapter import (
    LLMSummaryAdapter,
)
from qzdap.modules.agent_runtime.adapter.graph.agent_loop import (
    AgentToolsReader,
    ModuleToolRuntime,
    RuntimeLLMPort,
    RuntimeModelResolver,
    SessionAgentRouter,
    to_base_messages,
    to_dict_messages,
    to_runtime_actor,
)
from qzdap.modules.agent_runtime.adapter.graph.state import LoopState, estimate_tokens
from qzdap.modules.agent_runtime.adapter.graph.tools import (
    execute_tool,
    result_text,
)
from qzdap.modules.agent_runtime.adapter.tools.tool_binding_adapter import (
    ToolBindingAdapter,
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
from qzdap_agent_runtime.agent_loop.evaluate import HARD_MAX_STEPS, Evaluator
from qzdap_agent_runtime.agent_loop.expert import ExpertAssembler, ExpertInstance
from qzdap_agent_runtime.agent_loop.observe import Observer
from qzdap_agent_runtime.agent_loop.reason import Reasoner
from qzdap_agent_runtime.agent_loop.runner import (
    AgentLoopRunner,
    BoundTool,
    LoopHooks,
)
from qzdap_agent_runtime.agent_router.classifier import (
    DEFAULT_CLASSIFIER,
    AgentRouteConfig,
)
from qzdap_agent_runtime.context.compressor import (
    DEFAULT_WINDOW,
    CompactionOutcome,
    ContextCompressor,
)
from qzdap_agent_runtime.context.persistence import ContextManifestStore
from qzdap_agent_runtime.context.tokens import estimate_tokens as estimate_text_tokens
from qzdap_agent_runtime.context.types import AssembledContext, ManifestEntry
from qzdap_agent_runtime.memory.policy import MemoryPolicy, PolicyBinding
from qzdap_kernel.ids import ModelId, TenantId, WorkspaceId
from qzdap_observability.metrics import record_new_call
from qzdap_observability.tracing import get_tracer
from qzdap_schema.dtos.turn import (
    ApprovalRequiredChunk,
    ArtifactReadyChunk,
    AttachmentReadyChunk,
    ContextCompactedChunk,
    DoneChunk,
    ErrorChunk,
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
from qzdap_vault.actor import ActorContext

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
        # ⚠️ **专家装配器** ✓（Agent Stage 4 ✓）—— **请求作用域** ✓ ——
        # 绑定集与工具运行时都绑着租户 / 工作区 / 用户 ✓ → **按请求装配** ✓
        # （不是全局单例 ✗ —— 那样会串租户 ✗✗）。
        # ⚠️ **没绑就用兜底装配器** ✓（不选专家 ✓ —— 落回会话绑定 ✓）。
        self._expert_assembler: ExpertAssembler | None = None
        self.last_loop_state: dict[str, Any] = {}

    def bind_ports(
        self,
        *,
        skill_port: SkillPort | None = None,
        sandbox_port: SandboxPort | None = None,
        tool_port: ToolPort | None = None,
        expert_assembler: ExpertAssembler | None = None,
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
        if expert_assembler is not None:
            self._expert_assembler = expert_assembler

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
        # ⚠️ **本轮的降级标记** ✓（C-22 ✓ —— Gateway 方案 §9.0 ✓）——
        # 盒子是**本轮的局部变量** ✓（不挂在实例上 ✓ —— 并发轮次会串 ✗✗）。
        flags_box: dict[str, tuple[str, ...]] = {}
        try:
            async with aclosing(
                self._drive_turn(span_ctx=child_ctx, flags_box=flags_box, **kwargs)
            ) as inner:
                async for chunk in inner:
                    if getattr(chunk, "kind", None) == "tool_call":
                        tools += 1
                    # ⚠️ **一处盖章** ✓（每一块都带 ✓ —— 前端读哪块都一样 ✓）。
                    flags = flags_box.get("flags") or ()
                    yield (chunk.model_copy(update={"flags": list(flags)}) if flags else chunk)
        except Exception:
            span.set_status(_trace.Status(_trace.StatusCode.ERROR))
            span.record_exception(_sys.exc_info()[1])  # type: ignore[arg-type]
            raise
        finally:
            span.set_attribute("agent.tool_calls", tools)
            span.end()

    async def _drive_turn(
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
        # ⚠️ **这一轮是不是受保护** ✓（Gateway 决策 #5 ✓）—— 不受保护就
        # **剔除副作用工具** ✓（§5.3.1 规则 3 ✓）。
        protected: bool = True,
        # ⚠️ **这一轮能不能挂起审批** ✓ —— IM 渠道是 False ✓（没有人能完成
        # 审批 ✓ → 挂起 = 这一轮卡死 ✗✗）→ **需要审批的工具不暴露** ✓。
        allow_approval: bool = True,
        # ⚠️ **本轮的降级标记盒子** ✓（C-22 ✓）—— 由 ``run_turn`` 建 ✓，
        # 这里**装配完**就填 ✓（第一块产出之前 ✓ → 每块都带得上 ✓）。
        flags_box: dict[str, tuple[str, ...]] | None = None,
    ) -> AsyncGenerator[TurnChunk, None]:
        seq = 0
        max_steps = 8
        if agent is not None:
            max_steps = max(1, min(int(agent.max_steps), HARD_MAX_STEPS))
            if agent.model and not model:
                model = agent.model

        # ⚠️ **actor 只建一次** ✓ —— 摘要调用与主对话调用**同一个身份** ✓
        # （摘要也是一次模型调用 ✗ —— 用别人的身份调模型不行 ✗✗）。
        actor = ActorContext(
            tenant_id=TenantId(tenant_id),
            workspace_id=WorkspaceId(workspace_id) if workspace_id is not None else None,
            principal_id=owner_id,
        )

        whitelist = await self._whitelist(agent)
        # ⚠️ **走新的 ContextBuilder** ✓（A-26 ✓）—— 旧的上下文组装
        # **已删除** ✓（Context Stage 5 ✓ —— 台账 X8 ✓）。
        assembled, knowledge_hits = await self._assemble_context(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            user_input=user_input,
            history=history,
            agent=agent,
            session_id=session_id,
        )
        # ⚠️ **降级标记从 Context 出来** ✓（C-22 ✓ —— Context 侧**已经产出**
        # ✓ —— 之前**没有可投递的通道** ✗✗ → 现在有了 ✓）。
        degraded_flags = tuple(
            sorted(name for name, degraded in (assembled.degraded_flags or {}).items() if degraded)
        )
        if flags_box is not None:
            flags_box["flags"] = degraded_flags
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
                degraded="recall_degraded" in degraded_flags,
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
            # ⚠️ **resume 是一份「部分状态」** ✓（不是 TypedDict ✓）→ 合并后
            # 重新认回 `LoopState` ✓（mypy 不允许把 `dict[str, Any]` 直接
            # 展开进 TypedDict ✗ → 这里显式收窄 ✓）。
            state = cast("LoopState", {**state, **resume})
            pending = state.get("pending_approval")
            if pending and pending.get("decision") == "approved":
                extra, state = await self._finish_pending(
                    state,
                    pending,
                    turn_id,
                    seq,
                    whitelist,
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
                state["messages"] = [*list(state.get("messages") or []), denied]
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
        final = ""
        model_id: str | None = None
        # ⚠️ **新循环** ✓（Agent Stage 5 · A-28 ✓）—— 旧的手写 ReAct 循环
        # **退役** ✓（六个终止条件归 runtime 的 `Evaluator` ✓ —— 单一判定点 ✓）。
        #
        # ⚠️ **每步的旁路** ✓（压缩 ✓ / manifest ✓ / 成本 ✓ / 旁路事件 ✓）
        # 走**钩子** ✓ —— 循环本体不碰业务 ✓。
        summary_box = {"summary": rolling_summary}
        cost_box = {"usd": 0.0}

        async def _before_step(loop_state):  # type: ignore[no-untyped-def]
            """**每步推理之前** ✓（压缩上下文 ✓）。"""
            outcome = await self._compact(
                messages=to_dict_messages(list(loop_state.messages)),
                rolling_summary=summary_box["summary"],
                context_window=context_window,
                model=model,
                actor=actor,
            )
            summary_box["summary"] = outcome.summary
            loop_state.messages = to_base_messages(list(outcome.messages))
            if _did_compact(outcome):
                yield ContextCompactedChunk(
                    turn_id=turn_id,
                    # ⚠️ **seq 由外层统一编号** ✓（钩子不知道当前序号 ✓）。
                    seq=0,
                    tokens_before=outcome.tokens_before,
                    tokens_after=outcome.tokens_after,
                    degraded=outcome.degraded,
                )
            # ⚠️ **manifest 先于模型落库** ✓（Context 方案 §5.2 ✓）——
            # 模型已经回答了却查不到那次的组成 ✗✗（审计与评测失去依据 ✗）。
            await self._save_manifest(
                assembled=assembled,
                messages=to_dict_messages(list(loop_state.messages)),
                turn_id=turn_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                session_id=session_id,
                # ⚠️ **步骤号从 0 起** ✓（第一次模型调用是第 0 步 ✓）。
                step=int(loop_state.step) - 1,
                compaction_degraded=outcome.degraded,
            )

        async def _after_step(loop_state):  # type: ignore[no-untyped-def]
            """**每步推理之后** ✓（manifest ✓ / 成本 ✓ / 旁路事件 ✓）。"""
            cost_box["usd"] += await self._price_of(
                resolved_model_id=str(model_id or ""),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                input_tokens=int(loop_state.step_input_tokens),
                output_tokens=int(loop_state.step_output_tokens),
            )
            for raw in await self._llm.synthetic_chunks(user_input, turn_id=turn_id):
                chunk = _build_synthetic_chunk(raw, turn_id=turn_id, seq=0)
                if chunk is not None:
                    yield chunk

        # ⚠️ **专家实例** ✓（Agent Stage 4 ✓）—— 专家 = 模型 + 工具集 ✓
        # （选专家 ✓ / 取模型 ✓ / 取工具 ✓ —— 全是「取」✓ 不是「挑」✓）。
        expert = await self._assemble_expert(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            agent=agent,
            model=model,
            route_id=route_id,
            user_input=user_input,
            history_count=len(history),
            actor=actor,
            protected=protected,
            allow_approval=allow_approval,
        )
        model_id = str((expert.decision.get("model") or {}).get("model_id") or "") or None
        bound_tools = [
            BoundTool(tool=tool, binding=binding)
            for tool, binding in zip(expert.tools, expert.bindings, strict=False)
        ]
        loop = AgentLoopRunner(
            reasoner=Reasoner(expert.model),
            evaluator=Evaluator(max_steps=max_steps),
            observer=Observer(),
            actor=to_runtime_actor(actor),
            turn_id=str(turn_id),
            session_id=str(session_id) if session_id else None,
            protected=protected,
            allow_approval=allow_approval,
            hooks=LoopHooks(before_step=_before_step, after_step=_after_step),
        )
        # ⚠️ **把轮次的 span 设为当前** ✓ —— 模型 / 工具的子 span 挂在它
        # 下面 ✓（观测树不变 ✓ —— ``agent.turn`` → ``agent.llm`` /
        # ``agent.tool`` ✓）。
        span_token = _otel_context.attach(span_ctx) if span_ctx is not None else None
        try:
            async for event in loop.run(
                messages=to_base_messages(list(state.get("messages") or [])),
                tools=bound_tools,
            ):
                if event.kind == "text":
                    seq += 1
                    yield MessageChunk(turn_id=turn_id, seq=seq, content=event.text)
                elif event.kind == "tool_call":
                    call = event.tool_call or {}
                    name = str(call.get("name") or "")
                    arguments = call.get("args") or {}
                    if not isinstance(arguments, dict):
                        arguments = {}
                    call_uuid = _as_uuid(call.get("id"))
                    seq += 1
                    yield ToolCallChunk(
                        turn_id=turn_id,
                        seq=seq,
                        tool_call_id=call_uuid,
                        tool_name=name,
                        arguments=dict(arguments),
                    )
                    if _binding_kind(bound_tools, name) == "skill":
                        seq += 1
                        yield SkillInvocationChunk(
                            turn_id=turn_id,
                            seq=seq,
                            invocation_id=call_uuid,
                            skill_name=name,
                            status="started",
                            tool_call_id=call_uuid,
                        )
                elif event.kind == "tool_result":
                    result = event.tool_result or {}
                    call_uuid = _as_uuid(result.get("tool_call_id"))
                    name = str(result.get("name") or "")
                    is_error = bool(result.get("is_error"))
                    output = str(result.get("output") or "")
                    seq += 1
                    yield ToolResultChunk(
                        turn_id=turn_id,
                        seq=seq,
                        tool_call_id=call_uuid,
                        output=output,
                        is_error=is_error,
                        latency_ms=0,
                    )
                    if _binding_kind(bound_tools, name) == "skill":
                        seq += 1
                        yield SkillInvocationChunk(
                            turn_id=turn_id,
                            seq=seq,
                            invocation_id=call_uuid,
                            skill_name=name,
                            status="failed" if is_error else "succeeded",
                            tool_call_id=call_uuid,
                        )
                    action = _interactive_action(output)
                    if action is not None:
                        seq += 1
                        yield InteractiveActionChunk(
                            turn_id=turn_id,
                            seq=seq,
                            call_id=str(result.get("tool_call_id") or ""),
                            action=action[0],
                            payload=action[1],
                        )
                elif event.kind == "approval_required":
                    approval = event.approval or {}
                    approval_id = await self._request_approval(
                        tenant_id=tenant_id,
                        owner_id=owner_id,
                        tool_name=str(approval.get("tool_name") or ""),
                        arguments=dict(approval.get("arguments") or {}),
                        session_id=session_id,
                        tool_call_id=str(approval.get("tool_call_id") or ""),
                    )
                    seq += 1
                    yield ApprovalRequiredChunk(
                        turn_id=turn_id,
                        seq=seq,
                        approval_id=approval_id,
                        tool_name=str(approval.get("tool_name") or ""),
                        arguments=dict(approval.get("arguments") or {}),
                        reason="高风险操作需要确认后才会执行",
                    )
                    # ⚠️ **挂起** ✓ —— 状态留给恢复 ✓（§3.5 ✓）。
                    loop_state = event.payload
                    self.last_loop_state = {
                        "pending_approval": {
                            "approval_id": str(approval_id),
                            "tool_name": str(approval.get("tool_name") or ""),
                            "arguments": dict(approval.get("arguments") or {}),
                            "tool_call_id": str(approval.get("tool_call_id") or ""),
                            "call_id": str(approval.get("tool_call_id") or ""),
                        },
                        "messages": (
                            to_dict_messages(list(loop_state.messages))
                            if loop_state is not None
                            else []
                        ),
                        "step": int(loop_state.step) if loop_state is not None else 0,
                    }
                    return
                elif event.kind == "extra":
                    # ⚠️ **钩子带出来的事件** ✓（压缩 ✓ / 旁路事件 ✓）——
                    # 本层**不解释它** ✓ —— 只补上序号 ✓。
                    chunk = event.payload
                    if chunk is None:
                        continue
                    seq += 1
                    yield chunk.model_copy(update={"seq": seq})
                elif event.kind == "usage":
                    input_tokens += int(event.usage.get("input_tokens") or 0)
                    output_tokens += int(event.usage.get("output_tokens") or 0)
                elif event.kind == "error":
                    seq += 1
                    yield ErrorChunk(
                        turn_id=turn_id,
                        seq=seq,
                        code=str(event.error_code or "AGENT_LOOP_ABORTED"),
                        message=str(event.error_message or ""),
                    )
                elif event.kind == "final":
                    final = event.text
                    loop_state = event.payload
                    if loop_state is not None:
                        state["messages"] = to_dict_messages(list(loop_state.messages))
                    state["final"] = final
        finally:
            if span_token is not None:
                _otel_context.detach(span_token)
        rolling_summary = summary_box["summary"]
        cost_usd = cost_box["usd"]
        self.last_loop_state = {
            **dict(state),
            "pending_approval": None,
            "rolling_summary": rolling_summary,
        }
        final = str(state.get("final") or "")
        # ⚠️ **摘要写新列** ✓（Context 方案 §5.1 ✓）—— 旧的
        # `metadata['rolling_summary']` 是**旧副本** ✓（它的写入点归零 ✓
        # —— 清理归 Context Stage 5 ✓）。
        await self._save_rolling_summary(
            tenant_id=tenant_id,
            session_id=session_id,
            summary=rolling_summary,
        )
        # ⚠️ **走新的 Writer** ✓（A-26 ✓）—— 旧的记忆写入**已删除** ✓
        # （Memory Stage 7 ✓ —— 台账 X11 ✓）。
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
        _ = rolling_summary

    def export_loop_state(
        self, pending: dict[str, Any] | None, messages: list[dict[str, Any]], step: int
    ) -> dict[str, Any]:
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
        session_id: UUID | None = None,
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
            # ⚠️ **记忆策略绑定** ✓（§7.1 ✓）—— 作用域 / 显式绑定的条目 ✓
            # —— 不传 = agent 绑了没用 ✗✗（§1.7 那个问题 ✗）。
            memory_policy=_memory_policy(agent),
            session_id=session_id,
        )
        knowledge = list(assembled.recalled.get("knowledge") or [])
        record_new_call("X8")  # 新的上下文组装已接管
        # ⚠️ **不再打 X15** ✓ —— L3 退役 ✓（决策 #1 ✓ —— M-47 ✓）→
        # 记忆里**不再有团队知识** ✓ → 「运行时双份注入」**没有了** ✓
        # （团队知识只从 knowledge 进「相关知识」✓ —— 台账 **X15 已清理** ✓）。
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
        payload = self._manifest_payload(assembled=assembled, messages=messages)
        degraded = {
            "recall_degraded": bool(assembled.degraded_flags.get("recall_degraded")),
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

        ⚠️ **对不上的是「后来加的消息」** ✓（工具结果 ✓ / 助手回复 ✓）→
        现算一条 ✓（来源标 ``tool_result`` ✓）。
        """
        # ⚠️ **按「内容 + 顺序」对齐** ✓（新路径的消息是**转换过的对象** ✓
        # —— 身份对不上 ✗）—— 压缩后留下的**内容不变** ✓、**顺序不变** ✓
        # → 从前往后找同一条 ✓（重复内容也不会错位 ✓ —— 游标只前进 ✓）。
        entries: list[dict[str, Any]] = []
        cursor = 0
        for message, entry in zip(assembled.messages, assembled.manifest.entries, strict=False):
            content = str(message.get("content") or "")
            role = str(message.get("role") or "")
            match = None
            for index in range(cursor, len(messages)):
                candidate = messages[index]
                if (
                    str(candidate.get("content") or "") == content
                    and str(candidate.get("role") or "") == role
                ):
                    match = index
                    break
            if match is None:
                # ⚠️ **被压缩掉了** ✓（这一条没发出去 ✓ —— 不进 manifest ✓）。
                continue
            cursor = match + 1
            entries.append(_entry_to_dict(entry))
        for message in messages[cursor:]:
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
        return (input_tokens / 1000.0) * float(price_in) + (output_tokens / 1000.0) * float(
            price_out
        )

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
            except Exception:  # noqa: S110
                pass
        catalog: dict[str, dict[str, Any]] = {}
        if self._tool_port is not None:
            try:
                for item in await self._tool_port.list_tools():
                    name = str(item.get("name") or "")
                    if name:
                        catalog[name] = {**item, "kind": "tool"}
            except Exception:
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

    async def _assemble_expert(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        agent: CatalogAgent | None,
        model: str,
        route_id: ModelId | None,
        user_input: str,
        history_count: int,
        actor: ActorContext,
        protected: bool,
        allow_approval: bool = True,
    ) -> ExpertInstance:
        """**装配专家实例** ✓（Agent Stage 4 ✓）。

        ⚠️ **模型与工具不是运行时「挑」出来的** ✓（决策 #4 ✓）—— 它们来自
        **agent 配置** ✓（模型名 ✓ / 绑定集 ✓）—— 运行时只负责**取** ✓。

        ⚠️ **请求里明确指定的模型 / 路由优先** ✓（§5.2.1 取值链的第 1 条 ✓
        —— 但那仍然是**取值链的输入** ✓ 不是运行时「挑」✗✗）。
        """
        _ = owner_id
        assembler = self._expert_assembler or self._fallback_assembler(agent, tenant_id=tenant_id)
        classification = DEFAULT_CLASSIFIER.classify(
            message_count=history_count,
            tools_count=len(agent.tools) if agent is not None else 0,
            message_text=user_input,
            agent_config=AgentRouteConfig(
                agent_id=str(agent.id) if agent is not None else "",
                deep_research=bool((agent.profile or {}).get("deep_research"))
                if agent is not None
                else False,
            ),
        )
        return await assembler.assemble(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            session_agent_id=agent.id if agent is not None else uuid4(),
            task_kind=classification.kind,
            confidence=classification.confidence,
            protected=protected,
            allow_approval=allow_approval,
            actor=to_runtime_actor(actor),
            model_override=model or None,
            route_id_override=route_id,
        )

    def _fallback_assembler(
        self, agent: CatalogAgent | None, *, tenant_id: UUID | None = None
    ) -> ExpertAssembler:
        """**兜底的专家装配器** ✓（没有装配专家路由时落回会话绑定 ✓）。

        ⚠️ **它也走同一套端口** ✓ —— 不是第二套实现 ✓（只是「路由端口」换成
        「不选专家」的那个 ✓）。
        """
        instruction = ""
        if agent is not None:
            instruction = str(agent.prompts.get("prompt") or agent.description or "")
        return ExpertAssembler(
            router=SessionAgentRouter(
                agent_id=agent.id if agent is not None else uuid4(),
                agent_version=agent.version if agent is not None else "",
                model_name=(agent.model if agent is not None else "") or "default",
                instruction=instruction,
            ),
            bindings=ToolBindingAdapter(
                tools=self._tool_port,
                skills=self._skill_port,
                agents=AgentToolsReader(agent),
                sandbox=self._sandbox_port is not None,
            ),
            llm=RuntimeLLMPort(self._llm),
            resolver=RuntimeModelResolver(self._catalog_model_resolver),
            tool_runtime=ModuleToolRuntime(
                skill_port=self._skill_port,
                sandbox_port=self._sandbox_port,
                tool_port=self._tool_port,
                tenant_id=tenant_id,
            ),
        )

    async def _request_approval(
        self,
        *,
        tenant_id: UUID,
        owner_id: UUID,
        tool_name: str,
        arguments: dict[str, Any],
        session_id: UUID | None = None,
        tool_call_id: str = "",
    ) -> UUID:
        if self._approval_factory is None:
            return uuid4()
        from qzdap_agent_runtime.session.approval import (
            approval_correlation_id,
            arguments_digest,
        )
        from qzdap_kernel.ids import TenantId, UserId

        svc = self._approval_factory
        # ⚠️ **幂等** ✓（Session 方案 S-31 ✓）—— 同一个工具调用**复用同一个
        # 审批** ✓（重试不该多出一条待办 ✗✗）。
        correlation_id = None
        if session_id is not None and tool_call_id:
            correlation_id = approval_correlation_id(
                session_id=session_id,
                tool_call_id=tool_call_id,
                request_hash=arguments_digest(arguments),
            )
        approval = await svc.create(
            tenant_id=TenantId(tenant_id),
            requester_id=UserId(owner_id),
            action=f"agent.tool.{tool_name}",
            resource={"tool": tool_name, "arguments": arguments, "owner_id": str(owner_id)},
            correlation_id=correlation_id,
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

        ⚠️ **输入只有本轮对话** ✓（**不含召回结果** ✓ —— Memory 方案 §4.6 ✓）。
        """
        policy = _memory_policy(agent)
        if not policy.enabled or self._memory_port is None:
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
            # ⚠️ **策略绑定** ✓（§7.1 ✓）—— 关了记忆就一条不写 ✓。
            policy=policy,
        )
        written = int(result.get("written") or 0)
        if not written:
            return []
        # ⚠️ **只报一层** ✓ —— 新 Writer 写的是 L2 ✓（旧的 L1/L2 两层报法是
        # L1 缓冲表的产物 ✓，那张表要退役 ✓）。
        return [("l2", final[:80])]

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
            turn_id=turn_id,
            # ⚠️ **审批恢复后重跑同一个 tool_call** ✓ —— 幂等键**必须一样** ✓
            # （不然审批后的执行会变成第二次执行 ✗✗ —— 审批前那次没执行 ✓
            # 但键一致才挡得住「点了两次同意」✓）。
            idempotency_key=_tool_idempotency_key(
                turn_id, str(pending.get("tool_call_id") or pending.get("call_id") or "")
            ),
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
                "show_question_card",
                "toast",
                "render_plan",
                "render_todo_list",
                "delegate_agent",
            }:
                out.append(
                    InteractiveActionChunk(
                        turn_id=turn_id,
                        seq=next_seq + 1,
                        call_id=str(pending.get("call_id") or ""),
                        action=action,
                        payload={k: v for k, v in inner.items() if k != "_pending_frontend_action"},
                    )
                )
        return out, state


def _tool_idempotency_key(turn_id: UUID, tool_call_id: UUID | str) -> str:
    """**一次模型工具调用的幂等键** ✓。

    ⚠️ **键 = 轮次 + tool_call id** ✓ —— 同一次调用重试**键不变** ✓（挡住重复
    执行 ✓）；不同调用**键不同** ✓（不误伤 ✓）。
    """
    return f"{turn_id}:{tool_call_id}"


def _binding_kind(bound_tools: list[BoundTool], name: str) -> str:
    """**这个工具是哪一类** ✓（skill ✓ / tool ✓）—— 事件形态不一样 ✓。"""
    for bound in bound_tools:
        if bound.tool.name == name:
            return bound.binding.kind
    return ""


def _interactive_action(output: str) -> tuple[str, dict[str, Any]] | None:
    """**工具结果里带前端动作** ✓（旧路径的口径 ✓）。

    ⚠️ **只认白名单里的动作** ✓ —— 别的键不外泄给前端 ✓。
    """
    try:
        payload = json.loads(output)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    action = payload.get("_pending_frontend_action")
    if action not in {
        "show_question_card",
        "toast",
        "render_plan",
        "render_todo_list",
        "delegate_agent",
    }:
        return None
    return str(action), {k: v for k, v in payload.items() if k != "_pending_frontend_action"}


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


def _memory_policy(agent: CatalogAgent | None) -> MemoryPolicy:
    """agent 的**记忆策略绑定** ✓（§7.1 ✓ —— C6 ✓）。

    ⚠️ **管理端绑的东西运行时要真的读到** ✓ —— 否则「后台改了绑定，行为
    不变」✗✗（= §1.7 那个问题原地不动 ✗）。

    ⚠️ **没有 agent 就用默认** ✓（允许写 ✓ / 用户级 ✓ —— 与旧路径一致 ✓）。
    """
    if agent is None:
        return PolicyBinding().to_policy()
    return PolicyBinding(
        raw=dict(agent.memory_policy),
        refs=tuple(ref for ref in agent.knowledge_refs if isinstance(ref, dict)),
    ).to_policy()


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
            return ArtifactReadyChunk.model_validate({**payload, "turn_id": turn_id, "seq": seq})
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
    except Exception:
        return None
    return None


__all__ = ["SessionGraphRunner"]
