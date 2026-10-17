"""Phase 21: round-robin + weighted 端到端 integration.

通过 ModelService.select_chain_for_strategy 走真 DB, 验证:
  - round-robin: 多次调用, fallback 段轮转; primary 固定第一
  - weighted: dict-list [{id, weight}] 按 weight 比例采样
  - string-list (旧格式) 走 uniform weight
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest
from qzdap_schema.ids import ModelId
from qzdap_vault.actor import ActorContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from qzdap.modules.model.adapter.persistence.models import (
    CatalogModelORM,
    HealthEventORM,
    ProviderORM,
    RouteORM,
)
from qzdap.modules.model.adapter.persistence.repositories import (
    SqlModelRepository,
    SqlProviderRepository,
    SqlRouteRepository,
)
from qzdap.modules.model.application.services import ModelService
from qzdap.modules.model.domain.entities import HealthEvent, Model, Provider, RouteRule


def _pg_dsn() -> str:
    return os.environ.get(
        "QZDAP_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:9153/qzdap_dev",
    ).replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture
async def setup_db() -> Any:
    url = os.environ.get("QZDAP_TEST_DATABASE_URL", _pg_dsn())
    if not os.environ.get("QZDAP_TEST_DATABASE_URL"):
        pytest.skip("QZDAP_TEST_DATABASE_URL is not set")
    engine = create_async_engine(url)
    schema = "strat_p21_" + uuid4().hex
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        for table in [
            HealthEventORM.__table__,
            ProviderORM.__table__,
            CatalogModelORM.__table__,
            RouteORM.__table__,
        ]:
            await connection.run_sync(
                lambda conn, table=table: table.create(conn)
            )

        @asynccontextmanager
        async def session():
            yield AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )

        tenant = uuid4()
        workspace = uuid4()
        try:
            yield {"session": session, "tenant": tenant, "workspace": workspace}
        finally:
            await transaction.rollback()
    await engine.dispose()


async def _seed_models_and_route(
    setup: Any,
    *,
    n_models: int = 4,
    strategy: str = "round-robin",
    fallback_model_ids: list[Any] | None = None,
    model_ids: list[UUID] | None = None,
) -> dict[str, Any]:
    """Seed n active models in workspace + 1 route with given strategy.

    ``model_ids`` 可外部传入, 避免多次 seed 时新 model 不在 fallback 配里.
    """
    import datetime as _dt

    tenant = setup["tenant"]
    workspace = setup["workspace"]
    provider_id = uuid4()
    if model_ids is None:
        primary_id = uuid4()
        model_ids = [primary_id] + [uuid4() for _ in range(n_models - 1)]
    else:
        primary_id = model_ids[0]
    now = _dt.datetime.now(_dt.UTC)
    async with setup["session"]() as db:
        # provider
        await db.execute(
            text(
                "INSERT INTO admin_model_providers (id, tenant_id, workspace_id, "
                "name, region, status, base_url, protocol, api_key_masked, "
                "encrypted_payload, error_rate, avg_latency_ms, qps, created_at, updated_at) "
                "VALUES (:id, :t, :w, 'p', 'global', 'healthy', 'https://x.com', 'openai', '****', "
                "CAST('' AS bytea), 0, 0, 0, :now, :now)"
            ),
            {"id": provider_id, "t": tenant, "w": workspace, "now": now},
        )
        # models
        for idx, mid in enumerate(model_ids):
            await db.execute(
                text(
                    "INSERT INTO admin_models (id, tenant_id, workspace_id, "
                    "provider_id, provider_name, name, upstream_model, status, tier, "
                    "context_window, price_in, price_out, latency_ms, success_rate, "
                    "calls, trend, description, tags, created_at, updated_at) "
                    "VALUES (:id, :t, :w, :pid, 'p', :name, :name, 'active', 'balanced', "
                    "8000, 0.001, 0.002, 100, 99.0, 0, '[]'::jsonb, '', '[]'::jsonb, :now, :now)"
                ),
                {
                    "id": mid,
                    "t": tenant,
                    "w": workspace,
                    "pid": provider_id,
                    "name": f"m{idx}",
                    "now": now,
                },
            )
        # route
        route_id = uuid4()
        # serialize fallback to JSON-safe list
        fb_serialized: list[Any] = []
        for item in fallback_model_ids or []:
            if isinstance(item, dict):
                fb_serialized.append({k: str(v) if isinstance(v, UUID) else v for k, v in item.items()})
            elif isinstance(item, UUID):
                fb_serialized.append(str(item))
            else:
                fb_serialized.append(str(item))
        await db.execute(
            text(
                "INSERT INTO admin_model_routes (id, tenant_id, workspace_id, "
                "name, task, strategy, priority, primary_model_id, fallback_model_ids, "
                "enabled, description, created_at, updated_at) "
                "VALUES (:id, :t, :w, 'r', 'generation', :strategy, 0, :pm, "
                "CAST(:fb AS jsonb), true, '', :now, :now)"
            ),
            {
                "id": route_id,
                "t": tenant,
                "w": workspace,
                "strategy": strategy,
                "pm": primary_id,
                "fb": _safe_json_dumps(fb_serialized),
                "now": now,
            },
        )
        await db.commit()
    return {
        "tenant": tenant,
        "workspace": workspace,
        "primary_id": primary_id,
        "model_ids": model_ids,
        "route_id": route_id,
    }


def _safe_json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, default=str)


def _make_svc(setup: Any) -> ModelService:
    return ModelService(
        models=_FakeModels(setup),  # type: ignore[arg-type]
        providers=_FakeProviders(setup),  # type: ignore[arg-type]
        routes=_FakeRoutes(setup),  # type: ignore[arg-type]
        health=_FakeHealth(),  # type: ignore[arg-type]
    )


class _FakeModels:
    """用真 SqlModelRepository, session 来自 setup['session']."""

    def __init__(self, setup: Any) -> None:
        self._setup = setup

    async def add(self, model: Model) -> None:
        raise NotImplementedError("use session directly")

    async def get(self, model_id: UUID) -> Model | None:
        async with self._setup["session"]() as db:
            return await SqlModelRepository(db).get(model_id)

    async def list_for_workspace(self, workspace_id: UUID) -> list[Model]:
        async with self._setup["session"]() as db:
            return await SqlModelRepository(db).list_for_workspace(workspace_id)

    async def update(self, model: Model) -> None:
        raise NotImplementedError

    async def delete(self, model_id: UUID) -> None:
        raise NotImplementedError


class _FakeProviders:
    def __init__(self, setup: Any) -> None:
        self._setup = setup

    async def get(self, provider_id: UUID) -> Provider | None:
        async with self._setup["session"]() as db:
            return await SqlProviderRepository(db).get(provider_id)

    async def list_for_workspace(self, workspace_id: UUID) -> list[Provider]:
        async with self._setup["session"]() as db:
            return await SqlProviderRepository(db).list_for_workspace(workspace_id)

    async def add(self, provider: Provider) -> None:
        raise NotImplementedError

    async def update(self, provider: Provider) -> None:
        raise NotImplementedError


class _FakeRoutes:
    def __init__(self, setup: Any) -> None:
        self._setup = setup

    async def get(self, route_id: UUID) -> RouteRule | None:
        async with self._setup["session"]() as db:
            return await SqlRouteRepository(db).get(route_id)

    async def list_for_workspace(self, workspace_id: UUID) -> list[RouteRule]:
        async with self._setup["session"]() as db:
            return await SqlRouteRepository(db).list_for_workspace(workspace_id)

    async def add(self, route: RouteRule) -> None:
        raise NotImplementedError

    async def update(self, route: RouteRule) -> None:
        raise NotImplementedError

    async def delete(self, route_id: UUID) -> None:
        raise NotImplementedError


class _FakeHealth:
    async def add(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def list_for_workspace(
        self, *_args: Any, **_kwargs: Any
    ) -> list[HealthEvent]:
        return []


@pytest.mark.asyncio
async def test_select_chain_round_robin_through_real_db(setup_db: Any) -> None:
    """端到端 round-robin 走真 DB + 真 RouteORM."""
    # 注意: SqlRouteRepository 反序列化时 fallback_model_ids 仍是 list[str]
    setup = await _seed_models_and_route(
        setup_db, n_models=4, strategy="round-robin"
    )
    svc = _make_svc(setup_db)
    actor = ActorContext(tenant_id=setup["tenant"], workspace_id=setup["workspace"])
    seen_starts: list[UUID] = []
    primary = setup["primary_id"]
    for _ in range(6):
        chain = await svc.select_chain_for_strategy(
            actor=actor, route_id=ModelId(setup["route_id"])
        )
        assert UUID(str(chain[0])) == primary
        seen_starts.append(UUID(str(chain[1])))
    # 6 次轮转 3 个 fallback (4 models - 1 primary) → 每个出现 2 次
    from collections import Counter

    counts = Counter(seen_starts)
    fallbacks = [m for m in setup["model_ids"] if m != primary]
    for fb in fallbacks:
        assert counts[fb] == 2, f"fallback {fb} 出现 {counts[fb]} 次, 期望 2"


@pytest.mark.asyncio
async def test_select_chain_weighted_with_dict_fallback(setup_db: Any) -> None:
    """weighted 用 [{id, weight}] 配 → 按 weight 采样.

    关键: 预先计算 model_ids, 再 seed 一次, 保证 fallback 配里的 id 真的
    指向 workspace 的 active models. 否则两次 seed 会用新 uuid, 配漂移.
    """
    primary_id = uuid4()
    m1, m2, m3 = uuid4(), uuid4(), uuid4()
    model_ids = [primary_id, m1, m2, m3]
    setup = await _seed_models_and_route(
        setup_db,
        n_models=4,
        strategy="weighted",
        fallback_model_ids=[
            {"id": str(m1), "weight": 1.0},
            {"id": str(m2), "weight": 3.0},
            {"id": str(m3), "weight": 0.5},
        ],
        model_ids=model_ids,
    )
    svc = _make_svc(setup_db)
    actor = ActorContext(tenant_id=setup["tenant"], workspace_id=setup["workspace"])
    chosen_counter: dict[UUID, int] = {m: 0 for m in model_ids}
    for _ in range(80):
        chain = await svc.select_chain_for_strategy(
            actor=actor, route_id=ModelId(setup["route_id"])
        )
        assert UUID(str(chain[0])) == primary_id
        chosen_counter[UUID(str(chain[1]))] += 1
    # m2 weight=3 应出现最多
    assert chosen_counter[m2] > chosen_counter[m1]
    assert chosen_counter[m1] > chosen_counter[m3]
    # primary 不在 chosen
    assert chosen_counter[primary_id] == 0


@pytest.mark.asyncio
async def test_select_chain_weighted_string_list_uniform(setup_db: Any) -> None:
    """weighted 旧 string-list 配 → uniform weight."""
    primary_id = uuid4()
    m1, m2 = uuid4(), uuid4()
    model_ids = [primary_id, m1, m2]
    setup = await _seed_models_and_route(
        setup_db,
        n_models=3,
        strategy="weighted",
        fallback_model_ids=[str(m1), str(m2)],
        model_ids=model_ids,
    )
    svc = _make_svc(setup_db)
    actor = ActorContext(tenant_id=setup["tenant"], workspace_id=setup["workspace"])
    seen: list[UUID] = []
    for _ in range(60):
        chain = await svc.select_chain_for_strategy(
            actor=actor, route_id=ModelId(setup["route_id"])
        )
        seen.append(UUID(str(chain[1])))
    from collections import Counter

    counts = Counter(seen)
    assert counts[m1] > 0
    assert counts[m2] > 0
