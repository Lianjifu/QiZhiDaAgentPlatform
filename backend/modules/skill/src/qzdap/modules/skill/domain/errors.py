"""Skill errors aligned with the admin skills UI."""

from __future__ import annotations

from qzdap_kernel.errors import AppError, NotFoundError


class SkillError(AppError):
    """Base for skill catalog errors."""


class SkillNotFound(SkillError, NotFoundError):
    code = "SKILL_NOT_FOUND"


class SkillDisabled(SkillError):
    code = "SKILL_DISABLED"
    status = 409


class SkillNeedsConfirm(SkillError):
    code = "SKILL_NEEDS_CONFIRM"
    status = 409


class SkillNotExecutable(SkillError):
    code = "SKILL_NOT_EXECUTABLE"
    status = 409


class SkillSandboxUnavailable(SkillError):
    code = "SANDBOX_UNAVAILABLE"
    status = 503


__all__ = [
    "SkillDisabled",
    "SkillError",
    "SkillNeedsConfirm",
    "SkillNotExecutable",
    "SkillNotFound",
    "SkillSandboxUnavailable",
]
