"""Memory 层：写入流水线 ✓ / 召回 ✓ / 脱敏 ✓ / 作用域 ✓（Memory 方案 §4 ✓）。

⚠️ **这里没有内存假实现** ✓ —— L1 / L2 / L3 的真实实现归 ``modules/memory`` ✓
（旧的那份 ``InMemoryLayeredMemory`` 已删 ✓ —— 逻辑还是反转的 ✗✗）。
"""

from __future__ import annotations

__all__: list[str] = []
