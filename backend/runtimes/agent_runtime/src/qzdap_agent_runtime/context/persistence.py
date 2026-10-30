"""上下文持久化的**端口** —— manifest 落库 + 摘要写入 ✓。

依据：Context 方案 §5（Persistence）、§5.2（写入时机）、§5.3（与 Session
事件的关系）。

⚠️ **这一层是契约层** —— **不引框架** ✓（SQL 实现在模块侧 ✓）。

⚠️ **manifest 不是事件** ✓（§5.3 ✓）—— 它**不进 outbox** ✓（不投递 ✓）
—— 面向的是审计 / 评测 / 排障 ✓。

⚠️ **写入时机：必须在交付模型之前** ✓（§5.2 ✓）—— 否则模型已经基于某个
上下文回答了，事后却查不到那次的组成 ✗✗（审计与评测就失去依据 ✗）。

⚠️ **``step`` 由 Session 层分配** ✓（§5.1.1 ✓）—— Context 是**无状态
函数** ✓，计数器放在 Context 内部会在重试 / 回放时错位 ✗✗。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class ContextManifestStore(Protocol):
    """上下文清单的落库口 ✓（§5.1 ✓）。"""

    async def save_manifest(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        session_id: UUID,
        turn_id: UUID,
        step: int,
        manifest: dict[str, Any],
        tokens_total: int,
        degraded: dict[str, Any] | None = None,
    ) -> None:
        """落一条 manifest ✓ —— **每次模型调用一条** ✓（决策 #6 ✓）。

        ⚠️ **唯一约束是 ``(turn_id, step)``** ✓ —— 冲突即视为 bug ✓
        （抛错，不静默覆盖 ✗✗）。

        ⚠️ **不投递** ✓ —— manifest 不是事件 ✓（§5.3 ✓）。
        """
        ...

    async def save_rolling_summary(
        self,
        *,
        tenant_id: UUID,
        session_id: UUID,
        summary: str,
    ) -> None:
        """把摘要写进 ``agent_sessions.rolling_summary`` ✓（§5.1 ✓）。

        ⚠️ **新写入只走这一列** ✓（旧副本在 ``metadata`` 里 ✓ —— 清理归
        Stage 4 之后 ✓，因为旧路径仍是当前的写者 ✗）。
        """
        ...


__all__ = ["ContextManifestStore"]
