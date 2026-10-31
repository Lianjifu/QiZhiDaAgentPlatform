"""Skill errors aligned with the admin skills UI."""

from __future__ import annotations

from qzdap_kernel.error_codes import ErrorCode
from qzdap_kernel.errors import AppError, NotFoundError


class SkillError(AppError):
    """Base for skill catalog errors."""


class SkillNotFound(SkillError, NotFoundError):
    code = ErrorCode.SKILL_NOT_FOUND.value


class SkillDisabled(SkillError):
    code = ErrorCode.SKILL_DISABLED.value
    status = 409


class SkillNeedsConfirm(SkillError):
    code = ErrorCode.SKILL_NEEDS_CONFIRM.value
    status = 409


class SkillNotExecutable(SkillError):
    code = ErrorCode.SKILL_NOT_EXECUTABLE.value
    status = 409


class SkillSandboxUnavailable(SkillError):
    code = ErrorCode.SANDBOX_UNAVAILABLE.value
    status = 503


__all__ = [
    "SkillDisabled",
    "SkillError",
    "SkillNeedsConfirm",
    "SkillNotExecutable",
    "SkillNotFound",
    "SkillSandboxUnavailable",
]
