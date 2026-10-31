"""agent_runtime: agent_turns.started_at — no-op reconciliation.

The original intent of this migration was to add `started_at` to
`agent_turns`, but 0002_agent_runtime already ships the column (the
"Turn" semantic split from `created_at` was put in place from day 1
during the agent_runtime P1 cutover). Re-running the ADD COLUMN here
fails with ``DuplicateColumnError`` on a fresh database.

This revision is kept in the chain so environments that previously
applied it remain at the same head, but the upgrade is now a no-op:
``started_at`` is guaranteed by 0002. Downgrade is also a no-op for the
same reason.

Revision ID: 0003_agent_turn_started_at
Revises: 0002_agent_runtime
Create Date: 2026-09-21
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Union

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "0003_agent_turn_started_at"
down_revision: str | None = "0002_agent_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No-op: 0002_agent_runtime already creates agent_turns.started_at.
    pass


def downgrade() -> None:
    # No-op: dropping the column would also need to undo 0002.
    pass
