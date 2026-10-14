from uuid import UUID

import pytest
from qzdap.modules.agent_runtime.application.catalog import AgentCatalogService
from .test_agent_catalog import InMemoryCatalogRepo, TENANT, WORKSPACE


async def test_release_snapshots_diff_and_rollback_preserve_audit():
    repo = InMemoryCatalogRepo()
    svc = AgentCatalogService(repo)
    created = await svc.create(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={
            "name": "version-test",
            "prompts": {"prompt": "first"},
            "status": "published",
        },
    )
    aid = UUID(created["id"])
    await svc.update(
        agent_id=aid, body={"status": "draft", "prompts": {"prompt": "second"}}
    )
    await svc.update(agent_id=aid, body={"status": "published"})
    difference = await svc.diff(agent_id=aid, left_version="v1", right_version="v2")
    assert difference["changes"]["prompts"]["before"]["prompt"] == "first"
    rolled = await svc.rollback(agent_id=aid, version="v1")
    assert rolled["prompts"]["prompt"] == "first"
    assert rolled["version"] == "v3"
    assert (await svc.audit(aid))[-1]["action"] == "回滚版本"
    assert (await repo.get(aid)).versions[0]["rollbackOf"] == "v1"


async def test_export_contains_selected_real_configuration():
    svc = AgentCatalogService(InMemoryCatalogRepo())
    created = await svc.create(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "export-test", "model": "saved-model"},
    )
    result = await svc.export(workspace_id=WORKSPACE, ids=[created["id"]])
    assert result["agents"][0]["model"] == "saved-model"
    assert result["count"] == 1


async def test_bound_scope_rejects_cross_workspace_agent():
    svc = AgentCatalogService(InMemoryCatalogRepo())
    created = await svc.create(
        tenant_id=TENANT, workspace_id=WORKSPACE, body={"name": "scope-test"}
    )
    svc.bind_scope(tenant_id=TENANT, workspace_id=UUID(int=8))
    from qzdap.modules.agent_runtime.domain.catalog_errors import CatalogAgentNotFound

    with pytest.raises(CatalogAgentNotFound):
        await svc.get_admin(UUID(created["id"]))
