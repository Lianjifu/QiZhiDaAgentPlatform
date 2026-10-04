"""Self-evolution integration suite — Postgres-backed.

Spins up the ``evolve_candidates`` table in a per-test schema so each
test is independent. Skips the entire suite when the dev DB is
unreachable.
"""

from __future__ import annotations

import os
import socket
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

_EVOLVE_DDL = """
CREATE TABLE IF NOT EXISTS evolve_candidates (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    workspace_id UUID,
    kind VARCHAR(32) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    trigger_reason VARCHAR(256) NOT NULL DEFAULT '',
    fingerprint VARCHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    requester_id UUID,
    approver_id UUID,
    reviewed_at TIMESTAMPTZ,
    applied_at TIMESTAMPTZ,
    correlation_id UUID,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_evolve_candidates_fingerprint UNIQUE (tenant_id, fingerprint),
    CONSTRAINT ck_evolve_candidates_status
        CHECK (status IN ('pending','approved','rejected','applied')),
    CONSTRAINT ck_evolve_candidates_kind
        CHECK (kind IN ('memory_promote','skill_patch','routing_hint','dream'))
);
CREATE INDEX IF NOT EXISTS ix_evolve_candidates_tenant_status
    ON evolve_candidates (tenant_id, status);
CREATE INDEX IF NOT EXISTS ix_evolve_candidates_tenant_created
    ON evolve_candidates (tenant_id, created_at);
"""


_DEFAULT_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5499/postgres"


def _db_reachable(url: str) -> bool:
    try:
        bare = url.split("://", 1)[1]
        auth_host = bare.split("@", 1)[1]
        host_port, _ = auth_host.split("/", 1)
        host, port = host_port.rsplit(":", 1)
        with socket.create_connection((host, int(port)), timeout=1.0):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.environ.get("QZDAP_DATABASE_URL", _DEFAULT_DB_URL)


@pytest.fixture(scope="session", autouse=True)
def _require_postgres(database_url: str) -> None:
    if not _db_reachable(database_url):
        pytest.skip(
            f"postgres unreachable at {database_url}; "
            "self_evolution integration tests require the dev DB",
            allow_module_level=True,
        )


@pytest.fixture(scope="session")
def schema_name() -> str:
    return f"qzdap_evo_test_{uuid.uuid4().hex[:8]}"


def _register_search_path(engine: AsyncEngine, schema: str) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        try:
            cur.execute(f'SET search_path TO "{schema}"')
        finally:
            cur.close()


@pytest_asyncio.fixture
async def engine(database_url: str, schema_name: str):
    eng = create_async_engine(database_url, future=True, poolclass=NullPool)
    _register_search_path(eng, schema_name)
    async with eng.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
        await conn.execute(text(f'SET search_path TO "{schema_name}"'))
        for stmt in _EVOLVE_DDL.strip().split(";"):
            s = stmt.strip()
            if s:
                await conn.execute(text(s))
    yield eng
    async with eng.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
    await eng.dispose()


@pytest_asyncio.fixture
async def postgres_session_factory(
    engine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
