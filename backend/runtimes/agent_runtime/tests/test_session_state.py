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
    plan_turn_transition,
    turn_status_of,
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
    [(source, target) for source, targets in SESSION_TRANSITIONS.items() for target in targets],
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
    [(source, target) for source, targets in TURN_TRANSITIONS.items() for target in targets],
)
def test_every_allowed_turn_transition_passes(source: TurnStatus, target: TurnStatus) -> None:
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
def test_every_illegal_turn_transition_raises(source: TurnStatus, target: TurnStatus) -> None:
    with pytest.raises(IllegalTransitionError):
        assert_turn_transition(source, target)


def test_a_queued_turn_can_start_be_cancelled_or_be_reaped() -> None:
    """排队中的轮次只能「开跑」「被取消」「被僵尸接管」✓。

    ⚠️ **``queued → failed`` 合法** ✓ —— 幂等键撞上一个排队途中死掉的轮次
    ✓ → 把它落终态 ✓（不落它就一直占着键 ✗✗）。
    """
    assert TurnStatus.RUNNING in TURN_TRANSITIONS[TurnStatus.QUEUED]
    assert TurnStatus.CANCELLED in TURN_TRANSITIONS[TurnStatus.QUEUED]
    assert TurnStatus.FAILED in TURN_TRANSITIONS[TurnStatus.QUEUED]
    assert TurnStatus.SUCCEEDED not in TURN_TRANSITIONS[TurnStatus.QUEUED]


def test_the_terminal_turn_statuses() -> None:
    assert is_terminal_turn(TurnStatus.SUCCEEDED) is True
    assert is_terminal_turn(TurnStatus.FAILED) is True
    assert is_terminal_turn(TurnStatus.CANCELLED) is True
    assert is_terminal_turn(TurnStatus.RUNNING) is False


# ── 唯一的状态写入点（§13.2 规则 2）────────────────────────────────────────


def test_turn_status_of_normalizes_and_rejects_unknown_statuses() -> None:
    """**状态词表只有一份** ✓ —— 认不出来的直接报错 ✓（不猜 ✓）。"""
    assert turn_status_of("running") is TurnStatus.RUNNING
    assert turn_status_of(TurnStatus.WAITING) is TurnStatus.WAITING
    with pytest.raises(ValueError):
        turn_status_of("done")


def test_plan_turn_transition_returns_the_target_for_a_legal_move() -> None:
    assert plan_turn_transition(TurnStatus.RUNNING, TurnStatus.SUCCEEDED) == "succeeded"
    assert plan_turn_transition("running", TurnStatus.WAITING) == "waiting"
    assert plan_turn_transition(TurnStatus.QUEUED, TurnStatus.RUNNING) == "running"


def test_plan_turn_transition_writes_nothing_for_the_same_status() -> None:
    """同态 = 幂等 ✓ —— 不写 ✓（重复收尾不会把状态改坏 ✓）。"""
    assert plan_turn_transition(TurnStatus.SUCCEEDED, TurnStatus.SUCCEEDED) is None


def test_plan_turn_transition_never_overwrites_a_finished_turn() -> None:
    """⚠️ **已经在终态就不写** ✓ —— 僵尸接管先到就以它为准 ✓。

    （否则一个迟到的「成功」会把僵尸的结论盖掉 ✗✗ —— 状态机说终态不可转移 ✓。）
    """
    assert plan_turn_transition(TurnStatus.FAILED, TurnStatus.SUCCEEDED) is None
    assert plan_turn_transition(TurnStatus.CANCELLED, TurnStatus.FAILED) is None


def test_plan_turn_transition_refuses_to_revive_a_finished_turn() -> None:
    """**终态 → 非终态非法** ✓ —— 把完结的轮次拉回运行 ✗✗ → 报错 ✓。"""
    with pytest.raises(IllegalTransitionError):
        plan_turn_transition(TurnStatus.SUCCEEDED, TurnStatus.RUNNING)


def test_plan_turn_transition_rejects_an_illegal_move() -> None:
    """非法转移**报错** ✓ —— 不是静默忽略 ✓。"""
    with pytest.raises(IllegalTransitionError):
        plan_turn_transition(TurnStatus.RUNNING, TurnStatus.QUEUED)
