"""Knowledge catalog errors aligned with the admin knowledge UI."""

from __future__ import annotations

from qzdap_kernel.errors import AppError, NotFoundError


class KnowledgeError(AppError):
    """Base for knowledge catalog errors."""


class KnowledgeNotFound(KnowledgeError, NotFoundError):
    code = "KNOWLEDGE_NOT_FOUND"


__all__ = ["KnowledgeError", "KnowledgeNotFound"]
