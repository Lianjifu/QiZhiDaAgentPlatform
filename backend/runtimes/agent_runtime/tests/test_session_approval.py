"""审批挂起的**落库形状**与**参数摘要**（Session 方案 §8）。

⚠️ 「参数被改过」是这套校验的**核心** —— 摘要必须对**键序不敏感** ✓
（否则用户只是把 JSON 的键换个顺序，就会被误判成「参数被改了」✗✗）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from qzdap_agent_runtime.session.approval import PendingApproval, arguments_digest


def test_the_digest_is_the_same_for_the_same_arguments() -> None:
    a = arguments_digest({"path": "/tmp/x", "mode": "r"})
    b = arguments_digest({"path": "/tmp/x", "mode": "r"})
    assert a == b


def test_the_digest_ignores_the_key_order() -> None:
    """键序不同**不算**参数被改 ✓（否则会误杀）。"""
    a = arguments_digest({"path": "/tmp/x", "mode": "r"})
    b = arguments_digest({"mode": "r", "path": "/tmp/x"})
    assert a == b


def test_the_digest_ignores_the_key_order_in_nested_structures() -> None:
    a = arguments_digest({"args": {"b": 1, "a": [1, {"y": 2, "x": 3}]}})
    b = arguments_digest({"args": {"a": [1, {"x": 3, "y": 2}], "b": 1}})
    assert a == b


def test_the_digest_changes_when_an_argument_changes() -> None:
    assert arguments_digest({"path": "/tmp/x"}) != arguments_digest({"path": "/tmp/y"})


def test_the_digest_of_empty_arguments_is_stable() -> None:
    assert arguments_digest({}) == arguments_digest(None)


def test_a_pending_approval_round_trips_through_json() -> None:
    pending = PendingApproval(
        approval_id=uuid4(),
        tool_name="danger_tool",
        arguments_digest=arguments_digest({"path": "/"}),
        session_id=uuid4(),
        turn_id=uuid4(),
        created_at=datetime.now(UTC),
    )
    restored = PendingApproval.from_json(pending.to_json())
    assert restored == pending


def test_unreadable_json_gives_none_instead_of_guessing() -> None:
    """读不懂就返回 ``None`` ✓ —— 不猜（猜错 = 放行一个没校验过的审批 ✗✗）。"""
    assert PendingApproval.from_json(None) is None
    assert PendingApproval.from_json({}) is None
    assert PendingApproval.from_json({"approval_id": "不是 uuid"}) is None
