"""渠道入站 → 一轮会话（**Session 层**的实现）。

⚠️ **这是「唯一 turn 实现」在渠道侧的落点** —— 旧的
``use_cases/run_turn_to_completion.py``（第二套 turn 实现，台账 **X2**）由
本模块取代 ✓。

三件事，按顺序：

1. **选 agent**（台账 **R19**）：走 **Router 的规则链** ✓ —— 与 web 侧**同一条链**
   ✓（渠道登记的 agent 只是「显式指定」这一条规则的输入 ✓）；
2. **会话粘性**（台账 **R1**）：按 ``channel_session_key`` 找到 / 建一个会话
   —— 同一个渠道 + 同一个聊天 = 同一个会话 ✓（IM 过去每条消息新建会话，
   跨消息没有上下文 ✗）；
3. **跑一轮**：交给 :class:`CopilotSessionService`（它内部是契约层的
   ``TurnRunner`` —— **唯一 turn 实现** ✓）；
4. **汇总结果**：``drain_to_completion``（契约层 ✓，与子代理 / 评估共用
   同一份 ✓）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

from qzdap_agent_runtime.router.strategy import Strategy
from qzdap_agent_runtime.router.types import (
    AgentTarget,
    RouteDecision,
    RoutingRequest,
    RoutingUnavailable,
)
from qzdap_agent_runtime.session.channel_turn import (
    ChannelTurnRequest,
    ChannelTurnResult,
)
from qzdap_agent_runtime.session.completion import drain_to_completion
from qzdap_agent_runtime.session.manager import (
    AgentBinding,
    SessionIdentity,
    SessionManagerPort,
)

from qzdap.modules.agent_runtime.application.copilot import CopilotSessionService
from qzdap.modules.agent_runtime.domain.errors import DuplicateRequestError

_log = logging.getLogger("qzdap.agent_runtime.channel_turn")


class ChannelTurnService:
    """``ChannelTurnPort`` 的实现 ✓。"""

    def __init__(
        self,
        *,
        sessions: SessionManagerPort,
        copilot: CopilotSessionService,
        ports: Callable[[ChannelTurnRequest], Mapping[str, Any]] | None = None,
        strategy: Strategy | None = None,
    ) -> None:
        self._sessions = sessions
        self._copilot = copilot
        # 请求作用域的端口（skill / sandbox / tool）—— **每请求重新绑定** ✓
        # （web 侧由 HTTP 层绑；IM 侧由组合根给一个绑定回调 ✓）。
        self._ports = ports
        # ⚠️ **Router 的规则链** ✓（台账 R19 ✓）—— 渠道入站**也走规则链** ✓
        # （与 web 侧同一条链 ✓ —— 两套路由就不是同一套了 ✗✗）。
        # 没有它 = 旧行为 ✓（直取渠道登记的 agent ✓ —— 开关式降级 ✓）。
        self._strategy = strategy

    async def _route(
        self, request: ChannelTurnRequest
    ) -> tuple[AgentBinding, dict[str, Any]]:
        """**选 agent** ✓（台账 R19 ✓）—— 走 Router 的规则链 ✓。

        ⚠️ **渠道登记的 agent 只是「显式指定」这一条规则的输入** ✓ —— 它
        不再是「直接用这个」✓（否则 IM 就永远走不到业务线 / 用户标签 /
        兜底那几条规则 ✓✗）。

        ⚠️ **粘性优先** ✓ —— 既有会话已绑定的 agent 由规则 1 给出 ✓
        （Session Manager 是它的唯一来源 ✓ —— Router 不自己查会话表 ✓）。

        ⚠️ **路由失败不丢消息** ✓（Router 方案 §3.1 ✓）—— 规则一条都没命中
        时**退回渠道登记的 agent** ✓（而不是把这条消息扔掉 ✓）。
        """
        metadata = dict(request.metadata)
        if self._strategy is None:
            return (
                AgentBinding(
                    agent_id=request.agent_id,
                    agent_version=request.agent_version,
                ),
                metadata,
            )
        sticky: AgentTarget | None = None
        existing = await self._sessions.lookup(
            session_key=request.channel_session_key,
            tenant_id=request.tenant_id,
        )
        if existing is not None:
            sticky = AgentTarget(
                agent_id=existing.agent_id,
                agent_version=existing.agent_version,
            )
        roles = frozenset(str(role) for role in (metadata.get("roles") or ()))
        try:
            decision: RouteDecision = await self._strategy.decide(
                RoutingRequest(
                    tenant_id=request.tenant_id,
                    workspace_id=request.workspace_id,
                    user_id=request.owner_id,
                    explicit_agent_id=request.agent_id,
                    sticky_agent=sticky,
                    roles=roles,
                )
            )
        except RoutingUnavailable:
            # 一条规则都没命中 —— **不丢消息** ✓（退回渠道登记的 agent ✓）。
            _log.warning(
                "channel routing unmatched; falling back to the channel agent",
                extra={
                    "tenant_id": str(request.tenant_id),
                    "workspace_id": str(request.workspace_id),
                },
            )
            return (
                AgentBinding(
                    agent_id=request.agent_id,
                    agent_version=request.agent_version,
                ),
                metadata,
            )
        # ⚠️ **路由决策随会话留痕** ✓ —— 轮次行因此能回答「为什么是这个
        # agent」✓（与 web 侧同口径 ✓）。
        metadata["route_decision"] = decision.to_dict()
        _log.info(
            "channel turn routed",
            extra={
                "session_key": request.channel_session_key,
                "source": decision.source,
                "agent_id": str(decision.agent_id),
            },
        )
        return (
            AgentBinding(
                agent_id=decision.agent_id,
                agent_version=decision.agent_version,
            ),
            metadata,
        )

    async def run(self, request: ChannelTurnRequest) -> ChannelTurnResult:
        binding, metadata = await self._route(request)
        ref = await self._sessions.resolve_or_create(
            identity=SessionIdentity(
                tenant_id=request.tenant_id,
                workspace_id=request.workspace_id,
                owner_id=request.owner_id,
                channel_session_key=request.channel_session_key,
                metadata=metadata,
            ),
            agent=binding,
        )
        if self._ports is not None:
            self._copilot.bind_ports(**dict(self._ports(request)))
        chunks = self._copilot.stream_turn(
            tenant_id=ref.tenant_id,
            workspace_id=ref.workspace_id,
            owner_id=ref.owner_id,
            session_id=ref.session_id,
            user_input=request.user_input,
            channel=request.channel_type,
            idempotency_key=request.idempotency,
        )
        try:
            completion = await drain_to_completion(chunks)
        except DuplicateRequestError:
            # **重复请求不是错误**（Gateway §4.5）—— 同一平台消息重投 → 不跑第二轮 ✓。
            # IM 侧**还没有重放**（事件流重放只接了 web）→ 记一笔就返回 ✓。
            _log.info(
                "channel turn duplicated; skipping",
                extra={"session_id": str(ref.session_id)},
            )
            return ChannelTurnResult(
                session_id=ref.session_id,
                final_message="",
                duplicate=True,
            )
        _log.info(
            "channel turn finished",
            extra={
                "session_id": str(ref.session_id),
                "turn_id": str(completion.turn_id),
                "channel": str(request.channel_type),
                "created_session": ref.created,
            },
        )
        return ChannelTurnResult(
            session_id=ref.session_id,
            final_message=completion.final_message,
            turn_id=completion.turn_id,
            waiting_approval=completion.waiting_approval is not None,
        )


__all__ = ["ChannelTurnService"]
