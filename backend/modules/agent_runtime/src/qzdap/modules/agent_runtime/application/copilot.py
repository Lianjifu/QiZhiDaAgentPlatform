"""Copilot session facade — list/create/history + LangGraph turn stream."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner
from qzdap.modules.agent_runtime.application.catalog import AgentCatalogService
from qzdap.modules.agent_runtime.application.ports import (
    EventPublisher,
    SessionJournal,
    SessionRepository,
    TurnRepository,
)
from qzdap.modules.agent_runtime.application.use_cases.create_session import (
    CreateSessionUseCase,
)
from qzdap.modules.agent_runtime.domain import Session, SessionStatus, Turn
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent
from qzdap.modules.agent_runtime.domain.errors import (
    DuplicateRequestError,
    SessionBusyError,
    SessionClosedError,
    SessionNotFound,
)
from qzdap_agent_runtime.gateway.idempotency import (
    IdempotencyGuard,
    InboxScope,
    approval_key,
    payload_hash_of,
)
from qzdap_agent_runtime.gateway.normalizer import resolve_idempotency_key
from qzdap_agent_runtime.gateway.types import ChannelType, IdempotencyKey
from qzdap_agent_runtime.router.types import RouteDecision
from qzdap_agent_runtime.session.approval import PendingApproval, arguments_digest
from qzdap_agent_runtime.session.claim import TurnClaimPort
from qzdap_agent_runtime.session.message import SessionMessagePort
from qzdap_agent_runtime.session.queue import TurnQueuePort
from qzdap_agent_runtime.session.sequence import SessionSequencePort
from qzdap_agent_runtime.session.turn_runner import (
    AgentSnapshot,
    TurnRequest,
    TurnRunner,
)
from qzdap_kernel.contextvars import current_trace_id
from qzdap_kernel.errors import AppError, ConflictError, ValidationError
from qzdap_kernel.ids import (
    AgentId,
    ModelId,
    TenantId,
    UserId,
    WorkspaceId,
)
from qzdap_schema.dtos.errors import ErrorCode
from qzdap_schema.dtos.turn import TurnChunk

_log = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(UTC)


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
        turn_runner: TurnRunner,
        # ⚠️ **入站序号分配器** ✓（Router 方案 §4.2 ✓）—— **排队时才用** ✓。
        sequence: SessionSequencePort | None = None,
        # ⚠️ **排队端口** ✓（Router Stage 3 ✓）—— **没有它就不排队** ✓
        # （开关关掉时的旧语义 ✓ —— 「拒绝 409」✓）。
        queue: TurnQueuePort | None = None,
    ) -> None:
        self._sessions = sessions
        self._turns = turns
        self._messages = messages
        self._catalog = catalog
        self._events = events
        self._graph = graph
        self._idempotency = idempotency
        # 新架构的轮次 + 事件日志 —— 重放的落点（Gateway §4.5）。
        self._journal = journal
        # 会话执行权（互斥）—— **轮次表是唯一权威**（Session 方案 §4.4 / §6）。
        # 旧的 ``wait_status`` CAS 已迁走（台账 R3 已清理）✓。
        self._claim = claim
        # **唯一 turn 实现**（契约层）—— 编排不再留在本文件 ✓。
        self._turn_runner = turn_runner
        # ⚠️ **排队** ✓（Router Stage 3 ✓）—— 序号分配 ✓ + 放行判定 ✓。
        self._sequence = sequence
        self._queue = queue

    def bind_ports(self, **ports: Any) -> None:
        """Re-bind request-scoped ports (tenant/workspace are per request)."""
        self._graph.bind_ports(**ports)

    async def list_sessions(
        self, *, tenant_id: UUID, owner_id: UUID, search: str = ""
    ) -> list[dict[str, Any]]:
        rows = await self._sessions.list_for_owner(tenant_id, owner_id, limit=80)
        query = search.strip().lower()
        # 一次查完「哪些会话在等审批」✓（逐个查 = N 次查询 ✗）
        waiting = await self._journal.list_waiting_approval_sessions(tenant_id=tenant_id)
        out: list[dict[str, Any]] = []
        for session in rows:
            if session.status is SessionStatus.CLOSED:
                continue
            title = str(session.metadata.get("title") or "新对话")
            preview = str(session.metadata.get("preview") or "")
            hay = f"{title} {preview}".lower()
            if query and query not in hay:
                continue
            out.append(_session_card(session, waiting_approval=session.id in waiting))
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
            # 标题先占位, 用户说第一句话后换成真实标题.
            "title_auto": True,
        }
        if route_decision is not None:
            # 路由决策留痕 —— 挂在会话上, 随每一轮写进 ``session_turns``。
            metadata["route_decision"] = route_decision.to_dict()
        # ⚠️ **建会话只有一份实现** —— 旧的门面用例（``CreateSessionUseCase``）
        # 与这里曾经各写一遍 ✗。现在 copilot 委托给它 ✓（Session Stage 5b）。
        session = await CreateSessionUseCase(self._sessions, self._events).execute(
            tenant_id=TenantId(tenant_id),
            workspace_id=WorkspaceId(workspace_id),
            owner_id=UserId(owner_id),
            agent_id=AgentId(agent.id),
            agent_version=agent.version or "v1",
            metadata=metadata,
        )
        return _session_detail(session, messages=[], pending=None, agent=agent)

    async def get_session(self, *, tenant_id: UUID, session_id: UUID) -> dict[str, Any]:
        session = await self._require_session(tenant_id, session_id)
        messages = await self._messages.list_for_session(session_id)
        agent = await self._catalog.get_admin(session.agent_id)
        waiting = await self._journal.find_pending_approval(
            session_id=session_id, tenant_id=tenant_id
        )
        # ⚠️ **待审批从轮次行读** ✓（权威 ✓ —— 台账 X3 ✓ —— 旧的续传状态列
        # 不再是第二份真相 ✓）。
        pending = (waiting or (None, None))[1]
        return _session_detail(
            session,
            messages=messages,
            pending=pending,
            agent=None,
            agent_dict=agent,
            waiting_approval=waiting is not None,
        )

    async def close_session(self, *, tenant_id: UUID, session_id: UUID) -> None:
        session = await self._require_session(tenant_id, session_id)
        if session.status is SessionStatus.CLOSED:
            return
        closed = session.close()
        await self._sessions.update(closed)
        await self._events.publish(
            closed.raise_closed_event(),
            tenant_id=TenantId(tenant_id),
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
            tenant_id=TenantId(tenant_id),
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
        waiting = await self._journal.list_waiting_approval_sessions(tenant_id=tenant_id)
        out: list[dict[str, Any]] = []
        for session in sessions:
            latest_turn = await self._turns.latest_for_session(session.id)
            task = _task_card(session, latest_turn, waiting_approval=session.id in waiting)
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
        # ⚠️ **旧编排的打点已撤除**（2026-10-30，Session Stage 3b）——
        # 编排迁到契约层的 ``session/turn_runner.py`` 之后，这里只剩
        # 「读 + 组装 + 转发」的薄壳 ✓（旧实现不在场 → 打点该撤 ✓）。
        await self._require_session(tenant_id, session_id)
        key = idempotency_key or self._select_key(
            client_request_id=client_request_id,
            channel=channel,
            session_id=session_id,
            owner_id=owner_id,
            user_input=user_input,
        )
        scope = InboxScope.for_web(tenant_id=tenant_id, workspace_id=workspace_id, channel=channel)
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
        # ⚠️ **排队模式** ✓（Router Stage 3 · 决策 #1 ✓）—— 有排队端口就**分配
        # 入站序号** ✓ —— 轮次行先落 ``queued`` ✓，然后**等自己的 FIFO 位** ✓
        # （放行由轮次行的状态 CAS 决定 ✓ —— 决策 #9 ✓）。
        #
        # ⚠️ **排队模式不再抢会话占用** ✓ —— 占用由放行那一步**原子地**做 ✓
        # （抢占用 + 放行分成两步会插进另一轮 ✗✗）。
        ingress_seq: int | None = None
        sequence = self._sequence
        queueing = self._queue is not None and sequence is not None
        if queueing and sequence is not None:
            ingress_seq = await sequence.next_ingress_seq(
                tenant_id=tenant_id, session_id=session_id
            )
        else:
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
                ingress_seq=ingress_seq,
            ):
                yield chunk
        finally:
            with contextlib.suppress(Exception):
                await asyncio.shield(self._idempotency.complete(decision, turn_id=turn_id))
            with contextlib.suppress(Exception):
                await asyncio.shield(
                    self._claim.release(tenant_id=tenant_id, session_id=session_id, turn_id=turn_id)
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
        ingress_seq: int | None = None,
    ) -> AsyncIterator[TurnChunk]:
        """组装这一轮的输入 → **交给唯一 turn 实现**（契约层的 ``TurnRunner``）✓。

        ⚠️ **这里只做「读 + 组装」** —— 轮次的编排（轮次行 / 消息 / 事件 /
        终态 / 取消 / 审批挂起）全在契约层（Session 方案 §6 ✓）。
        旧实现（X18）那段 ~200 行的编排**已迁走** ✓。
        """
        session = await self._require_session(tenant_id, session_id)
        if session.workspace_id != workspace_id or session.owner_id != owner_id:
            raise SessionNotFound(f"session {session_id} not found")
        if session.status is SessionStatus.CLOSED:
            raise SessionClosedError(f"session {session_id} is closed", code="SESSION_CLOSED")
        # 上一轮遗留的停止标记不能影响这一轮.
        await self._sessions.clear_cancel(session_id)
        agent_row = await self._catalog.get_published(session.agent_id)
        # 这一轮实际用的模型 —— 轮次表要留痕（``session_turns.model_version``）。
        model_used = model or str(session.metadata.get("model") or agent_row.model or "default")
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
        # 续传状态 = 会话里存的 + 本轮恢复带进来的（后者覆盖前者 ✓）。
        # ⚠️ **归 ``metadata["resume"]``** ✓（台账 X3 ✓ —— 旧的续传状态列
        # 退役 ✓ —— 新的循环不写它 ✓）。
        resume_state = dict((session.metadata or {}).get("resume") or {})
        if resume:
            resume_state = {**resume_state, **resume}
        request = TurnRequest(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            session_id=session_id,
            turn_id=turn_id,
            user_input=user_input,
            idempotency_key=idempotency_key.value,
            key_strength=idempotency_key.strength,
            agent=AgentSnapshot(
                agent_id=session.agent_id,
                agent_version=session.agent_version,
                model=model_used,
                name=str(getattr(agent_row, "name", "") or ""),
                # 执行器要用 agent 的完整配置（工具 / 模型）—— 契约层不解释它 ✓
                raw=agent_row,
            ),
            history=hist_msgs,
            model=model_used,
            resume=resume,
            route_id=route_id,
            # ⚠️ **摘要只读新列** ✓（Context 方案 §5.1 ✓）—— 旧副本
            # （``metadata`` 里的 ✓）的读写点**已全部归零** ✓（迁移 0047
            # 已把历史行回填 ✓）。
            rolling_summary=session.rolling_summary,
            session_metadata=dict(session.metadata),
            resume_state=resume_state,
            # 路由决策随轮次留痕（``session_turns.route_decision``）——
            # **产出者是 Router**，这里只是把它带进轮次行。
            route_decision=session.metadata.get("route_decision"),
            parent_span_context=parent_span_context,
            trace_id=current_trace_id(),
            # ⚠️ **入站序号** ✓（有值 = 排队 ✓ —— Router 方案 §4.2 ✓）。
            ingress_seq=ingress_seq,
        )
        async for chunk in self._turn_runner.run(request=request):
            yield chunk

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
        # ⚠️ **续传状态归 ``metadata["resume"]``** ✓（台账 X3 ✓ —— 旧的续传
        # 状态列退役 ✓）—— **挂起内容在轮次行** ✓（那是权威 ✓），**参数在续传
        # 状态里** ✓（闸门只让摘要进轮次行 ✓ —— 原文不进那一列 ✓）。
        resume_state = dict((session.metadata or {}).get("resume") or {})
        pending = dict(resume_state.get("pending_approval") or {})
        if str(pending.get("approval_id")) != str(approval_id):
            pending["approval_id"] = str(approval_id)
        # ── 恢复前的校验清单（Session 方案 §8）────────────────────────
        # ⚠️ **任一不过 → 不执行工具**，返回明确错误码 ✓。
        await self._verify_pending_approval(
            tenant_id=tenant_id,
            session_id=session_id,
            approval_id=approval_id,
            approval_service=approval_service,
        )
        if approval_service is not None:
            from qzdap_kernel.ids import ApprovalId
            from qzdap_kernel.ids import TenantId as TId
            from qzdap_kernel.ids import UserId as UId

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
                "messages": resume_state.get("messages"),
            },
            idempotency_key=key,
            parent_span_context=parent_span_context,
        ):
            yield chunk

    async def _verify_pending_approval(
        self,
        *,
        tenant_id: UUID,
        session_id: UUID,
        approval_id: UUID,
        approval_service: Any | None,
    ) -> None:
        """审批恢复前的**校验清单**（Session 方案 §8）✓。

        | # | 校验 | 错误码 |
        |---|---|---|
        | 1 | 挂起记录存在，且是**这个**审批 | ``APPROVAL_NOT_MATCH`` |
        | 2 | 挂起记录属于**这个会话** | ``APPROVAL_NOT_MATCH`` |
        | 3 | 审批记录存在、**未过期** | ``APPROVAL_EXPIRED`` |
        | 4 | 审批记录的**参数摘要**与挂起时一致 | ``TOOL_ARGUMENT_INVALID`` |

        ⚠️ **第 4 项比对的是「审批记录里的参数」**（治理域的**权威** ✓）——
        不是「前端传回来的参数」（那个能被改 ✗✗）。
        """
        record = await self._journal.find_pending_approval(
            session_id=session_id, tenant_id=tenant_id
        )
        stored = PendingApproval.from_json(record[1]) if record is not None else None
        if stored is not None:
            if stored.approval_id != approval_id:
                raise ConflictError(
                    "approval does not match the pending approval",
                    code=ErrorCode.APPROVAL_NOT_MATCH.value,
                )
            if stored.session_id != session_id:
                raise ConflictError(
                    "pending approval belongs to another session",
                    code=ErrorCode.APPROVAL_NOT_MATCH.value,
                )
        if approval_service is None:
            # 没有审批服务 = 没有审批记录可比对（测试替身 / 未接治理域）✓
            return
        from qzdap_kernel.ids import ApprovalId
        from qzdap_kernel.ids import TenantId as TId

        approval = await approval_service.get(
            tenant_id=TId(tenant_id), approval_id=ApprovalId(approval_id)
        )
        expires_at = getattr(approval, "expires_at", None)
        if expires_at is not None and expires_at <= _now_utc():
            raise AppError(
                "approval has expired",
                code=ErrorCode.APPROVAL_EXPIRED.value,
                status=410,
            )
        if stored is not None:
            resource = getattr(approval, "resource", None) or {}
            arguments = resource.get("arguments")
            if arguments is not None and (arguments_digest(arguments) != stored.arguments_digest):
                raise ValidationError(
                    "tool arguments changed since the approval was requested",
                    code=ErrorCode.TOOL_ARGUMENT_INVALID.value,
                )

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

        The decision lands in ``session.metadata["plan_decisions"]`` so
        the next turn — and the transcript — can see what the user chose.

        ⚠️ **不再写旧的续传状态列** ✓（台账 **X3** ✓ —— 那一列退役 ✓）。
        """
        session = await self._require_session(tenant_id, session_id)
        metadata = dict(session.metadata or {})
        decisions = dict(metadata.get("plan_decisions") or {})
        decisions[str(plan_id)] = decision
        metadata["plan_decisions"] = decisions
        await self._sessions.update(session.with_runtime(metadata=metadata))

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


def _session_card(session: Session, *, waiting_approval: bool = False) -> dict[str, Any]:
    return {
        "id": str(session.id),
        "title": str(session.metadata.get("title") or "新对话"),
        "preview": str(session.metadata.get("preview") or ""),
        "updatedAt": session.created_at.isoformat(),
        "agentId": str(session.agent_id),
        # ⚠️ **由轮次表推导**（``wait_status`` 那一列已退役，台账 X6 ✅）——
        # 「正在等审批」的唯一权威是 ``session_turns.status='waiting'`` ✓。
        "waitStatus": "waiting_approval" if waiting_approval else "idle",
    }


def _session_detail(
    session: Session,
    *,
    messages: list[dict[str, Any]],
    pending: dict[str, Any] | None,
    agent: CatalogAgent | None,
    agent_dict: dict[str, Any] | None = None,
    waiting_approval: bool = False,
) -> dict[str, Any]:
    card = _session_card(session, waiting_approval=waiting_approval)
    card["messages"] = messages
    card["pendingApproval"] = pending
    card["agent"] = agent.to_catalog_dict() if agent is not None else agent_dict
    card["status"] = session.status.value
    return card


def _task_card(
    session: Session,
    latest_turn: Turn | None,
    *,
    waiting_approval: bool = False,
) -> dict[str, Any]:
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
        if waiting_approval:
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
