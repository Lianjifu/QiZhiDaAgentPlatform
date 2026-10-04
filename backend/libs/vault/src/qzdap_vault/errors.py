"""Errors raised by vault resolvers."""

from __future__ import annotations

from qzdap_kernel.errors import AppError, NotFoundError


class VaultError(AppError):
    """Base for all vault resolution failures."""


class SecretNotFound(VaultError, NotFoundError):
    """The ``ref`` does not match any known secret in the configured backend."""

    code = "SECRET_NOT_FOUND"


class SecretAccessDenied(VaultError):
    """The actor is not allowed to read the referenced secret."""

    code = "SECRET_ACCESS_DENIED"
    status = 403


class InvalidSecretRef(VaultError):
    """The ``ref`` string is malformed (missing scheme, bad characters, …)."""

    code = "INVALID_SECRET_REF"
    status = 422


__all__ = ["InvalidSecretRef", "SecretAccessDenied", "SecretNotFound", "VaultError"]
