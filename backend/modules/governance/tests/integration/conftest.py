"""Governance integration suite — Postgres-backed.

Spins up the four governance tables (``policies``, ``approvals``,
``decision_events``, ``audit_log``) in a per-session schema on the dev
``qzdap-postgres`` container. The schema name is unique per test run so
concurrent suites don't collide. Tables are torn down at session end.

Connects via ``QZDAP_DATABASE_URL`` (default: postgres on localhost:5499).
Skips the entire suite if the database is unreachable so a developer's
machine without docker doesn't fail the whole unit test run.
"""

from __future__ import annotations

import os
import socket
import uuid
from collections.abc import AsyncIterator

import qzdap_persistence.pgvector  # noqa: F401
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

from qzdap.modules.governance.adapter.persistence import (
    models as gov_models,  # noqa: F401
)

_GOVERNANCE_DDL = """
CREATE TABLE IF NOT EXISTS policies (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    workspace_id UUID,
    subject_type VARCHAR(16) NOT NULL,
    subject_ref VARCHAR(256) NOT NULL,
    action_pattern VARCHAR(256) NOT NULL,
    effect VARCHAR(16) NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    approval_required BOOLEAN NOT NULL DEFAULT false,
    quota JSONB,
    enabled BOOLEAN NOT NULL DEFAULT true,
    version_lock INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_policies_effect CHECK (effect IN ('allow','deny','approval')),
    CONSTRAINT ck_policies_subject CHECK (subject_type IN ('role','user','agent'))
);
CREATE INDEX IF NOT EXISTS ix_policies_tenant_id ON policies (tenant_id);
CREATE INDEX IF NOT EXISTS ix_policies_enabled_lookup
    ON policies (tenant_id, subject_type, action_pattern) WHERE enabled;

CREATE TABLE IF NOT EXISTS approvals (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    requester_id UUID NOT NULL,
    resource JSONB NOT NULL,
    action VARCHAR(256) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    approver_id UUID,
    decided_at TIMESTAMPTZ,
    correlation_id UUID,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_approvals_status CHECK (status IN ('pending','approved','denied','expired'))
);
CREATE INDEX IF NOT EXISTS ix_approvals_tenant_id ON approvals (tenant_id);
CREATE INDEX IF NOT EXISTS ix_approvals_tenant_status_created
    ON approvals (tenant_id, status, created_at);

CREATE TABLE IF NOT EXISTS decision_events (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    actor_id UUID NOT NULL,
    action VARCHAR(256) NOT NULL,
    effect VARCHAR(16) NOT NULL,
    resource JSONB,
    rule_id UUID,
    approval_id UUID,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_decision_events_tenant_created
    ON decision_events (tenant_id, created_at);

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    actor_id UUID,
    event_type VARCHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_audit_log_tenant_created
    ON audit_log (tenant_id, created_at);
CREATE INDEX IF NOT EXISTS ix_audit_log_tenant_event
    ON audit_log (tenant_id, event_type);
"""


_DEFAULT_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5499/postgres"


def _db_reachable(url: str) -> bool:
    """Best-effort TCP probe so we can skip cleanly when no DB is up."""
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
            "governance integration tests require the dev DB",
            allow_module_level=True,
        )


@pytest.fixture(scope="session")
def schema_name() -> str:
    return f"qzdap_gov_test_{uuid.uuid4().hex[:8]}"


def _register_search_path(engine: AsyncEngine, schema: str) -> None:
    """Set ``search_path`` on every new connection from this engine."""

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        try:
            cur.execute(f'SET search_path TO "{schema}"')
        finally:
            cur.close()


@pytest_asyncio.fixture
async def engine(database_url: str, schema_name: str):
    """Function-scoped engine.

    pytest-asyncio 1.4 with default ``loop_scope=function`` makes
    session-scoped async fixtures impossible without overriding
    ``asyncio_default_fixture_loop_scope = session``. Instead we
    recreate the engine per test and rebuild the schema — it's cheap
    (4 tables, no data) and keeps each test independent.
    """
    eng = create_async_engine(database_url, future=True, poolclass=NullPool)
    _register_search_path(eng, schema_name)
    async with eng.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
        await conn.execute(text(f'SET search_path TO "{schema_name}"'))
        # Apply raw DDL from migration 0007_governance.py so the table
        # structure matches what production runs use, sidestepping the
        # double-index declaration in PolicyORM (the column has
        # `index=True` AND a stand-alone ``Index(...)`` for the same
        # name).
        for stmt in _GOVERNANCE_DDL.strip().split(";"):
            s = stmt.strip()
            if s:
                await conn.execute(text(s))
    yield eng
    async with eng.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
