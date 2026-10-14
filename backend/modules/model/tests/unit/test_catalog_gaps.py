from uuid import UUID
from .test_model_admin import seeded
from .test_model_catalog import WORKSPACE


async def test_health_check_executes_saved_provider_and_persists_event():
    svc, mid = await seeded()
    model = await svc.get_model(mid)
    result = await svc.health_check(UUID(model["providerId"]))
    assert result["success"] is True
    assert svc._tester.last["model"] == "gpt-4o"
    assert len(await svc.list_health(workspace_id=WORKSPACE)) == 1


async def test_import_saved_provider_persists_exact_model_rows():
    svc, mid = await seeded()
    model = await svc.get_model(mid)
    result = await svc.import_models(
        tenant_id=svc._tenant_id,
        workspace_id=WORKSPACE,
        body={
            "format": "json",
            "content": '[{"name":"imported","providerId":"'
            + model["providerId"]
            + '","upstreamModel":"gpt-4o"}]',
        },
    )
    assert result["created"] == 1
    imported = next(
        m
        for m in await svc.list_models(workspace_id=WORKSPACE)
        if m["name"] == "imported"
    )
    assert imported["status"] == "draft"
    assert imported["upstreamModel"] == "gpt-4o"
