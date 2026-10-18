"""Scoped administration and verified enrollment regression tests."""

from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from qzdap_llm import ChatRequest, LLMChunk
from qzdap_vault.actor import ActorContext

from qzdap.modules.model.adapter.http.router import build_router
from qzdap.modules.model.domain.errors import CredentialNotFound, ModelNotFound

from test_model_catalog import TENANT, WORKSPACE, _svc


class AADCipher:
    def encrypt(self, plaintext, *, aad=None):
        return aad + b"\x00" + plaintext

    def decrypt(self, blob, *, aad=None):
        stored, value = blob.split(b"\x00", 1)
        if stored != aad:
            raise ValueError("bad aad")
        return value


class Tester:
    __test__ = False

    async def test_connection(self, **kwargs):
        self.last = kwargs
        return {
            "success": True,
            "requestedModel": kwargs["model"],
            "actualModel": kwargs["model"],
            "response": "ok",
        }


async def seeded(*, shared=False):
    svc = _svc()
    svc._cipher = AADCipher()
    svc._tester = Tester()
    svc.bind_scope(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        actor_id=uuid4(),
        actor_name="Real Admin",
    )
    model = await svc.create_from_provider(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={
            "providerName": "Provider",
            "apiKey": "secret-1234",
            "baseUrl": "https://api.example.com/v1",
            "protocol": "openai",
            "source": "catalog",
            "models": ["gpt-4o", "gpt-4o-mini"] if shared else ["gpt-4o"],
        },
    )
    return svc, UUID(model["id"])


@pytest.mark.asyncio
async def test_shared_cow_name_noop_and_secret_retention():
    svc, mid = await seeded(shared=True)
    original = await svc.get_model(mid)
    original_provider = original["providerId"]
    stamp = svc._models.rows[mid].updated_at
    await svc.update_model(
        model_id=mid, body={"patch": {"provider": {"name": "Provider", "apiKey": ""}}}
    )
    assert svc._models.rows[mid].updated_at == stamp
    changed = await svc.update_model(
        model_id=mid,
        body={"patch": {"provider": {"name": "Current Only", "apiKey": ""}}},
    )
    assert changed["providerId"] != original_provider
    assert changed["providerName"] == changed["provider"]["name"] == "Current Only"
    assert len(svc._providers.rows) == 2
    assert svc._decrypt(await svc._provider(svc._models.rows[mid])) == "secret-1234"
    siblings = [m for m in svc._models.rows.values() if m.id != mid]
    assert siblings[0].provider_name == "Provider"


@pytest.mark.asyncio
async def test_connection_override_reencrypts_old_aad_preserves_uuid():
    svc, mid = await seeded()
    original = await svc.get_model(mid)
    response = await svc.test_connectivity(
        {
            "modelId": str(mid),
            "baseUrl": "https://new.example.com/v1",
            "model": "custom-upstream",
        }
    )
    result = await svc.update_model(
        model_id=mid,
        body={
            "patch": {
                "name": "Display Name",
                "upstreamModel": "custom-upstream",
                "source": "verified",
                "verificationToken": response["verificationToken"],
                "provider": {"baseUrl": "https://new.example.com/v1", "apiKey": ""},
            }
        },
    )
    assert result["id"] == str(mid)
    assert result["providerId"] == original["providerId"]
    assert result["upstreamModel"] == "custom-upstream"
    assert svc._decrypt(await svc._provider(svc._models.rows[mid])) == "secret-1234"


@pytest.mark.asyncio
async def test_verified_token_tamper_scope_config_and_expiry(monkeypatch):
    svc, mid = await seeded()
    tested = await svc.test_connectivity({"modelId": str(mid), "model": "custom"})
    patch = {
        "upstreamModel": "custom",
        "source": "verified",
        "verificationToken": tested["verificationToken"],
    }
    for override in [
        {"upstreamModel": "other"},
        {"verificationToken": "invalid"},
        {"provider": {"apiKey": "other-key"}},
        {"provider": {"apiVersion": "v2"}},
    ]:
        with pytest.raises(ValueError):
            await svc.update_model(model_id=mid, body={"patch": {**patch, **override}})
    actor = svc._actor_id
    svc._actor_id = uuid4()
    with pytest.raises(ValueError):
        await svc.update_model(model_id=mid, body={"patch": patch})
    svc._actor_id = actor
    from qzdap.modules.model.application import services

    now = services.time.time()
    monkeypatch.setattr(services.time, "time", lambda: now + 601)
    with pytest.raises(ValueError):
        await svc.update_model(model_id=mid, body={"patch": patch})


@pytest.mark.asyncio
async def test_ownership_applies_to_detail_diagnostics_mutations_and_runtime():
    svc, mid = await seeded()
    svc._workspace_id = uuid4()
    for call in [
        svc.get_model(mid),
        svc.test_connectivity({"modelId": str(mid)}),
        svc.update_model(model_id=mid, body={"patch": {"name": "x"}}),
        svc.delete_model(mid),
    ]:
        with pytest.raises(ModelNotFound):
            await call
    svc._workspace_id = WORKSPACE
    svc._models.rows[mid] = replace(svc._models.rows[mid], status="active")
    with pytest.raises(ModelNotFound):
        await svc.invoke(
            actor=ActorContext(tenant_id=uuid4(), workspace_id=WORKSPACE),
            model_id=mid,
            req=ChatRequest(model="x", messages=[]),
        )


@pytest.mark.asyncio
async def test_diagnostics_no_writes_saved_override_and_safe_corrupt_credentials():
    svc, mid = await seeded()
    before = svc._models.rows[mid]
    result = await svc.test_connectivity(
        {
            "modelId": str(mid),
            "apiKey": "",
            "protocol": "anthropic-compatible",
            "baseUrl": "https://new.example.com",
            "model": "new",
        }
    )
    assert result["requestedModel"] == "new"
    assert svc._tester.last["api_key"] == "secret-1234"
    assert svc._models.rows[mid] == before
    provider = await svc._provider(before)
    svc._providers.rows[provider.id] = replace(
        provider, encrypted_payload=b"corrupt-secret"
    )
    with pytest.raises(CredentialNotFound, match="新的 API Key"):
        await svc.test_connectivity({"modelId": str(mid), "model": "new"})


@pytest.mark.asyncio
async def test_stream_incremental_uses_saved_upstream_and_closes_on_exit():
    svc, mid = await seeded()
    svc._models.rows[mid] = replace(
        svc._models.rows[mid],
        status="active",
        name="Display",
        upstream_model="saved-upstream",
    )

    class Client:
        closed = False

        async def stream(self, req):
            assert req.model == "saved-upstream"
            yield LLMChunk(model=req.model, delta="first")
            yield LLMChunk(model=req.model, delta="second")

        async def aclose(self):
            self.closed = True

    client = Client()
    svc._client_factory = SimpleNamespace(build=lambda **kwargs: client)
    iterator = svc.stream(
        actor=ActorContext(tenant_id=TENANT, workspace_id=WORKSPACE),
        model_id=mid,
        req=ChatRequest(model="untrusted", messages=[]),
    )
    assert (await anext(iterator)).delta == "first"
    await iterator.aclose()
    assert client.closed


@pytest.mark.asyncio
async def test_star_status_bulk_noop_audit_and_cross_scope_bulk_rejection():
    svc, mid = await seeded(shared=True)
    assert svc._models.rows[mid].context_window == 0
    assert svc._models.rows[mid].trend == []
    await svc.set_starred(model_id=mid, starred=False)
    await svc.batch_status(ids=[str(mid)], status="draft")
    await svc.set_starred(model_id=mid, starred=True)
    sibling = next(m for m in svc._models.rows.values() if m.id != mid)
    svc._models.rows[sibling.id] = replace(sibling, workspace_id=uuid4())
    with pytest.raises(ModelNotFound):
        await svc.batch_status(ids=[str(mid), str(sibling.id)], status="active")
    assert svc._models.rows[mid].status == "draft"
    assert svc._models.rows[mid].record_call(latency_ms=10, ok=True).trend == []


@pytest.mark.asyncio
async def test_verified_create_requires_proof_and_binds_requested_model():
    svc, _ = await seeded()
    body = {
        "providerName": "GLM",
        "protocol": "glm",
        "baseUrl": "https://api.example.com",
        "apiKey": "new-key",
        "model": "custom-glm",
    }
    result = await svc.test_connectivity(body)
    create = {**body, "models": ["custom-glm"], "source": "verified"}
    with pytest.raises(ValueError):
        await svc.create_from_provider(
            tenant_id=TENANT, workspace_id=WORKSPACE, body=create
        )
    saved = await svc.create_from_provider(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={**create, "verificationToken": result["verificationToken"]},
    )
    assert saved["upstreamModel"] == "custom-glm"
    assert saved["provider"]["hasCredential"] is True


@pytest.mark.asyncio
async def test_provider_ownership_is_checked_independently_of_model():
    svc, mid = await seeded()
    model = svc._models.rows[mid]
    provider = svc._providers.rows[model.provider_id]
    svc._providers.rows[provider.id] = replace(provider, tenant_id=uuid4())
    with pytest.raises(CredentialNotFound):
        await svc.get_model(mid)
    with pytest.raises(CredentialNotFound):
        await svc.test_connectivity({"modelId": str(mid), "model": "new"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("roles", "tenant", "workspace", "expected"),
    [
        (None, TENANT, WORKSPACE, 401),
        (set(), TENANT, WORKSPACE, 403),
        ({"admin"}, uuid4(), WORKSPACE, 403),
        ({"admin"}, TENANT, uuid4(), 403),
        ({"admin"}, TENANT, WORKSPACE, 200),
        ({"workspace_owner"}, TENANT, WORKSPACE, 200),
    ],
)
async def test_http_admin_auth_and_scope(roles, tenant, workspace, expected):
    app = FastAPI()
    app.include_router(build_router())

    @app.middleware("http")
    async def principal(request, call_next):
        if roles is not None:
            request.state.principal = SimpleNamespace(
                id=uuid4(),
                roles=roles,
                tenant_id=tenant,
                workspace_id=workspace,
                display_name="Admin",
            )
        return await call_next(request)

    svc = _svc()

    class Session:
        async def commit(self):
            pass

        async def rollback(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    app.state.container = SimpleNamespace(
        session_factory=lambda: SimpleNamespace(session=Session)
    )
    app.state.model_service_factory = SimpleNamespace(for_session=lambda session: svc)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        result = await client.get(
            "/api/admin/models",
            headers={"X-Tenant-Id": str(TENANT), "X-Workspace-Id": str(WORKSPACE)},
        )
    assert result.status_code == expected
