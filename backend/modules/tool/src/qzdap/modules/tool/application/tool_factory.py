"""Per-call `ToolService` factory protocol.

Lives in its own module so `services.py` and
`use_cases/batch_invoke_tools.py` can both depend on it without
creating a `services ↔ use_cases` circular import.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol


class ToolServiceFactory(Protocol):
    """Opens a fresh `ToolService` bound to a fresh DB session.

    The composition root supplies a closure over
    `container.session_factory()` + `_ToolFactory.for_session`. Test
    code supplies an equivalent over in-memory ports. The router
    passes the factory to `ToolService.batch_invoke_tools(factory)`
    so each batch item runs on its own session — SQLAlchemy's async
    session forbids concurrent operations on a shared session.
    """

    def __call__(self) -> AsyncIterator[ToolService]: ...  # type: ignore[name-defined]  # noqa: F821


__all__ = ["ToolServiceFactory"]
