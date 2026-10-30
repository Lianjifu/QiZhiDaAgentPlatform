"""作用域规则 —— 记忆的三层归属 ✓。

依据：Memory 方案 §3.2（作用域模型 ✓）、§2.8 规则 3（A3 策略层**无 IO** ✓）。

⚠️ **这一层是契约层** —— 纯规则 ✓（不碰数据库 ✓）。

⚠️ **作用域过滤必须下推到 SQL / 向量的 WHERE** ✓（§3.1 第 2 步 ✓）——
在 Python 侧逐行判断是**现状的缺陷** ✗✗（全量加载 + 逐行过滤 ✗）。
"""

from __future__ import annotations

from enum import StrEnum


class MemoryScope(StrEnum):
    """记忆的作用域 ✓（§3.2 ✓）。

    | 作用域 | 谁能召回 |
    |---|---|
    | ``SESSION`` | 仅当前会话 ✓ |
    | ``USER`` | 仅该用户 ✓（L2 个人事实 ✓） |
    | ``WORKSPACE`` | 工作区全体 ✓（L3 团队知识 ✓，受 ACL 约束 ✓） |
    """

    SESSION = "session"
    USER = "user"
    WORKSPACE = "workspace"


#: 层级 → 作用域的默认映射 ✓（§3.2 ✓）。
LAYER_SCOPES: dict[str, MemoryScope] = {
    "l1": MemoryScope.SESSION,
    "l2": MemoryScope.USER,
    "l3": MemoryScope.WORKSPACE,
}


def scope_of_layer(layer: str) -> MemoryScope:
    """层级 → 作用域 ✓（未知层级按**工作区级**处理 ✓ —— 最宽的可见性 ✓）。

    ⚠️ 未知层级放宽可见性是**保守**的选择吗？ ✗ —— 放宽意味着**可能泄漏** ✗✗。
    所以这里**收紧**：未知层级按 ``USER`` ✓（只召回本人 ✓）。
    """
    return LAYER_SCOPES.get(layer.strip().lower(), MemoryScope.USER)


__all__ = ["LAYER_SCOPES", "MemoryScope", "scope_of_layer"]
