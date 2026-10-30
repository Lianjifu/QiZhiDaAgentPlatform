"""Session 层 —— 会话生命周期（Session 方案 §2 / §3 / §4）。

**三个子件**：

- **Manager**（`manager.py`）—— 会话的创建 / 查回 / 关闭（§3）；
- **State**（`state.py`）—— 会话与轮次的状态机 + 转移校验（§4）；
- **Thread**（`sequence.py` / `message.py`）—— 会话内的两个序列与消息读写
  （§5.2，Stage 2 ✓）；
- **turn_runner**（`turn_runner.py`）—— **唯一** turn 实现（§6，**Stage 3** 才
  落地 ✓）。

**边界**：Router 只派生 key、选 agent；**会话实例的创建与查回归本层**
（决策 #10：Router 不直接写会话表 ✓）。
"""

from qzdap_agent_runtime.session.manager import (
    AgentBinding,
    CloseReason,
    SessionCreationConflict,
    SessionIdentity,
    SessionManager,
    SessionManagerPort,
    SessionRef,
    SessionStorePort,
)
from qzdap_agent_runtime.session.message import SessionMessagePort
from qzdap_agent_runtime.session.sequence import (
    SessionSequencePort,
    checkpoint_thread_id,
)
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

__all__ = [
    "SESSION_TRANSITIONS",
    "TURN_TRANSITIONS",
    "AgentBinding",
    "CloseReason",
    "IllegalTransitionError",
    "SessionCreationConflict",
    "SessionIdentity",
    "SessionManager",
    "SessionManagerPort",
    "SessionMessagePort",
    "SessionRef",
    "SessionSequencePort",
    "SessionStatus",
    "SessionStorePort",
    "TurnStatus",
    "assert_session_transition",
    "assert_turn_transition",
    "can_transition_session",
    "checkpoint_thread_id",
    "is_terminal_session",
    "is_terminal_turn",
]
