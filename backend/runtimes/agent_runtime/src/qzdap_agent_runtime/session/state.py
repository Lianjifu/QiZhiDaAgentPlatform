"""会话与轮次的**状态机**（Session 方案 §4）。

**为什么要有它**：会话的「状态」曾散落在两列里 —— `agent_sessions.status`
（`open` / `closed` …）与 `agent_sessions.wait_status`（`idle` / `running` …）
**表达同一件事却取值不一致** —— 那是数据层的**第二套真相** ✗。

⚠️ **2026-10-30 更新**：`wait_status` 那一列**整体退役**（台账 **X6** ✅ ——
互斥迁到 `current_turn_id`，审批挂起落到 `session_turns.pending_approval`，
迁移 0053 DROP 掉它）。本模块把状态与转移**收在一处**，非法转移**报错**
（不是静默忽略）✓。

**两套状态机**（互不重叠）：

- **会话状态机**（§4.2）—— 会话这一行的 ``status``；
- **轮次状态机**（§4.3）—— 轮次这一行的 ``status``。

⚠️ **会话没有「复活」这个转移**（决策 #2）：空闲超时后同一外部会话再次来消息
→ **新建一个会话接管**（旧会话保持 ``closed`` 终态），**不是**状态转移 ✓。
所以转移表里**没有** ``closed → open`` ✓。

**这一层不引框架**（契约层）—— 状态与转移是纯逻辑 ✓。
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum


class SessionStatus(StrEnum):
    """会话状态 —— 沿用 ``agent_sessions.status`` 已有的 check constraint ✓。

    ⚠️ **不新增枚举**（方案 §4.1）—— 表里已有这五个值的约束 ✓。
    """

    OPEN = "open"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class TurnStatus(StrEnum):
    """轮次状态 —— 沿用 ``session_turns.status`` 的枚举 ✓（含 ``queued`` ✓）。"""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


#: 会话状态的合法转移（§4.2）。
#:
#: - ``closed`` 是**终态** —— 复活是**创建侧**的行为（决策 #2 ✓）；
#: - 非法转移**报错**，不静默忽略 ✓。
SESSION_TRANSITIONS: Mapping[SessionStatus, frozenset[SessionStatus]] = {
    SessionStatus.OPEN: frozenset(
        {
            SessionStatus.RUNNING,
            SessionStatus.WAITING_APPROVAL,
            SessionStatus.CANCELLED,
            SessionStatus.CLOSED,
        }
    ),
    SessionStatus.RUNNING: frozenset(
        {
            SessionStatus.OPEN,
            SessionStatus.WAITING_APPROVAL,
            SessionStatus.CANCELLED,
            SessionStatus.CLOSED,
        }
    ),
    SessionStatus.WAITING_APPROVAL: frozenset(
        {
            SessionStatus.RUNNING,
            SessionStatus.OPEN,
            SessionStatus.CANCELLED,
            SessionStatus.CLOSED,
        }
    ),
    SessionStatus.CLOSED: frozenset(),
    SessionStatus.CANCELLED: frozenset(),
}

#: 轮次状态的合法转移（§4.3）。
TURN_TRANSITIONS: Mapping[TurnStatus, frozenset[TurnStatus]] = {
    TurnStatus.QUEUED: frozenset({TurnStatus.RUNNING, TurnStatus.CANCELLED}),
    TurnStatus.RUNNING: frozenset(
        {
            TurnStatus.WAITING,
            TurnStatus.SUCCEEDED,
            TurnStatus.FAILED,
            TurnStatus.CANCELLED,
        }
    ),
    TurnStatus.WAITING: frozenset({TurnStatus.RUNNING, TurnStatus.FAILED, TurnStatus.CANCELLED}),
    TurnStatus.SUCCEEDED: frozenset(),
    TurnStatus.FAILED: frozenset(),
    TurnStatus.CANCELLED: frozenset(),
}

#: 会话的终态 —— 不可再转移 ✓。
TERMINAL_SESSION_STATUSES = frozenset({SessionStatus.CLOSED, SessionStatus.CANCELLED})

#: 轮次的终态 ✓。
TERMINAL_TURN_STATUSES = frozenset({TurnStatus.SUCCEEDED, TurnStatus.FAILED, TurnStatus.CANCELLED})


class IllegalTransitionError(RuntimeError):
    """非法状态转移 —— **报错**，不静默忽略（§4.2）。

    ⚠️ 这不是「用户输入错误」，是**代码写错了** —— 所以是 `RuntimeError`
    而不是 4xx ✓。
    """

    def __init__(self, kind: str, source: str, target: str) -> None:
        super().__init__(f"{kind}: {source} → {target} 是非法转移")
        self.kind = kind
        self.source = source
        self.target = target


def assert_session_transition(source: SessionStatus, target: SessionStatus) -> None:
    """校验一次会话状态转移；非法就抛 :class:`IllegalTransitionError` ✓。"""
    allowed = SESSION_TRANSITIONS.get(source, frozenset())
    if target not in allowed:
        raise IllegalTransitionError("session", str(source), str(target))


def assert_turn_transition(source: TurnStatus, target: TurnStatus) -> None:
    """校验一次轮次状态转移；非法就抛 :class:`IllegalTransitionError` ✓。"""
    allowed = TURN_TRANSITIONS.get(source, frozenset())
    if target not in allowed:
        raise IllegalTransitionError("turn", str(source), str(target))


def can_transition_session(source: SessionStatus, target: SessionStatus) -> bool:
    """这次转移合法吗（不抛异常 ✓ —— 给「要不要报错」的调用点用）。"""
    return target in SESSION_TRANSITIONS.get(source, frozenset())


def is_terminal_session(status: SessionStatus) -> bool:
    return status in TERMINAL_SESSION_STATUSES


def is_terminal_turn(status: TurnStatus) -> bool:
    return status in TERMINAL_TURN_STATUSES


__all__ = [
    "SESSION_TRANSITIONS",
    "TERMINAL_SESSION_STATUSES",
    "TERMINAL_TURN_STATUSES",
    "TURN_TRANSITIONS",
    "IllegalTransitionError",
    "SessionStatus",
    "TurnStatus",
    "assert_session_transition",
    "assert_turn_transition",
    "can_transition_session",
    "is_terminal_session",
    "is_terminal_turn",
]
