"""Add runtime JSONB to admin_skills for gVisor sandbox execution.

Revision ID: 0026_skill_runtime
Revises: 0025_admin_models
Create Date: 2026-10-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_skill_runtime"
down_revision: str | Sequence[str] | None = "0025_admin_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_skills",
        sa.Column(
            "runtime",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("admin_skills", "runtime")
