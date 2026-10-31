"""Admin memory catalog errors."""

from __future__ import annotations

from qzdap_kernel.error_codes import ErrorCode
from qzdap_kernel.errors import AppError, NotFoundError


class MemoryError(AppError):
    """Base for memory catalog errors."""


class MemoryNotFound(MemoryError, NotFoundError):
    code = ErrorCode.MEMORY_NOT_FOUND.value


__all__ = ["MemoryError", "MemoryNotFound"]
