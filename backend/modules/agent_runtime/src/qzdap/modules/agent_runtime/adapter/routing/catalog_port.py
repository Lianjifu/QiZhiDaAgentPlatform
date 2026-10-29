"""``AgentCatalogPort`` 的实现 —— **复用既有的 ``AgentCatalogService``**。

⚠️ **不另起一套查询**：候选池直接来自 ``AgentCatalogService.list_admin``
（同一份真相、同一套租户过滤）。策略只是**读**这些 agent 的配置字段，
不改它们（Router 方案 §3.3：不新建策略表）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from qzdap_agent_runtime.router.types import AgentCatalogPort, RoutingAgent

from qzdap.modules.agent_runtime.application.catalog import AgentCatalogService


def _str_tuple(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        raw = (raw,)
    if not isinstance(raw, (list, tuple, set)):
        return ()
    return tuple(str(item).strip() for item in raw if str(item).strip())


class CatalogRoutingAdapter(AgentCatalogPort):
    """把 ``admin_agents`` 的行翻译成 Router 的候选。"""

    def __init__(self, catalog: AgentCatalogService) -> None:
        self._catalog = catalog

    async def list_agents(
        self, *, tenant_id: UUID, workspace_id: UUID
    ) -> tuple[RoutingAgent, ...]:
        rows = await self._catalog.list_admin(workspace_id=workspace_id)
        agents: list[RoutingAgent] = []
        for row in rows:
            agents.append(
                RoutingAgent(
                    agent_id=UUID(str(row["id"])),
                    agent_version=str(row.get("version") or ""),
                    name=str(row.get("name") or ""),
                    category=str(row.get("category") or ""),
                    visible_scope=_str_tuple(row.get("visibleScope")),
                    tags=_str_tuple(row.get("tags")),
                    profile=row.get("profile") or {},
                    status=str(row.get("status") or ""),
                )
            )
        return tuple(agents)


__all__ = ["CatalogRoutingAdapter"]
