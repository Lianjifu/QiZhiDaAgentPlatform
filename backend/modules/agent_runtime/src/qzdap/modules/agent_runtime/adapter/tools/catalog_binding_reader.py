"""``CatalogBindingReader`` —— **从 agent 配置里读声明的绑定集** ✓。

依据：Agent 方案 §5.3.1（绑定集从 **agent 配置** 来 ✓ —— 「管理员配置工具 →
agent 绑定 → 运行时取用」✓）。

⚠️ **配置在 ``admin_agents.tools``** ✓（JSONB ✓）—— 那是 agent_runtime 自己的
表 ✓（不跨模块读别人的表 ✗✗）。

⚠️ **版本不参与筛选** ✓ —— 目录行是**当前发布**的那份配置 ✓；「按版本冻结」
是调用方（Stage 4 选专家时）的事 ✓。
"""

from __future__ import annotations

from uuid import UUID

from qzdap.modules.agent_runtime.application.catalog_ports import CatalogAgentRepository
from qzdap.modules.agent_runtime.application.ports import AgentBindingReader


class CatalogBindingReader(AgentBindingReader):
    """**agent 配置 → 声明的工具 / skill 名** ✓。"""

    def __init__(self, repository: CatalogAgentRepository) -> None:
        self._repository = repository

    async def declared(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        agent_id: UUID,
        agent_version: str,
    ) -> tuple[str, ...]:
        _ = (tenant_id, agent_version)
        agent = await self._repository.get(agent_id)
        if agent is None:
            return ()
        if agent.workspace_id != workspace_id:
            # ⚠️ **作用域外的 agent 不给绑定集** ✓（§5.3.1 的作用域维度 ✓）。
            return ()
        names: list[str] = []
        for entry in agent.tools:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            if not entry.get("enabled", True):
                continue
            if name not in names:
                names.append(name)
        return tuple(names)


__all__ = ["CatalogBindingReader"]
