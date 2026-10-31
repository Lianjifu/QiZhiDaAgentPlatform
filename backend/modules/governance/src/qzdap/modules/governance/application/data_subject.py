"""**数据主体请求**（C9 ✓）—— 删除 / 导出 ✓。

⚠️ **治理域不认识记忆表** ✓ —— 也不该认识 ✗✗ → 它只认 **scope** ✓
（决策 #8 ✓ —— 「记忆模块实现 `data_subject` 的一个 scope」 ✓）。
每个域自己实现一个 scope ✓（``scope: str`` + ``delete`` + ``export`` ✓）——
治理域负责**分发与汇总** ✓，**不碰别人的表** ✓（边界 ✓）。

⚠️ **删不干净要报出来** ✓ —— 一个 scope 失败**不能**当成功 ✓（§2.2 规则 5 ✓）——
但**不能因为一个失败就不删别的** ✓ → **全部跑完** ✓ 再统一报错 ✓。
"""

from __future__ import annotations

from typing import Any

from qzdap.modules.governance.domain.errors import DataSubjectFailed
from qzdap_agent_runtime.governance.data_subject import (
    DataSubjectRequest,
    DataSubjectScope,
)


class DataSubjectService:
    """**按 scope 分发** ✓（注册进来的都跑一遍 ✓）。"""

    def __init__(self, scopes: list[DataSubjectScope] | None = None) -> None:
        self._scopes: dict[str, DataSubjectScope] = {}
        for scope in scopes or []:
            self.register(scope)

    def register(self, scope: DataSubjectScope) -> None:
        """**注册一个 scope** ✓（同名**后者覆盖前者** ✓ —— 免得重复注册踩坑 ✗✗）。"""
        self._scopes[scope.scope] = scope

    @property
    def scopes(self) -> tuple[str, ...]:
        """**已注册的 scope** ✓（管理端要看得见 ✓）。"""
        return tuple(self._scopes)

    async def delete(self, request: DataSubjectRequest) -> dict[str, Any]:
        """**删干净** ✓（逐个 scope ✓）。

        ⚠️ **一个失败不挡别的** ✓ —— 都跑完 ✓ 再报错 ✓（否则「删了一半」
        还显示成功 ✗✗）。
        """
        results, failures = await self._run("delete", request)
        if failures:
            raise DataSubjectFailed(_describe(failures))
        return results

    async def export(self, request: DataSubjectRequest) -> dict[str, Any]:
        """**导出** ✓（逐个 scope ✓ —— 汇总成一个 dict ✓）。"""
        results, failures = await self._run("export", request)
        if failures:
            raise DataSubjectFailed(_describe(failures))
        return results

    async def _run(
        self, action: str, request: DataSubjectRequest
    ) -> tuple[dict[str, Any], dict[str, str]]:
        results: dict[str, Any] = {}
        failures: dict[str, str] = {}
        for name, scope in self._scopes.items():
            try:
                results[name] = await getattr(scope, action)(request)
            except Exception as exc:
                failures[name] = f"{type(exc).__name__}: {exc}"
        return results, failures


def _describe(failures: dict[str, str]) -> str:
    """**失败要说清楚** ✓（哪个 scope 报了什么 ✓）。"""
    return "; ".join(f"{name}: {reason}" for name, reason in sorted(failures.items()))


__all__ = [
    "DataSubjectRequest",
    "DataSubjectScope",
    "DataSubjectService",
]
