"""Admin agent catalog unit tests."""

from __future__ import annotations

from uuid import UUID

import pytest

from qzdap.modules.agent_runtime.application.catalog import AgentCatalogService
from qzdap.modules.agent_runtime.application.catalog_ports import (
    CatalogAgentRepository,
    CatalogAgentUserStateRepository,
)
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent
from qzdap.modules.agent_runtime.domain.catalog_errors import CatalogAgentDisabled, CatalogAgentNotFound

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")


class InMemoryCatalogRepo(CatalogAgentRepository):
    def __init__(self) -> None:
        self._by_id: dict[UUID, CatalogAgent] = {}

    async def add(self, agent: CatalogAgent) -> None:
        self._by_id[agent.id] = agent

    async def get(self, agent_id: UUID) -> CatalogAgent | None:
        return self._by_id.get(agent_id)

    async def list_for_workspace(self, workspace_id: UUID) -> list[CatalogAgent]:
        return [item for item in self._by_id.values() if item.workspace_id == workspace_id]

    async def update(self, agent: CatalogAgent) -> None:
        self._by_id[agent.id] = agent

    async def delete(self, agent_id: UUID) -> None:
        self._by_id.pop(agent_id, None)


class InMemoryUserState(CatalogAgentUserStateRepository):
    async def set_favorite(self, **kwargs: object) -> None:
        _ = kwargs


@pytest.mark.asyncio
async def test_admin_crud_and_catalog_projection() -> None:
    svc = AgentCatalogService(InMemoryCatalogRepo(), InMemoryUserState())
    created = await svc.create(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "销售助手", "category": "销售支持", "model": "qwen"},
    )
    agent_id = UUID(created["id"])
    listed = await svc.list_admin(workspace_id=WORKSPACE, search="销售")
    assert listed[0]["name"] == "销售助手"
    catalog = await svc.list_catalog(workspace_id=WORKSPACE)
    assert catalog == []
    published = await svc.update(agent_id=agent_id, body={"status": "published"})
    assert published["status"] == "published"
    catalog = await svc.list_catalog(workspace_id=WORKSPACE)
    assert catalog[0]["category"] == "销售支持"
    live = await svc.get_published(agent_id)
    assert live.model == "qwen"
    await svc.batch_status(ids=[str(agent_id)], status="draft")
    with pytest.raises(CatalogAgentDisabled):
        await svc.get_published(agent_id)


@pytest.mark.asyncio
async def test_missing_agent() -> None:
    svc = AgentCatalogService(InMemoryCatalogRepo())
    with pytest.raises(CatalogAgentNotFound):
        await svc.get_admin(UUID(int=9))
