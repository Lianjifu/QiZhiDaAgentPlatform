"""Scoped model administration, credential-safe diagnostics and saved execution."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
from qzdap_llm import ChatRequest, ChatResponse, LLMChunk
from qzdap_schema.ids import ModelId
from qzdap_vault.actor import ActorContext

_log = logging.getLogger(__name__)

from qzdap.modules.model.application.ports import (
    CatalogDiscoveryUnsupported,
    CatalogProber,
    ConnectivityTester,
    CredentialCipher,
    HealthRepository,
    ModelClientFactory,
    ModelRepository,
    ProviderRepository,
    RouteRepository,
)
from qzdap.modules.model.domain.entities import (
    MODEL_STATUSES,
    PROTOCOLS,
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

# Shared by per-request service instances; short-lived proofs intentionally expire on restart.
_VERIFICATION_SECRET = secrets.token_bytes(32)


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
        connectivity_tester: ConnectivityTester | None = None,
        verification_secret: bytes = _VERIFICATION_SECRET,
    ) -> None:
        self._models, self._providers, self._routes, self._health = (
            models,
            providers,
            routes,
            health,
        )
        # Phase 4: 暴露 internal session 供 QuotaService 复用. 仅在 SqlModelRepository
        # 是 session-backed 时可用 (in-memory fake 没 _s). 检查 hasattr 防御.
        self._quota_session = getattr(models, "_s", None)
        self._cipher, self._client_factory, self._prober = (
            cipher,
            client_factory,
            prober,
        )
        self._tester, self._verification_secret = (
            connectivity_tester,
            verification_secret,
        )
        self._tenant_id: UUID | None = None
        self._workspace_id: UUID | None = None
        self._actor_id: UUID | None = None
        self._actor_name: str | None = None

    def bind_scope(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        actor_id: UUID,
        actor_name: str | None = None,
    ) -> None:
        self._tenant_id, self._workspace_id = tenant_id, workspace_id
        self._actor_id, self._actor_name = actor_id, actor_name

    def _owns(self, item: Any) -> bool:
        return (self._tenant_id is None or item.tenant_id == self._tenant_id) and (
            self._workspace_id is None or item.workspace_id == self._workspace_id
        )

    def _check_workspace(
        self, workspace_id: UUID, tenant_id: UUID | None = None
    ) -> None:
        if (self._workspace_id is not None and workspace_id != self._workspace_id) or (
            tenant_id is not None
            and self._tenant_id is not None
            and tenant_id != self._tenant_id
        ):
            raise PermissionError("scope mismatch")

    async def _require_model(self, model_id: UUID) -> Model:
        model = await self._models.get(model_id)
        if model is None or not self._owns(model):
            raise ModelNotFound(f"model {model_id} not found")
        return model

    async def _provider(self, model: Model) -> Provider:
        provider = await self._providers.get(model.provider_id)
        if (
            provider is None
            or not self._owns(provider)
            or provider.tenant_id != model.tenant_id
            or provider.workspace_id != model.workspace_id
        ):
            raise CredentialNotFound("provider missing")
        return provider

    async def get_model(self, model_id: UUID) -> dict[str, Any]:
        model = await self._require_model(model_id)
        result = model.to_admin_dict()
        result["provider"] = (await self._provider(model)).to_admin_dict()
        return result

    async def list_models(
        self,
        *,
        workspace_id: UUID,
        search: str = "",
        status: str = "all",
        tier: str = "all",
    ) -> list[dict[str, Any]]:
        self._check_workspace(workspace_id)
        query = search.strip().lower()
        items = [
            m
            for m in await self._models.list_for_workspace(workspace_id)
            if self._owns(m)
            and (status in ("all", "", None) or m.status == status)
            and (tier in ("all", "", None) or m.tier == tier)
            and (
                not query
                or query
                in f"{m.name} {m.provider_name} {m.description} {' '.join(m.tags)}".lower()
            )
        ]
        items.sort(key=lambda m: (m.updated_at, str(m.id)), reverse=True)
        return [m.to_admin_dict() for m in items]

    async def list_providers(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        self._check_workspace(workspace_id)
        return [
            p.to_admin_dict()
            for p in await self._providers.list_for_workspace(workspace_id)
            if self._owns(p)
        ]

    async def list_routes(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        self._check_workspace(workspace_id)
        items = [
            r
            for r in await self._routes.list_for_workspace(workspace_id)
            if self._owns(r)
        ]
        items.sort(key=lambda r: (-r.priority, r.name, str(r.id)))
        return [r.to_admin_dict() for r in items]

    async def list_health(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        self._check_workspace(workspace_id)
        return [
            e.to_admin_dict()
            for e in await self._health.list_for_workspace(workspace_id)
            if self._owns(e)
        ]

    def _decrypt(self, provider: Provider) -> str:
        if not provider.encrypted_payload or self._cipher is None:
            raise CredentialNotFound("凭据不可用，请输入新的 API Key。")
        try:
            return self._cipher.decrypt(
                provider.encrypted_payload,
                aad=self._aad(provider.protocol, provider.base_url),
            ).decode()
        except Exception as exc:
            raise CredentialNotFound("凭据不可用，请输入新的 API Key。") from exc

    @staticmethod
    def _aad(protocol: str, base_url: str) -> bytes:
        return f"protocol={protocol}|base_url={base_url}".encode()

    def _encrypt(self, key: str, protocol: str, base_url: str) -> bytes:
        if self._cipher is None:
            raise CredentialNotFound("凭据加密未配置，请联系管理员。")
        return self._cipher.encrypt(key.encode(), aad=self._aad(protocol, base_url))

    async def _effective(self, body: dict[str, Any]) -> tuple[str, str, str, str, str]:
        provider = None
        model = None
        if body.get("modelId"):
            model = await self._require_model(UUID(str(body["modelId"])))
            provider = await self._provider(model)
        protocol = str(
            body.get("protocol") or (provider.protocol if provider else "openai")
        )
        if protocol not in PROTOCOLS:
            raise ValueError("unsupported protocol")
        url = str(
            body.get("baseUrl") or (provider.base_url if provider else "")
        ).strip()
        version = str(
            body.get("apiVersion", provider.api_version if provider else "") or ""
        ).strip()
        key = str(body.get("apiKey") or "").strip()
        if not key and provider:
            key = self._decrypt(provider)
        upstream = str(
            body.get("model")
            or body.get("upstreamModel")
            or (model.upstream_model or model.name if model else "")
        ).strip()
        if not key or not url:
            raise ValueError("请填写 API Key 和请求地址后再拉取。")
        return key, url, protocol, version, upstream

    def _proof_binding(self, config: tuple[str, str, str, str, str]) -> str:
        key, url, protocol, version, model = config
        data = [
            str(self._actor_id),
            str(self._tenant_id),
            str(self._workspace_id),
            protocol,
            url,
            version,
            model,
            hashlib.sha256(key.encode()).hexdigest(),
        ]
        return hmac.new(
            self._verification_secret,
            json.dumps(data, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()

    def _issue_proof(self, config: tuple[str, str, str, str, str]) -> str:
        raw = json.dumps(
            {"exp": int(time.time()) + 600, "binding": self._proof_binding(config)},
            separators=(",", ":"),
        ).encode()
        return (
            base64.urlsafe_b64encode(raw).decode()
            + "."
            + hmac.new(self._verification_secret, raw, hashlib.sha256).hexdigest()
        )

    def _check_proof(self, token: Any, config: tuple[str, str, str, str, str]) -> None:
        try:
            encoded, signature = str(token or "").split(".")
            raw = base64.urlsafe_b64decode(encoded)
            expected = hmac.new(
                self._verification_secret, raw, hashlib.sha256
            ).hexdigest()
            payload = json.loads(raw)
            if (
                not hmac.compare_digest(signature, expected)
                or payload["exp"] < time.time()
                or not hmac.compare_digest(
                    payload["binding"], self._proof_binding(config)
                )
            ):
                raise ValueError
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("模型验证已失效，请使用当前配置重新测试。") from exc

    async def health_check(self, provider_id: UUID) -> dict[str, Any]:
        provider = await self._providers.get(provider_id)
        if provider is None or not self._owns(provider):
            raise ModelNotFound("provider not found")
        if self._tester is None:
            raise CredentialNotFound("连接测试器未配置")
        models = await self._models.list_for_workspace(provider.workspace_id)
        model = next((m for m in models if m.provider_id == provider.id), None)
        if model is None:
            raise ValueError("provider has no models")
        result = await self._tester.test_connection(
            api_key=self._decrypt(provider),
            base_url=provider.base_url,
            protocol=provider.protocol,
            model=model.upstream_model or model.name,
            api_version=provider.api_version,
        )
        from qzdap.modules.model.domain.entities import HealthEvent

        await self._health.add(
            HealthEvent(
                id=uuid4(),
                tenant_id=provider.tenant_id,
                workspace_id=provider.workspace_id,
                type="recovery" if result.get("success") else "incident",
                provider_id=provider.id,
                provider_name=provider.name,
                message=str(
                    result.get("response") or result.get("error") or "health check"
                ),
                occurred_at=datetime.now(UTC).isoformat(),
            )
        )
        # 显式 commit: 防止 outer rollback (e.g. background sampler session) 抹掉.
        commit_session = self._quota_session
        if commit_session is None:
            commit_session = getattr(self._health, "_s", None)
        if commit_session is not None:
            await commit_session.commit()
        return {
            "success": bool(result.get("success")),
            "providerId": str(provider.id),
            "message": result.get("response") or result.get("error"),
        }

    async def import_models(
        self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]
    ) -> dict[str, Any]:
        self._check_workspace(workspace_id, tenant_id)
        import json

        try:
            rows = json.loads(str(body.get("content") or ""))
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON model import") from exc
        if not isinstance(rows, list):
            raise TypeError("model import must be an array")
        created = 0
        for row in rows:
            if not isinstance(row, dict):
                raise TypeError("each imported model must be an object")
            provider = (
                await self._providers.get(UUID(str(row.get("providerId"))))
                if row.get("providerId")
                else None
            )
            if provider is None or not self._owns(provider):
                raise ValueError("providerId is required and must belong to workspace")
            model = Model.create(
                id=uuid4(),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                name=str(row.get("name") or "").strip(),
                provider_id=provider.id,
                provider_name=provider.name,
                protocol=provider.protocol,
            )
            model = replace(
                model,
                upstream_model=str(row.get("upstreamModel") or model.name),
                status="draft",
            )
            await self._models.add(model)
            created += 1
        return {"created": created}

    async def probe_catalog(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            key, url, protocol, _, _ = await self._effective(body)
            if self._prober is None:
                return {"models": [], "error": "目录探测器未配置，请联系管理员。"}
            names = await self._prober.list_models(
                api_key=key, base_url=url, protocol=protocol
            )
            return {
                "models": names,
                "discoverySupported": True,
                **({"error": "供应商未返回模型列表。"} if not names else {}),
            }
        except CatalogDiscoveryUnsupported:
            return {
                "models": [],
                "discoverySupported": False,
                "error": "供应商未提供可用的自动模型目录，请通过真实测试验证模型ID后接入。",
            }
        except (ValueError, CredentialNotFound) as exc:
            return {"models": [], "error": str(exc)}
        except httpx.HTTPStatusError as exc:
            return {
                "models": [],
                "error": f"供应商返回 {exc.response.status_code}，请检查请求地址、协议与 API Key。",
            }
        except Exception:  # noqa: BLE001 — provider exception text can contain credentials
            return {"models": [], "error": "无法拉取模型目录，请检查供应商配置。"}

    async def test_connectivity(self, body: dict[str, Any]) -> dict[str, Any]:
        config = await self._effective(body)
        key, url, protocol, version, model = config
        if not model:
            raise ValueError("model required")
        if self._tester is None:
            raise ValueError("连接测试器未配置。")
        result = await self._tester.test_connection(
            api_key=key,
            base_url=url,
            protocol=protocol,
            model=model,
            api_version=version,
        )
        result["requestedModel"] = model
        if result.get("success") is True:
            result["verificationToken"] = self._issue_proof(config)
        return result

    async def _validate_selection(
        self,
        body: dict[str, Any],
        config: tuple[str, str, str, str, str],
        names: list[str],
    ) -> None:
        source = body.get("source")
        if source == "verified":
            if len(names) != 1:
                raise ValueError("verified accepts one model")
            self._check_proof(body.get("verificationToken"), (*config[:4], names[0]))
        elif source == "catalog":
            if self._prober is None:
                raise ValueError("目录探测器未配置。")
            key, url, protocol, _, _ = config
            try:
                available = await self._prober.list_models(
                    api_key=key, base_url=url, protocol=protocol
                )
            except Exception as exc:
                raise ValueError(
                    "无法确认模型目录，请重新拉取或通过真实测试验证。"
                ) from exc
            if any(name not in available for name in names):
                raise ValueError("模型不在当前供应商目录中，请重新拉取或测试。")
        else:
            raise ValueError("source must be catalog or verified")

    async def create_from_provider(
        self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]
    ) -> dict[str, Any]:
        self._check_workspace(workspace_id, tenant_id)
        names = list(
            dict.fromkeys(
                str(n).strip() for n in body.get("models", []) if str(n).strip()
            )
        )
        if not names:
            raise ValueError("models required")
        config = await self._effective(body)
        await self._validate_selection(body, config, names)
        key, url, protocol, version, _ = config
        provider = Provider.create(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=str(body.get("providerName") or "未命名提供商"),
            base_url=url,
            protocol=protocol,
            api_version=version,
            api_key_masked=mask_api_key(key),
            encrypted_payload=self._encrypt(key, protocol, url),
        )
        await self._providers.add(provider)
        first = None
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
            first = first or model
        return await self.get_model(first.id)

    async def update_model(
        self, *, model_id: UUID, body: dict[str, Any]
    ) -> dict[str, Any]:
        model = await self._require_model(model_id)
        provider = await self._provider(model)
        patch = body.get("patch") if isinstance(body.get("patch"), dict) else body
        pp = patch.get("provider") or {}
        if not isinstance(pp, dict):
            raise ValueError("provider must be object")  # noqa: TRY004 — request validation error
        name = str(pp.get("name", provider.name)).strip()
        protocol = str(pp.get("protocol", provider.protocol))
        url = str(pp.get("baseUrl", provider.base_url)).strip()
        version = str(pp.get("apiVersion", provider.api_version) or "").strip()
        if not name or not url or protocol not in PROTOCOLS:
            raise ValueError("invalid provider configuration")
        supplied_key = str(pp.get("apiKey") or "").strip()
        old_key = None
        if supplied_key and provider.encrypted_payload:
            try:
                old_key = self._decrypt(provider)
            except CredentialNotFound:
                pass
        key_changed = bool(supplied_key) and supplied_key != old_key
        fields_changed = (name, protocol, url, version) != (
            provider.name,
            provider.protocol,
            provider.base_url,
            provider.api_version,
        )
        updated = model.apply_patch(patch)
        upstream = updated.upstream_model or updated.name
        connection_changed = (protocol, url, version) != (
            provider.protocol,
            provider.base_url,
            provider.api_version,
        ) or key_changed
        if upstream != (model.upstream_model or model.name) or connection_changed:
            key = supplied_key or self._decrypt(provider)
            await self._validate_selection(
                patch, (key, url, protocol, version, upstream), [upstream]
            )
        changes = {
            k: {"before": v, "after": updated.to_admin_dict()[k]}
            for k, v in model.to_admin_dict().items()
            if k
            in {
                "name",
                "upstreamModel",
                "description",
                "tier",
                "status",
                "contextWindow",
                "priceIn",
                "priceOut",
                "task",
                "tags",
                "starred",
            }
            and v != updated.to_admin_dict()[k]
        }
        if fields_changed or key_changed:
            encrypted = provider.encrypted_payload
            if key_changed or (protocol, url) != (provider.protocol, provider.base_url):
                key = supplied_key or self._decrypt(provider)
                encrypted = self._encrypt(key, protocol, url)
            shared = any(
                m.id != model.id
                and m.provider_id == provider.id
                and m.tenant_id == model.tenant_id
                for m in await self._models.list_for_workspace(model.workspace_id)
            )
            effective = replace(
                provider,
                id=uuid4() if shared else provider.id,
                name=name,
                protocol=protocol,
                base_url=url,
                api_version=version,
                encrypted_payload=encrypted,
                api_key_masked=mask_api_key(supplied_key)
                if key_changed
                else provider.api_key_masked,
                updated_at=datetime.now(UTC),
            )
            if shared:
                await self._providers.add(effective)
            else:
                await self._providers.update(effective)
            updated = replace(
                updated, provider_id=effective.id, provider_name=effective.name
            )
            for field, before, after in [
                ("providerName", provider.name, name),
                ("protocol", provider.protocol, protocol),
                ("baseUrl", provider.base_url, url),
                ("apiVersion", provider.api_version, version),
            ]:
                if before != after:
                    changes[field] = {"before": before, "after": after}
            if key_changed:
                changes["credentialUpdated"] = True
        if changes:
            await self._models.update(updated)
        return await self.get_model(model_id)

    async def delete_model(self, model_id: UUID) -> dict[str, Any]:
        await self._require_model(model_id)
        await self._models.delete(model_id)
        return {"id": str(model_id)}

    async def set_starred(self, *, model_id: UUID, starred: bool) -> dict[str, Any]:
        return await self.update_model(
            model_id=model_id, body={"patch": {"starred": starred}}
        )

    async def batch_status(self, *, ids: list[str], status: str) -> dict[str, Any]:
        if status not in MODEL_STATUSES:
            raise ValueError("invalid status")
        models = [await self._require_model(UUID(raw)) for raw in dict.fromkeys(ids)]
        for model in models:
            await self.update_model(
                model_id=model.id, body={"patch": {"status": status}}
            )
        return {"ids": [str(m.id) for m in models]}

    async def create_route(
        self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]
    ) -> dict[str, Any]:
        self._check_workspace(workspace_id, tenant_id)
        primary = await self._require_model(UUID(str(body.get("primaryModelId"))))
        if primary.tenant_id != tenant_id or primary.workspace_id != workspace_id:
            raise ModelNotFound("model not found")
        route = RouteRule.create(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=str(body.get("name") or "未命名路由"),
            task=body.get("task") or "generation",
            strategy=body.get("strategy") or "quality-first",
            priority=int(body.get("priority") or 0),
            primary_model_id=primary.id,
            description=str(body.get("description") or ""),
        )
        await self._routes.add(route)
        return route.to_admin_dict()

    async def toggle_route(self, route_id: UUID) -> dict[str, Any]:
        route = await self._routes.get(route_id)
        if route is None or not self._owns(route):
            raise RouteNotFound("route not found")
        updated = route.toggled()
        await self._routes.update(updated)
        return updated.to_admin_dict()

    async def delete_route(self, route_id: UUID) -> dict[str, Any]:
        route = await self._routes.get(route_id)
        if route is None or not self._owns(route):
            raise RouteNotFound("route not found")
        await self._routes.delete(route_id)
        return {"id": str(route_id)}

    async def _execution(
        self, actor: ActorContext, model_id: ModelId
    ) -> tuple[Model, Any]:
        model = await self._require_model(UUID(str(model_id)))
        if (
            model.tenant_id != actor.tenant_id
            or actor.workspace_id is None
            or model.workspace_id != actor.workspace_id
        ):
            raise ModelNotFound("model not found")
        if model.status not in {"active", "graying"}:
            raise ModelDisabled("model disabled")
        provider = await self._provider(model)
        if self._client_factory is None:
            raise CredentialNotFound("model client factory not wired")
        return model, self._client_factory.build(
            protocol=provider.protocol,
            api_key=self._decrypt(provider),
            base_url=provider.base_url,
            api_version=provider.api_version,
        )

    async def invoke(
        self, *, actor: ActorContext, model_id: ModelId, req: ChatRequest
    ) -> ChatResponse:
        model, client = await self._execution(actor, model_id)
        start = time.monotonic()
        ok = False
        try:
            response = await client.chat(
                replace(req, model=model.upstream_model or model.name)
            )
            ok = True
            return response
        finally:
            try:
                await client.aclose()
            finally:
                await self._models.update(
                    model.record_call(
                        latency_ms=int((time.monotonic() - start) * 1000), ok=ok
                    )
                )

    async def stream(
        self, *, actor: ActorContext, model_id: ModelId, req: ChatRequest
    ) -> AsyncIterator[LLMChunk]:
        # Phase 4: quota check BEFORE building the client.
        # estimated_tokens_in=0 (我们不预扣, 只预增 request 计数 + check).
        # 实际 token 数在 stream 完成后 record.
        if self._quota_session is not None:
            from qzdap.modules.model.application.quota_service import QuotaService

            await QuotaService(self._quota_session).check_and_consume(
                tenant_id=actor.tenant_id,
                workspace_id=actor.workspace_id,  # type: ignore[arg-type]
                model_id=UUID(str(model_id)),
                period="minute",
                estimated_tokens_in=0,
            )
        # Phase 5: look up provider info for audit/health tracking
        from uuid import uuid4 as _uuid4

        from qzdap.modules.model.domain.entities import HealthEvent

        provider_id = None
        provider_name = ""
        try:
            m = await self._models.get(UUID(str(model_id)))
            if m is not None:
                p = await self._providers.get(m.provider_id)
                if p is not None:
                    provider_id = p.id
                    provider_name = p.name
        except (RuntimeError, OSError, ValueError):  # defensive
            pass

        model, client = await self._execution(actor, model_id)
        start = time.monotonic()
        ok = False
        actual_in = 0
        actual_out = 0
        err: Exception | None = None
        try:
            async for chunk in client.stream(
                replace(req, model=model.upstream_model or model.name)
            ):
                # 累加 token usage (last chunk 通常有 usage)
                if chunk.usage is not None:
                    actual_in = int(chunk.usage.input_tokens or 0)
                    actual_out = int(chunk.usage.output_tokens or 0)
                yield chunk
            ok = True
        except Exception as exc:
            err = exc
            raise
        finally:
            latency_ms = int((time.monotonic() - start) * 1000)
            try:
                await client.aclose()
            finally:
                await self._models.update(
                    model.record_call(latency_ms=latency_ms, ok=ok)
                )
                # Phase 4: record actual tokens after the call.
                if (
                    ok
                    and (actual_in or actual_out)
                    and self._quota_session is not None
                ):
                    try:
                        from qzdap.modules.model.application.quota_service import (
                            QuotaService,
                        )

                        await QuotaService(self._quota_session).record(
                            tenant_id=actor.tenant_id,
                            workspace_id=actor.workspace_id,  # type: ignore[arg-type]
                            model_id=UUID(str(model_id)),
                            period="minute",
                            tokens_in=actual_in,
                            tokens_out=actual_out,
                        )
                    except (RuntimeError, OSError) as _exc:  # defensive
                        _log.warning("quota_record_failed: %s", _exc)
                # Phase 5: health event + audit row
                if provider_id is not None:
                    try:
                        health_type = "incident" if not ok else "latency"
                        health_msg = (
                            f"{type(err).__name__}: {str(err)[:200]}"
                            if err
                            else f"latency_ms={latency_ms}"
                        )
                        await self._health.add(
                            HealthEvent(
                                id=_uuid4(),
                                tenant_id=actor.tenant_id,
                                workspace_id=actor.workspace_id,  # type: ignore[arg-type]
                                type=health_type,
                                provider_id=provider_id,
                                provider_name=provider_name,
                                message=health_msg,
                                occurred_at=datetime.now(UTC).isoformat(),
                            )
                        )
                        # 关键: 显式 commit, 防止 outer facade rollback 抹掉
                        # health 事件 (和 QuotaService 同样的修复)
                        if self._quota_session is not None:
                            await self._quota_session.commit()
                    except (RuntimeError, OSError) as _exc:  # defensive
                        _log.warning("health_event_write_failed: %s", _exc)
                # Phase 8: audit log (governance 表). 复用同一个 session (跨模块
                # ORM 风险由 raw SQL INSERT 规避 — 见 audit_service.py)
                if self._quota_session is not None:
                    try:
                        from qzdap.modules.model.application.audit_service import (
                            LLMAuditService,
                        )

                        await LLMAuditService(self._quota_session).record(
                            tenant_id=actor.tenant_id,
                            actor_id=actor.principal_id,  # type: ignore[arg-type]
                            model_id=UUID(str(model_id)),
                            provider_id=provider_id,
                            provider_name=provider_name,
                            latency_ms=latency_ms,
                            tokens_in=actual_in,
                            tokens_out=actual_out,
                            ok=ok,
                            error_class=type(err).__name__ if err else None,
                            error_message=str(err)[:500] if err else None,
                        )
                    except (RuntimeError, OSError, ValueError) as _exc:  # defensive
                        _log.warning("audit_record_failed: %s", _exc)

    # ── Phase 3: 路由 + 故障转移 ────────────────────────────────────────
    async def stream_with_fallback(
        self,
        *,
        actor: ActorContext,
        primary_model_id: ModelId,
        fallback_model_ids: list[ModelId],
        req: ChatRequest,
    ) -> AsyncIterator[LLMChunk]:
        """Phase 3: 失败转移链. 先 primary, 任何 ProviderTransportError 触发下一个.

        错误归类:
          - ProviderTransportError (任何 code: STREAM_ERROR / TRANSPORT_ERROR / INVALID_RESPONSE):
            触发 fallback (上游服务出错或流异常)
          - 业务异常 (ModelNotFound / CredentialNotFound / ModelDisabled): 不 fallback
            (配置问题, 换 model 没用), 直接抛

        第一个成功的流就赢; 全失败抛 ModelRouteExhausted.
        全过程通过 _log.warning 记录每一次 fallback, 便于 audit.
        """
        from qzdap_llm import ProviderTransportError

        from qzdap.modules.model.domain.errors import ModelRouteExhausted

        chain: list[ModelId] = [primary_model_id, *fallback_model_ids]
        last_exc: Exception | None = None
        for index, model_id in enumerate(chain):
            try:
                start = time.monotonic()
                yielded_any = False
                async for chunk in self.stream(
                    actor=actor, model_id=model_id, req=req
                ):
                    if index > 0 and not yielded_any:
                        # 第一个 fallback 刚开始产生 chunk 时, 在流前插一个 notice event
                        # (kind='message' 走同一个 SSE pipeline, 客户端按 chunk.kind 渲染)
                        _log.info(
                            "model_fallback_used",
                            extra={
                                "model_id": str(model_id),
                                "index": index,
                                "chain_length": len(chain),
                                "latency_ms_primary": int((time.monotonic() - start) * 1000),
                            },
                        )
                    yielded_any = True
                    yield chunk
                if not yielded_any:
                    # 流开了但立即 EOF, 视作错误
                    raise ProviderTransportError(code="LLM_STREAM_EMPTY")
                return
            except ProviderTransportError as exc:
                last_exc = exc
                _log.warning(
                    "model_fallback_triggered",
                    extra={
                        "model_id": str(model_id),
                        "index": index,
                        "chain_length": len(chain),
                        "error_class": type(exc).__name__,
                        "error": str(exc),
                    },
                )
                continue
        # 全失败
        raise ModelRouteExhausted(
            f"all {len(chain)} models in route failed; last error: {last_exc!r}"
        ) from last_exc

    # ── Phase 7: 策略路由 (quality-first / cost-first / latency-first) ────────
    # 输入: route_id (UUID) + actor. 从 admin_model_routes 读 primary_model_id + strategy,
    # 再用策略从 workspace 内 active model 里选 N 个候选, primary 不在候选时也走 chain.
    # 输出: 排序好的 list[ModelId] (第一个试, 失败按顺序 fallback).
    # 注: RouteRepository.get + workspace 内 list_for_workspace 都在 session 内.
    async def select_chain_for_strategy(
        self, *, actor: ActorContext, route_id: ModelId
    ) -> list[ModelId]:
        """Phase 7: 策略路由选择.

        strategy 语义:
          - 'fallback': 用 RouteRule.primary_model_id + fallback_model_ids (Phase 3 旧行为)
          - 'quality-first': workspace 内 active model, 按 tier 降序 (premium > balanced > economy),
            success_rate 降序, latency_ms 升序; primary 排第一
          - 'cost-first': 按 (price_in + price_out) 升序, primary 排第一
          - 'latency-first': 按 latency_ms 升序, primary 排第一

        返回的链: [primary_or_best, *fallback_candidates]. 全部走 admin_models.
        """
        from qzdap.modules.model.domain.errors import ModelNotFound

        rule = await self._routes.get(UUID(str(route_id)))
        if rule is None:
            raise ModelNotFound(f"route {route_id} not found")
        if not rule.enabled:
            raise ModelNotFound(f"route {route_id} is disabled")

        # workspace 内所有 active model
        all_models = await self._models.list_for_workspace(actor.workspace_id)  # type: ignore[arg-type]
        active = [m for m in all_models if m.status == "active"]
        if not active:
            raise ModelNotFound("no active models in workspace")

        strategy = rule.strategy
        primary_id = UUID(str(rule.primary_model_id))

        # 找到 primary 在 active 里的位置
        primary_in_active = next((m for m in active if m.id == primary_id), None)

        if strategy == "fallback":
            # 旧行为: primary + explicit fallback list
            chain: list[ModelId] = [primary_id]
            for fid in rule.fallback_model_ids:
                try:
                    chain.append(ModelId(UUID(str(fid))))
                except (ValueError, TypeError):
                    continue
            return chain

        if strategy == "quality-first":
            tier_order = {"premium": 0, "balanced": 1, "economy": 2}
            sorted_models = sorted(
                active,
                key=lambda m: (
                    tier_order.get(m.tier, 99),
                    -m.success_rate,
                    m.latency_ms,
                ),
            )
        elif strategy == "cost-first":
            sorted_models = sorted(
                active,
                key=lambda m: (m.price_in + m.price_out, m.latency_ms),
            )
        elif strategy == "latency-first":
            sorted_models = sorted(active, key=lambda m: (m.latency_ms, m.price_in))
        else:
            # 未知 strategy 当 fallback 处理
            _log.warning("unknown_strategy_fallback", extra={"strategy": strategy})
            sorted_models = active

        # primary 排第一 (如果它在 active 里)
        if primary_in_active is not None:
            chain = [primary_in_active.id]
            for m in sorted_models:
                if m.id == primary_id:
                    continue
                chain.append(m.id)
        else:
            chain = [m.id for m in sorted_models]
        return chain

    # 给 facade 暴露新方法 (Phase 7): 用 route_id 走策略选择 + fallback chain
    async def stream_with_route(
        self, *, actor: ActorContext, route_id: ModelId, req: ChatRequest
    ) -> AsyncIterator[LLMChunk]:
        """Phase 7: 策略路由 stream. select_chain_for_strategy 选链, 走 stream_with_fallback."""
        chain = await self.select_chain_for_strategy(
            actor=actor, route_id=route_id
        )
        if not chain:
            from qzdap.modules.model.domain.errors import ModelNotFound

            raise ModelNotFound(f"route {route_id} resolved to empty chain")
        async for chunk in self.stream_with_fallback(
            actor=actor,
            primary_model_id=chain[0],
            fallback_model_ids=chain[1:],
            req=req,
        ):
            yield chunk


__all__ = ["ModelService"]
