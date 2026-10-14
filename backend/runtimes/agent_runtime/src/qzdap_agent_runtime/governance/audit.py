"""Audit logger — §5.7 治理事件审计。

Stage 6a PR B 范围：

- `AuditEvent` dataclass: actor / session / turn / tool / decision / policy / ttl
- `AuditLogger` Protocol: log_allow / log_deny / log_timeout / log_approve / log_override
- `InMemoryAuditLogger`: 进程内实现, 可注入发布到 governance topic
- 每条治理事件都包含 trace_id, 便于跨服务追踪
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Event kinds (§5.7)
# ---------------------------------------------------------------------------


class AuditKind(str, Enum):
    """§5.7 治理事件类型 (publish 到 governance topic)."""

    ALLOW = "allow"
    DENY = "deny"
    TIMEOUT = "timeout"
    APPROVE = "approve"
    OVERRIDE = "override"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """§5.7 治理审计事件 (每条对应一次 governance 决策)。"""

    kind: AuditKind
    actor_id: str
    session_id: str
    turn_id: str
    tool_call_id: str
    tool_name: str
    policy_id: str | None
    request_hash: str
    trace_id: str | None
    occurred_at: float = field(default_factory=time.time)
    reason: str | None = None  # deny / timeout 时记录原因
    approval_id: str | None = None  # approve 时必填


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class AuditLogger(Protocol):
    """§5.7 审计日志接口 (发布到 governance topic)。"""

    def log(self, event: AuditEvent) -> None: ...


# ---------------------------------------------------------------------------
# InMemoryAuditLogger
# ---------------------------------------------------------------------------


class InMemoryAuditLogger:
    """§5.7 进程内审计实现, 收集所有事件供测试 + 单测验证。

    生产实现可发布到 Kafka / Pulsar / 内部事件总线。
    """

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._log = logging.getLogger("qzdap.audit")

    def log(self, event: AuditEvent) -> None:
        self._events.append(event)
        # 同时打到结构化日志（生产替换为 Kafka producer）
        self._log.info(
            "governance.audit kind=%s actor=%s tool=%s session=%s turn=%s",
            event.kind.value, event.actor_id, event.tool_name,
            event.session_id, event.turn_id,
        )

    def all(self) -> list[AuditEvent]:
        return list(self._events)

    def by_kind(self, kind: AuditKind) -> list[AuditEvent]:
        return [e for e in self._events if e.kind == kind]

    def by_actor(self, actor_id: str) -> list[AuditEvent]:
        return [e for e in self._events if e.actor_id == actor_id]

    def clear(self) -> None:
        self._events.clear()


__all__ = [
    "AuditEvent",
    "AuditKind",
    "AuditLogger",
    "InMemoryAuditLogger",
]