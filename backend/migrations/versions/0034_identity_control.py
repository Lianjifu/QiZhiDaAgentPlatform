"""Identity control plane: pending invites, change audit and Copilot files."""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034_identity_control"
down_revision = "0033_agent_audit_events"
branch_labels = None
depends_on = None


def upgrade():
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "workspace_invitations",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, nullable=False, index=True),
        sa.Column("workspace_id", uuid, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("team", sa.String(120), nullable=False, server_default=""),
        sa.Column("invited_by", uuid, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_workspace_invitation_scope",
        "workspace_invitations",
        ["tenant_id", "workspace_id", "email", "status"],
    )
    op.create_table(
        "identity_control_audit",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, nullable=False, index=True),
        sa.Column("workspace_id", uuid, nullable=True),
        sa.Column("actor_id", uuid, nullable=False),
        sa.Column("actor_name", sa.String(120), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_identity_control_audit_tenant_created",
        "identity_control_audit",
        ["tenant_id", "created_at"],
    )
    op.create_table(
        "copilot_attachments",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, nullable=False, index=True),
        sa.Column("workspace_id", uuid, nullable=False),
        sa.Column("session_id", uuid, nullable=False),
        sa.Column("owner_id", uuid, nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("content", sa.LargeBinary, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_copilot_attachments_session",
        "copilot_attachments",
        ["tenant_id", "workspace_id", "session_id", "created_at"],
    )


def downgrade():
    op.drop_table("copilot_attachments")
    op.drop_table("identity_control_audit")
    op.drop_index("ix_workspace_invitation_scope", table_name="workspace_invitations")
    op.drop_table("workspace_invitations")
