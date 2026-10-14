"""Pending invitations and durable console change evidence."""

from uuid import UUID

from qzdap_persistence.base import Base, TenantScopedMixin
from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column


class WorkspaceInvitationORM(TenantScopedMixin, Base):
    __tablename__ = "workspace_invitations"
    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    team: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    invited_by: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    __table_args__ = (
        Index(
            "ix_workspace_invitation_scope",
            "tenant_id",
            "workspace_id",
            "email",
            "status",
        ),
    )


class IdentityControlAuditORM(TenantScopedMixin, Base):
    __tablename__ = "identity_control_audit"
    workspace_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    actor_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
