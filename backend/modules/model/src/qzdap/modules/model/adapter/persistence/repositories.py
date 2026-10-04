from __future__ import annotations

from uuid import UUID

from qzdap_persistence.tenant_guard import current_tenant_id
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.model.adapter.persistence.models import (
    CatalogModelORM,
    HealthEventORM,
    ProviderORM,
    RouteORM,
)
from qzdap.modules.model.application.ports import (
    HealthRepository,
    ModelRepository,
    ProviderRepository,
    RouteRepository,
)
from qzdap.modules.model.domain.entities import HealthEvent, Model, Provider, RouteRule


def _cross_tenant(row: object) -> bool:
    bound = current_tenant_id()
    if bound is None:
        return False
    return getattr(row, "tenant_id", None) != bound


def _provider_to_domain(row: ProviderORM) -> Provider:
    return Provider(
        id=row.id,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        name=row.name,
        region=row.region,
        status=row.status,  # type: ignore[arg-type]
        base_url=row.base_url,
        api_key_masked=row.api_key_masked,
        protocol=row.protocol,  # type: ignore[arg-type]
        encrypted_payload=bytes(row.encrypted_payload or b""),
        error_rate=row.error_rate,
        avg_latency_ms=row.avg_latency_ms,
        qps=row.qps,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _apply_provider(row: ProviderORM, provider: Provider) -> None:
    row.name = provider.name
    row.region = provider.region
    row.status = provider.status
    row.base_url = provider.base_url
    row.api_key_masked = provider.api_key_masked
    row.protocol = provider.protocol
    row.encrypted_payload = provider.encrypted_payload
    row.error_rate = provider.error_rate
    row.avg_latency_ms = provider.avg_latency_ms
    row.qps = provider.qps
    row.updated_at = provider.updated_at


def _model_to_domain(row: CatalogModelORM) -> Model:
    return Model(
        id=row.id,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        name=row.name,
        provider_id=row.provider_id,
        provider_name=row.provider_name,
        task=list(row.task or []),
        context_window=row.context_window,
        price_in=row.price_in,
        price_out=row.price_out,
        latency_ms=row.latency_ms,
        success_rate=row.success_rate,
        status=row.status,  # type: ignore[arg-type]
        tier=row.tier,  # type: ignore[arg-type]
        starred=row.starred,
        calls=row.calls,
        trend=list(row.trend or [0] * 12),
        description=row.description,
        tags=list(row.tags or []),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _apply_model(row: CatalogModelORM, model: Model) -> None:
    row.name = model.name
    row.provider_id = model.provider_id
    row.provider_name = model.provider_name
    row.task = list(model.task)
    row.context_window = model.context_window
    row.price_in = model.price_in
    row.price_out = model.price_out
    row.latency_ms = model.latency_ms
    row.success_rate = model.success_rate
    row.status = model.status
    row.tier = model.tier
    row.starred = model.starred
    row.calls = model.calls
    row.trend = list(model.trend)
    row.description = model.description
    row.tags = list(model.tags)
    row.updated_at = model.updated_at


class SqlProviderRepository(ProviderRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, provider: Provider) -> None:
        row = ProviderORM(
            id=provider.id,
            tenant_id=provider.tenant_id,
            workspace_id=provider.workspace_id,
            created_at=provider.created_at,
            updated_at=provider.updated_at,
        )
        _apply_provider(row, provider)
        self._s.add(row)

    async def get(self, provider_id: UUID) -> Provider | None:
        row = await self._s.get(ProviderORM, provider_id)
        if row is None or _cross_tenant(row):
            return None
        return _provider_to_domain(row)

    async def list_for_workspace(self, workspace_id: UUID) -> list[Provider]:
        result = await self._s.execute(
            select(ProviderORM).where(ProviderORM.workspace_id == workspace_id)
        )
        return [_provider_to_domain(row) for row in result.scalars().all() if not _cross_tenant(row)]

    async def update(self, provider: Provider) -> None:
        row = await self._s.get(ProviderORM, provider.id)
        if row is None or _cross_tenant(row):
            return
        _apply_provider(row, provider)


class SqlModelRepository(ModelRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, model: Model) -> None:
        row = CatalogModelORM(
            id=model.id,
            tenant_id=model.tenant_id,
            workspace_id=model.workspace_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
        _apply_model(row, model)
        self._s.add(row)

    async def get(self, model_id: UUID) -> Model | None:
        row = await self._s.get(CatalogModelORM, model_id)
        if row is None or _cross_tenant(row):
            return None
        return _model_to_domain(row)

    async def list_for_workspace(self, workspace_id: UUID) -> list[Model]:
        result = await self._s.execute(
            select(CatalogModelORM).where(CatalogModelORM.workspace_id == workspace_id)
        )
        return [_model_to_domain(row) for row in result.scalars().all() if not _cross_tenant(row)]

    async def update(self, model: Model) -> None:
        row = await self._s.get(CatalogModelORM, model.id)
        if row is None or _cross_tenant(row):
            return
        _apply_model(row, model)

    async def delete(self, model_id: UUID) -> None:
        row = await self._s.get(CatalogModelORM, model_id)
        if row is None or _cross_tenant(row):
            return
        await self._s.delete(row)


class SqlRouteRepository(RouteRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, route: RouteRule) -> None:
        self._s.add(
            RouteORM(
                id=route.id,
                tenant_id=route.tenant_id,
                workspace_id=route.workspace_id,
                name=route.name,
                task=route.task,
                strategy=route.strategy,
                priority=route.priority,
                primary_model_id=route.primary_model_id,
                fallback_model_ids=list(route.fallback_model_ids),
                enabled=route.enabled,
                description=route.description,
                created_at=route.created_at,
                updated_at=route.updated_at,
            )
        )

    async def get(self, route_id: UUID) -> RouteRule | None:
        row = await self._s.get(RouteORM, route_id)
        if row is None or _cross_tenant(row):
            return None
        return RouteRule(
            id=row.id,
            tenant_id=row.tenant_id,
            workspace_id=row.workspace_id,
            name=row.name,
            task=row.task,  # type: ignore[arg-type]
            strategy=row.strategy,  # type: ignore[arg-type]
            priority=row.priority,
            primary_model_id=row.primary_model_id,
            fallback_model_ids=[str(item) for item in (row.fallback_model_ids or [])],
            enabled=row.enabled,
            description=row.description,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def list_for_workspace(self, workspace_id: UUID) -> list[RouteRule]:
        result = await self._s.execute(select(RouteORM).where(RouteORM.workspace_id == workspace_id))
        out: list[RouteRule] = []
        for row in result.scalars().all():
            if _cross_tenant(row):
                continue
            out.append(
                RouteRule(
                    id=row.id,
                    tenant_id=row.tenant_id,
                    workspace_id=row.workspace_id,
                    name=row.name,
                    task=row.task,  # type: ignore[arg-type]
                    strategy=row.strategy,  # type: ignore[arg-type]
                    priority=row.priority,
                    primary_model_id=row.primary_model_id,
                    fallback_model_ids=[str(item) for item in (row.fallback_model_ids or [])],
                    enabled=row.enabled,
                    description=row.description,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
            )
        return out

    async def update(self, route: RouteRule) -> None:
        row = await self._s.get(RouteORM, route.id)
        if row is None or _cross_tenant(row):
            return
        row.name = route.name
        row.task = route.task
        row.strategy = route.strategy
        row.priority = route.priority
        row.primary_model_id = route.primary_model_id
        row.fallback_model_ids = list(route.fallback_model_ids)
        row.enabled = route.enabled
        row.description = route.description
        row.updated_at = route.updated_at

    async def delete(self, route_id: UUID) -> None:
        row = await self._s.get(RouteORM, route_id)
        if row is None or _cross_tenant(row):
            return
        await self._s.delete(row)


class SqlHealthRepository(HealthRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, event: HealthEvent) -> None:
        self._s.add(
            HealthEventORM(
                id=event.id,
                tenant_id=event.tenant_id,
                workspace_id=event.workspace_id,
                type=event.type,
                provider_id=event.provider_id,
                provider_name=event.provider_name,
                message=event.message,
                occurred_at=event.occurred_at,
                created_at=event.created_at,
                updated_at=event.created_at,
            )
        )

    async def list_for_workspace(self, workspace_id: UUID, limit: int = 50) -> list[HealthEvent]:
        result = await self._s.execute(
            select(HealthEventORM)
            .where(HealthEventORM.workspace_id == workspace_id)
            .order_by(HealthEventORM.created_at.desc())
            .limit(limit)
        )
        rows: list[HealthEvent] = []
        for row in result.scalars().all():
            if _cross_tenant(row):
                continue
            rows.append(
                HealthEvent(
                    id=row.id,
                    tenant_id=row.tenant_id,
                    workspace_id=row.workspace_id,
                    type=row.type,  # type: ignore[arg-type]
                    provider_id=row.provider_id,
                    provider_name=row.provider_name,
                    message=row.message,
                    occurred_at=row.occurred_at,
                    created_at=row.created_at,
                )
            )
        return rows
