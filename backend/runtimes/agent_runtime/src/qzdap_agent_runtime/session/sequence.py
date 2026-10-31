"""会话内的两个序列 —— 轮次序 + 消息序（Session 方案 §5.2）。

**两个序列都是「会话内单调」，但归属不同**：

| 序列 | 谁**调用** | 谁**分配**（端口在这层） | 落点 | 唯一性 |
|---|---|---|---|---|
| **轮次序** ``ingress_seq`` | **Router**（入站顺序 = FIFO 顺序 ✓） | Session（语义）· DDL 在 0045 的 ``next_ingress_seq`` | ``session_turns.ingress_seq`` | 唯一索引 ``(session_id, ingress_seq)``（迁移 0046 ✓） |
| **消息序** ``session_seq`` | **Session**（写消息的地方 ✓） | Session · DDL 在 0052 的 ``next_message_seq`` | ``session_messages.session_seq`` | 唯一索引 ``(session_id, session_seq)``（迁移 0046 ✓） |

⚠️ **为什么「分配器在 Session、调用方在 Router」**：DDL 归 Router（0045），
但「会话内怎么排号」是**会话域的语义**（Session 方案 §5.2）—— 放一处，
免得两个层各写一个原子自增，阈值与起始值迟早不一致 ✗。

⚠️ **分配必须原子**：``UPDATE ... SET next_x = next_x + 1 RETURNING`` ——
跨 worker 有效，不需要分布式锁 ✓；而 ``MAX(x) + 1`` 在两个写者之间会撞唯一
索引 ✗✗。

**这一层是契约层** —— 不引框架、不引模块；DB 访问走
:class:`SessionSequencePort`（实现在模块侧 ✓）。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class SessionSequencePort(Protocol):
    """会话内两个序列的**原子分配器**（实现在模块侧 ✓）。"""

    async def next_ingress_seq(self, *, tenant_id: UUID, session_id: UUID) -> int:
        """分配下一个**入站序号**（轮次序）—— 返回值从 1 开始 ✓。

        ⚠️ **调用方是 Router**（入站顺序 = FIFO 顺序 ✓）；分配语义归 Session ✓。
        """
        ...

    async def next_message_seq(self, *, tenant_id: UUID, session_id: UUID) -> int:
        """分配下一个**会话内消息序号** —— 返回值从 1 开始 ✓。

        ⚠️ 与轮次内的 ``seq`` **不是一回事**：``seq`` 是「本轮第几条」，
        ``session_seq`` 是「本会话第几条」—— 上下文重建与重放靠后者 ✓
        （Session 方案 §5.2）。
        """
        ...


__all__ = ["SessionSequencePort"]
