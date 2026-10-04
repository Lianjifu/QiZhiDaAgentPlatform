"""Use case: run a single turn on a session.

Streaming design
----------------
This use case is an **async generator** that yields `TurnChunk` envelopes
in order. The HTTP layer wraps the generator in a `StreamingResponse` and
the SSE encoder (`adapter/http/sse.py`) serializes each chunk.

Lifecycle:
  1. Load session, verify tenant + status. 404 / 410 as appropriate.
  2. Persist a `Turn(status=RUNNING)`. Emit `TurnStarted`.
  3. Build a `ChatRequest` from the session metadata + user input.
  4. Stream the LLM response:
       - `chunk.delta` → `MessageChunk`
       - `chunk.tool_calls` → `ToolCallChunk` (no execution; P2 implements)
       - `chunk.usage` → `UsageChunk`
       - `chunk.finish_reason` → `DoneChunk` (terminal)
  5. Persist the final turn, emit `TurnCompleted`.
  6. On `AppError`: persist `Turn(status=FAILED)`, yield an `ErrorChunk`,
     emit `TurnFailed`, re-raise so the HTTP middleware emits 410/4xx.

First-chunk latency budget: < 1000 ms. Achieved by yielding each chunk
as soon as the LLM produces it (no aggregation, no buffering).
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

from qzdap_kernel.contextvars import current_trace_id
from qzdap_kernel.errors import AppError
from qzdap_llm.client import ChatMessage, ChatRequest
from qzdap_schema.dtos.turn import (
    DoneChunk,
    ErrorChunk,
    MessageChunk,
    ToolCallChunk,
    ToolResultChunk,
    TurnChunk,
    UsageChunk,
)
from qzdap_schema.ids import TenantId, TurnId, WorkspaceId

from qzdap.modules.agent_runtime.adapter.llm.prompts import (
    build_system_prompt,
    build_system_prompt_with_knowledge,
    build_system_prompt_with_memory,
    build_system_prompt_with_memory_and_knowledge,
)
from qzdap.modules.agent_runtime.application.ports import (
    EventPublisher,
    KnowledgePort,
    LLMPort,
    MemoryPort,
    SandboxPort,
    SessionRepository,
    SkillPort,
    ToolPort,
    TurnRepository,
)
from qzdap.modules.agent_runtime.domain import SessionStatus, Turn
from qzdap.modules.agent_runtime.domain.errors import (
    SessionClosedError,
    SessionNotFound,
)


class RunTurnUseCase:
    def __init__(
        self,
        sessions: SessionRepository,
        turns: TurnRepository,
        llm: LLMPort,
        events: EventPublisher,
        *,
        tool_port: ToolPort | None = None,
        skill_port: SkillPort | None = None,
        sandbox_port: SandboxPort | None = None,
        memory_port: MemoryPort | None = None,
        knowledge_port: KnowledgePort | None = None,
    ) -> None:
        self._sessions = sessions
        self._turns = turns
        self._llm = llm
        self._events = events
        self._tool_port = tool_port
        self._skill_port = skill_port
        self._sandbox_port = sandbox_port
        self._memory_port = memory_port
        self._knowledge_port = knowledge_port

    async def execute(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        owner_id: UUID,
        session_id: UUID,
        user_input: str,
        model: str,
    ) -> AsyncIterator[TurnChunk]:
        session = await self._sessions.get(session_id)
        if session is None or session.tenant_id != tenant_id:
            raise SessionNotFound(f"session {session_id} not found")
        if session.status is SessionStatus.CLOSED:
            raise SessionClosedError(
                f"session {session_id} is closed",
                code="SESSION_CLOSED",
            )

        turn = Turn.create(
            id=TurnId(uuid4()),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            session_id=session.id,
            user_input=user_input,
        )
        await self._turns.add(turn)
        await self._events.publish(
            turn.raise_started_event(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            trace_id=current_trace_id(),
        )

        recalled_memories: list[dict] = []
        if self._memory_port is not None:
            try:
                recalled_memories = await self._memory_port.recall(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    query=user_input,
                    top_k=10,
                )
            except AppError as exc:
                # Memory failures are non-fatal for the turn — fall back to
                # the bare system prompt. The recall error is recorded via
                # the turn's own error handling below.
                import logging as _logging

                _logging.getLogger(__name__).warning(
                    "memory recall failed; continuing without context",
                    extra={
                        "code": exc.code,
                        "session_id": str(session.id),
                        "trace_id": current_trace_id(),
                    },
                )
                recalled_memories = []

        recalled_knowledge: list[dict] = []
        if self._knowledge_port is not None:
            try:
                recalled_knowledge = await self._knowledge_port.search(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    query=user_input,
                    top_k=10,
                )
            except AppError as exc:
                # Knowledge recall is best-effort — degrade to a bare system
                # prompt if the knowledge service is unavailable. The turn
                # continues; the agent only loses retrieved context.
                import logging as _logging

                _logging.getLogger(__name__).warning(
                    "knowledge recall failed; continuing without context",
                    extra={
                        "code": exc.code,
                        "session_id": str(session.id),
                        "trace_id": current_trace_id(),
                    },
                )
                recalled_knowledge = []

        if recalled_memories and recalled_knowledge:
            system_prompt = build_system_prompt_with_memory_and_knowledge(
                session, recalled_memories, recalled_knowledge
            )
        elif recalled_memories:
            system_prompt = build_system_prompt_with_memory(session, recalled_memories)
        elif recalled_knowledge:
            system_prompt = build_system_prompt_with_knowledge(
                session, recalled_knowledge
            )
        else:
            system_prompt = build_system_prompt(session)
        req = ChatRequest(
            model=model,
            messages=[
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_input),
            ],
            tools=await self._tool_defs(),
            trace_id=current_trace_id(),
        )

        seq = 0
        collected_text = ""
        collected_input_tokens: int | None = None
        collected_output_tokens: int | None = None
        try:
            async for chunk in self._llm.stream(req):
                if chunk.delta:
                    seq += 1
                    collected_text += chunk.delta
                    yield MessageChunk(turn_id=turn.id, seq=seq, content=chunk.delta)
                if chunk.tool_calls:
                    seq += 1
                    for tc in chunk.tool_calls:
                        try:
                            args = json.loads(
                                tc.get("function", {}).get("arguments", "{}")
                            )
                        except json.JSONDecodeError:
                            args = {"_raw": tc.get("function", {}).get("arguments", "")}
                        tool_call_id = UUID(tc["id"]) if tc.get("id") else uuid4()
                        tool_name = tc.get("function", {}).get("name", "unknown")
                        yield ToolCallChunk(
                            turn_id=turn.id,
                            seq=seq,
                            tool_call_id=tool_call_id,
                            tool_name=tool_name,
                            arguments=args,
                        )
                        # When a ToolPort is wired (P2+), execute the call
                        # immediately and emit a paired ToolResultChunk so
                        # downstream orchestrators can keep going. With no
                        # port wired, the agent emits the call as-is and the
                        # client / orchestrator decides what to do next.
                        if (
                            self._tool_port is not None
                            or self._skill_port is not None
                            or self._sandbox_port is not None
                        ):
                            seq += 1
                            tool_started = time.monotonic()
                            try:
                                result = await self._dispatch_tool(
                                    call_id=tool_call_id,
                                    tool_name=tool_name,
                                    arguments=args,
                                )
                                latency_ms = int(
                                    (time.monotonic() - tool_started) * 1000
                                )
                                yield ToolResultChunk(
                                    turn_id=turn.id,
                                    seq=seq,
                                    tool_call_id=tool_call_id,
                                    output=result,
                                    is_error=bool(result.get("error_code"))
                                    and result.get("ok") is False,
                                    latency_ms=latency_ms,
                                )
                            except AppError as exc:
                                latency_ms = int(
                                    (time.monotonic() - tool_started) * 1000
                                )
                                yield ToolResultChunk(
                                    turn_id=turn.id,
                                    seq=seq,
                                    tool_call_id=tool_call_id,
                                    output={"code": exc.code, "message": str(exc)},
                                    is_error=True,
                                    latency_ms=latency_ms,
                                )
                if chunk.usage is not None:
                    seq += 1
                    collected_input_tokens = chunk.usage.input_tokens
                    collected_output_tokens = chunk.usage.output_tokens
                    yield UsageChunk(
                        turn_id=turn.id,
                        seq=seq,
                        input_tokens=chunk.usage.input_tokens,
                        output_tokens=chunk.usage.output_tokens,
                        cache_read_tokens=chunk.usage.cache_read_tokens,
                        cache_write_tokens=chunk.usage.cache_write_tokens,
                        cost_usd=0.0,
                    )
                if chunk.finish_reason:
                    seq += 1
                    yield DoneChunk(
                        turn_id=turn.id,
                        seq=seq,
                        final_message=collected_text or None,
                    )

            completed = turn.succeed(
                finished_at=datetime.now(UTC),
                final_response=collected_text or None,
                input_tokens=collected_input_tokens,
                output_tokens=collected_output_tokens,
            )
            await self._turns.add(completed)
            await self._events.publish(
                completed.raise_completed_event(
                    final_message_length=len(collected_text)
                ),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                trace_id=current_trace_id(),
            )
        except AppError as exc:
            failed = turn.fail(
                finished_at=datetime.now(UTC),
                error_code=exc.code,
                error_message=str(exc),
            )
            try:
                await self._turns.add(failed)
            except Exception:
                # Persistence after stream-error shouldn't mask the original.
                import logging as _logging

                _logging.getLogger(__name__).exception(
                    "failed to persist failed-turn record",
                    extra={"turn_id": str(turn.id), "code": exc.code},
                )
            yield ErrorChunk(
                turn_id=turn.id,
                seq=seq,
                code=exc.code,
                message=str(exc),
                retriable=bool(exc.status and exc.status >= 500),
            )
            await self._events.publish(
                failed.raise_failed_event(),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                trace_id=current_trace_id(),
            )
            raise

    async def _tool_defs(self) -> list[dict] | None:
        tools: list[dict] = []
        if self._sandbox_port is not None:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "sandbox_exec",
                        "description": "Run python or shell in a gVisor sandbox. No network.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "language": {
                                    "type": "string",
                                    "enum": ["python", "shell"],
                                },
                                "code": {"type": "string"},
                            },
                            "required": ["language", "code"],
                        },
                    },
                }
            )
        if self._skill_port is not None:
            listed = await self._skill_port.list_executable()
            for item in listed:
                properties: dict = {}
                required: list[str] = []
                for field in item.get("inputSchema") or []:
                    name = str(field.get("name") or "")
                    if not name:
                        continue
                    properties[name] = {
                        "type": field.get("type") or "string",
                        "description": field.get("description") or "",
                    }
                    if field.get("required"):
                        required.append(name)
                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": item["name"],
                            "description": item.get("description") or item["name"],
                            "parameters": {
                                "type": "object",
                                "properties": properties,
                                "required": required,
                            },
                        },
                    }
                )
        return tools or None

    async def _dispatch_tool(
        self, *, call_id, tool_name: str, arguments: dict
    ) -> dict:
        if tool_name == "sandbox_exec" and self._sandbox_port is not None:
            return await self._sandbox_port.exec(
                call_id=call_id,
                language=str(arguments.get("language") or "python"),
                code=str(arguments.get("code") or ""),
                timeout_ms=int(arguments.get("timeout_ms") or 30_000),
            )
        if self._skill_port is not None:
            result = await self._skill_port.invoke(
                call_id=call_id,
                skill_name=tool_name,
                arguments=arguments,
            )
            if result.get("error_code") == "SKILL_NOT_FOUND" and self._tool_port is not None:
                return await self._tool_port.invoke(
                    call_id=call_id, tool_name=tool_name, arguments=arguments
                )
            return result
        if self._tool_port is not None:
            return await self._tool_port.invoke(
                call_id=call_id, tool_name=tool_name, arguments=arguments
            )
        return {
            "ok": False,
            "error_code": "NO_TOOL_BACKEND",
            "call_id": str(call_id),
        }


__all__ = ["RunTurnUseCase"]
