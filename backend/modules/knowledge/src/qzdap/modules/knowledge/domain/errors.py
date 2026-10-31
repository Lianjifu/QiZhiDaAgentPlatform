"""Knowledge catalog errors aligned with the admin knowledge UI."""

from __future__ import annotations

from qzdap_kernel.error_codes import ErrorCode
from qzdap_kernel.errors import AppError, NotFoundError, ValidationError


class KnowledgeError(AppError):
    """Base for knowledge catalog errors."""


class KnowledgeNotFound(KnowledgeError, NotFoundError):
    code = ErrorCode.KNOWLEDGE_NOT_FOUND.value


class KnowledgeValidationError(KnowledgeError, ValidationError):
    """**入参不合法** ✓（例如未知的发布态 ✓）。"""

    code = ErrorCode.KNOWLEDGE_INVALID.value


__all__ = ["KnowledgeError", "KnowledgeNotFound", "KnowledgeValidationError"]
