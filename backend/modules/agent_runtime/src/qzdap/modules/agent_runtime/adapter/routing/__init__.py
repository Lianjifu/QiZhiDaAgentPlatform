"""Router 端口的模块侧适配（agent_runtime 模块）。

**依赖方向**：模块 → 契约（``qzdap_agent_runtime.router``）——
契约层不反向依赖模块（架构测试守着这条线）。
"""

from qzdap.modules.agent_runtime.adapter.routing.catalog_port import (
    CatalogRoutingAdapter,
)

__all__ = ["CatalogRoutingAdapter"]
