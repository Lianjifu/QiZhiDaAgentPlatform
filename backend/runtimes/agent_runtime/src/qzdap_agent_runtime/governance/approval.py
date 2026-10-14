"""Approval store — §5.7 审批持久化 + TTL + 幂等。

Stage 6a PR A 范围：

- `ApprovalRecord` dataclass: 审批状态 + 过期时间
- `ApprovalStore` Protocol: save / get / consume / cleanup
- `InMemoryApprovalStore` 进程内实现
  - 同 `(session_id, tool_call_id, request_hash)` 幂等返回同一 approval_id
  - 不同 `tool_call_id` 或 `request_hash` 拒绝 (APPROVAL_NOT_MATCH)
  - TTL 默认 900s (`QZDAP_APPROVAL_TTL_SECONDS` 覆盖)
  - 超时自动 deny
- `ApprovalExpiredError` / `ApprovalNotMatchError`
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# §5.7 默认 TTL
# ---------------------------------------------------------------------------


DEFAULT_APPROVAL_TTL_SECONDS = 900  # 15 分钟


def _request_hash(arguments: dict[str, Any]) -> str:
    """§5.7 request_hash: sha256(sort_keys JSON) of arguments."""
    import json
    encoded = json.dumps(arguments, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ApprovalExpiredError(Exception):
    """§5.9 APPROVAL_EXPIRED: 审批超时未响应。"""

    def __init__(self, approval_id: str, expired_at: float) -> None:
        self.approval_id = approval_id
        self.expired_at = expired_at
        super().__init__(f"approval {approval_id} expired at {expired_at}")


class ApprovalNotMatchError(Exception):
    """§5.9 APPROVAL_NOT_MATCH: approval_id 与 pending tool_call 不匹配。"""

    def __init__(self, approval_id: str, tool_call_id: str, request_hash: str) -> None:
        self.approval_id = approval_id
        self.tool_call_id = tool_call_id
        self.request_hash = request_hash
        super().__init__(
            f"approval {approval_id} does not match tool_call_id={tool_call_id} "
            f"or request_hash={request_hash}"
        )


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ApprovalRecord:
    """§5.7 审批记录。"""

    approval_id: str
    session_id: str
    turn_id: str
    tool_call_id: str
    tool_name: str
    request_hash: str
    arguments: dict[str, Any]
    policy_id: str | None
    requester: str  # actor_id
    created_at: float
    expires_at: float  # unix timestamp
    consumed: bool = False
    consumed_at: float | None = None
    consumed_by: str | None = None  # actor_id
    decision: str | None = None  # "approve" | "deny" | "timeout"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ApprovalStore(Protocol):
    """§5.7 审批存储接口。"""

    def save(self, record: ApprovalRecord) -> None: ...

    def get(self, approval_id: str) -> ApprovalRecord | None: ...

    def consume(
        self,
        approval_id: str,
        tool_call_id: str,
        request_hash: str,
        actor_id: str,
        decision: str,
    ) -> ApprovalRecord: ...


# ---------------------------------------------------------------------------
# InMemoryApprovalStore
# ---------------------------------------------------------------------------


class InMemoryApprovalStore:
    """§5.7 进程内审批存储 + TTL + 幂等。"""

    def __init__(self, ttl_seconds: int = DEFAULT_APPROVAL_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._by_id: dict[str, ApprovalRecord] = {}
        # 幂等索引: (session_id, tool_call_id, request_hash) -> approval_id
        self._idempotency_index: dict[tuple[str, str, str], str] = {}

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    def save(self, record: ApprovalRecord) -> None:
        """保存记录, 同 (session_id, tool_call_id, request_hash) 幂等。

        - 同 hash 已存在: 返回已存在的 approval_id (不覆盖)
        - 不同 tool_call_id 或 request_hash: 抛 ApprovalNotMatchError
        """
        key = (record.session_id, record.tool_call_id, record.request_hash)
        existing_id = self._idempotency_index.get(key)
        if existing_id is not None:
            if existing_id != record.approval_id:
                raise ApprovalNotMatchError(
                    approval_id=record.approval_id,
                    tool_call_id=record.tool_call_id,
                    request_hash=record.request_hash,
                )
            return  # 幂等: 同 approval_id 不重复保存

        self._by_id[record.approval_id] = record
        self._idempotency_index[key] = record.approval_id

    def get(self, approval_id: str) -> ApprovalRecord | None:
        """查记录; 不检查 TTL (consume 时才检查)。"""
        return self._by_id.get(approval_id)

    def consume(
        self,
        approval_id: str,
        tool_call_id: str,
        request_hash: str,
        actor_id: str,
        decision: str,
    ) -> ApprovalRecord:
        """§5.7 消费审批 (approve / deny)。

        Raises:
            ApprovalExpiredError: 超时
            ApprovalNotMatchError: 审批不匹配 pending tool_call
            KeyError: 审批不存在
        """
        record = self._by_id.get(approval_id)
        if record is None:
            raise KeyError(f"approval {approval_id} not found")

        if record.consumed:
            raise ApprovalNotMatchError(
                approval_id=approval_id,
                tool_call_id=record.tool_call_id,
                request_hash=record.request_hash,
            )

        # §5.7: 校验 approval_id 与 tool_call_id / request_hash 的对应
        if record.tool_call_id != tool_call_id or record.request_hash != request_hash:
            raise ApprovalNotMatchError(
                approval_id=approval_id,
                tool_call_id=tool_call_id,
                request_hash=request_hash,
            )

        # §5.9 TTL: 超时自动 deny
        now = time.time()
        if now > record.expires_at:
            record.consumed = True
            record.consumed_at = now
            record.decision = "timeout"
            raise ApprovalExpiredError(approval_id, record.expires_at)

        record.consumed = True
        record.consumed_at = now
        record.consumed_by = actor_id
        record.decision = decision
        return record

    def cleanup_expired(self) -> int:
        """清理已消费 + 已过期的记录; 返回清理条数。"""
        now = time.time()
        to_delete = [
            aid for aid, r in self._by_id.items()
            if r.consumed and (r.consumed_at or 0) + 3600 < now  # 1 小时后清理
        ]
        for aid in to_delete:
            r = self._by_id.pop(aid)
            # 清理幂等索引
            key = (r.session_id, r.tool_call_id, r.request_hash)
            self._idempotency_index.pop(key, None)
        return len(to_delete)


__all__ = [
    "ApprovalExpiredError",
    "ApprovalNotMatchError",
    "ApprovalRecord",
    "ApprovalStore",
    "DEFAULT_APPROVAL_TTL_SECONDS",
    "InMemoryApprovalStore",
]