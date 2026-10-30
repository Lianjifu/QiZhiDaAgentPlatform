"""渠道入站 → 一轮会话的**窄端口**（Session 方案 §9 的边界契约）。

⚠️ **为什么是端口而不是直接调用**：IM 的入站在**渠道模块**里（它知道渠道、
服务账号、投递目标），而「跑一轮 + 会话粘性」是**会话层**的事 ✓。两者之间
只留这一个契约 —— 渠道模块**不引模块**（架构测试把关 ✓），会话模块**不知道
渠道的存在** ✓。

**这一层是契约层** —— 不引框架、不引模块 ✓。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from qzdap_agent_runtime.gateway.types import ChannelType, IdempotencyKey


@dataclass(frozen=True, slots=True)
class ChannelTurnRequest:
    """一次渠道入站的轮次输入 ✓。

    ⚠️ **``channel_session_key`` 是粘性的唯一依据** —— 同一个 key 永远落在
    同一个会话上（台账 R1：IM 过去每条消息新建会话，跨消息没有上下文 ✗）。
    """

    tenant_id: UUID
    workspace_id: UUID
    owner_id: UUID
    agent_id: UUID
    agent_version: str
    channel_session_key: str
    channel_type: ChannelType
    user_input: str
    idempotency: IdempotencyKey
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChannelTurnResult:
    """一轮跑完的结果 ✓。"""

    session_id: UUID
    final_message: str
    #: 轮次号 —— **重复请求时没有轮次**（那一轮根本没跑 ✓）。
    turn_id: UUID | None = None
    #: 这一轮**挂在审批上**（没有终态）—— 调用方据此回一句说明 ✓。
    waiting_approval: bool = False
    #: **重复请求**（同一平台消息重投）—— 这一轮**没有跑** ✓。
    duplicate: bool = False


@runtime_checkable
class ChannelTurnPort(Protocol):
    """「渠道消息 → 一轮会话」的唯一入口 ✓。"""

    async def run(self, request: ChannelTurnRequest) -> ChannelTurnResult:
        """跑一轮 —— **会话不存在就按 ``channel_session_key`` 建一个** ✓。

        幂等由 ``request.idempotency`` 承担（键由 Gateway ③ 派生 ✓）——
        同一平台消息重投 → 不跑第二轮 ✓。
        """
        ...


@runtime_checkable
class ChannelTurnFactoryPort(Protocol):
    """**请求作用域**的 :class:`ChannelTurnPort` 工厂 ✓。

    ⚠️ ``session`` 是**请求级 DB 会话** —— 契约层不引框架，所以它的类型是
    ``Any`` ✓（具体类型由模块侧 / 组合根知道 ✓）。
    """

    def for_session(self, session: Any) -> ChannelTurnPort:
        """按请求装配一个「跑一轮」的服务 ✓。"""
        ...


__all__ = [
    "ChannelTurnFactoryPort",
    "ChannelTurnPort",
    "ChannelTurnRequest",
    "ChannelTurnResult",
]
