"""Tenant guard.

The session-level tenant id is set at request entry (by Auth middleware) and
checked by every query via SQLAlchemy `before_compile` event hooks. This is
the single point that enforces "no cross-tenant query, ever".

ORM classes opt into auto-filtering by subclassing `TenantScopedLoader`
(typically via the `TenantScopedMixin` defined in `qzdap_persistence.base`).
"""

from __future__ import annotations

from contextvars import ContextVar
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.orm import with_loader_criteria

tenant_id_var: ContextVar[UUID | None] = ContextVar("qzdap_tenant_id", default=None)


def current_tenant_id() -> UUID | None:
    return tenant_id_var.get()


def bind_tenant_to_session(tenant_id: UUID | None) -> object:
    return tenant_id_var.set(tenant_id)


def reset_tenant_to_session(token: object) -> None:
    tenant_id_var.reset(token)  # type: ignore[arg-type]


def assert_tenant_scope(tenant_id: UUID) -> None:
    bound = current_tenant_id()
    if bound is not None and bound != tenant_id:
        from qzdap_kernel.errors import ForbiddenError

        raise ForbiddenError(
            "cross-tenant access attempted",
            code="TENANT_DENIED",
        )


class TenantScopedLoader:
    """Pure marker — ORM classes opt in by subclassing this.

    `with_loader_criteria` uses this marker to filter every query that
    touches a subclass; the filter compares the row's `tenant_id` column
    against the value bound via `bind_tenant_to_session`.

    Intentionally has no class attributes: subclasses supply their own
    `tenant_id` mapped column (via `TenantScopedMixin`), and a class-level
    `tenant_id: UUID | None = None` here would collide with SQLAlchemy's
    mapper and silently shadow the real column.
    """


class WorkspaceScopedLoader(TenantScopedLoader):
    """Marker for tables that also have a workspace_id column.

    Reserved for Week 2+ when agent_runtime / memory modules land.
    """


def install_tenant_loader() -> None:
    """Wire a `do_orm_execute` listener so every ORM query that loads a
    `TenantScopedLoader` subclass is auto-filtered by `current_tenant_id()`.

    SQLAlchemy applies the criteria *at the database level* (not in Python),
    so a forgotten `.where(Model.tenant_id == ...)` cannot silently leak rows.

    Idempotent: safe to call multiple times.
    """
    from sqlalchemy.orm import Session

    from qzdap_persistence.base import TenantScopedMixin

    if getattr(install_tenant_loader, "_installed", False):
        return

    @event.listens_for(Session, "do_orm_execute")
    def _add_tenant_criteria(state: object) -> None:  # type: ignore[no-redef]
        bound = tenant_id_var.get()
        if not bound:
            return
        # Target `TenantScopedMixin` (which exposes the `tenant_id` mapped
        # column) instead of the bare `TenantScopedLoader` marker so the
        # criteria lambda is only invoked for ORM classes that actually
        # carry a `tenant_id` column. Otherwise `with_loader_criteria`
        # walks the MRO of `TenantScopedLoader` and may invoke the lambda
        # with the marker itself (or `WorkspaceScopedLoader`), which has
        # no `tenant_id` and raises `AttributeError`.
        state.statement = state.statement.options(  # type: ignore[attr-defined]
            with_loader_criteria(
                TenantScopedMixin,
                lambda cls: cls.tenant_id == bound,
                include_aliases=True,
            )
        )

    install_tenant_loader._installed = True  # type: ignore[attr-defined]


def iterate_tree(obj: object) -> object:
    """Placeholder for a real AST walker — kept here for future expansion."""
    from sqlalchemy.sql.visitors import iterate

    return iterate(obj)  # type: ignore[arg-type]
