"""SessionEngine — §3.1 / §5.2 runtime library 入口。

Stage 5 PR B 范围：

- 6 个稳定入口（§5.2）：
  * ensure_session: identity → SessionRef
  * start_turn: TurnRequest → AsyncIterator[ResultEvent]
  * resume_turn: ResumeRequest → AsyncIterator[ResultEvent]
  * replay: turn_id, after_seq → AsyncIterator[ResultEvent]
  * cancel_turn: 标记 turn CANCELLED
  * close_session: 标记 session CLOSED
- 内部组合: build_session_graph + LockManager + ResultDispatcher + Memory
- 阶段退出条件（§8 Stage 1）：纯内存 fake 可编译图

注：Stage 5 范围内 start_turn / resume_turn 用 InMemory 简化实现
（不接 outbox / Postgres），Stage 7a 接入 cost_attribution + LangSmith 时再增强。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from .channels.gateway import (
    ChannelMessage,
    build_session_key,
    build_trace_id,
    payload_hash,
)
from .execution.lock import (
    InMemoryLockManager,
    LockManager,
    LockToken,
    RevisionConflictError,
    SessionBusyError,
)
from .graph.builder import build_session_graph
from .graph.nodes import (
    set_default_assembler,
    set_default_compactor,
    set_default_lock_manager,
    set_default_memory,
    set_default_policy,
    set_default_executor,
    set_default_tool_registry,
    set_default_agent_config,
    set_default_approval_store,
    set_default_audit,
    reset_default_dependencies,
)
from .graph.routing import AgentRouteConfig
from .memory.layered import InMemoryLayeredMemory, L1Source
from .result.events import DoneEvent, ErrorEvent, MessageEvent, ResultEvent
from .result.sink import InMemoryResultSink, ResultDispatcher, ResultSink


@dataclass(frozen=True, slots=True)
class SessionRef:
    """session 句柄。"""

    session_id: str
    tenant_id: str
    workspace_id: str
    channel_id: str
    channel_session_key: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True, slots=True)
class TurnRequest:
    """§5.2 start_turn 入参。"""

    tenant_id: str
    workspace_id: str
    user_id: str
    agent_id: str
    agent_version: str
    messages: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResumeRequest:
    """§5.2 resume_turn 入参（审批恢复）。"""

    turn_id: str
    approval_id: str
    decision: str  # "approve" | "deny"
    actor_id: str
    tool_call_id: str = ""
    request_hash: str = ""


# ---------------------------------------------------------------------------
# SessionEngine
# ---------------------------------------------------------------------------


class SessionEngine:
    """§3.1 / §5.2 入口 facade。"""

    def __init__(
        self,
        *,
        checkpointer: Any | None = None,
        lock_manager: LockManager | None = None,
        memory: InMemoryLayeredMemory | None = None,
        dispatcher: ResultDispatcher | None = None,
        approval_store: Any | None = None,
        audit: Any | None = None,
    ) -> None:
        self._graph = build_session_graph(checkpointer=checkpointer)
        self._lock = lock_manager or InMemoryLockManager()
        self._memory = memory or InMemoryLayeredMemory()
        self._dispatcher = dispatcher or ResultDispatcher()
        self._approval_store = approval_store
        self._audit = audit

        # 注入默认依赖（让 graph 节点能拿到）
        set_default_lock_manager(self._lock)
        set_default_memory(self._memory)
        set_default_assembler(None)  # Stage 4: 不强制注入
        set_default_compactor(None)
        set_default_policy(None)
        set_default_executor(None)
        set_default_tool_registry(None)
        set_default_agent_config(None)
        if approval_store is not None:
            set_default_approval_store(approval_store)
        if audit is not None:
            set_default_audit(audit)

        # 默认 sink: InMemoryResultSink (SSE 客户端从这里消费)
        self._sink = InMemoryResultSink()
        self._dispatcher.register(self._sink)

    @property
    def lock_manager(self) -> LockManager:
        return self._lock

    @property
    def memory(self) -> InMemoryLayeredMemory:
        return self._memory

    @property
    def dispatcher(self) -> ResultDispatcher:
        return self._dispatcher

    @property
    def sink(self) -> InMemoryResultSink:
        return self._sink

    @property
    def approval_store(self) -> Any:
        return self._approval_store

    @property
    def audit(self) -> Any:
        return self._audit

    # ---- 6 个稳定入口 (§5.2) ----

    async def ensure_session(self, identity: dict[str, Any]) -> SessionRef:
        """§5.2 ensure_session: identity → SessionRef。

        简化实现：基于 tenant/workspace/channel + external_* 计算 session_key，
        不持久化（Stage 2 接入 Postgres）。
        """
        session_key = build_session_key(
            tenant_id=identity.get("tenant_id", ""),
            workspace_id=identity.get("workspace_id", ""),
            channel_id=identity.get("channel_id", ""),
            external_chat_id=identity.get("external_chat_id", ""),
            external_user_id=identity.get("external_user_id", ""),
        )
        # deterministic session_id from key
        import hashlib
        session_id = hashlib.sha256(session_key.encode("utf-8")).hexdigest()[:32]
        return SessionRef(
            session_id=session_id,
            tenant_id=identity.get("tenant_id", ""),
            workspace_id=identity.get("workspace_id", ""),
            channel_id=identity.get("channel_id", ""),
            channel_session_key=session_key,
        )

    async def start_turn(
        self,
        request: TurnRequest,
        *,
        expected_revision: int | None = None,
    ) -> AsyncIterator[ResultEvent]:
        """§5.2 start_turn: 启动 turn, yield ResultEvent 流。

        简化实现：直接调 LangGraph graph，graph 完成后从 sink 拉所有事件。
        """
        ref = await self.ensure_session({
            "tenant_id": request.tenant_id,
            "workspace_id": request.workspace_id,
            "channel_id": "api",
            "external_chat_id": request.user_id,
            "external_user_id": request.user_id,
        })
        turn_id = str(uuid.uuid4())
        trace_id = build_trace_id("api", turn_id)
        thread_id = ref.session_id
        # 初始 state
        initial_state: dict[str, Any] = {
            "schema_version": 1,
            "tenant_id": request.tenant_id,
            "workspace_id": request.workspace_id,
            "session_id": ref.session_id,
            "turn_id": turn_id,
            "thread_id": thread_id,
            "idempotency_key": turn_id,
            "revision": expected_revision or 0,
            "expected_revision": expected_revision,
            "trace_id": trace_id,
            "agent_id": request.agent_id,
            "agent_version": request.agent_version,
            "model_version": "m1",
            "messages": list(request.messages),
            "tool_calls": [],
            "tool_results": [],
            "todos": [],
            "usage": {
                "input_tokens": 0, "output_tokens": 0, "cache_tokens": 0,
                "cost_usd": None, "cost_unknown": True, "attribution_status": "degraded",
            },
            "emitted_seq": 0,
            "errors": [],
            "degraded": {},
        }
        # 跑 graph (同步, 在线程池)
        import asyncio
        import concurrent.futures
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            final = await loop.run_in_executor(
                ex,
                lambda: self._graph.invoke(
                    initial_state, config={"configurable": {"thread_id": thread_id}}
                ),
            )

        # emit done event
        done = DoneEvent(
            turn_id=turn_id, seq=1, event_id=f"done-{turn_id}",
            final_message=str(final.get("result", {}).get("final_message", ""))
                if isinstance(final.get("result"), dict) else "completed",
            status="succeeded" if not final.get("errors") else "failed",
            agent_version=request.agent_version,
            model_version="m1",
        )
        await self._dispatcher.dispatch(done)

        # 拉所有事件
        for ev in self._sink.get_events(turn_id):
            yield ev

    async def resume_turn(
        self,
        request: ResumeRequest,
        *,
        expected_revision: int | None = None,
    ) -> AsyncIterator[ResultEvent]:
        """§5.2 resume_turn: 审批恢复 (Stage 6a 完整实现)。

        行为：
        - 调 ApprovalStore.consume() 校验 approval_id / tool_call_id / request_hash
        - 校验 TTL：超时报 ApprovalExpiredError → emit ErrorEvent + AuditLogger
        - 校验不匹配：报 ApprovalNotMatchError → emit ErrorEvent
        - approve: AuditLogger.log(APPROVE) + emit DoneEvent(succeeded)
        - deny: AuditLogger.log(DENY) + emit DoneEvent(failed)
        """
        from .governance.approval import (
            ApprovalExpiredError,
            ApprovalNotMatchError,
        )
        from .governance.audit import AuditEvent, AuditKind
        from .graph.nodes import get_default_audit
        from .result.events import DoneEvent

        store = self._approval_store
        if store is None:
            err = ErrorEvent(
                turn_id=request.turn_id, seq=1, event_id=f"err-resume",
                error_code="APPROVAL_NOT_MATCH",
                safe_message="approval store not configured",
                retriable=False,
            )
            await self._dispatcher.dispatch(err)
            yield err
            return

        # 审批 ID 形如 "apr-<tool_call_id>"; 简化: tool_call_id 在 request 里
        # 实际系统应从 approval 记录里读 tool_call_id; 这里允许 request 传入
        tool_call_id = getattr(request, "tool_call_id", "")
        request_hash = getattr(request, "request_hash", "")
        if not tool_call_id or not request_hash:
            # 从 approval_id 解析 (apr-<tool_call_id> 格式)
            parts = request.approval_id.split("-", 1)
            if len(parts) == 2:
                tool_call_id = parts[1]
            # request_hash 必须由调用方提供
            err = ErrorEvent(
                turn_id=request.turn_id, seq=1, event_id="err-resume-args",
                error_code="APPROVAL_NOT_MATCH",
                safe_message="tool_call_id and request_hash required",
                retriable=False,
            )
            await self._dispatcher.dispatch(err)
            yield err
            return

        try:
            rec = store.consume(
                approval_id=request.approval_id,
                tool_call_id=tool_call_id,
                request_hash=request_hash,
                actor_id=request.actor_id,
                decision=request.decision,
            )
        except ApprovalExpiredError:
            audit = get_default_audit()
            if audit is not None:
                audit.log(AuditEvent(
                    kind=AuditKind.TIMEOUT,
                    actor_id=request.actor_id,
                    session_id="", turn_id=request.turn_id,
                    tool_call_id=tool_call_id, tool_name="",
                    policy_id=None, request_hash=request_hash,
                    trace_id=None, reason="approval TTL expired",
                ))
            err = ErrorEvent(
                turn_id=request.turn_id, seq=1, event_id="err-timeout",
                error_code="APPROVAL_EXPIRED",
                safe_message="approval expired",
                retriable=False,
            )
            await self._dispatcher.dispatch(err)
            yield err
            return
        except ApprovalNotMatchError:
            err = ErrorEvent(
                turn_id=request.turn_id, seq=1, event_id="err-mismatch",
                error_code="APPROVAL_NOT_MATCH",
                safe_message="approval does not match pending tool_call",
                retriable=False,
            )
            await self._dispatcher.dispatch(err)
            yield err
            return
        except KeyError:
            err = ErrorEvent(
                turn_id=request.turn_id, seq=1, event_id="err-not-found",
                error_code="APPROVAL_NOT_MATCH",
                safe_message="approval not found",
                retriable=False,
            )
            await self._dispatcher.dispatch(err)
            yield err
            return

        # 成功路径: 记 audit
        audit = get_default_audit()
        if audit is not None:
            audit_kind = AuditKind.APPROVE if rec.decision == "approve" else AuditKind.DENY
            audit.log(AuditEvent(
                kind=audit_kind,
                actor_id=rec.consumed_by or request.actor_id,
                session_id=rec.session_id,
                turn_id=rec.turn_id,
                tool_call_id=rec.tool_call_id,
                tool_name=rec.tool_name,
                policy_id=rec.policy_id,
                request_hash=rec.request_hash,
                trace_id=None,
                approval_id=rec.approval_id,
            ))

        # emit done event
        status = "succeeded" if rec.decision == "approve" else "failed"
        done = DoneEvent(
            turn_id=request.turn_id, seq=1, event_id=f"done-resume",
            final_message=f"approval {rec.decision}",
            status=status,  # type: ignore[arg-type]
            agent_version="v1", model_version="m1",
        )
        await self._dispatcher.dispatch(done)
        yield done

    async def replay(
        self,
        turn_id: str,
        after_seq: int = -1,
        *,
        expected_revision: int | None = None,
    ) -> AsyncIterator[ResultEvent]:
        """§4.4 Last-Event-ID 重放: 拉 seq > after_seq 的所有事件。"""
        for ev in self._sink.get_events(turn_id, after_seq=after_seq):
            yield ev

    async def cancel_turn(self, session_id: str, turn_id: str, reason: str) -> None:
        """§5.2 cancel_turn: 标记 turn CANCELLED。

        §13.2 节点 19 决议: 已发送的 event 保留用于审计, 后续未发送停止。
        Stage 5 stub: 仅记录到 in-memory map (Stage 2 接入 session_turns.status)。
        """
        # 简化: 记日志
        import logging
        logging.getLogger(__name__).info(
            "turn cancelled: session_id=%s turn_id=%s reason=%s",
            session_id, turn_id, reason,
        )

    async def close_session(self, session_id: str) -> None:
        """§5.2 close_session: 标记 session CLOSED."""
        import logging
        logging.getLogger(__name__).info("session closed: session_id=%s", session_id)


# ---------------------------------------------------------------------------
# ChannelGateway
# ---------------------------------------------------------------------------


class ChannelGateway:
    """§5.1 Channel 入站 gateway: ChannelMessage → SessionEngine.start_turn."""

    def __init__(self, engine: SessionEngine) -> None:
        self._engine = engine

    async def handle(self, msg: ChannelMessage) -> AsyncIterator[ResultEvent]:
        """处理入站 ChannelMessage, 调 engine.start_turn。

        §5.1 关键:
        - 用 build_session_key 计算稳定 session_key
        - trace_id 优先从 webhook header 提取, 无则 UUIDv5
        - Channel adapter 不直接调 LLM
        """
        # 优先用 msg 自带的 trace_id, 无则生成
        trace_id = msg.trace_id or build_trace_id(msg.channel_id, msg.external_message_id)

        # 把附件映射为 messages（简化: 文本作为 user message, 附件 metadata 一起）
        request = TurnRequest(
            tenant_id=msg.tenant_id,
            workspace_id=msg.workspace_id,
            user_id=msg.external_user_id,
            agent_id="default-agent",  # 实际从 agent catalog 注入 (Stage 4)
            agent_version="v1",
            messages=[
                {
                    "role": "user",
                    "content": msg.text,
                    "message_id": msg.external_message_id,
                    "metadata": {
                        "channel": msg.channel_type,
                        "chat_id": msg.external_chat_id,
                        "trace_id": trace_id,
                        "attachments": list(msg.attachments),
                    },
                },
            ],
        )
        async for ev in self._engine.start_turn(request):
            yield ev


__all__ = [
    "ChannelGateway",
    "ResumeRequest",
    "SessionEngine",
    "SessionRef",
    "TurnRequest",
]