"""Real PostgreSQL regressions in a transaction-only disposable schema."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from dotenv import dotenv_values
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from qzdap.modules.model.adapter.persistence.models import (
    CatalogModelORM,
    HealthEventORM,
    ProviderORM,
    RouteORM,
)
from qzdap.modules.model.adapter.persistence.repositories import (
    SqlHealthRepository,
    SqlModelRepository,
    SqlProviderRepository,
    SqlRouteRepository,
)
from qzdap.modules.model.application.services import ModelService

BACKEND = Path(__file__).resolve().parents[4]


class Cipher:
    def encrypt(self, value, *, aad=None):
        return aad + b"\x00" + value

    def decrypt(self, value, *, aad=None):
        stored, plain = value.split(b"\x00", 1)
        assert stored == aad
        return plain


class Catalog:
    async def list_models(self, **kwargs):
        return ["upstream-one", "upstream-two"]


def service(session, tenant, workspace):
    svc = ModelService(
        SqlModelRepository(session),
        SqlProviderRepository(session),
        SqlRouteRepository(session),
        SqlHealthRepository(session),
        cipher=Cipher(),
        prober=Catalog(),
    )
    svc.bind_scope(
        tenant_id=tenant,
        workspace_id=workspace,
        actor_id=uuid4(),
        actor_name="Database Admin",
    )
    return svc


def migrate(connection):
    path = BACKEND / "migrations/versions/0029_model_upstream.py"
    spec = importlib.util.spec_from_file_location("model_upstream_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with Operations.context(MigrationContext.configure(connection)):
        module.upgrade()


@pytest.mark.asyncio
async def test_migration_shared_credentials_and_rollback():
    url = os.environ.get("QZDAP_DATABASE_URL") or dotenv_values(BACKEND / ".env").get(
        "QZDAP_DATABASE_URL"
    )
    if not url:
        pytest.skip("local development PostgreSQL is not configured")
    parsed = make_url(url)
    if parsed.host not in {"localhost", "127.0.0.1"} or parsed.port not in {9153, 5499}:
        pytest.skip(
            "this integration test only permits the local development PostgreSQL"
        )
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                schema = "model_test_" + uuid4().hex
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
                for table in [
                    ProviderORM.__table__,
                    CatalogModelORM.__table__,
                    RouteORM.__table__,
                    HealthEventORM.__table__,
                ]:
                    await connection.run_sync(
                        lambda conn, table=table: table.create(conn)
                    )
                # Exercise the real migration, including a pre-existing legacy name.
                await connection.execute(
                    text("ALTER TABLE admin_models DROP COLUMN upstream_model")
                )
                await connection.execute(
                    text("ALTER TABLE admin_model_providers DROP COLUMN api_version")
                )
                legacy, tenant, workspace, provider = uuid4(), uuid4(), uuid4(), uuid4()
                await connection.execute(
                    text(
                        "INSERT INTO admin_models (id, tenant_id, workspace_id, name, provider_id) VALUES (:id,:tenant,:workspace,'legacy-model',:provider)"
                    ),
                    {
                        "id": legacy,
                        "tenant": tenant,
                        "workspace": workspace,
                        "provider": provider,
                    },
                )
                await connection.run_sync(migrate)
                assert (
                    await connection.execute(
                        text("SELECT upstream_model FROM admin_models WHERE id=:id"),
                        {"id": legacy},
                    )
                ).scalar_one() == "legacy-model"
                await connection.execute(
                    text("DELETE FROM admin_models WHERE id=:id"), {"id": legacy}
                )
                async with AsyncSession(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    svc = service(session, tenant, workspace)
                    created = await svc.create_from_provider(
                        tenant_id=tenant,
                        workspace_id=workspace,
                        body={
                            "providerName": "Shared",
                            "protocol": "openai",
                            "baseUrl": "https://api.example.com/v1",
                            "apiKey": "db-secret-1234",
                            "source": "catalog",
                            "models": ["upstream-one", "upstream-two"],
                        },
                    )
                    mid = UUID(created["id"])
                    await session.commit()
                    before_id = created["providerId"]
                    updated = await svc.update_model(
                        model_id=mid,
                        body={
                            "patch": {
                                "upstreamModel": "upstream-two",
                                "source": "catalog",
                                "provider": {
                                    "name": "Current",
                                    "apiKey": "",
                                    "baseUrl": "https://new.example.com/v1",
                                },
                            }
                        },
                    )
                    await session.commit()
                    assert updated["providerId"] != before_id
                    assert updated["id"] == str(mid)
                    assert (
                        svc._decrypt(await svc._provider(await svc._require_model(mid)))
                        == "db-secret-1234"
                    )
                    assert (
                        await session.execute(
                            select(func.count()).select_from(ProviderORM)
                        )
                    ).scalar_one() == 2
            finally:
                await (
                    transaction.rollback()
                )  # Removes schema, tables, migration and every test row.
    finally:
        await engine.dispose()
