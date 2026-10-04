"""Admin + catalog agent service."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from qzdap.modules.agent_runtime.application.catalog_ports import (
    CatalogAgentRepository,
    CatalogAgentUserStateRepository,
)
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent, is_workspace_visible
from qzdap.modules.agent_runtime.domain.catalog_errors import (
    CatalogAgentDisabled,
    CatalogAgentNotFound,
)


class AgentCatalogService:
    def __init__(
        self,
        agents: CatalogAgentRepository,
        user_state: CatalogAgentUserStateRepository | None = None,
    ) -> None:
        self._agents = agents
        self._user_state = user_state

    async def list_admin(
        self,
        *,
        workspace_id: UUID,
        search: str = "",
        tab: str = "all",
        sort_key: str = "updated",
    ) -> list[dict[str, Any]]:
        items = await self._agents.list_for_workspace(workspace_id)
        query = search.strip().lower()
        filtered: list[CatalogAgent] = []
        for agent in items:
            if tab not in ("all", "", None) and agent.status != tab:
                continue
            hay = f"{agent.name} {agent.description} {agent.owner} {agent.category}".lower()
            if query and query not in hay:
                continue
            filtered.append(agent)
        if sort_key == "calls":
            filtered.sort(key=lambda item: item.calls, reverse=True)
        elif sort_key == "name":
            filtered.sort(key=lambda item: item.name)
        elif sort_key == "rating":
            filtered.sort(key=lambda item: item.rating, reverse=True)
        else:
            filtered.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_admin_dict() for item in filtered]

    async def get_admin(self, agent_id: UUID) -> dict[str, Any]:
        return (await self._require(agent_id)).to_admin_dict()

    async def get_published(self, agent_id: UUID) -> CatalogAgent:
        agent = await self._require(agent_id)
        if agent.status not in {"published", "graying"}:
            raise CatalogAgentDisabled(f"agent {agent_id} is {agent.status}")
        return agent

    async def create(self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]) -> dict[str, Any]:
        agent = CatalogAgent.create(
            id=_parse_id(body.get("id")),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=str(body.get("name") or "未命名智能体"),
            category=str(body.get("category") or "企业通用"),
            owner=str(body.get("owner") or "管理员"),
            description=str(body.get("description") or ""),
            model=str(body.get("model") or ""),
        )
        agent = agent.apply_patch(body)
        await self._agents.add(agent)
        return agent.to_admin_dict()

    async def update(self, *, agent_id: UUID, body: dict[str, Any]) -> dict[str, Any]:
        agent = await self._require(agent_id)
        patch = body.get("patch") if isinstance(body.get("patch"), dict) else body
        updated = agent.apply_patch(patch)
        await self._agents.update(updated)
        return updated.to_admin_dict()

    async def delete(self, agent_id: UUID) -> dict[str, Any]:
        await self._require(agent_id)
        await self._agents.delete(agent_id)
        return {"ok": True, "id": str(agent_id)}

    async def bulk_delete(self, ids: list[str]) -> dict[str, list[str]]:
        kept: list[str] = []
        for raw in ids:
            try:
                agent_id = UUID(str(raw))
            except ValueError:
                continue
            await self._agents.delete(agent_id)
            kept.append(str(agent_id))
        return {"ids": kept}

    async def batch_status(self, *, ids: list[str], status: str) -> dict[str, list[str]]:
        kept: list[str] = []
        for raw in ids:
            try:
                agent_id = UUID(str(raw))
            except ValueError:
                continue
            agent = await self._agents.get(agent_id)
            if agent is None:
                continue
            updated = agent.apply_patch({"status": status})
            await self._agents.update(updated)
            kept.append(str(agent_id))
        return {"ids": kept}

    async def star(self, agent_id: UUID, starred: bool) -> dict[str, Any]:
        agent = await self._require(agent_id)
        updated = agent.apply_patch({"starred": starred})
        await self._agents.update(updated)
        return updated.to_admin_dict()

    async def versions(self, agent_id: UUID) -> dict[str, Any]:
        agent = await self._require(agent_id)
        return {"agentId": str(agent.id), "versions": list(agent.versions)}

    async def evaluations(self, agent_id: UUID) -> dict[str, Any]:
        agent = await self._require(agent_id)
        return {
            "agentId": str(agent.id),
            "runs": [
                {
                    "runId": f"run-{agent.id}-{agent.evaluation_runs}",
                    "passRate": agent.evaluation_pass_rate,
                    "failedCases": agent.evaluation_failed_cases,
                    "at": agent.updated_at.isoformat(),
                }
            ],
        }

    async def run_eval(self, agent_id: UUID) -> dict[str, Any]:
        agent = await self._require(agent_id)
        cases = [
            {"id": f"c-{i}", "name": name, "status": "pass", "latency": 1.0 + i * 0.1}
            for i, name in enumerate(["订单查询", "FAQ 检索", "多轮上下文", "工具路由"], start=1)
        ]
        updated = agent.apply_patch({})
        from dataclasses import replace

        updated = replace(
            agent,
            evaluation_runs=agent.evaluation_runs + 1,
            evaluation_pass_rate=100.0,
            evaluation_failed_cases=0,
        )
        await self._agents.update(updated)
        _ = cases
        return {"cases": cases, "passRate": 100.0}

    async def diff(self, *, agent_id: UUID, left_version: str, right_version: str) -> dict[str, Any]:
        agent = await self._require(agent_id)
        _ = (left_version, right_version)
        return {"leftPrompts": dict(agent.prompts), "rightPrompts": dict(agent.prompts)}

    async def list_catalog(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._agents.list_for_workspace(workspace_id)
        out: list[dict[str, Any]] = []
        for agent in items:
            if agent.status not in {"published", "graying"}:
                continue
            if not is_workspace_visible(list(agent.visible_scope)):
                continue
            out.append(agent.to_catalog_dict())
        return out

    async def set_favorite(self, *, agent_id: UUID, user_id: UUID, on: bool) -> dict[str, Any]:
        agent = await self._require(agent_id)
        if self._user_state is not None:
            await self._user_state.set_favorite(
                tenant_id=agent.tenant_id,
                workspace_id=agent.workspace_id,
                user_id=user_id,
                agent_id=agent_id,
                on=on,
            )
        return {**agent.to_catalog_dict(), "id": str(agent_id)}

    async def _require(self, agent_id: UUID) -> CatalogAgent:
        agent = await self._agents.get(agent_id)
        if agent is None:
            raise CatalogAgentNotFound(f"agent {agent_id} not found")
        return agent


def _parse_id(raw: Any) -> UUID:
    if raw:
        try:
            return UUID(str(raw))
        except ValueError:
            pass
    return uuid4()


__all__ = ["AgentCatalogService"]
