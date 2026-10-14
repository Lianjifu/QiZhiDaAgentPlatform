"""Durable attachment bytes and provenance, isolated to a session owner."""

from uuid import UUID

from qzdap_persistence.base import Base, TenantScopedMixin
from sqlalchemy import Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column


class CopilotAttachmentORM(TenantScopedMixin, Base):
    __tablename__ = "copilot_attachments"
    workspace_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    session_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    owner_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
