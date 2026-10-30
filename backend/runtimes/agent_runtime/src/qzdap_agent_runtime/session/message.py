"""会话消息的读写端口（Session 方案 §5.2 / §7）。

**为什么要有这一层**：消息**规范真相**是 ``session_messages``（新表），旧表
``agent_session_messages`` 只在**双写期**里被一起写（Stage 2）—— 调用方
（copilot）应该只认**一个**端口，切读 / 停旧写时只改**实现** ✓（不碰调用点）。

**双写期的实现形态**（模块侧的 ``PostgresSessionMessageStore``）：
① 写：新表 + 旧表**都写**（新表带会话内序号 ``session_seq``）；
② 读：**仍读旧表** —— 切读（S-15a）要等对账窗口，不是本 Stage ✓。

**这一层是契约层** —— 不引框架、不引模块；DB 访问走
:class:`SessionMessagePort`（实现在模块侧 ✓）。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class SessionMessagePort(Protocol):
    """会话消息的读写（实现在模块侧 ✓）。"""

    async def list_for_session(self, session_id: UUID) -> list[dict[str, Any]]:
        """会话的消息列表 —— **按会话内顺序**（``seq`` 升序）✓。

        ⚠️ 返回的是 **API 形状**的字典（``role`` / ``content`` /
        ``toolName`` / ``seq`` / ``turnId``）—— 调用方直接把它拼进响应 ✓。
        """
        ...

    async def next_seq(self, *, session_id: UUID) -> int:
        """下一个**轮次内**消息序号 —— 从会话已有的最大序号 +1 ✓。

        ⚠️ 与 ``session_seq``（会话内序号）**不是一回事**：那个由计数器分配
        （原子 ✓），这个是「本轮第几条」的序号 ✓。
        """
        ...

    async def append(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        session_id: UUID,
        turn_id: UUID | None,
        seq: int,
        role: str,
        content: str,
        tool_name: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """追加一条消息 —— ``seq`` 是**轮次内**序号 ✓。

        ⚠️ **会话内序号 ``session_seq`` 由实现自己分配**（原子计数器 ✓）——
        调用方不该自己算（并发下会撞唯一索引 ✗✗）。
        """
        ...


__all__ = ["SessionMessagePort"]
