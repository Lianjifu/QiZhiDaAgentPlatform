"""把**记忆策略配置发布到 agent** ✓（B2 的「配置发布与生效」✓ —— M-37 ✓）。

⚠️ **这是窄端口的模块侧实现** ✓ —— 实现在 agent_runtime 模块 ✓（它拥有
agent 目录 ✓），契约在 ``qzdap_agent_runtime.memory.policy`` ✓ ——
Memory 模块**只依赖契约** ✓（层次不倒 ✓ —— §2.2 规则 6 ✓）。

⚠️ **发布 = 写 agent 行** ✓ —— 运行时**只读**那行 ✓（``PolicyBinding`` ✓）
→ 发布完**立刻生效** ✓（不用重启 ✓）。

⚠️ **引用另有一处落点** ✓ —— ``knowledge_refs`` 是 agent 的**另一个字段**
✓（§1.7 ✓）→ 那里才是唯一的引用真相 ✓（不在 ``memory_policy`` 里存第二份 ✗✗）。
"""

from __future__ import annotations

from qzdap.modules.agent_runtime.application.catalog_ports import CatalogAgentRepository
from qzdap_agent_runtime.memory.policy import MemoryPolicyConfig
from qzdap_kernel.ids import TenantId, WorkspaceId


class AgentMemoryPolicyPublisher:
    """把策略配置写到**绑了这个 label 的 agent** 上 ✓。"""

    def __init__(self, repo: CatalogAgentRepository) -> None:
        self._repo = repo

    async def publish(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        label: str,
        config: MemoryPolicyConfig,
    ) -> int:
        """**发布** ✓ —— 返回**改了几条** ✓。

        ⚠️ **只改「已经绑了这个 label」的 agent** ✓ —— 没绑的**不碰** ✓
        （乱改 = 把别人的策略也换了 ✗✗）。
        ⚠️ **没人绑 = 0 条** ✓（不是错误 ✓ —— 但调用方要能分清 ✓）。
        """
        published = 0
        for agent in await self._repo.list_for_workspace(workspace_id):
            if agent.tenant_id != tenant_id:
                continue
            current = dict(agent.memory_policy or {})
            bound = str(current.get("policyLabel") or current.get("policy_label") or "")
            if bound != label:
                continue
            agent.memory_policy = {**current, **config.to_agent_policy(label=label)}
            if config.knowledge_refs:
                # ⚠️ **引用落在另一个字段** ✓（唯一真相 ✓ —— 不存第二份 ✗✗）。
                agent.knowledge_refs = [dict(ref) for ref in config.knowledge_refs]
            await self._repo.update(agent)
            published += 1
        return published


__all__ = ["AgentMemoryPolicyPublisher"]
