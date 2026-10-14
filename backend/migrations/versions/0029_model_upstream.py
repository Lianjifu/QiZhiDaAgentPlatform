"""Separate display names from upstream model IDs and persist provider API versions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_model_upstream"
down_revision: str | Sequence[str] | None = "0028_admin_ops"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_models",
        sa.Column("upstream_model", sa.String(256), nullable=False, server_default=""),
    )
    op.execute("UPDATE admin_models SET upstream_model = name")
    op.add_column(
        "admin_model_providers",
        sa.Column("api_version", sa.String(64), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("admin_model_providers", "api_version")
    op.drop_column("admin_models", "upstream_model")
