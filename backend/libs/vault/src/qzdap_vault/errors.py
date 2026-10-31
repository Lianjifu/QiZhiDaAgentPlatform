"""Errors raised by vault resolvers."""

from __future__ import annotations

from qzdap_kernel.error_codes import ErrorCode
from qzdap_kernel.errors import AppError, NotFoundError


class VaultError(AppError):
    """Base for all vault resolution failures."""


class SecretNotFound(VaultError, NotFoundError):
    """The ``ref`` does not match any known secret in the configured backend."""

    code = ErrorCode.SECRET_NOT_FOUND.value


class SecretAccessDenied(VaultError):
    """The actor is not allowed to read the referenced secret."""

    code = ErrorCode.SECRET_ACCESS_DENIED.value
    status = 403


class InvalidSecretRef(VaultError):
    """The ``ref`` string is malformed (missing scheme, bad characters, …)."""

    code = ErrorCode.INVALID_SECRET_REF.value
    status = 422


__all__ = ["InvalidSecretRef", "SecretAccessDenied", "SecretNotFound", "VaultError"]
