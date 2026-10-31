"""Knowledge catalog errors aligned with the admin knowledge UI."""

from __future__ import annotations

from qzdap_kernel.errors import AppError, NotFoundError, ValidationError


class KnowledgeError(AppError):
    """Base for knowledge catalog errors."""


class KnowledgeNotFound(KnowledgeError, NotFoundError):
    code = "KNOWLEDGE_NOT_FOUND"


class KnowledgeValidationError(KnowledgeError, ValidationError):
    """**入参不合法** ✓（例如未知的发布态 ✓）。"""

    code = "KNOWLEDGE_INVALID"


__all__ = ["KnowledgeError", "KnowledgeNotFound", "KnowledgeValidationError"]
