"""Copilot session facade — list/create/history + LangGraph turn stream."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

from qzdap_agent_runtime.gateway.idempotency import (
    IdempotencyGuard,
    InboxScope,
    approval_key,
    payload_hash_of,
)
from qzdap_agent_runtime.gateway.normalizer import resolve_idempotency_key
from qzdap_agent_runtime.gateway.types import ChannelType, IdempotencyKey
from qzdap_agent_runtime.router.types import RouteDecision
from qzdap_agent_runtime.session.claim import TurnClaimPort
from qzdap_agent_runtime.session.message import SessionMessagePort
from qzdap_kernel.contextvars import current_trace_id
from qzdap_observability.metrics import record_legacy_call
from qzdap_schema.dtos.errors import ErrorCode, project_error_message
from qzdap_schema.dtos.turn import (
    ApprovalRequiredChunk,
    DoneChunk,
    ErrorChunk,
    TurnChunk,
    UsageChunk,
)
from qzdap_schema.ids import (
    AgentId,
    ModelId,
    SessionId,
    TenantId,
    TurnId,
    UserId,
    WorkspaceId,
)

from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner
from qzdap.modules.agent_runtime.application.catalog import AgentCatalogService
from qzdap.modules.agent_runtime.application.ports import (
    EventPublisher,
    SessionJournal,
    SessionRepository,
    TurnRepository,
)
from qzdap.modules.agent_runtime.domain import Session, SessionStatus, Turn
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent
from qzdap.modules.agent_runtime.domain.errors import (
    DuplicateRequestError,
    SessionBusyError,
    SessionClosedError,
    SessionNotFound,
)

_log = logging.getLogger(__name__)

# 用户点「停止」后, 最多隔多久检查一次停止标记.
CANCEL_POLL_SECONDS = 1.0


class _TurnCancelled(Exception):
    """内部信号: 用户请求停止当前轮次."""


class CopilotSessionService:
    def __init__(
        self,
        *,
        sessions: SessionRepository,
        turns: TurnRepository,
        messages: SessionMessagePort,
        catalog: AgentCatalogService,
        events: EventPublisher,
        graph: SessionGraphRunner,
        idempotency: IdempotencyGuard,
        journal: SessionJournal,
        claim: TurnClaimPort,
    ) -> None:
        self._sessions = sessions
        self._turns = turns
        self._messages = messages
        self._catalog = catalog
        self._events = events
        self._graph = graph
        self._idempotency = idempotency
        # 新架构的轮次 + 事件日志（双写期）—— 重放的落点（Gateway §4.5）。
        self._journal = journal
        # 会话执行权（互斥）—— **轮次表是唯一权威**（Session 方案 §4.4 / §6）。
        # 旧的 ``wait_status`` CAS 已迁走（台账 R3 已清理）✓。
        self._claim = claim

    def bind_ports(self, **ports: Any) -> None:
        """Re-bind request-scoped ports (tenant/workspace are per request)."""
        self._graph.bind_ports(**ports)

    async def list_sessions(
        self, *, tenant_id: UUID, owner_id: UUID, search: str = ""
    ) -> list[dict[str, Any]]:
        rows = await self._sessions.list_for_owner(tenant_id, owner_id, limit=80)
        query = search.strip().lower()
        out: list[dict[str, Any]] = []
        for session in rows:
            if session.status is SessionStatus.CLOSED:
                continue
            title = str(session.metadata.get("title") or "新对话")
            preview = str(session.metadata.get("preview") or "")
            hay = f"{title} {preview}".lower()
            if query and query not in hay:
                continue
            out.append(_session_card(session))
        return out

    async def create_session(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        agent_id: UUID,
        title: str = "",
        route_decision: RouteDecision | None = None,
    ) -> dict[str, Any]:
        agent = await self._catalog.get_published(agent_id)
        metadata: dict[str, Any] = {
            "title": title.strip() or f"与{agent.name}对话",
            "preview": "",
            "agentName": agent.name,
            "model": agent.model,
            "rolling_summary": "",
            # 标题先占位, 用户说第一句话后换成真实标题.
            "title_auto": True,
        }
        if route_decision is not None:
            # 路由决策留痕 —— 挂在会话上, 随每一轮写进 ``session_turns``。
            metadata["route_decision"] = route_decision.to_dict()
        session = Session.create(
            id=SessionId(uuid4()),
            tenant_id=TenantId(tenant_id),
            workspace_id=WorkspaceId(workspace_id),
            owner_id=UserId(owner_id),
            agent_id=AgentId(agent.id),
            agent_version=agent.version or "v1",
            metadata=metadata,
        )
        await self._sessions.add(session)
        await self._events.publish(
            session.raise_opened_event(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        return _session_detail(session, messages=[], pending=None, agent=agent)

    async def get_session(self, *, tenant_id: UUID, session_id: UUID) -> dict[str, Any]:
        session = await self._require_session(tenant_id, session_id)
        messages = await self._messages.list_for_session(session_id)
        pending = (session.graph_state or {}).get("pending_approval")
        agent = await self._catalog.get_admin(session.agent_id)
        return _session_detail(
            session, messages=messages, pending=pending, agent=None, agent_dict=agent
        )

    async def close_session(self, *, tenant_id: UUID, session_id: UUID) -> None:
        session = await self._require_session(tenant_id, session_id)
        if session.status is SessionStatus.CLOSED:
            return
        closed = session.close()
        await self._sessions.update(closed)
        await self._events.publish(
            closed.raise_closed_event(),
            tenant_id=tenant_id,
            workspace_id=session.workspace_id,
        )

    async def archive_session(self, *, tenant_id: UUID, session_id: UUID) -> None:
        """归档 = close + 标记 archived. 用于 /api/tasks 的归档入口."""
        session = await self._require_session(tenant_id, session_id)
        if session.status is SessionStatus.CLOSED:
            return
        closed = session.close()
        meta = dict(closed.metadata)
        meta["archived"] = True
        meta["archived_at"] = (
            __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat()
        )
        closed = closed.with_runtime(metadata=meta)
        await self._sessions.update(closed)
        await self._events.publish(
            closed.raise_closed_event(),
            tenant_id=tenant_id,
            workspace_id=closed.workspace_id,
        )

    async def list_tasks(
        self,
        *,
        tenant_id: UUID,
        owner_id: UUID,
        workspace_id: UUID,
        q: str = "",
        status: str = "all",
    ) -> list[dict[str, Any]]:
        """我的任务列表 — 派生自 owner=me 的 agent_sessions, 不新建表.

        状态映射:
          session.open  + latest_turn.running   → 执行中
          session.open  + latest_turn.succeeded → 待处理
          session.open  + latest_turn.failed/denied → 异常
          session.closed                         → 已完成
        """
        sessions = await self._sessions.list_for_owner_workspace(
            tenant_id=tenant_id,
            owner_id=owner_id,
            workspace_id=workspace_id,
            limit=200,
        )
        out: list[dict[str, Any]] = []
        for session in sessions:
            latest_turn = await self._turns.latest_for_session(session.id)
            task = _task_card(session, latest_turn)
            if status != "all" and task["status"] != status:
                continue
            needle = q.strip().lower()
            if needle:
                hay = f"{task['title']} {task['source']} {task['description']}".lower()
                if needle not in hay:
                    continue
            out.append(task)
        return out

    async def stream_turn(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        session_id: UUID,
        user_input: str,
        model: str | None = None,
        route_id: ModelId | None = None,
        resume: dict[str, Any] | None = None,
        client_request_id: str = "",
        channel: ChannelType = ChannelType.WEB,
        idempotency_key: IdempotencyKey | None = None,
        parent_span_context: Any = None,
    ) -> AsyncIterator[TurnChunk]:
        """Run one turn, holding an exclusive claim on the session.

        Two turns on the same session would interleave their messages and
        race on the message sequence number, so the second one is rejected
        with ``SESSION_BUSY`` instead.

        幂等在**抢占用之前**：同一个键重复到达（双击 / 网络重试）不会跑第二轮；
        而因会话被占导致本轮没跑起来时，键会被释放，调用方仍可用同一个键重试。
        """
        # 先校验会话存在且未关闭, 再抢占用 —— 否则「会话不存在」会被误报成
        # 「会话忙」.
        # 收敛打点：旧实现被调用 = 「旧路径还在服役」的**可观测事实**。
        record_legacy_call("X18")  # copilot.py 的 turn 编排
        await self._require_session(tenant_id, session_id)
        key = idempotency_key or self._select_key(
            client_request_id=client_request_id,
            channel=channel,
            session_id=session_id,
            owner_id=owner_id,
            user_input=user_input,
        )
        scope = InboxScope.for_web(
            tenant_id=tenant_id, workspace_id=workspace_id, channel=channel
        )
        decision = await self._idempotency.accept(
            scope,
            key,
            payload_hash=payload_hash_of(str(session_id), user_input),
            trace_id=current_trace_id() or "",
        )
        if decision.is_duplicate:
            # 同一个键又来了 —— 双击或网络重试, 不跑第二轮.
            # ⚠️ 带上「上次那一轮的 turn_id」：重复请求**不是错误** —— 上层据此
            # **重放上一轮的事件流**（§4.5 / Stage 4b）。
            raise DuplicateRequestError(
                f"request {key.value} was already handled",
                code=ErrorCode.DUPLICATE_REQUEST.value,
                turn_id=decision.turn_id,
            )
        # ⚠️ **turn_id 预先生成** —— claim 需要它, 而 claim 必须在建轮次行
        # **之前**（否则「会话忙」时会留下一行失败的轮次 —— 那是给用户看的
        # 噪音 ✗✗）。
        turn_id = uuid4()
        claimed = await self._claim.claim(
            tenant_id=tenant_id, session_id=session_id, turn_id=turn_id
        )
        if not claimed:
            # 这一轮根本没跑起来 → 键不能被消费, 否则调用方用同一个键重试
            # 会被误判成重复请求.
            with contextlib.suppress(Exception):
                await self._idempotency.release(decision)
            raise SessionBusyError(
                f"session {session_id} already has a turn in flight",
                code="SESSION_BUSY",
            )
        try:
            async for chunk in self._run_turn(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                owner_id=owner_id,
                session_id=session_id,
                user_input=user_input,
                model=model,
                route_id=route_id,
                resume=resume,
                parent_span_context=parent_span_context,
                idempotency_key=key,
                turn_id=turn_id,
            ):
                yield chunk
        finally:
            with contextlib.suppress(Exception):
                await asyncio.shield(
                    self._idempotency.complete(decision, turn_id=turn_id)
                )
            with contextlib.suppress(Exception):
                await asyncio.shield(
                    self._claim.release(
                        tenant_id=tenant_id, session_id=session_id, turn_id=turn_id
                    )
                )

    def _select_key(
        self,
        *,
        client_request_id: str,
        channel: ChannelType,
        session_id: UUID,
        owner_id: UUID,
        user_input: str,
    ) -> IdempotencyKey:
        """幂等键的阶梯 —— **委托给 Gateway 的那一份**（Gateway 方案 §4.2）。

        ⚠️ **阶梯只有一份实现**（``gateway/normalizer.py`` 的
        ``resolve_idempotency_key``）—— 这里只是把本方法的参数映射过去，
        不自己再写一遍规则。

        走 HTTP 的入口**不再到这里**：web 的键由 Gateway ③ 派生后经
        ``idempotency_key`` 传进来（§10 Stage 4a）；这里只服务**直接调用方**。
        """
        if not client_request_id:
            _log.warning(
                "inbound_without_client_request_id session_id=%s — 幂等降级为 weak（不抑制）",
                session_id,
            )
        return resolve_idempotency_key(
            client_request_id=client_request_id or None,
            channel=str(channel),
            chat_id=str(session_id),
            user_id=str(owner_id),
            text=user_input,
        )

    async def _run_turn(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        session_id: UUID,
        user_input: str,
        model: str | None = None,
        route_id: ModelId | None = None,
        resume: dict[str, Any] | None = None,
        parent_span_context: Any = None,
        idempotency_key: IdempotencyKey,
        turn_id: UUID,
    ) -> AsyncIterator[TurnChunk]:
        session = await self._require_session(tenant_id, session_id)
        if session.workspace_id != workspace_id or session.owner_id != owner_id:
            raise SessionNotFound(f"session {session_id} not found")
        if session.status is SessionStatus.CLOSED:
            raise SessionClosedError(
                f"session {session_id} is closed", code="SESSION_CLOSED"
            )
        # 上一轮遗留的停止标记不能影响这一轮.
        await self._sessions.clear_cancel(session_id)
        agent_row = await self._catalog.get_published(session.agent_id)
        # 这一轮实际用的模型 —— 轮次表要留痕（``session_turns.model_version``）。
        model_used = model or str(
            session.metadata.get("model") or agent_row.model or "default"
        )
        history = await self._messages.list_for_session(session_id)
        hist_msgs = [
            {
                "role": item["role"],
                "content": item["content"],
                "name": item.get("toolName") or None,
            }
            for item in history
            if item.get("role") in {"user", "assistant", "tool", "system"}
        ]
        turn = Turn.create(
            id=TurnId(turn_id),
            tenant_id=TenantId(tenant_id),
            workspace_id=WorkspaceId(workspace_id),
            session_id=session.id,
            user_input=user_input if not resume else (user_input or "继续"),
        )
        await self._turns.add(turn)
        # 新表（**双写期**，Session 方案 §12）—— 它同时是 ``session_events``
        # 的外键父行：事件必须挂在一个已存在的轮次上。
        await self._journal.start_turn(
            turn_id=turn.id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            session_id=session.id,
            idempotency_key=idempotency_key.value,
            key_strength=idempotency_key.strength,
            agent_version=session.agent_version,
            model_version=model_used,
            trace_id=current_trace_id(),
            # 路由决策随轮次留痕（``session_turns.route_decision``）——
            # **产出者是 Router**，这里只是把它带进轮次行。
            route_decision=session.metadata.get("route_decision"),
        )
        await self._events.publish(
            turn.raise_started_event(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            trace_id=current_trace_id(),
        )
        seq = await self._next_seq(session_id)
        if not resume:
            await self._messages.append(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                session_id=session_id,
                turn_id=turn.id,
                seq=seq,
                role="user",
                content=user_input,
            )
            seq += 1
            # 会话标题还没定的话, 用第一句话当标题 —— 会话列表里全是
            # 「与 XX 对话」根本没法认.
            if session.metadata.get("title_auto"):
                meta = dict(session.metadata)
                meta["title"] = _auto_title(user_input)
                meta["title_auto"] = False
                session = session.with_runtime(metadata=meta)
                await self._sessions.update(session)
        graph_resume = dict(session.graph_state or {})
        if resume:
            graph_resume = {**graph_resume, **resume}
        assistant_parts: list[str] = []
        turn_usage: UsageChunk | None = None
        graph_stream = self._graph.run_turn(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            turn_id=turn.id,
            user_input=user_input,
            history=hist_msgs,
            agent=agent_row,
            model=model_used,
            # Phase 12: 策略路由. 当 route_id 提供时, 优先用它走 Phase 7 select_chain_for_strategy
            route_id=route_id,
            rolling_summary=str(session.metadata.get("rolling_summary") or ""),
            resume=graph_resume
            if graph_resume.get("pending_approval") or resume
            else None,
            # Phase 14: 把 session_id 透给 graph, 让 delegate_to_agent 工具 stub
            # 知道在哪个 session 上 spawn sub-session.
            session_id=session_id,
            parent_span_context=parent_span_context,
        )
        emitted = False
        # 事件序号 —— 轮次内严格递增，且与 SSE 的 ``id:`` 一致（客户端断线
        # 重连时把它作为 ``Last-Event-ID`` 带回来）。
        event_seq = 1
        last_cancel_check = monotonic()
        try:
            async with aclosing(graph_stream):
                async for chunk in graph_stream:
                    emitted = True
                    now = monotonic()
                    if now - last_cancel_check >= CANCEL_POLL_SECONDS:
                        last_cancel_check = now
                        if await self._sessions.cancel_requested(session_id):
                            raise _TurnCancelled("用户请求停止生成")
                    chunk = await self._publish_chunk(turn, chunk, seq=event_seq)
                    event_seq += 1
                    yield chunk
                    if getattr(chunk, "kind", None) == "message":
                        assistant_parts.append(getattr(chunk, "content", "") or "")
                    if isinstance(chunk, ApprovalRequiredChunk):
                        meta = dict(session.metadata)
                        meta["preview"] = "等待确认操作"
                        updated = session.with_runtime(
                            metadata=meta,
                            graph_state=dict(self._graph.last_loop_state),
                            wait_status="waiting_approval",
                        )
                        await self._sessions.update(updated)
                    if isinstance(chunk, UsageChunk):
                        turn_usage = chunk
                    if isinstance(chunk, DoneChunk):
                        final = chunk.final_message or "".join(assistant_parts)
                        await self._messages.append(
                            tenant_id=tenant_id,
                            workspace_id=workspace_id,
                            session_id=session_id,
                            turn_id=turn.id,
                            seq=seq,
                            role="assistant",
                            content=final,
                        )
                        meta = dict(session.metadata)
                        meta["preview"] = final[:80]
                        summary = str(
                            (self._graph.last_loop_state or {}).get("rolling_summary")
                            or meta.get("rolling_summary")
                            or ""
                        )
                        meta["rolling_summary"] = summary
                        updated = session.with_runtime(
                            metadata=meta,
                            graph_state=dict(self._graph.last_loop_state or {}),
                            wait_status="idle",
                        )
                        await self._sessions.update(updated)
                        finished = turn.succeed(
                            final_response=final,
                            input_tokens=turn_usage.input_tokens
                            if turn_usage
                            else None,
                            output_tokens=turn_usage.output_tokens
                            if turn_usage
                            else None,
                            cost_usd=turn_usage.cost_usd if turn_usage else None,
                        )
                        await self._turns.add(finished)
                        await self._journal.finish_turn(
                            turn_id=turn.id,
                            status="succeeded",
                            cost_usd=turn_usage.cost_usd if turn_usage else None,
                        )
                        await self._journal.mark_delivered(turn_id=turn.id)
        except _TurnCancelled as exc:
            await self._fail_turn(turn, code="TURN_CANCELLED", message=str(exc))
            yield await self._publish_chunk(
                turn,
                ErrorChunk(
                    turn_id=turn.id,
                    seq=0,
                    code="TURN_CANCELLED",
                    message="已停止生成",
                    retriable=True,
                ),
                seq=event_seq,
            )
        except (asyncio.CancelledError, GeneratorExit):
            # 客户端断开 / 请求被取消 (GeneratorExit = 响应体生成器被关闭):
            # 轮次必须落到 failed, 否则它会永远停在 running, 任务列表里一直
            # 显示「执行中」.
            with contextlib.suppress(Exception):
                await asyncio.shield(self._fail_turn(turn, code="TURN_CANCELLED"))
            raise
        except Exception as exc:  # 失败必须可见
            _log.warning("copilot turn failed turn_id=%s", turn.id, exc_info=True)
            await self._fail_turn(turn, code="TURN_FAILED", message=str(exc))
            if not emitted:
                # 一个 chunk 都没产出 → 轮次根本没起来. 抛给 HTTP 层, 让状态码
                # 表达失败 (而不是 200 + error 事件).
                raise
            yield await self._publish_chunk(
                turn,
                ErrorChunk(
                    turn_id=turn.id,
                    seq=0,
                    code="TURN_FAILED",
                    # web 投放面：**没写消息的领域异常** → 用投影文案
                    # （别把 "EXTERNAL_SERVICE_ERROR" 甩到聊天气泡里）；
                    # 有具体消息的保留原样，技术细节留在日志 ✓。
                    message=project_error_message(
                        str(getattr(exc, "code", "")),
                        str(exc) or type(exc).__name__,
                        "web",
                    ),
                    retriable=False,
                ),
                seq=event_seq,
            )

    async def _publish_chunk(
        self, turn: Turn, chunk: TurnChunk, *, seq: int
    ) -> TurnChunk:
        """把 chunk 落进事件流并重新编号 —— **落库先于投递**（Session §7）。

        事件序号由**这里**统一分配：轮次内严格递增，与 SSE 的 ``id:`` 一致
        （客户端断线重连时把它作为 ``Last-Event-ID`` 带回来）。

        ⚠️ **重新编号**：上游（graph runner）的 seq 有两套编号空间（chunk 序号
        与消息序号），还会出现重复 —— 直接拿它当事件主键会撞
        ``session_events`` 的 ``(turn_id, seq)``。
        """
        stamped = chunk.model_copy(update={"seq": seq})
        await self._journal.append_event(
            turn_id=turn.id,
            seq=seq,
            event_type=str(stamped.kind),
            payload=stamped.model_dump(mode="json"),
        )
        return stamped

    async def _fail_turn(self, turn: Turn, *, code: str, message: str = "") -> None:
        """Persist a failed turn. Best effort — never raises."""
        try:
            await self._turns.add(
                turn.fail(error_code=code, error_message=message or None)
            )
        except Exception:  # noqa: BLE001
            _log.exception("failed to persist failed turn turn_id=%s", turn.id)
        try:
            await self._journal.finish_turn(
                turn_id=turn.id,
                status="cancelled" if code == "TURN_CANCELLED" else "failed",
                error_code=code,
            )
        except Exception:  # noqa: BLE001
            _log.exception("failed to close session_turns row turn_id=%s", turn.id)

    async def decide_approval(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        session_id: UUID,
        approval_id: UUID,
        approved: bool,
        approval_service: Any | None,
        parent_span_context: Any = None,
    ) -> AsyncIterator[TurnChunk]:
        session = await self._require_session(tenant_id, session_id)
        pending = dict((session.graph_state or {}).get("pending_approval") or {})
        if str(pending.get("approval_id")) != str(approval_id):
            pending["approval_id"] = str(approval_id)
        if approval_service is not None:
            from qzdap_schema.ids import ApprovalId
            from qzdap_schema.ids import TenantId as TId
            from qzdap_schema.ids import UserId as UId

            try:
                if approved:
                    await approval_service.approve(
                        tenant_id=TId(tenant_id),
                        approval_id=ApprovalId(approval_id),
                        approver_id=UId(owner_id),
                    )
                else:
                    await approval_service.deny(
                        tenant_id=TId(tenant_id),
                        approval_id=ApprovalId(approval_id),
                        approver_id=UId(owner_id),
                        reason="user denied",
                    )
            except Exception:
                # 审批失败**必须可见**（台账 X7）—— 吞掉它 = 工具照常执行 ✗✗
                _log.warning(
                    "approval decision failed approval_id=%s",
                    approval_id,
                    exc_info=True,
                )
                raise
        pending["decision"] = "approved" if approved else "denied"
        # 审批恢复路径必须带幂等键 —— 键由 approval_id 派生：同一次审批的重复
        # 点击会撞键（连点两次「同意」只执行一次工具，台账 G10），而下一次
        # 审批（新的 approval_id）不会误伤.
        key = approval_key(str(approval_id), str(pending["decision"]))
        async for chunk in self.stream_turn(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            session_id=session_id,
            user_input="继续",
            resume={
                "pending_approval": pending,
                "decision": pending["decision"],
                "messages": (session.graph_state or {}).get("messages"),
            },
            idempotency_key=key,
            parent_span_context=parent_span_context,
        ):
            yield chunk

    async def request_cancel(self, *, tenant_id: UUID, session_id: UUID) -> bool:
        """Ask the running turn to stop.

        Returns True when a turn was actually in flight. The flag lives in
        the session row, so it reaches the worker that owns the turn.
        """
        session = await self._require_session(tenant_id, session_id)
        live = await self._sessions.request_cancel(session_id)
        _ = session
        return live

    async def require_owned_session(
        self, *, tenant_id: UUID, session_id: UUID, owner_id: UUID
    ) -> Session:
        """Fetch a session, enforcing tenant + owner.

        Used by endpoints that act on behalf of the user (feedback),
        where a tenant-level read is not enough.
        """
        session = await self._require_session(tenant_id, session_id)
        if session.owner_id != owner_id:
            raise SessionNotFound(f"session {session_id} not found")
        return session

    async def decide_plan(
        self,
        *,
        tenant_id: UUID,
        session_id: UUID,
        plan_id: UUID,
        decision: str,
    ) -> None:
        """Persist a plan decision (approve / deny) on the session.

        The decision lands in ``session.graph_state["plan_decisions"]`` so
        the next turn — and the transcript — can see what the user chose.
        """
        session = await self._require_session(tenant_id, session_id)
        graph_state = dict(session.graph_state or {})
        decisions = dict(graph_state.get("plan_decisions") or {})
        decisions[str(plan_id)] = decision
        graph_state["plan_decisions"] = decisions
        await self._sessions.update(session.with_runtime(graph_state=graph_state))

    async def _require_session(self, tenant_id: UUID, session_id: UUID) -> Session:
        session = await self._sessions.get(session_id)
        if session is None or session.tenant_id != tenant_id:
            raise SessionNotFound(f"session {session_id} not found")
        return session

    async def _next_seq(self, session_id: UUID) -> int:
        rows = await self._messages.list_for_session(session_id)
        return (rows[-1]["seq"] + 1) if rows else 0


def _auto_title(user_input: str) -> str:
    """Derive a session title from the first user message."""
    text = " ".join(str(user_input or "").split())
    if len(text) <= 24:
        return text or "新对话"
    return text[:24] + "…"


def _session_card(session: Session) -> dict[str, Any]:
    return {
        "id": str(session.id),
        "title": str(session.metadata.get("title") or "新对话"),
        "preview": str(session.metadata.get("preview") or ""),
        "updatedAt": session.created_at.isoformat(),
        "agentId": str(session.agent_id),
        "waitStatus": session.wait_status,
    }


def _session_detail(
    session: Session,
    *,
    messages: list[dict[str, Any]],
    pending: dict[str, Any] | None,
    agent: CatalogAgent | None,
    agent_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    card = _session_card(session)
    card["messages"] = messages
    card["pendingApproval"] = pending
    card["agent"] = agent.to_catalog_dict() if agent is not None else agent_dict
    card["status"] = session.status.value
    return card


def _task_card(session: Session, latest_turn: Turn | None) -> dict[str, Any]:
    """/api/tasks 派生 — 把 Session + 最新 turn 翻译成前端 Task 形状.

    故意用 session.metadata 存的 agentName / title, 不再 join agents,
    避免跨模块查询失败时整条列表挂掉.
    """
    meta = dict(session.metadata or {})
    title = str(meta.get("title") or "新对话")
    source = str(meta.get("agentName") or session.agent_version or "智能体")
    description = (
        latest_turn.user_input[:120] if latest_turn and latest_turn.user_input else ""
    ).strip()
    if not description:
        description = str(meta.get("preview") or "无内容")

    # 状态映射
    if session.status is SessionStatus.CLOSED:
        if meta.get("archived"):
            status = "已完成"
            priority = "低"
            due = "已归档"
            time_label = "已归档"
        else:
            status = "已完成"
            priority = "中"
            due = "已完成"
            time_label = "已完成"
    elif latest_turn is None:
        status = "待处理"
        priority = "中"
        due = "未排期"
        time_label = "—"
    elif latest_turn.status.value == "running":
        # 轮次挂起等审批时, 展示成「等你确认」而不是「执行中」—— 后者会让人
        # 以为系统还在跑, 实际上球在用户手里.
        if session.wait_status == "waiting_approval":
            status = "待处理"
            priority = "高"
            due = "等你确认"
            time_label = "待确认"
        else:
            status = "执行中"
            priority = "高"
            due = "进行中"
            time_label = "运行中"
    elif latest_turn.status.value == "failed":
        status = "异常"
        priority = "高"
        due = "需要重试"
        time_label = "异常"
    elif latest_turn.status.value == "denied":
        status = "异常"
        priority = "中"
        due = "已拒绝"
        time_label = "已拒绝"
    else:
        status = "待处理"
        priority = "中"
        due = "等你回复"
        time_label = "已完成本轮"

    return {
        "id": str(session.id),
        "title": title,
        "source": source,
        "owner": "我",
        "status": status,
        "due": due,
        "time": time_label,
        "description": description,
        "priority": priority,
    }


__all__ = ["CopilotSessionService"]
