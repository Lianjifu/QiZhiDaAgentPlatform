from __future__ import annotations

from uuid import UUID

from qzdap_persistence.base import Base, TenantScopedMixin
from sqlalchemy import Boolean, Float, Index, Integer, LargeBinary, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column


class ProviderORM(TenantScopedMixin, Base):
    __tablename__ = "admin_model_providers"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    region: Mapped[str] = mapped_column(String(64), nullable=False, default="custom", server_default=text("'custom'"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="healthy", server_default=text("'healthy'"))
    base_url: Mapped[str] = mapped_column(String(512), nullable=False, default="", server_default=text("''"))
    api_key_masked: Mapped[str] = mapped_column(String(64), nullable=False, default="••••", server_default=text("'••••'"))
    protocol: Mapped[str] = mapped_column(
        String(32), nullable=False, default="openai", server_default=text("'openai'")
    )
    encrypted_payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, default=b"")
    error_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default=text("0"))
    avg_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    qps: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))

    __table_args__ = (Index("ix_admin_model_providers_tenant_ws", "tenant_id", "workspace_id"),)


class CatalogModelORM(TenantScopedMixin, Base):
    __tablename__ = "admin_models"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    provider_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    provider_name: Mapped[str] = mapped_column(String(256), nullable=False, default="", server_default=text("''"))
    task: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    context_window: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    price_in: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default=text("0"))
    price_out: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default=text("0"))
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    success_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default=text("'draft'"))
    tier: Mapped[str] = mapped_column(String(16), nullable=False, default="balanced", server_default=text("'balanced'"))
    starred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    trend: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))

    __table_args__ = (Index("ix_admin_models_tenant_ws_status", "tenant_id", "workspace_id", "status"),)


class RouteORM(TenantScopedMixin, Base):
    __tablename__ = "admin_model_routes"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    task: Mapped[str] = mapped_column(String(32), nullable=False, default="generation", server_default=text("'generation'"))
    strategy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="quality-first", server_default=text("'quality-first'")
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    primary_model_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    fallback_model_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))

    __table_args__ = (Index("ix_admin_model_routes_tenant_ws", "tenant_id", "workspace_id"),)


class HealthEventORM(TenantScopedMixin, Base):
    __tablename__ = "admin_model_health"

    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    provider_name: Mapped[str] = mapped_column(String(256), nullable=False, default="", server_default=text("''"))
    message: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    occurred_at: Mapped[str] = mapped_column(String(32), nullable=False, default="", server_default=text("''"))

    __table_args__ = (Index("ix_admin_model_health_tenant_ws", "tenant_id", "workspace_id"),)
