"""Model catalog service — admin CRUD + provider probe + invoke."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from qzdap_llm import ChatRequest, ChatResponse
from qzdap_schema.ids import ModelId
from qzdap_vault.actor import ActorContext

from qzdap.modules.model.application.ports import (
    CatalogProber,
    CredentialCipher,
    HealthRepository,
    ModelClientFactory,
    ModelRepository,
    ProviderRepository,
    RouteRepository,
)
from qzdap.modules.model.domain.entities import (
    FALLBACK_CATALOG,
    MODEL_STATUSES,
    PROTOCOLS,
    HealthEvent,
    Model,
    Provider,
    RouteRule,
    mask_api_key,
)
from qzdap.modules.model.domain.errors import (
    CredentialNotFound,
    ModelDisabled,
    ModelNotFound,
    RouteNotFound,
)


class ModelService:
    def __init__(
        self,
        models: ModelRepository,
        providers: ProviderRepository,
        routes: RouteRepository,
        health: HealthRepository,
        *,
        cipher: CredentialCipher | None = None,
        client_factory: ModelClientFactory | None = None,
        prober: CatalogProber | None = None,
    ) -> None:
        self._models = models
        self._providers = providers
        self._routes = routes
        self._health = health
        self._cipher = cipher
        self._client_factory = client_factory
        self._prober = prober

    async def list_models(
        self,
        *,
        workspace_id: UUID,
        search: str = "",
        status: str = "all",
        tier: str = "all",
    ) -> list[dict[str, Any]]:
        items = await self._models.list_for_workspace(workspace_id)
        query = search.strip().lower()
        out: list[Model] = []
        for model in items:
            if status not in ("all", "", None) and model.status != status:
                continue
            if tier not in ("all", "", None) and model.tier != tier:
                continue
            hay = f"{model.name} {model.provider_name} {model.description} {' '.join(model.tags)}".lower()
            if query and query not in hay:
                continue
            out.append(model)
        out.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_admin_dict() for item in out]

    async def get_model(self, model_id: UUID) -> dict[str, Any]:
        return (await self._require_model(model_id)).to_admin_dict()

    async def list_providers(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._providers.list_for_workspace(workspace_id)
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_admin_dict() for item in items]

    async def list_routes(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._routes.list_for_workspace(workspace_id)
        items.sort(key=lambda item: (-item.priority, item.name))
        return [item.to_admin_dict() for item in items]

    async def list_health(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._health.list_for_workspace(workspace_id)
        return [item.to_admin_dict() for item in items]

    async def probe_catalog(self, body: dict[str, Any]) -> dict[str, Any]:
        api_key = str(body.get("apiKey") or "").strip()
        base_url = str(body.get("baseUrl") or "").strip()
        protocol = str(body.get("protocol") or "openai")
        if protocol not in PROTOCOLS:
            protocol = "openai"
        if not api_key or not base_url:
            return {"models": []}
        names: list[str] = []
        if self._prober is not None:
            try:
                names = await self._prober.list_models(
                    api_key=api_key, base_url=base_url, protocol=protocol
                )
            except Exception:  # noqa: BLE001 — probe must not 500 the admin form
                names = []
        if not names:
            names = list(FALLBACK_CATALOG.get(protocol, []))
        return {"models": names}

    async def create_from_provider(
        self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]
    ) -> dict[str, Any]:
        names = [
            str(item).strip()
            for item in (body.get("models") or [])
            if str(item).strip()
        ]
        if not names:
            raise ValueError("models required")
        protocol = str(body.get("protocol") or "openai")
        if protocol not in PROTOCOLS:
            protocol = "openai-compatible"
        api_key = str(body.get("apiKey") or "")
        base_url = str(body.get("baseUrl") or "")
        provider_name = str(body.get("providerName") or "未命名提供商")
        encrypted = b""
        if api_key and self._cipher is not None:
            aad = f"protocol={protocol}|base_url={base_url}".encode()
            encrypted = self._cipher.encrypt(api_key.encode("utf-8"), aad=aad)
        provider = Provider.create(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=provider_name,
            base_url=base_url,
            protocol=protocol,  # type: ignore[arg-type]
            api_key_masked=mask_api_key(api_key),
            encrypted_payload=encrypted,
        )
        await self._providers.add(provider)
        first: Model | None = None
        for name in names:
            model = Model.create(
                id=uuid4(),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                name=name,
                provider_id=provider.id,
                provider_name=provider.name,
                protocol=protocol,
            )
            await self._models.add(model)
            if first is None:
                first = model
        assert first is not None
        return first.to_admin_dict()

    async def update_model(self, *, model_id: UUID, body: dict[str, Any]) -> dict[str, Any]:
        model = await self._require_model(model_id)
        patch = body.get("patch") if isinstance(body.get("patch"), dict) else body
        updated = model.apply_patch(patch)
        await self._models.update(updated)
        return updated.to_admin_dict()

    async def delete_model(self, model_id: UUID) -> dict[str, Any]:
        await self._require_model(model_id)
        await self._models.delete(model_id)
        return {"id": str(model_id)}

    async def set_starred(self, *, model_id: UUID, starred: bool) -> dict[str, Any]:
        model = await self._require_model(model_id)
        updated = model.with_starred(starred)
        await self._models.update(updated)
        return updated.to_admin_dict()

    async def batch_status(self, *, ids: list[str], status: str) -> dict[str, Any]:
        if status not in MODEL_STATUSES:
            status = "draft"
        affected: list[str] = []
        for raw in ids:
            try:
                model_id = UUID(str(raw))
            except ValueError:
                continue
            model = await self._models.get(model_id)
            if model is None:
                continue
            await self._models.update(model.with_status(status))  # type: ignore[arg-type]
            affected.append(str(model_id))
        return {"ids": affected}

    async def create_route(
        self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]
    ) -> dict[str, Any]:
        primary = _parse_id(body.get("primaryModelId"))
        route = RouteRule.create(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=str(body.get("name") or "未命名路由"),
            task=body.get("task") or "generation",
            strategy=body.get("strategy") or "quality-first",
            priority=int(body.get("priority") or 0),
            primary_model_id=primary,
            description=str(body.get("description") or ""),
        )
        await self._routes.add(route)
        return route.to_admin_dict()

    async def toggle_route(self, route_id: UUID) -> dict[str, Any]:
        route = await self._routes.get(route_id)
        if route is None:
            raise RouteNotFound(f"route {route_id} not found")
        updated = route.toggled()
        await self._routes.update(updated)
        return updated.to_admin_dict()

    async def delete_route(self, route_id: UUID) -> dict[str, Any]:
        route = await self._routes.get(route_id)
        if route is None:
            raise RouteNotFound(f"route {route_id} not found")
        await self._routes.delete(route_id)
        return {"id": str(route_id)}

    async def invoke(
        self,
        *,
        actor: ActorContext,
        model_id: ModelId,
        req: ChatRequest,
    ) -> ChatResponse:
        _ = actor
        model = await self._require_model(UUID(str(model_id)))
        if model.status not in {"active", "graying"}:
            raise ModelDisabled(f"model {model.name!r} disabled")
        provider = await self._providers.get(model.provider_id)
        if provider is None:
            raise CredentialNotFound("provider missing")
        api_key = self._decrypt(provider)
        if not api_key:
            raise CredentialNotFound(f"model {model.name!r} has no credential attached")
        if self._client_factory is None:
            raise CredentialNotFound("model client factory not wired")
        client = self._client_factory.build(
            protocol=provider.protocol,
            api_key=api_key,
            base_url=provider.base_url,
        )
        start = datetime.now(UTC)
        try:
            resp = await client.chat(req)
        except Exception as exc:
            latency_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
            await self._models.update(model.record_call(latency_ms=latency_ms, ok=False))
            await self._health.add(
                HealthEvent(
                    id=uuid4(),
                    tenant_id=model.tenant_id,
                    workspace_id=model.workspace_id,
                    type="incident",
                    provider_id=provider.id,
                    provider_name=provider.name,
                    message=f"{model.name} 调用失败: {exc}",
                    occurred_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M"),
                )
            )
            raise
        latency_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
        await self._models.update(model.record_call(latency_ms=latency_ms, ok=True))
        return resp

    def _decrypt(self, provider: Provider) -> str:
        if not provider.encrypted_payload or self._cipher is None:
            return ""
        aad = f"protocol={provider.protocol}|base_url={provider.base_url}".encode()
        return self._cipher.decrypt(provider.encrypted_payload, aad=aad).decode("utf-8")

    async def _require_model(self, model_id: UUID) -> Model:
        model = await self._models.get(model_id)
        if model is None:
            raise ModelNotFound(f"model {model_id} not found")
        return model


def _parse_id(raw: Any) -> UUID:
    if raw:
        try:
            return UUID(str(raw))
        except ValueError:
            pass
    return uuid4()


__all__ = ["ModelService"]
