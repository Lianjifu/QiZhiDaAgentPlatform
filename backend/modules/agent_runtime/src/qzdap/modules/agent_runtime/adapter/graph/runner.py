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

from qzdap.modules.agent_runtime.adapter.graph.chat_model import stream_chat
from qzdap.modules.agent_runtime.adapter.graph.compact import (
    DEFAULT_WINDOW,
    compact_messages,
)
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
        seq = 0
        max_steps = 8
        if agent is not None:
            max_steps = max(1, min(int(agent.max_steps), HARD_MAX_STEPS))
            if agent.model and not model:
                model = agent.model

        whitelist = await self._whitelist(agent)
        tools_schema = _openai_tools(whitelist)
        messages, knowledge_hits = await self._load_messages(
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
        messages, rolling_summary, did_compact = compact_messages(
            messages, rolling_summary=rolling_summary, context_window=context_window
        )
        if did_compact:
            seq += 1
            yield ContextCompactedChunk(
                turn_id=turn_id,
                seq=seq,
                tokens_before=0,
                tokens_after=estimate_tokens(messages),
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
            messages, rolling_summary, did_compact = compact_messages(
                list(state.get("messages") or []),
                rolling_summary=rolling_summary,
                context_window=context_window,
            )
            state["messages"] = messages
            if did_compact:
                seq += 1
                yield ContextCompactedChunk(
                    turn_id=turn_id,
                    seq=seq,
                    tokens_before=0,
                    tokens_after=estimate_tokens(messages),
                )

            chat_stream = stream_chat(
                self._llm,
                model=model or "default",
                messages=list(state["messages"]),
                tools=tools_schema,
                model_id=ModelId(UUID(model)) if _looks_uuid(model) else None,
                # Phase 12: 策略路由. 当 route_id 提供时, 优先用它走 Phase 7.
                route_id=route_id,
                actor=ActorContext(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    principal_id=owner_id,
                ),
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
        writes = await self._remember(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            agent=agent,
            user_input=user_input,
            final=final,
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

    async def _load_messages(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        user_input: str,
        history: list[dict[str, Any]],
        agent: CatalogAgent | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Build the model input and report what knowledge was recalled."""
        prompts = dict(agent.prompts) if agent is not None else {}
        system_parts = [
            prompts.get("soul") or "",
            prompts.get("prompt") or "",
            prompts.get("agents") or "",
            prompts.get("tools") or "",
            prompts.get("user") or "",
        ]
        system = "\n\n".join(part for part in system_parts if part).strip() or "你是企业助手，使用可用工具完成任务，最终给出中文回答。"
        memories: list[dict] = []
        if self._memory_port is not None:
            try:
                memories = await self._memory_port.recall(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    query=user_input,
                    top_k=8,
                    # ⚠️ 按当前用户过滤 —— 缺失这一项会把同工作区其他用户的
                    # 记忆召回进本用户的上下文（X14 跨用户泄漏）。
                    user_id=owner_id,
                )
            except Exception:  # noqa: BLE001
                memories = []
        knowledge: list[dict] = []
        package_ids: tuple[UUID, ...] = ()
        if agent is not None:
            raw_ids = []
            for ref in agent.knowledge_refs:
                if not ref.get("enabled", True):
                    continue
                try:
                    raw_ids.append(UUID(str(ref.get("id"))))
                except ValueError:
                    continue
            package_ids = tuple(raw_ids)
        if self._knowledge_port is not None:
            try:
                knowledge = await self._knowledge_port.search(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    query=user_input,
                    top_k=6,
                    package_ids=package_ids,
                )
            except Exception:  # noqa: BLE001
                knowledge = []
        if memories:
            hits = "\n".join(
                f"- ({item.get('score', 0):.2f}) {item.get('content') or item.get('value') or ''}"[:400]
                for item in sorted(memories, key=lambda row: float(row.get("score") or 0), reverse=True)[:8]
            )
            system += f"\n\n相关记忆：\n{hits}"
        if knowledge:
            hits = "\n".join(
                f"- ({item.get('score', 0):.2f}) {item.get('content') or ''}"[:400]
                for item in sorted(knowledge, key=lambda row: float(row.get("score") or 0), reverse=True)[:6]
            )
            system += f"\n\n相关知识：\n{hits}"
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for item in history:
            role = item.get("role")
            if role in {"user", "assistant", "tool", "system"}:
                messages.append(item)
        messages.append({"role": "user", "content": user_input})
        return messages, knowledge

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
