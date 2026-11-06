"""Copilot session facade — 会话生命周期 + 审批 + 取消。

⚠️ **「跑一轮」不在这儿** ✓（S-21b ✓）—— 薄壳退场 ✓（台账 X18 ✓）：
幂等 + claim + 转发在契约层（``TurnRunner.run_turn`` ✓），读 + 组装在模块侧
（``TurnEntryService`` ✓）—— 本类只留**会话生命周期 / 审批 / 取消** ✓。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner
from qzdap.modules.agent_runtime.application.catalog import AgentCatalogService
from qzdap.modules.agent_runtime.application.ports import (
    EventPublisher,
    SessionJournal,
    SessionRepository,
    TurnRepository,
)
from qzdap.modules.agent_runtime.application.turn_entry import TurnEntryService
from qzdap.modules.agent_runtime.application.use_cases.create_session import (
    CreateSessionUseCase,
)
from qzdap.modules.agent_runtime.domain import Session, SessionStatus, Turn
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent
from qzdap.modules.agent_runtime.domain.errors import (
    SessionNotFound,
)
from qzdap_agent_runtime.gateway.idempotency import (
    approval_key,
)
from qzdap_agent_runtime.router.types import RouteDecision
from qzdap_agent_runtime.session.approval import PendingApproval, arguments_digest
from qzdap_agent_runtime.session.message import SessionMessagePort
from qzdap_kernel.error_codes import ErrorCode
from qzdap_kernel.errors import AppError, ConflictError, ValidationError
from qzdap_kernel.ids import (
    AgentId,
    TenantId,
    UserId,
    WorkspaceId,
)
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
        journal: SessionJournal,
        # ⚠️ **跑一轮**归它 ✓（S-21b ✓）—— 本类**只管会话生命周期 + 审批 +
        # 取消** ✓（薄壳已退场 ✓ —— 台账 X18 ✓）。
        turn_entry: TurnEntryService,
    ) -> None:
        self._sessions = sessions
        self._turns = turns
        self._messages = messages
        self._catalog = catalog
        self._events = events
        self._graph = graph
        # 新架构的轮次 + 事件日志 —— 重放的落点（Gateway §4.5）。
        self._journal = journal
        # **跑一轮**的入口 ✓（幂等 + claim + 转发在契约层 ✓）。
        self.turn_entry = turn_entry

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
        async for chunk in self.turn_entry.stream(
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
    elif waiting_approval or latest_turn.status.value == "waiting":
        # 轮次挂起等审批 —— 展示成「等你确认」而不是「执行中」：后者会让人
        # 以为系统还在跑, 实际上球在用户手里.
        #
        # ⚠️ **以「会话正在等审批」为准** ✓（journal 说它等 ✓）—— 哪怕
        # 最新那一轮不是它 ✓（挂起的是**上一轮** ✓ —— 恢复走的是新一轮 ✓）。
        status = "待处理"
        priority = "高"
        due = "等你确认"
        time_label = "待确认"
    elif latest_turn.status.value == "running":
        status = "执行中"
        priority = "高"
        due = "进行中"
        time_label = "运行中"
    elif latest_turn.status.value == "failed":
        status = "异常"
        priority = "高"
        due = "需要重试"
        time_label = "异常"
    elif latest_turn.status.value == "cancelled":
        # ⚠️ **被取消 ≠ 被拒绝** ✓（原先有损映射把它当成 denied ✓ →
        # 用户看见「已拒绝」✗✗ —— 那是另一件事 ✓）。
        status = "已取消"
        priority = "低"
        due = "已取消"
        time_label = "已取消"
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
