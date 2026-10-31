"""**数据主体请求**的契约 ✓（C9 ✓ —— 决策 #8 ✓）。

⚠️ **契约放在契约层** ✓ —— 因为**两个方向都要用它** ✓：
治理域**按 scope 分发** ✓，记忆域**实现一个 scope** ✓ ——
两边**不互相 import** ✓（peer 模块隔离 ✓ —— 层次不倒 ✓）。

⚠️ **治理域不认识记忆表** ✓ —— 也不该认识 ✗✗ → 它只认 **scope** ✓
（每个域一个 scope ✓ —— §7.4 ✓）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DataSubjectRequest:
    """**一次数据主体请求** ✓（针对某个用户 ✓）。

    ⚠️ **工作区可选** ✓ —— 有的域按租户删（✓）有的按工作区删（✓）
    → **域自己判断** ✓（域里缺工作区就**明确失败** ✓ —— 不猜 ✓）。
    """

    tenant_id: UUID
    user_id: UUID
    workspace_id: UUID | None = None


@runtime_checkable
class DataSubjectScope(Protocol):
    """**一个数据域的删除 / 导出能力** ✓（决策 #8 ✓）。"""

    #: **scope 的名字** ✓（注册表按它去重 ✓ —— 重复注册**后者覆盖前者** ✓）。
    scope: str

    async def delete(self, request: DataSubjectRequest) -> dict[str, Any]:
        """**删掉这个用户在本域的数据** ✓（返回删了多少 ✓）。"""
        ...

    async def export(self, request: DataSubjectRequest) -> dict[str, Any]:
        """**导出这个用户在本域的数据** ✓（返回可序列化的内容 ✓）。"""
        ...


__all__ = ["DataSubjectRequest", "DataSubjectScope"]
