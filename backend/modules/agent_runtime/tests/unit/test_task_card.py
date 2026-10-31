"""**任务卡的状态翻译** ✓（``/api/tasks`` ✓）。

⚠️ **轮次状态只有一份** ✓（契约层状态机 ✓ —— 2026-10-31 收口 ✓）——
所以这里**没有**「有损映射」✓：``cancelled``（被取消 ✓）就是被取消 ✓，
**不是**「被拒绝」✗✗（那是审批语义的另一个词 ✓）。

回归锁 ✓：模块侧原先自己定义了一套四值枚举（含 ``denied`` ✓）→ 映射时
``cancelled`` 被折成 ``denied`` ✓ → **用户在任务列表里看到「已拒绝」** ✗✗
（明明是自己取消的 ✓）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from qzdap.modules.agent_runtime.application.copilot import _task_card
from qzdap.modules.agent_runtime.domain import Session, Turn
from qzdap_agent_runtime.session.state import TurnStatus
from qzdap_kernel.ids import AgentId, SessionId, TenantId, TurnId, UserId, WorkspaceId


def _session() -> Session:
    return Session.create(
        id=SessionId(uuid4()),
        tenant_id=TenantId(uuid4()),
        workspace_id=WorkspaceId(uuid4()),
        owner_id=UserId(uuid4()),
        agent_id=AgentId(uuid4()),
        agent_version="v1",
        metadata={"title": "一轮对话", "agentName": "助手"},
    )


def _turn(status: TurnStatus) -> Turn:
    return Turn(
        id=TurnId(uuid4()),
        tenant_id=TenantId(uuid4()),
        workspace_id=WorkspaceId(uuid4()),
        session_id=SessionId(uuid4()),
        user_input="hi",
        status=status,
        started_at=datetime.now(UTC),
    )


def test_a_cancelled_turn_shows_as_cancelled_not_denied() -> None:
    """⚠️ **「已取消」不是「已拒绝」** ✓ —— 用户看见的是自己取消的那一轮 ✓。"""
    card = _task_card(_session(), _turn(TurnStatus.CANCELLED))
    assert card["status"] == "已取消"
    assert card["due"] == "已取消"
    assert card["status"] != "异常"


def test_a_waiting_turn_asks_the_user_to_confirm() -> None:
    """挂起等审批 → **「等你确认」** ✓（不是「执行中」✓ —— 球在用户手里 ✓）。"""
    card = _task_card(_session(), _turn(TurnStatus.WAITING))
    assert card["status"] == "待处理"
    assert card["due"] == "等你确认"


def test_a_session_waiting_for_approval_asks_to_confirm_even_on_a_running_turn() -> None:
    """⚠️ **以「会话正在等审批」为准** ✓ —— 挂起的是**上一轮** ✓ 也得提示 ✓。"""
    card = _task_card(_session(), _turn(TurnStatus.RUNNING), waiting_approval=True)
    assert card["due"] == "等你确认"


def test_a_running_turn_shows_as_running() -> None:
    card = _task_card(_session(), _turn(TurnStatus.RUNNING))
    assert card["status"] == "执行中"
    assert card["due"] == "进行中"


def test_a_failed_turn_shows_as_an_error() -> None:
    card = _task_card(_session(), _turn(TurnStatus.FAILED))
    assert card["status"] == "异常"
    assert card["due"] == "需要重试"
