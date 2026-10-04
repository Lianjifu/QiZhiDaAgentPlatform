"""Persistence: SQLAlchemy 2.0 async + tenant guard + UnitOfWork."""

from qzdap_persistence.base import Base, TenantScopedMixin
from qzdap_persistence.pgvector import register_pgvector
from qzdap_persistence.session_factory import (
    SessionFactory,
    create_engine,
    create_session_factory,
)
from qzdap_persistence.tenant_guard import (
    assert_tenant_scope,
    bind_tenant_to_session,
    current_tenant_id,
    tenant_id_var,
)
from qzdap_persistence.uow import UnitOfWork, unit_of_work

__all__ = [
    "Base",
    "SessionFactory",
    "TenantScopedMixin",
    "UnitOfWork",
    "assert_tenant_scope",
    "bind_tenant_to_session",
    "create_engine",
    "create_session_factory",
    "current_tenant_id",
    "register_pgvector",
    "tenant_id_var",
    "unit_of_work",
]
