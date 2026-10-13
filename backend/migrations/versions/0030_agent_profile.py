"""Add agent profile (ToolConfig / MCPConfig) JSONB column."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030_agent_profile"
down_revision: str | Sequence[str] | None = "0029_model_upstream"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_agents",
        sa.Column("profile", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("admin_agents", "profile")
