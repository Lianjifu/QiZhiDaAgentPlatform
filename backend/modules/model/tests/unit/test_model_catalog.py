"""Model catalog unit tests."""

from __future__ import annotations

from uuid import UUID

import pytest
from qzdap_llm.client import ChatMessage, ChatRequest, ChatResponse, Usage
from qzdap_schema.ids import ModelId
from qzdap_vault.actor import ActorContext

from qzdap.modules.model.application.ports import (
    CatalogProber,
    HealthRepository,
    ModelClientFactory,
    ModelRepository,
    ProviderRepository,
    RouteRepository,
)
from qzdap.modules.model.application.services import ModelService
from qzdap.modules.model.domain.entities import HealthEvent, Model, Provider, RouteRule
from qzdap.modules.model.domain.errors import ModelDisabled, ModelNotFound

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")


class _MemModels(ModelRepository):
    def __init__(self) -> None:
        self.rows: dict[UUID, Model] = {}

    async def add(self, model: Model) -> None:
        self.rows[model.id] = model

    async def get(self, model_id: UUID) -> Model | None:
        return self.rows.get(model_id)

    async def list_for_workspace(self, workspace_id: UUID) -> list[Model]:
        return [
            item for item in self.rows.values() if item.workspace_id == workspace_id
        ]

    async def update(self, model: Model) -> None:
        self.rows[model.id] = model

    async def delete(self, model_id: UUID) -> None:
        self.rows.pop(model_id, None)

    async def get_by_upstream_name(
        self, *, workspace_id: UUID, upstream_model: str
    ) -> Model | None:
        for item in self.rows.values():
            if (
                item.workspace_id == workspace_id
                and item.upstream_model == upstream_model
            ):
                return item
        return None


class _MemProviders(ProviderRepository):
    def __init__(self) -> None:
        self.rows: dict[UUID, Provider] = {}

    async def add(self, provider: Provider) -> None:
        self.rows[provider.id] = provider

    async def get(self, provider_id: UUID) -> Provider | None:
        return self.rows.get(provider_id)

    async def list_for_workspace(self, workspace_id: UUID) -> list[Provider]:
        return [
            item for item in self.rows.values() if item.workspace_id == workspace_id
        ]

    async def update(self, provider: Provider) -> None:
        self.rows[provider.id] = provider


class _MemRoutes(RouteRepository):
    def __init__(self) -> None:
        self.rows: dict[UUID, RouteRule] = {}

    async def add(self, route: RouteRule) -> None:
        self.rows[route.id] = route

    async def get(self, route_id: UUID) -> RouteRule | None:
        return self.rows.get(route_id)

    async def list_for_workspace(self, workspace_id: UUID) -> list[RouteRule]:
        return [
            item for item in self.rows.values() if item.workspace_id == workspace_id
        ]

    async def update(self, route: RouteRule) -> None:
        self.rows[route.id] = route

    async def delete(self, route_id: UUID) -> None:
        self.rows.pop(route_id, None)


class _MemHealth(HealthRepository):
    def __init__(self) -> None:
        self.rows: list[HealthEvent] = []

    async def add(self, event: HealthEvent) -> None:
        self.rows.insert(0, event)

    async def list_for_workspace(
        self, workspace_id: UUID, limit: int = 50
    ) -> list[HealthEvent]:
        return [item for item in self.rows if item.workspace_id == workspace_id][:limit]


class _PlainCipher:
    key_version = 1

    def encrypt(self, plaintext: bytes, *, aad: bytes | None = None) -> bytes:
        _ = aad
        return plaintext

    def decrypt(self, blob: bytes, *, aad: bytes | None = None) -> bytes:
        _ = aad
        return blob


class _FakeClient:
    async def aclose(self) -> None:
        pass

    async def chat(self, req: ChatRequest) -> ChatResponse:
        _ = req
        return ChatResponse(
            model="gpt-4o",
            message=ChatMessage(role="assistant", content="ok"),
            finish_reason="stop",
            usage=Usage(input_tokens=1, output_tokens=1),
        )


class _FakeFactory(ModelClientFactory):
    def build(
        self,
        *,
        protocol: str,
        api_key: str,
        base_url: str | None,
        api_version: str = "",
    ) -> object:
        _ = (protocol, api_key, base_url)
        return _FakeClient()


class _FakeProber(CatalogProber):
    def __init__(
        self, models: list[str] | None = None, *, raise_exc: Exception | None = None
    ) -> None:
        self.models = models if models is not None else ["gpt-4o", "gpt-4o-mini"]
        self.raise_exc = raise_exc

    async def list_models(
        self, *, api_key: str, base_url: str, protocol: str
    ) -> list[str]:
        _ = (api_key, base_url, protocol)
        if self.raise_exc is not None:
            raise self.raise_exc
        return list(self.models)


def _svc(*, prober: CatalogProber | None = None) -> ModelService:
    if prober is None:
        prober = _FakeProber(
            ["gpt-4o", "gpt-4o-mini", "text-embedding-3-large", "qwen-max"]
        )
    return ModelService(
        _MemModels(),
        _MemProviders(),
        _MemRoutes(),
        _MemHealth(),
        cipher=_PlainCipher(),
        client_factory=_FakeFactory(),
        prober=prober,
    )


@pytest.mark.asyncio
async def test_create_list_and_filters() -> None:
    svc = _svc()
    created = await svc.create_from_provider(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={
            "source": "catalog",
            "providerName": "OpenAI 官方",
            "apiKey": "sk-test-1234",
            "baseUrl": "https://api.openai.com/v1",
            "protocol": "openai",
            "models": ["gpt-4o", "text-embedding-3-large"],
        },
    )
    assert created["status"] == "draft"
    assert created["providerName"] == "OpenAI 官方"
    listed = await svc.list_models(workspace_id=WORKSPACE)
    assert len(listed) == 2
    providers = await svc.list_providers(workspace_id=WORKSPACE)
    assert providers[0]["apiKeyMasked"] == "••••1234"
    embeds = await svc.list_models(workspace_id=WORKSPACE, search="embed")
    assert len(embeds) == 1
    assert embeds[0]["task"] == ["embedding"]


@pytest.mark.asyncio
async def test_update_star_batch_and_delete() -> None:
    svc = _svc()
    created = await svc.create_from_provider(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={
            "source": "catalog",
            "providerName": "通义",
            "apiKey": "sk-abcd",
            "baseUrl": "https://dashscope.aliyuncs.com",
            "protocol": "openai-compatible",
            "models": ["qwen-max"],
        },
    )
    model_id = UUID(created["id"])
    patched = await svc.update_model(
        model_id=model_id, body={"patch": {"status": "active", "tier": "premium"}}
    )
    assert patched["status"] == "active"
    starred = await svc.set_starred(model_id=model_id, starred=True)
    assert starred["starred"] is True
    await svc.batch_status(ids=[str(model_id)], status="retired")
    assert (await svc.get_model(model_id))["status"] == "retired"
    deleted = await svc.delete_model(model_id)
    assert deleted == {"id": str(model_id)}
    with pytest.raises(ModelNotFound):
        await svc.get_model(model_id)


@pytest.mark.asyncio
async def test_routes_and_probe_fallback() -> None:
    svc = _svc(prober=_FakeProber(["gpt-4o", "gpt-4o-mini"]))
    created = await svc.create_from_provider(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={
            "source": "catalog",
            "providerName": "OpenAI",
            "apiKey": "sk-xxxx",
            "baseUrl": "https://api.openai.com/v1",
            "protocol": "openai",
            "models": ["gpt-4o"],
        },
    )
    route = await svc.create_route(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={
            "name": "推理任务",
            "task": "reasoning",
            "strategy": "quality-first",
            "priority": 90,
            "primaryModelId": created["id"],
            "description": "主链路",
        },
    )
    assert route["enabled"] is True
    toggled = await svc.toggle_route(UUID(route["id"]))
    assert toggled["enabled"] is False
    catalog = await svc.probe_catalog(
        {"apiKey": "sk", "baseUrl": "https://example.com", "protocol": "openai"}
    )
    assert "gpt-4o" in catalog["models"]
    assert catalog.get("error") is None
    empty = await svc.probe_catalog({"apiKey": "", "baseUrl": ""})
    assert empty == {"models": [], "error": "请填写 API Key 和请求地址后再拉取。"}


@pytest.mark.asyncio
async def test_probe_catalog_no_prober_wired() -> None:
    svc = _svc()
    svc._prober = None
    catalog = await svc.probe_catalog(
        {"apiKey": "sk", "baseUrl": "https://example.com", "protocol": "openai"}
    )
    assert catalog == {"models": [], "error": "目录探测器未配置，请联系管理员。"}


@pytest.mark.asyncio
async def test_probe_catalog_prober_raises() -> None:
    svc = _svc(prober=_FakeProber(raise_exc=RuntimeError("boom")))
    catalog = await svc.probe_catalog(
        {"apiKey": "sk", "baseUrl": "https://example.com", "protocol": "openai"}
    )
    assert catalog == {"models": [], "error": "无法拉取模型目录，请检查供应商配置。"}


@pytest.mark.asyncio
async def test_probe_catalog_prober_returns_empty() -> None:
    svc = _svc(prober=_FakeProber([]))
    catalog = await svc.probe_catalog(
        {"apiKey": "sk", "baseUrl": "https://example.com", "protocol": "openai"}
    )
    assert catalog == {
        "models": [],
        "error": "供应商未返回模型列表。",
        "discoverySupported": True,
    }


@pytest.mark.asyncio
async def test_invoke_requires_active_and_records_call() -> None:
    svc = _svc()
    created = await svc.create_from_provider(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={
            "source": "catalog",
            "providerName": "OpenAI",
            "apiKey": "sk-live",
            "baseUrl": "https://api.openai.com/v1",
            "protocol": "openai",
            "models": ["gpt-4o"],
        },
    )
    model_id = UUID(created["id"])
    actor = ActorContext(
        tenant_id=TENANT, workspace_id=WORKSPACE, principal_id=None, roles=frozenset()
    )
    req = ChatRequest(model="gpt-4o", messages=[])
    with pytest.raises(ModelDisabled):
        await svc.invoke(actor=actor, model_id=ModelId(model_id), req=req)
    await svc.update_model(model_id=model_id, body={"patch": {"status": "active"}})
    resp = await svc.invoke(actor=actor, model_id=ModelId(model_id), req=req)
    assert resp.message.content == "ok"
    again = await svc.get_model(model_id)
    assert again["calls"] == 1
