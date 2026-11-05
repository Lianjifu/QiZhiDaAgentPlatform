"""**任务清单载荷的前缀** ✓ —— tool 模块与 runtime 共享的**单一真相** ✓。

⚠️ **为什么在 kernel** ✓ —— 两边都要用它 ✓：
- ``modules/tool`` ✓ —— 工具输出里带它 ✓（不依赖 runtime ✓ —— 分层约束 ✓）
- ``runtimes/agent_runtime`` ✓ —— 解析它 ✓（不依赖 modules ✓ —— 分层约束 ✓）

⚠️ **为什么是前缀而不是契约新字段** ✓ —— 工具执行链路的形状是
``{text, artifact}`` ✓（``ToolCallOutput`` ✓）—— 加第三格要动**契约** ✓
（影响所有工具适配器 ✗✗）→ 用前缀**不动契约** ✓。
"""

from __future__ import annotations

#: **todo 载荷的前缀** ✓ —— 工具输出里带它 = 这是一次 todo 更新 ✓。
TODO_PREFIX = "__qzdap_todos__:"

#: 合法状态 ✓（与 runtime 的 ``agent_loop/todos.py`` 同一份 ✓）。
TODO_STATUSES = ("pending", "in_progress", "completed")


__all__ = ["TODO_PREFIX", "TODO_STATUSES"]
