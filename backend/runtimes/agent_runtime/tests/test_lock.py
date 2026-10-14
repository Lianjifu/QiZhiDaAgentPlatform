"""Tests for LockManager + acquire_turn_lock / release_turn_lock nodes (§4.2 / §4.3)."""

from __future__ import annotations

import pytest

from qzdap_agent_runtime.execution import (
    InMemoryLockManager,
    LockToken,
    RevisionConflictError,
    SessionBusyError,
)
from qzdap_agent_runtime.graph import nodes
from qzdap_agent_runtime.graph.state import SessionState


# ---------------------------------------------------------------------------
# LockManager 单元测试（InMemoryLockManager）
# ---------------------------------------------------------------------------


class TestInMemoryLockManager:
    def test_acquire_first_time_succeeds(self) -> None:
        mgr = InMemoryLockManager()
        token = mgr.acquire(
            session_id="s-1",
            turn_id="t-1",
            expected_revision=0,
            current_revision=0,
        )
        assert token.session_id == "s-1"
        assert token.turn_id == "t-1"
        assert token.holder_id  # 非空

    def test_acquire_second_turn_raises_session_busy(self) -> None:
        mgr = InMemoryLockManager()
        mgr.acquire(
            session_id="s-1", turn_id="t-1",
            expected_revision=0, current_revision=0,
        )
        with pytest.raises(SessionBusyError) as exc_info:
            mgr.acquire(
                session_id="s-1", turn_id="t-2",  # 不同 turn_id
                expected_revision=0, current_revision=0,
            )
        assert exc_info.value.current_turn_id == "t-1"

    def test_acquire_same_turn_id_succeeds_idempotent(self) -> None:
        """同一 turn_id 重复 acquire 必须幂等（重入语义）。"""
        mgr = InMemoryLockManager()
        mgr.acquire(
            session_id="s-1", turn_id="t-1",
            expected_revision=0, current_revision=0,
        )
        # 同一 turn_id 再次 acquire（典型场景：checkpoint 恢复 + 重试）
        token = mgr.acquire(
            session_id="s-1", turn_id="t-1",
            expected_revision=0, current_revision=0,
        )
        assert token.turn_id == "t-1"

    def test_acquire_revision_mismatch_raises_conflict(self) -> None:
        mgr = InMemoryLockManager()
        with pytest.raises(RevisionConflictError) as exc_info:
            mgr.acquire(
                session_id="s-1", turn_id="t-1",
                expected_revision=0,
                current_revision=5,  # 不匹配
            )
        assert exc_info.value.expected == 0
        assert exc_info.value.current == 5

    def test_release_frees_lock(self) -> None:
        mgr = InMemoryLockManager()
        token = mgr.acquire(
            session_id="s-1", turn_id="t-1",
            expected_revision=0, current_revision=0,
        )
        mgr.release(token)
        # 释放后另一个 turn 可以获取
        new_token = mgr.acquire(
            session_id="s-1", turn_id="t-2",
            expected_revision=0, current_revision=0,
        )
        assert new_token.turn_id == "t-2"

    def test_release_silently_ignores_stale_token(self) -> None:
        """§13.2 节点 19: 释放失败仅记日志，不影响已成功的 turn 状态。"""
        mgr = InMemoryLockManager()
        # 释放一个从未持有的 token → 必须静默忽略
        stale = LockToken(session_id="s-x", turn_id="t-x", holder_id="0")
        mgr.release(stale)  # 不抛异常

    def test_peek_returns_current_holder(self) -> None:
        mgr = InMemoryLockManager()
        assert mgr.peek("s-1") is None
        token = mgr.acquire(
            session_id="s-1", turn_id="t-1",
            expected_revision=0, current_revision=0,
        )
        assert mgr.peek("s-1") == token

    def test_holder_id_is_deterministic_per_session(self) -> None:
        """同一 session_id 必须产出同一 holder_id（Postgres hashtext 等价）。"""
        mgr1 = InMemoryLockManager()
        mgr2 = InMemoryLockManager()
        t1 = mgr1.acquire(
            session_id="s-X", turn_id="t-1",
            expected_revision=0, current_revision=0,
        )
        t2 = mgr2.acquire(
            session_id="s-X", turn_id="t-1",
            expected_revision=0, current_revision=0,
        )
        assert t1.holder_id == t2.holder_id


# ---------------------------------------------------------------------------
# acquire_turn_lock 节点测试
# ---------------------------------------------------------------------------


@pytest.fixture
def lock_mgr() -> InMemoryLockManager:
    """每个测试独立的 fresh InMemoryLockManager，自动注入到节点。"""
    mgr = InMemoryLockManager()
    nodes.set_default_lock_manager(mgr)
    return mgr


@pytest.fixture(autouse=True)
def _reset_lock_manager():
    """每个测试结束后清空默认 lock manager。"""
    yield
    nodes.set_default_lock_manager(None)  # type: ignore[arg-type]


def _state(**kwargs: object) -> SessionState:
    base: SessionState = {  # type: ignore[typeddict-item]
        "session_id": "s-1",
        "turn_id": "t-1",
        "revision": 0,
        "expected_revision": 0,
        "agent_id": "agt-1",
        "trace_id": "tr-1",
    }
    base.update(kwargs)  # type: ignore[typeddict-unknown]
    return base


class TestAcquireTurnLockNode:
    def test_passthrough_when_no_manager_injected(self) -> None:
        """Stage 1 兼容：未注入 LockManager 时节点 passthrough。"""
        nodes.set_default_lock_manager(None)  # type: ignore[arg-type]
        out = nodes.acquire_turn_lock(_state())
        assert out == {}

    def test_acquire_succeeds_writes_pending_approval(self, lock_mgr: InMemoryLockManager) -> None:
        out = nodes.acquire_turn_lock(_state())
        pa = out.get("pending_approval")
        assert pa is not None
        assert pa.get("tool_name") == "turn_lock:t-1"  # type: ignore[union-attr]
        assert pa.get("policy_id") == "turn_lock"  # type: ignore[union-attr]

    def test_session_busy_writes_error_to_state(self, lock_mgr: InMemoryLockManager) -> None:
        # 先占锁（用 t-1）
        lock_mgr.acquire(
            session_id="s-1", turn_id="t-1",
            expected_revision=0, current_revision=0,
        )
        # 用 t-2 试图抢锁
        out = nodes.acquire_turn_lock(_state(turn_id="t-2"))
        errors = out.get("errors") or []
        assert len(errors) == 1
        assert errors[0]["error_code"] == "SESSION_BUSY"  # type: ignore[index]
        assert errors[0]["retriable"] is True  # type: ignore[index]

    def test_revision_conflict_writes_error_to_state(self, lock_mgr: InMemoryLockManager) -> None:
        out = nodes.acquire_turn_lock(_state(revision=5, expected_revision=0))
        errors = out.get("errors") or []
        assert len(errors) == 1
        assert errors[0]["error_code"] == "REVISION_CONFLICT"  # type: ignore[index]
        assert errors[0]["retriable"] is True  # type: ignore[index]

    def test_revision_uses_default_when_expected_missing(self, lock_mgr: InMemoryLockManager) -> None:
        """未传 expected_revision 时 fallback 到 current revision。"""
        out = nodes.acquire_turn_lock(
            _state(revision=3, expected_revision=None)
        )
        # expected=3, current=3 一致，应该成功
        pa = out.get("pending_approval")
        assert pa is not None


# ---------------------------------------------------------------------------
# release_turn_lock 节点测试
# ---------------------------------------------------------------------------


class TestReleaseTurnLockNode:
    def test_passthrough_when_no_manager_injected(self) -> None:
        nodes.set_default_lock_manager(None)  # type: ignore[arg-type]
        out = nodes.release_turn_lock(_state())
        assert out == {}

    def test_passthrough_when_no_pending_approval(self, lock_mgr: InMemoryLockManager) -> None:
        out = nodes.release_turn_lock(_state(pending_approval=None))
        assert out == {}

    def test_release_succeeds_clears_pending_approval(self, lock_mgr: InMemoryLockManager) -> None:
        """先 acquire，再 release，必须清空 pending_approval。"""
        # 先 acquire（注入同一 mgr）
        acquire_out = nodes.acquire_turn_lock(_state())
        # 用 acquire 的 state（含 pending_approval）作为 release 的输入
        full_state = _state(
            **{"pending_approval": acquire_out.get("pending_approval")}
        )
        out = nodes.release_turn_lock(full_state)
        assert out.get("pending_approval") is None

    def test_release_failure_does_not_raise(self, lock_mgr: InMemoryLockManager) -> None:
        """§13.2 节点 19: 释放失败仅记日志，不影响已成功的 turn 状态。"""
        # 构造一个不存在的 holder_id（释放会失败）
        state = _state()
        state["pending_approval"] = {  # type: ignore[typeddict-item]
            "approval_id": "999999",
            "tool_name": "turn_lock:t-1",
            "policy_id": "turn_lock",
        }
        # 不应抛异常
        out = nodes.release_turn_lock(state)
        assert out.get("pending_approval") is None