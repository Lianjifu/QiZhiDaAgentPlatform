"""``Retrieval`` —— 记忆检索的**端口** ✓（C2）。

依据：Memory 方案 §3（召回七步 ✓）、§10.1（A2 ``retrieval.py`` ✓）。

⚠️ **这一层是契约层** —— 端口 + 结果形状 ✓（实现归模块侧 ✓）。

⚠️ **七步流水线**（§3.1 ✓）：归一化 → 作用域过滤 → 候选检索 → 去重 →
rerank → 阈值 + top-k → provenance ✓。

⚠️ **作用域过滤必须在 SQL / 向量的 WHERE 里** ✓（§3.1 第 2 步 ✓）——
Python 侧逐行过滤是**现状的缺陷** ✗✗。

⚠️ **abstain** ✓（§3.4 ✓）—— 得分低于阈值时**返回 abstain 信号** ✓，
不硬塞给模型 ✗（「禁止把『没召回』伪装成『没有相关知识』」✓）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RetrievalOutcome:
    """一次召回的结果 ✓。

    ⚠️ ``abstained=True`` 表示「**没找到够格的**」✓（§3.4 ✓）—— 调用方要
    能区分「没有相关知识」与「有但没达标」✗✗。
    """

    hits: list[dict] = field(default_factory=list)
    #: 是否**弃权** ✓（阈值过滤后一条都不剩 ✓）。
    abstained: bool = False
    #: 读取侧是否**降级** ✓（embedding / 向量库不可用 → 纯词法 ✓ —— C10 ✓）。
    degraded: bool = False
    #: 降级原因 ✓（审计 / 排障 ✓）。
    degraded_reason: str = ""


@runtime_checkable
class Retrieval(Protocol):
    """记忆检索 ✓（C2 ✓）。"""

    async def recall(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID | None,
        query: str,
        top_k: int = 8,
        session_id: UUID | None = None,
        extra_l3_entry_ids: tuple[str, ...] = (),
    ) -> RetrievalOutcome:
        """按作用域检索 ✓ —— **过滤下推到存储层** ✓（§3.1 ✓）。"""
        ...


__all__ = ["Retrieval", "RetrievalOutcome"]
