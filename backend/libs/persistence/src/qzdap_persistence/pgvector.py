"""Register pgvector column type with SQLAlchemy at import time.

Importing this module is enough — call once from composition root or tests.
"""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

_REGISTERED = False


def register_pgvector() -> None:
    """Register pgvector types. Idempotent."""
    global _REGISTERED
    if _REGISTERED:
        return
    try:
        from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pgvector not installed; pip install pgvector") from e

    postgresql.base.ischema_names["vector"] = Vector
    _REGISTERED = True
