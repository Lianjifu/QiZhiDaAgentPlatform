"""Gateway ④ Idempotency Guard —— 端口、键阶梯与编排（无框架、无 DB）。

依据：``docs/architecture/session-lifecycle.md``。

**这一层只定义契约**：键怎么来（阶梯）、判定怎么表达（:class:`IdempotencyDecision`）、
落库走哪个端口（:class:`IdempotencyStore`）。**没有 SQL、没有框架依赖** ——
表 ``session_inbox`` 归 Session 层，Gateway 只持端口。

⚠️ **两条 INSERT 路径必须分开**（决策 #5）：strong 走原子 claim，weak 走不带 arbiter
的普通 INSERT —— weak **永不判重**。若二者共用一条语句，weak 会落进唯一索引的冲突面，
两条内容相同、同一分钟桶的消息会互相抑制，**直接违反决策 #5**。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from qzdap_agent_runtime.gateway.types import (
    ChannelType,
    IdempotencyDecision,
    IdempotencyKey,
    KeySource,
)

# ── TTL（§4.2 的表）─────────────────────────────────────────────────────────
CLIENT_REQUEST_TTL = timedelta(hours=24)
PLATFORM_MESSAGE_TTL = timedelta(days=7)
APPROVAL_TTL = timedelta(hours=24)
WEAK_TTL = timedelta(seconds=120)

# 内容指纹的时间桶粒度 —— 60 秒内连发两条内容相同的消息才会撞键（§4.2）。
FINGERPRINT_BUCKET_SECONDS = 60

# 「无 workspace」的哨兵 —— 幂等索引的列是 NOT NULL，NULL 互不相等会让幂等失效（§3.1）。
SENTINEL_WORKSPACE_ID = UUID(int=0)


@dataclass(frozen=True, slots=True)
class InboxScope:
    """幂等键的作用域 —— 对应 ``session_inbox`` 的 (tenant, workspace, channel) 三列。"""

    tenant_id: UUID
    workspace_id: UUID
    channel_id: str

    @classmethod
    def for_web(
        cls,
        *,
        tenant_id: UUID,
        workspace_id: UUID | None,
        channel: ChannelType = ChannelType.WEB,
    ) -> InboxScope:
        """web / api 的合成值约定（§3.1）：channel_id 是 ``'web'`` / ``'api'``，
        workspace 缺省时用哨兵 UUID —— **不能改成 nullable**。"""
        return cls(
            tenant_id=tenant_id,
            workspace_id=workspace_id or SENTINEL_WORKSPACE_ID,
            channel_id=str(channel),
        )


class IdempotencyStore(Protocol):
    """④ 的落库端口 —— 实现由 Session 侧提供（表 ``session_inbox`` 归 Session）。"""

    async def claim(
        self,
        scope: InboxScope,
        key: IdempotencyKey,
        *,
        payload_hash: str,
        external_message_id: str | None,
        trace_id: str,
    ) -> IdempotencyDecision:
        """strong 键的**原子** claim：冲突即重复，不得再跑一轮。"""
        ...

    async def record_weak(
        self,
        scope: InboxScope,
        key: IdempotencyKey,
        *,
        payload_hash: str,
        trace_id: str,
    ) -> IdempotencyDecision:
        """weak 键的落表记录 —— **永不判重、永远放行**（决策 #5）。"""
        ...

    async def mark_completed(self, row_id: UUID, *, turn_id: UUID | None = None) -> None:
        """把一行标记为已完成。"""
        ...

    async def release(self, row_id: UUID) -> None:
        """释放一行 —— **这一轮根本没跑起来**（会话被别的轮次占着）。

        键没被消费，因此要删掉，让调用方用同一个键重试时还能被受理。
        """
        ...


def fit_key(value: str) -> str:
    """把键压进 ``session_inbox.idempotency_key`` 的 128 字符列。

    超长时取 sha256 —— **不截断**：截断会让两个不同的长键前缀相同，
    变成假重复。
    """
    if len(value) <= 128:
        return value
    return hashlib.sha256(value.encode()).hexdigest()


# ── 键的构造（阶梯）────────────────────────────────────────────────────────


def client_request_key(value: str, *, now: datetime | None = None) -> IdempotencyKey:
    """① 客户端显式 ``clientRequestId`` —— strong，TTL 24h。"""
    now = now or datetime.now(UTC)
    return IdempotencyKey(
        value=fit_key(value),
        source=KeySource.CLIENT_REQUEST_ID,
        strength="strong",
        expires_at=now + CLIENT_REQUEST_TTL,
    )


def platform_message_key(value: str, *, now: datetime | None = None) -> IdempotencyKey:
    """② 平台原始事件 ID（飞书 / 企微 / 钉钉）—— strong，TTL 7d。"""
    now = now or datetime.now(UTC)
    return IdempotencyKey(
        value=fit_key(value),
        source=KeySource.PLATFORM_MESSAGE_ID,
        strength="strong",
        expires_at=now + PLATFORM_MESSAGE_TTL,
    )


def approval_key(
    approval_id: str,
    decision: str,
    *,
    now: datetime | None = None,
) -> IdempotencyKey:
    """审批决策的键 —— strong。

    连点两次「同意」必须只执行一次工具（台账 G10）。键里带 ``approval_id``，
    因此**同一次审批**的重复点击会撞键，而**下一次**审批（新的 approval_id）
    不会误伤。

    ⚠️ **键里不能掺进「原轮次的键」**：审批恢复时原轮次的状态已经推进
    （``pending_approval`` 被清空），原键取不到 → 同一个审批两次派生出的键
    不同 → 重复点击挡不住。**键只能由审批自身的稳定标识派生。**
    """
    now = now or datetime.now(UTC)
    value = f"approval|{approval_id}|{decision}"
    return IdempotencyKey(
        value=fit_key(value),
        source=KeySource.APPROVAL_DECISION,
        strength="strong",
        expires_at=now + APPROVAL_TTL,
    )


def payload_fingerprint_key(
    *,
    channel: str,
    chat_id: str,
    user_id: str,
    text: str,
    now: datetime | None = None,
) -> IdempotencyKey:
    """③ 内容指纹 —— **weak**，TTL 120s。

    ``sha256(channel + chat + user + text + time_bucket)``，桶粒度 60 秒。
    weak **只记录、不抑制**（决策 #5）—— 用户连发两条「好的」必须都跑。
    """
    now = now or datetime.now(UTC)
    bucket = int(now.timestamp()) // FINGERPRINT_BUCKET_SECONDS
    digest = hashlib.sha256(
        "|".join([channel, chat_id, user_id, text, str(bucket)]).encode()
    ).hexdigest()
    return IdempotencyKey(
        value=digest,
        source=KeySource.PAYLOAD_FINGERPRINT,
        strength="weak",
        expires_at=now + WEAK_TTL,
    )


def payload_hash_of(*parts: str) -> str:
    """载荷指纹 —— 落进 ``session_inbox.payload_hash``，用于审计与排查。"""
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


# ── ④ 编排 ─────────────────────────────────────────────────────────────────


class IdempotencyGuard:
    """④ Idempotency Guard —— 决定「这一轮能不能跑」。

    **两条路径**（§4.4）：strong 走 :meth:`IdempotencyStore.claim`（原子 claim），
    weak 走 :meth:`IdempotencyStore.record_weak`（落表但**永不判重**）。
    """

    def __init__(self, store: IdempotencyStore) -> None:
        self._store = store

    async def accept(
        self,
        scope: InboxScope,
        key: IdempotencyKey,
        *,
        payload_hash: str = "",
        external_message_id: str | None = None,
        trace_id: str = "",
    ) -> IdempotencyDecision:
        """受理一条入站消息，返回判定结果。"""
        if key.strength == "strong":
            return await self._store.claim(
                scope,
                key,
                payload_hash=payload_hash,
                external_message_id=external_message_id,
                trace_id=trace_id,
            )
        return await self._store.record_weak(
            scope,
            key,
            payload_hash=payload_hash,
            trace_id=trace_id,
        )

    async def complete(self, decision: IdempotencyDecision, *, turn_id: UUID | None = None) -> None:
        """把受理的这一行标记为已完成。"""
        if decision.row_id is None or not decision.should_run:
            return
        await self._store.mark_completed(decision.row_id, turn_id=turn_id)

    async def release(self, decision: IdempotencyDecision) -> None:
        """释放这一行 —— 本轮没跑起来，键不该被消费。"""
        if decision.row_id is None or not decision.should_run:
            return
        await self._store.release(decision.row_id)


__all__ = [
    "APPROVAL_TTL",
    "CLIENT_REQUEST_TTL",
    "FINGERPRINT_BUCKET_SECONDS",
    "PLATFORM_MESSAGE_TTL",
    "SENTINEL_WORKSPACE_ID",
    "WEAK_TTL",
    "IdempotencyGuard",
    "IdempotencyStore",
    "InboxScope",
    "approval_key",
    "client_request_key",
    "payload_fingerprint_key",
    "payload_hash_of",
    "platform_message_key",
]
