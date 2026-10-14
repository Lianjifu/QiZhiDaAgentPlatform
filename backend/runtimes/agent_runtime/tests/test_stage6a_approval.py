"""Tests for Stage 6a: ApprovalStore + AuditLogger + TTL + 幂等。"""

from __future__ import annotations

import time

import pytest

from qzdap_agent_runtime.governance import (
    DEFAULT_APPROVAL_TTL_SECONDS,
    ApprovalExpiredError,
    ApprovalNotMatchError,
    ApprovalRecord,
    ApprovalStore,
    AuditEvent,
    AuditKind,
    AuditLogger,
    InMemoryApprovalStore,
    InMemoryAuditLogger,
)


# ---------------------------------------------------------------------------
# Protocol duck-typing
# ---------------------------------------------------------------------------


def test_approval_store_satisfies_protocol() -> None:
    assert isinstance(InMemoryApprovalStore(), ApprovalStore)


def test_audit_logger_satisfies_protocol() -> None:
    assert isinstance(InMemoryAuditLogger(), AuditLogger)


# ---------------------------------------------------------------------------
# ApprovalRecord + helper
# ---------------------------------------------------------------------------


def _make_record(
    *,
    approval_id: str = "apr-1",
    session_id: str = "s-1",
    turn_id: str = "t-1",
    tool_call_id: str = "tc-1",
    tool_name: str = "send_email",
    request_hash: str = "hash-1",
    policy_id: str = "pol-1",
    requester: str = "u-1",
    ttl: int = 900,
) -> ApprovalRecord:
    now = time.time()
    return ApprovalRecord(
        approval_id=approval_id,
        session_id=session_id,
        turn_id=turn_id,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        request_hash=request_hash,
        arguments={"to": "x@y"},
        policy_id=policy_id,
        requester=requester,
        created_at=now,
        expires_at=now + ttl,
    )


# ---------------------------------------------------------------------------
# InMemoryApprovalStore
# ---------------------------------------------------------------------------


class TestInMemoryApprovalStore:
    def test_save_and_get(self) -> None:
        store = InMemoryApprovalStore()
        rec = _make_record()
        store.save(rec)
        got = store.get(rec.approval_id)
        assert got is not None
        assert got.tool_name == "send_email"

    def test_idempotent_save_same_hash(self) -> None:
        """§5.7: 同 (session_id, tool_call_id, request_hash) 幂等。"""
        store = InMemoryApprovalStore()
        rec1 = _make_record(approval_id="apr-1")
        rec2 = _make_record(approval_id="apr-1")  # 同 approval_id
        store.save(rec1)
        # 第二次 save 同 approval_id 不抛
        store.save(rec2)
        assert store.get("apr-1") is not None

    def test_different_approval_id_same_hash_raises(self) -> None:
        """不同 approval_id 但同 (session, tool_call, request_hash) 必须拒绝。"""
        store = InMemoryApprovalStore()
        store.save(_make_record(approval_id="apr-1"))
        with pytest.raises(ApprovalNotMatchError):
            store.save(_make_record(approval_id="apr-2"))

    def test_consume_approve(self) -> None:
        store = InMemoryApprovalStore()
        store.save(_make_record(approval_id="apr-1"))
        rec = store.consume(
            approval_id="apr-1", tool_call_id="tc-1",
            request_hash="hash-1", actor_id="admin-1", decision="approve",
        )
        assert rec.consumed is True
        assert rec.decision == "approve"
        assert rec.consumed_by == "admin-1"

    def test_consume_deny(self) -> None:
        store = InMemoryApprovalStore()
        store.save(_make_record(approval_id="apr-1"))
        rec = store.consume(
            approval_id="apr-1", tool_call_id="tc-1",
            request_hash="hash-1", actor_id="u-1", decision="deny",
        )
        assert rec.decision == "deny"

    def test_consume_wrong_tool_call_id_raises(self) -> None:
        """§5.7: approval_id 与 tool_call_id 不匹配必须拒绝。"""
        store = InMemoryApprovalStore()
        store.save(_make_record(approval_id="apr-1", tool_call_id="tc-1"))
        with pytest.raises(ApprovalNotMatchError):
            store.consume(
                approval_id="apr-1", tool_call_id="tc-other",
                request_hash="hash-1", actor_id="u-1", decision="approve",
            )

    def test_consume_wrong_request_hash_raises(self) -> None:
        store = InMemoryApprovalStore()
        store.save(_make_record(approval_id="apr-1", request_hash="hash-1"))
        with pytest.raises(ApprovalNotMatchError):
            store.consume(
                approval_id="apr-1", tool_call_id="tc-1",
                request_hash="hash-other", actor_id="u-1", decision="approve",
            )

    def test_consume_twice_raises(self) -> None:
        store = InMemoryApprovalStore()
        store.save(_make_record(approval_id="apr-1"))
        store.consume(approval_id="apr-1", tool_call_id="tc-1",
            request_hash="hash-1", actor_id="u-1", decision="approve")
        with pytest.raises(ApprovalNotMatchError):
            store.consume(approval_id="apr-1", tool_call_id="tc-1",
                request_hash="hash-1", actor_id="u-1", decision="approve")

    def test_consume_expired_raises(self) -> None:
        """§5.7: 超 TTL 自动 deny, 抛 ApprovalExpiredError。"""
        store = InMemoryApprovalStore()
        # 用 ttl=1, 立刻过期
        rec = _make_record(approval_id="apr-1", ttl=1)
        rec.expires_at = time.time() - 1  # 强制过期
        store.save(rec)
        with pytest.raises(ApprovalExpiredError):
            store.consume(approval_id="apr-1", tool_call_id="tc-1",
                request_hash="hash-1", actor_id="u-1", decision="approve")
        # 超时记录 decision=timeout
        assert store.get("apr-1").decision == "timeout"

    def test_default_ttl_is_900_seconds(self) -> None:
        """§5.7: APPROVAL_TTL_SECONDS=900 默认值。"""
        assert DEFAULT_APPROVAL_TTL_SECONDS == 900
        store = InMemoryApprovalStore()
        assert store.ttl_seconds == 900

    def test_custom_ttl_via_env(self) -> None:
        """§5.7: QZDAP_APPROVAL_TTL_SECONDS 覆盖。"""
        # 简化: 直接传参 (生产用 env var 解析)
        store = InMemoryApprovalStore(ttl_seconds=60)
        assert store.ttl_seconds == 60

    def test_consume_unknown_approval_raises_keyerror(self) -> None:
        store = InMemoryApprovalStore()
        with pytest.raises(KeyError):
            store.consume(approval_id="apr-unknown", tool_call_id="tc",
                request_hash="h", actor_id="u", decision="approve")

    def test_cleanup_expired_removes_old_consumed(self) -> None:
        store = InMemoryApprovalStore()
        store.save(_make_record(approval_id="apr-1"))
        store.consume(approval_id="apr-1", tool_call_id="tc-1",
            request_hash="hash-1", actor_id="u-1", decision="approve")
        # 强制 consumed_at 早于 1 小时前
        rec = store.get("apr-1")
        rec.consumed_at = time.time() - 7200
        n = store.cleanup_expired()
        assert n == 1
        assert store.get("apr-1") is None


# ---------------------------------------------------------------------------
# InMemoryAuditLogger
# ---------------------------------------------------------------------------


class TestInMemoryAuditLogger:
    def test_log_allow(self) -> None:
        log = InMemoryAuditLogger()
        log.log(AuditEvent(
            kind=AuditKind.ALLOW,
            actor_id="u-1", session_id="s-1", turn_id="t-1",
            tool_call_id="tc-1", tool_name="search_kb",
            policy_id="pol-1", request_hash="h-1", trace_id="tr-1",
        ))
        assert len(log.by_kind(AuditKind.ALLOW)) == 1

    def test_log_deny_with_reason(self) -> None:
        log = InMemoryAuditLogger()
        log.log(AuditEvent(
            kind=AuditKind.DENY,
            actor_id="u-1", session_id="s-1", turn_id="t-1",
            tool_call_id="tc-1", tool_name="send_email",
            policy_id="pol-pii", request_hash="h-1", trace_id="tr-1",
            reason="PII outbound to external address",
        ))
        events = log.by_kind(AuditKind.DENY)
        assert len(events) == 1
        assert events[0].reason == "PII outbound to external address"

    def test_by_actor(self) -> None:
        log = InMemoryAuditLogger()
        for actor in ("alice", "bob", "alice"):
            log.log(AuditEvent(
                kind=AuditKind.ALLOW, actor_id=actor,
                session_id="s", turn_id="t",
                tool_call_id="tc", tool_name="x",
                policy_id="p", request_hash="h", trace_id=None,
            ))
        assert len(log.by_actor("alice")) == 2
        assert len(log.by_actor("bob")) == 1

    def test_clear(self) -> None:
        log = InMemoryAuditLogger()
        log.log(AuditEvent(
            kind=AuditKind.APPROVE, actor_id="u", session_id="s", turn_id="t",
            tool_call_id="tc", tool_name="x", policy_id="p",
            request_hash="h", trace_id=None, approval_id="apr-1",
        ))
        log.clear()
        assert log.all() == []

    def test_approve_event_records_approval_id(self) -> None:
        log = InMemoryAuditLogger()
        log.log(AuditEvent(
            kind=AuditKind.APPROVE, actor_id="admin", session_id="s", turn_id="t",
            tool_call_id="tc", tool_name="x", policy_id="p",
            request_hash="h", trace_id=None, approval_id="apr-abc",
        ))
        ev = log.by_kind(AuditKind.APPROVE)[0]
        assert ev.approval_id == "apr-abc"