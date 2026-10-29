"""会话 / 轮次**状态机**的单测（Session 方案 §4）。

⚠️ **全部合法转移 + 全部非法转移都要覆盖** —— 状态机的价值全在「非法转移
报错」这一侧 ✓（静默忽略 = 状态烂在数据里 ✗）。
"""

from __future__ import annotations

import pytest
from qzdap_agent_runtime.session.state import (
    SESSION_TRANSITIONS,
    TURN_TRANSITIONS,
    IllegalTransitionError,
    SessionStatus,
    TurnStatus,
    assert_session_transition,
    assert_turn_transition,
    can_transition_session,
    is_terminal_session,
    is_terminal_turn,
)


def test_the_session_status_covers_every_value_the_table_allows() -> None:
    """领域枚举**不能落后于**表的 check constraint（'running' / 'waiting_approval'
    / 'cancelled' 原先在领域层根本不存在 ✗）。"""
    assert {status.value for status in SessionStatus} == {
        "open",
        "running",
        "waiting_approval",
        "closed",
        "cancelled",
    }


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (source, target)
        for source, targets in SESSION_TRANSITIONS.items()
        for target in targets
    ],
)
def test_every_allowed_session_transition_passes(
    source: SessionStatus, target: SessionStatus
) -> None:
    assert_session_transition(source, target)
    assert can_transition_session(source, target) is True


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (source, target)
        for source in SESSION_TRANSITIONS
        for target in SessionStatus
        if target not in SESSION_TRANSITIONS[source]
    ],
)
def test_every_illegal_session_transition_raises(
    source: SessionStatus, target: SessionStatus
) -> None:
    """非法转移**报错** —— 不是静默忽略 ✓。"""
    with pytest.raises(IllegalTransitionError):
        assert_session_transition(source, target)
    assert can_transition_session(source, target) is False


def test_closed_is_terminal_and_there_is_no_revive_transition() -> None:
    """**复活不是状态转移**（决策 #2）—— 那是创建侧的行为 ✓。"""
    assert is_terminal_session(SessionStatus.CLOSED) is True
    assert is_terminal_session(SessionStatus.CANCELLED) is True
    assert SESSION_TRANSITIONS[SessionStatus.CLOSED] == frozenset()
    assert can_transition_session(SessionStatus.CLOSED, SessionStatus.OPEN) is False


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (source, target)
        for source, targets in TURN_TRANSITIONS.items()
        for target in targets
    ],
)
def test_every_allowed_turn_transition_passes(
    source: TurnStatus, target: TurnStatus
) -> None:
    assert_turn_transition(source, target)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (source, target)
        for source in TURN_TRANSITIONS
        for target in TurnStatus
        if target not in TURN_TRANSITIONS[source]
    ],
)
def test_every_illegal_turn_transition_raises(
    source: TurnStatus, target: TurnStatus
) -> None:
    with pytest.raises(IllegalTransitionError):
        assert_turn_transition(source, target)


def test_a_queued_turn_can_only_start_or_be_cancelled() -> None:
    """排队中的轮次只能「开跑」或「被取消」✓。"""
    assert TurnStatus.RUNNING in TURN_TRANSITIONS[TurnStatus.QUEUED]
    assert TurnStatus.CANCELLED in TURN_TRANSITIONS[TurnStatus.QUEUED]
    assert TurnStatus.SUCCEEDED not in TURN_TRANSITIONS[TurnStatus.QUEUED]


def test_the_terminal_turn_statuses() -> None:
    assert is_terminal_turn(TurnStatus.SUCCEEDED) is True
    assert is_terminal_turn(TurnStatus.FAILED) is True
    assert is_terminal_turn(TurnStatus.CANCELLED) is True
    assert is_terminal_turn(TurnStatus.RUNNING) is False
