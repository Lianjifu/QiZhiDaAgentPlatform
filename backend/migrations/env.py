"""Alembic env for 企智搭 · 智能体平台.

Imports every module's metadata so `alembic revision --autogenerate` picks
up new tables. Connection URL comes from env (QZDAP_DATABASE_URL).
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig
from typing import TYPE_CHECKING

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

# Import the global Base; every model attaches itself on import.
from qzdap_persistence.base import Base
import qzdap_persistence.pgvector
from qzdap_persistence.pgvector import register_pgvector
from pgvector.sqlalchemy import Vector

register_pgvector()
# Pre-0009 migrations (0006_memory) reference ``postgresql.VECTOR(N)``;
# pgvector only exposes ``Vector``. Expose the uppercase alias so old
# migrations resolve without a schema rewrite.
from sqlalchemy.dialects import postgresql as _pg

_pg.VECTOR = Vector  # type: ignore[attr-defined]

# Import each module's models so they register on Base.metadata.
from qzdap.modules.identity.adapter.persistence import models as identity_models
from qzdap.modules.agent_runtime.adapter.persistence import (
    models as agent_runtime_models,
)
from qzdap.modules.agent_runtime.adapter.persistence import catalog_models as agent_catalog_models
from qzdap.modules.tool.adapter.persistence import models as tool_models
from qzdap.modules.skill.adapter.persistence import models as skill_models
from qzdap.modules.knowledge.adapter.persistence import models as knowledge_models
from qzdap.modules.memory.adapter.persistence import models as memory_models
from qzdap.modules.orchestration.adapter.persistence import (
    models as orchestration_models,
)
from qzdap.modules.model.adapter.persistence import models as model_models
from qzdap.modules.agent_factory.adapter.persistence import (
    models as agent_factory_models,
)
from qzdap.modules.evaluation.adapter.persistence import (
    models as evaluation_models,
)
from qzdap.modules.observability_module.adapter.persistence import (
    models as observability_models,
)
from qzdap.modules.platform.adapter.persistence import (
    models as platform_models,
)

_ = observability_models  # registered on Base.metadata
_ = platform_models  # registered on Base.metadata
_ = memory_models  # registered on Base.metadata
_ = model_models  # registered on Base.metadata
_ = agent_runtime_models
_ = agent_catalog_models

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# URL from env wins over the placeholder in alembic.ini.
#
# alembic runs OUTSIDE the main application process (a separate pod in
# staging / prod), so it reads the raw ``QZDAP_DATABASE_URL`` env var
# rather than going through the ``QZDAP_*_REF`` indirection. In
# production this must be injected by an init container or the
# secrets manager via the pod spec — never baked into alembic.ini.
# We deliberately do not raise on a missing value here because the
# local alembic.ini default (``postgresql+asyncpg://postgres:...
# @localhost:5432/qzdap_dev``) is sufficient for sandbox / dev shells.
database_url = os.environ.get("QZDAP_DATABASE_URL") or config.get_main_option(
    "sqlalchemy.url"
)
if not database_url:
    raise RuntimeError(
        "QZDAP_DATABASE_URL is required for alembic. In prod this is "
        "injected by the secrets manager / CSI driver; locally set "
        "QZDAP_DATABASE_URL or configure sqlalchemy.url in alembic.ini."
    )
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live connection."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations with an async engine."""
    cfg_section = config.get_section(config.config_ini_section, {})
    cfg_section["sqlalchemy.url"] = database_url
    connectable = async_engine_from_config(
        cfg_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
