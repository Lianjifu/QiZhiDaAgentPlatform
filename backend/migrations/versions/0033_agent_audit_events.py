"""Persist agent audit events and immutable release snapshots."""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0033_agent_audit_events"
down_revision: str | Sequence[str] | None = "0030_agent_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "admin_agents",
        sa.Column(
            "audit_events",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("admin_agents", "audit_events")
