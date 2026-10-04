"""Session-layer graph: load → recall/retrieve → compact → ReAct loop → remember."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

from qzdap_schema.dtos.turn import (
    ApprovalRequiredChunk,
    ContextCompactedChunk,
    DoneChunk,
    ErrorChunk,
    MemoryWriteChunk,
    MessageChunk,
    ToolCallChunk,
    ToolResultChunk,
    TurnChunk,
    UsageChunk,
)
from qzdap_schema.ids import ModelId

from qzdap.modules.agent_runtime.adapter.graph.chat_model import complete_chat
from qzdap.modules.agent_runtime.adapter.graph.compact import DEFAULT_WINDOW, compact_messages
from qzdap.modules.agent_runtime.adapter.graph.loop import HARD_MAX_STEPS, apply_stall_guard, compile_loop_graph, next_route
from qzdap.modules.agent_runtime.adapter.graph.state import LoopState, estimate_tokens
from qzdap.modules.agent_runtime.adapter.graph.tools import (
    execute_tool,
    needs_confirm,
    parse_arguments,
    result_text,
)
from qzdap.modules.agent_runtime.application.ports import (
    KnowledgePort,
    LLMPort,
    MemoryPort,
    SandboxPort,
    SkillPort,
    ToolPort,
)
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent


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
    ) -> None:
        self._llm = llm
        self._skill_port = skill_port
        self._sandbox_port = sandbox_port
        self._tool_port = tool_port
        self._memory_port = memory_port
        self._knowledge_port = knowledge_port
        self._approval_factory = approval_factory
        self._graph = compile_loop_graph(llm_node=_passthrough_llm, tools_node=_passthrough_tools)
        self.last_loop_state: dict[str, Any] = {}

    async def run_turn(
        self,
        *,
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
    ) -> AsyncIterator[TurnChunk]:
        seq = 0
        max_steps = 8
        if agent is not None:
            max_steps = max(1, min(int(agent.max_steps), HARD_MAX_STEPS))
            if agent.model and not model:
                model = agent.model

        whitelist = await self._whitelist(agent)
        tools_schema = _openai_tools(whitelist)
        messages = await self._load_messages(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_input=user_input,
            history=history,
            agent=agent,
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
                    state, pending, turn_id, seq, whitelist
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

            deltas: list[str] = []

            async def on_delta(piece: str, _seq_holder: list[int] = [seq]) -> None:  # noqa: B006
                deltas.append(piece)

            assistant = await complete_chat(
                self._llm,
                model=model or "default",
                messages=list(state["messages"]),
                tools=tools_schema,
                model_id=ModelId(UUID(model)) if _looks_uuid(model) else None,
                on_delta=on_delta,
            )
            usage = assistant.get("usage") or {}
            input_tokens += int(usage.get("input_tokens") or 0)
            output_tokens += int(usage.get("output_tokens") or 0)
            if "".join(deltas):
                seq += 1
                yield MessageChunk(turn_id=turn_id, seq=seq, content="".join(deltas))
            elif assistant.get("content"):
                seq += 1
                yield MessageChunk(turn_id=turn_id, seq=seq, content=str(assistant["content"]))

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
                result = await execute_tool(
                    name=name,
                    arguments=arguments,
                    skill_port=self._skill_port,
                    sandbox_port=self._sandbox_port,
                    tool_port=self._tool_port,
                    confirmed=False,
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
            cost_usd=0,
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
        user_input: str,
        history: list[dict[str, Any]],
        agent: CatalogAgent | None,
    ) -> list[dict[str, Any]]:
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
        return messages

    async def _whitelist(self, agent: CatalogAgent | None) -> dict[str, dict[str, Any]]:
        allowed = {"sandbox_exec": {"name": "sandbox_exec", "needConfirm": True, "risk": "high"}}
        if self._skill_port is not None:
            try:
                for item in await self._skill_port.list_executable():
                    allowed[str(item.get("name"))] = item
            except Exception:  # noqa: BLE001
                pass
        if agent is None:
            return allowed
        named = {str(tool.get("name")) for tool in agent.tools if tool.get("enabled", True)}
        if not named:
            return allowed
        named.add("sandbox_exec")
        return {key: value for key, value in allowed.items() if key in named}

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
            requester_id=UserId(UUID(int=1)),
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
    ) -> tuple[list[Any], LoopState]:
        _ = whitelist
        result = await execute_tool(
            name=str(pending.get("tool_name")),
            arguments=dict(pending.get("arguments") or {}),
            skill_port=self._skill_port,
            sandbox_port=self._sandbox_port,
            tool_port=self._tool_port,
            confirmed=True,
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
        chunk = ToolResultChunk(
            turn_id=turn_id,
            seq=seq + 1,
            tool_call_id=_as_uuid(pending.get("call_id")),
            output=text,
            is_error=result.get("ok") is False,
            latency_ms=0,
        )
        return [chunk], state


async def _passthrough_llm(state: LoopState) -> LoopState:
    return state


async def _passthrough_tools(state: LoopState) -> LoopState:
    return state


def _openai_tools(whitelist: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    tools = []
    for name, meta in whitelist.items():
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": str(meta.get("description") or name),
                    "parameters": {"type": "object", "properties": {}},
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


__all__ = ["SessionGraphRunner"]
