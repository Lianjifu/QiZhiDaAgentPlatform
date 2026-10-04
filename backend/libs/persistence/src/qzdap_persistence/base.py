"""Declarative Base + TenantScopedMixin.

Every ORM model inherits from `Base`. Every tenant-owned row also inherits
from `TenantScopedMixin`, which guarantees a non-null `tenant_id` and a
composite index `(tenant_id, ...)` to keep cross-tenant queries fast.

`TenantScopedMixin` also subclasses `TenantScopedLoader` from
`tenant_guard.py` so the `do_orm_execute` listener can auto-filter every
query — a forgotten `.where(Model.tenant_id == ...)` cannot leak rows.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, MetaData
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column
from sqlalchemy.sql import func

from qzdap_persistence.tenant_guard import TenantScopedLoader

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Project-wide declarative base. All ORM models must subclass this."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TenantScopedMixin(TenantScopedLoader):
    """Mixin: row belongs to a tenant.

    - `tenant_id` is non-null, indexed as the leftmost column of every
      composite index.
    - Subclasses get a `__table_args__` block that puts `(tenant_id, ...)`
      first; modules MAY extend it.
    - Inherits `TenantScopedLoader` so the ORM auto-filter hook in
      `install_tenant_loader()` applies to every query against subclasses.
    """

    @declared_attr
    def tenant_id(self) -> Mapped[UUID]:
        return mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)

    @declared_attr
    def id(self) -> Mapped[UUID]:
        return mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)

    @declared_attr
    def created_at(self) -> Mapped[object]:
        return mapped_column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        )

    @declared_attr
    def updated_at(self) -> Mapped[object]:
        return mapped_column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        )


def make_composite_index(*columns: str) -> Index:
    """Build a tenant-prefixed composite index, e.g.

    make_composite_index("workspace_id", "status")
    → ix_<table>_tenant_id_workspace_id_status
    """
    cols = ["tenant_id", *columns]
    return Index(f"ix_{cols[0]}_{'_'.join(cols[1:])}", *cols)
