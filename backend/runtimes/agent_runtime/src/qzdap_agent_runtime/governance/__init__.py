"""治理层的**契约** ✓ —— 数据主体请求（C9 ✓ —— 决策 #8 ✓）。

⚠️ **这里只有契约** ✓ —— 实现归 ``modules/governance`` ✓（分发与汇总 ✓），
各个域的 scope 实现归各自的模块 ✓（记忆域 → ``modules/memory`` ✓）。
"""

from __future__ import annotations

from .data_subject import DataSubjectRequest, DataSubjectScope

__all__ = ["DataSubjectRequest", "DataSubjectScope"]
