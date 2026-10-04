"""Admin memory catalog errors."""

from __future__ import annotations

from qzdap_kernel.errors import AppError, NotFoundError


class MemoryError(AppError):
    """Base for memory catalog errors."""


class MemoryNotFound(MemoryError, NotFoundError):
    code = "MEMORY_NOT_FOUND"


__all__ = ["MemoryError", "MemoryNotFound"]
