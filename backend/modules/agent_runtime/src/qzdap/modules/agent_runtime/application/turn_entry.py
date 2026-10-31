"""**跑一轮**的模块侧入口 ✓（Session S-21b —— `copilot.py` 薄壳退场后的新家 ✓）。

⚠️ **这里只做三件事** ✓：
- **读**：会话 / 历史 / agent ✓（模块侧的领域对象 ✓）；
- **组装**：拼出 :class:`TurnRequest` ✓（契约层不认模块侧的实体 ✓）；
- **翻译**：契约层的异常 → 模块侧的异常 ✓（**HTTP 契约不变** ✓ ——
  409 ``SESSION_BUSY`` ✓ + ``DUPLICATE_REQUEST`` 带 ``turn_id`` ✓）。

⚠️ **幂等 + claim + 转发不在这里** ✓ —— 那是**编排** ✓（契约层的
``TurnRunner.run_turn`` ✓）—— 这里**不重复实现** ✓（那正是「第二套 turn
实现」✗ —— 台账 X2 的教训 ✓）。
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from qzdap.modules.agent_runtime.application.catalog import AgentCatalogService
from qzdap.modules.agent_runtime.application.ports import (
    SessionRepository,
)
from qzdap.modules.agent_runtime.domain import Session, SessionStatus
from qzdap.modules.agent_runtime.domain.errors import (
    DuplicateRequestError,
    SessionBusyError,
    SessionClosedError,
    SessionNotFound,
)
from qzdap_agent_runtime.gateway.types import ChannelType, IdempotencyKey
from qzdap_agent_runtime.session.message import SessionMessagePort
from qzdap_agent_runtime.session.turn_runner import (
    AgentSnapshot,
    DuplicateTurnRequest,
    TurnBusy,
    TurnContext,
    TurnRequest,
    TurnRunner,
)
from qzdap_kernel.contextvars import current_trace_id
from qzdap_kernel.error_codes import ErrorCode
from qzdap_kernel.ids import ModelId
from qzdap_schema.dtos.turn import TurnChunk


class TurnEntryService:
    """**跑一轮**的入口 ✓（web / IM / 内部调用方共用这一条 ✓）。"""

    def __init__(
        self,
        *,
        sessions: SessionRepository,
        messages: SessionMessagePort,
        catalog: AgentCatalogService,
        turn_runner: TurnRunner,
    ) -> None:
        self._sessions = sessions
        self._messages = messages
        self._catalog = catalog
        self._turn_runner = turn_runner

    async def stream(
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
        """跑一轮并产出 chunk 流 ✓。

        ⚠️ **先校验会话存在** ✓ —— 否则「会话不存在」会被误报成「会话忙」✓
        （与旧薄壳同口径 ✓）。
        """
        await self._require_session(tenant_id, session_id)
        context = TurnContext(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            session_id=session_id,
            user_input=user_input,
            model=model,
            route_id=route_id,
            resume=resume,
            client_request_id=client_request_id,
            channel=channel,
            idempotency_key=idempotency_key,
            parent_span_context=parent_span_context,
        )
        try:
            # ⚠️ **显式关掉内层生成器** ✓ —— 客户端断开时 ``GeneratorExit``
            # 落在**这一层**的 ``yield`` 上 ✓（不是内层 ✓）—— 不显式关的话
            # 内层的收尾（轮次落终态 ✓）只能等 GC ✗✗。
            stream = self._turn_runner.run_turn(context=context, factory=self)
            try:
                async for chunk in stream:
                    yield chunk
            finally:
                with contextlib.suppress(Exception):
                    await stream.aclose()
        except DuplicateTurnRequest as exc:
            # ⚠️ **重复请求不是错误**（Gateway 方案 §4.5）—— 上层据此**重放
            # 上一轮的事件流** ✓（带上「上次那一轮的 turn_id」✓）。
            raise DuplicateRequestError(
                "request was already handled",
                code=ErrorCode.DUPLICATE_REQUEST.value,
                turn_id=exc.turn_id,
            ) from exc
        except TurnBusy as exc:
            raise SessionBusyError(
                f"session {session_id} already has a turn in flight",
                code=ErrorCode.SESSION_BUSY.value,
            ) from exc

    async def build(
        self,
        *,
        context: TurnContext,
        turn_id: UUID,
        idempotency_key: IdempotencyKey,
        ingress_seq: int | None,
    ) -> TurnRequest:
        """**读 + 组装**这一轮的请求 ✓（契约层的工厂端口 ✓）。

        ⚠️ **这里读的都是模块侧的领域对象** ✓ —— 契约层不解释它们 ✓，
        只把 ``raw`` 原样递给执行器 ✓。
        """
        session = await self._require_session(context.tenant_id, context.session_id)
        if session.workspace_id != context.workspace_id or session.owner_id != context.owner_id:
            raise SessionNotFound(f"session {context.session_id} not found")
        if session.status is SessionStatus.CLOSED:
            raise SessionClosedError(
                f"session {context.session_id} is closed",
                code=ErrorCode.SESSION_CLOSED.value,
            )
        # 上一轮遗留的停止标记不能影响这一轮.
        await self._sessions.clear_cancel(context.session_id)
        agent_row = await self._catalog.get_published(session.agent_id)
        # 这一轮实际用的模型 —— 轮次表要留痕（``session_turns.model_version``）。
        model_used = context.model or str(
            session.metadata.get("model") or agent_row.model or "default"
        )
        history = await self._messages.list_for_session(context.session_id)
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
        if context.resume:
            resume_state = {**resume_state, **context.resume}
        return TurnRequest(
            tenant_id=context.tenant_id,
            workspace_id=context.workspace_id,
            owner_id=context.owner_id,
            session_id=context.session_id,
            turn_id=turn_id,
            user_input=context.user_input,
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
            resume=context.resume,
            route_id=context.route_id,
            # ⚠️ **摘要只读新列** ✓（Context 方案 §5.1 ✓）—— 旧副本
            # （``metadata`` 里的 ✓）的读写点**已全部归零** ✓（迁移 0047
            # 已把历史行回填 ✓）。
            rolling_summary=session.rolling_summary,
            session_metadata=dict(session.metadata),
            resume_state=resume_state,
            # 路由决策随轮次留痕（``session_turns.route_decision``）——
            # **产出者是 Router**，这里只是把它带进轮次行。
            route_decision=session.metadata.get("route_decision"),
            parent_span_context=context.parent_span_context,
            trace_id=current_trace_id(),
            # ⚠️ **入站序号** ✓（有值 = 排队 ✓ —— Router 方案 §4.2 ✓）。
            ingress_seq=ingress_seq,
            # ⚠️ **IM 渠道不能挂起审批** ✓（没有人能完成审批 ✓ —— 卡片点了
            # 回不来 ✓ → 挂起 = 这一轮卡死 ✗✗）→ **需要审批的工具不暴露** ✓。
            allow_approval=context.channel in (ChannelType.WEB, ChannelType.API),
        )

    async def _require_session(self, tenant_id: UUID, session_id: UUID) -> Session:
        session = await self._sessions.get(session_id)
        if session is None or session.tenant_id != tenant_id:
            raise SessionNotFound(f"session {session_id} not found")
        return session


__all__ = ["TurnEntryService"]
