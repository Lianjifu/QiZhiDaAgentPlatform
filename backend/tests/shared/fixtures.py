"""Shared pytest fixtures.

* `pg_session` and `redis_client` start pgvector/Redis testcontainers only
  when the `integration` or `contract` marker is requested; for plain unit
  tests they stay unused and no containers are spawned.
* `_ensure_qzdap_env` autouse fixture sets safe defaults for any test that
  reads QZDAP_-prefixed settings without going through an env file.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest

# ── Defaults usable across all tests ─────────────────────────────────────────


@pytest.fixture(autouse=True)
def _ensure_qzdap_env() -> None:
    """Set safe defaults for tests that don't go through env files."""
    os.environ.setdefault("QZDAP_ENV", "test")
    os.environ.setdefault("QZDAP_JWT_SECRET", "test-secret-not-for-production-use-only")
    os.environ.setdefault("QZDAP_LLM_PROVIDER", "mock")
    os.environ.setdefault("QZDAP_BAN_MOCK_TOKEN", "1")
    os.environ.setdefault("QZDAP_ALLOW_DEMO_TOKEN", "0")


# ── Async event loop (pytest-asyncio in auto mode handles this; kept for
#    any tests that need explicit loop control) ──────────────────────────────


@pytest.fixture
def event_loop():  # type: ignore[no-untyped-def]
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Integration / contract: pg + redis testcontainers ──────────────────────
#
# `testcontainers-python` is an optional dev dep. If the library isn't
# installed we skip rather than fail; CI installs it via the `dev` extra.


def _has_testcontainers() -> bool:
    try:
        import testcontainers  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.fixture(scope="session")
def pg_dsn() -> str:
    """Boot a single pgvector container per test session, return its DSN.

    Skips the test if `testcontainers` isn't installed locally.
    """
    if not _has_testcontainers():
        pytest.skip("testcontainers-python not installed")
    from testcontainers.postgres import PostgresContainer

    pg = PostgresContainer("pgvector/pgvector:pg16")
    pg.start()
    try:
        # asyncpg URL form
        url = pg.get_connection_url()
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        yield url
    finally:
        pg.stop()


@pytest.fixture(scope="session")
def redis_url() -> str:
    """Boot a single Redis container per test session, return its URL."""
    if not _has_testcontainers():
        pytest.skip("testcontainers-python not installed")
    from testcontainers.redis import RedisContainer

    r = RedisContainer("redis:7")
    r.start()
    try:
        yield f"redis://{r.get_container_host_ip()}:{r.get_exposed_port(6379)}/0"
    finally:
        r.stop()


@pytest.fixture(scope="session")
def pg_session(pg_dsn: str):
    """Run schema migrations against the pgvector container once per session.

    Yields nothing — tests build their own AsyncSession via SessionFactory.
    """
    from qzdap_persistence.session_factory import SessionFactory

    sf = SessionFactory(_async_url(pg_dsn))
    try:
        yield sf
    finally:
        import asyncio

        asyncio.run(sf.dispose())


@pytest.fixture(scope="session")
def redis_client(redis_url: str):
    """Yield an async Redis client connected to the testcontainer."""
    from redis.asyncio import Redis

    client = Redis.from_url(redis_url, decode_responses=False)
    try:
        yield client
    finally:
        import asyncio

        asyncio.run(client.aclose())


@pytest.fixture(scope="session")
def kafka_bootstrap_servers() -> str:
    """Boot a single Kafka KRaft container per test session, return bootstrap.

    Skips if ``testcontainers[kafka]`` is not installed (CI installs it
    via the dev extra).
    """
    if not _has_testcontainers():
        pytest.skip("testcontainers-python not installed")
    try:
        from testcontainers.kafka import KafkaContainer
    except ImportError as exc:
        pytest.skip(f"testcontainers[kafka] not available: {exc}")

    from testcontainers.kafka import KafkaContainer

    kafka = KafkaContainer("bitnami/kafka:3.7")
    kafka.start()
    try:
        host = kafka.get_container_host_ip()
        port = kafka.get_exposed_port(9092)
        yield f"{host}:{port}"
    finally:
        kafka.stop()


def _async_url(dsn: str) -> str:
    if dsn.startswith("postgresql+asyncpg://"):
        return dsn
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    return dsn


# ── Markers ────────────────────────────────────────────────────────────────


def pytest_configure(config: Any) -> None:
    config.addinivalue_line("markers", "integration: requires PG/Redis")
    config.addinivalue_line("markers", "contract: contract test")
    config.addinivalue_line("markers", "smoke: end-to-end smoke test")
