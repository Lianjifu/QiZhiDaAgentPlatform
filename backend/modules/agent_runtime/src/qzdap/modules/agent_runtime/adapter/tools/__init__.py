"""Tool adapters (cross-module glue).

⚠️ **工具执行只有一个模块侧实现** ✓ —— ``adapter/graph/agent_loop.py`` 的
``ModuleToolRuntime`` ✓（它包着旧的 ``execute_tool`` ✓ —— 那条路最终落到
``modules/tool`` 的 ``InvokeToolUseCase`` ✓ 唯一权威 ✓）。
"""

from qzdap.modules.agent_runtime.adapter.tools.catalog_binding_reader import (
    CatalogBindingReader,
)
from qzdap.modules.agent_runtime.adapter.tools.tool_binding_adapter import (
    ToolBindingAdapter,
)
from qzdap.modules.agent_runtime.adapter.tools.tool_service_adapter import (
    ToolServiceAdapter,
)

__all__ = [
    "CatalogBindingReader",
    "ToolBindingAdapter",
    "ToolServiceAdapter",
]
