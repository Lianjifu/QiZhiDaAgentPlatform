"""会话的**执行权**（一轮一个）—— 轮次表是唯一权威（Session 方案 §6 / §4.4）。

**旧实现**：``agent_sessions.wait_status`` 的 CAS（``try_claim``）—— 语义是
「会话执行权」与「审批挂起」**混装在同一列** ✗（台账 X6 / R3）。

**新实现**：``agent_sessions.current_turn_id`` + ``session_turns.status`` 推导
（方案 §4.4 ✓）——
- **claim** = 会话行上的**原子 CAS**：``current_turn_id`` 为空，或它指向的
  轮次**已到终态 / 已是僵尸**（超过阈值没人管）→ 可以接管；
- **谁在飞** = ``current_turn_id`` 非空 → 不用问「会话是不是 running」✗。

⚠️ **僵尸阈值复用同一个来源**（``CLAIM_STALE_MINUTES``，30 分钟）—— 两处各写
一个数字，迟早不一致 ✗。

⚠️ **claim 不需要轮次行已存在**：``turn_id`` 由调用方**预先生成**，claim
之后才建轮次行 —— 这样「会话忙」时**不会留下一行失败的轮次** ✗✗（那是给
用户看的噪音）。

**这一层是契约层** —— 不引框架、不引模块；DB 访问走 :class:`TurnClaimPort`
（实现在模块侧 ✓）。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from qzdap_agent_runtime.session.state import TurnStatus


@runtime_checkable
class TurnClaimPort(Protocol):
    """会话执行权的占用与释放（实现在模块侧 ✓）。"""

    async def claim(self, *, tenant_id: UUID, session_id: UUID, turn_id: UUID) -> bool:
        """占用会话的执行权 —— **成功 ``True`` / 已被占用 ``False``** ✓。

        ⚠️ **原子**：两个并发请求只有一个能拿到执行权 —— 否则两轮的消息会
        交错、会话内序号会撞 ✗✗。
        """
        ...

    async def release(self, *, tenant_id: UUID, session_id: UUID, turn_id: UUID) -> None:
        """释放执行权 —— **只释放自己占的那个**（别人的不动 ✓）。"""
        ...

    async def current_turn_status(self, *, tenant_id: UUID, session_id: UUID) -> TurnStatus | None:
        """当前轮次的状态 —— **没有在飞的轮次就是 ``None``** ✓。

        用于「这一轮是不是真的在跑」（取消 / 展示）—— 不再问
        ``wait_status`` ✗（那列的语义是混装的老问题）。
        """
        ...


__all__ = ["TurnClaimPort"]
