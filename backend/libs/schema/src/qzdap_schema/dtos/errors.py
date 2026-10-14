"""Stable wire-level error codes shared across the platform.

`ErrorCode` is the canonical machine code used in HTTP responses,
LangGraph node failures, outbox events and trace metadata. It is a
`str`-valued `Enum` so existing `qzdap_kernel.errors.AppError.code`
string fields accept the enum value without conversion.

新增错误码（Stage 1 起使用）必须登记到本枚举；运行时不允许抛出
未在本枚举中登记的字符串错误码。

历史：
- v3.1：基于 §2.5 阻塞 5 决议新增 9 个会话模块错误码，与 kernel
  `AppError` 子类的 `code` 字符串共享同一字面值。
"""

from __future__ import annotations

from enum import Enum


# 既有错误码（与 kernel `AppError.code` 字面值一致）
class ErrorCode(str, Enum):
    """Stable wire-level error code for every user-visible failure."""

    # 既有错误码（kernel 同步）
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    FORBIDDEN = "FORBIDDEN"
    ACTION_DENIED = "ACTION_DENIED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    BUSINESS_RULE_VIOLATED = "BUSINESS_RULE_VIOLATED"
    RATE_LIMITED = "RATE_LIMITED"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"

    # 新增错误码（Stage 1 起使用；见 §2.5 阻塞 5）
    SESSION_BUSY = "SESSION_BUSY"
    AGENT_NOT_AVAILABLE = "AGENT_NOT_AVAILABLE"
    CONTEXT_TOO_LARGE = "CONTEXT_TOO_LARGE"
    REVISION_CONFLICT = "REVISION_CONFLICT"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_NOT_MATCH = "APPROVAL_NOT_MATCH"
    TOOL_ARGUMENT_INVALID = "TOOL_ARGUMENT_INVALID"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    TOOL_RATE_LIMITED = "TOOL_RATE_LIMITED"


# ---------------------------------------------------------------------------
# 元数据表
# ---------------------------------------------------------------------------

_HTTP_STATUS: dict[ErrorCode, int] = {
    # 既有
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.AUTHENTICATION_FAILED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.ACTION_DENIED: 403,
    ErrorCode.APPROVAL_REQUIRED: 202,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.BUSINESS_RULE_VIOLATED: 422,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.EXTERNAL_SERVICE_ERROR: 502,
    ErrorCode.INTERNAL_ERROR: 500,
    # 新增（Stage 1）
    ErrorCode.SESSION_BUSY: 409,
    ErrorCode.AGENT_NOT_AVAILABLE: 502,
    ErrorCode.CONTEXT_TOO_LARGE: 413,
    ErrorCode.REVISION_CONFLICT: 409,
    ErrorCode.APPROVAL_EXPIRED: 410,
    ErrorCode.APPROVAL_NOT_MATCH: 409,
    ErrorCode.TOOL_ARGUMENT_INVALID: 400,
    ErrorCode.TOOL_TIMEOUT: 504,
    ErrorCode.TOOL_RATE_LIMITED: 429,
}


_RETRIABLE: frozenset[ErrorCode] = frozenset(
    {
        ErrorCode.SESSION_BUSY,
        ErrorCode.REVISION_CONFLICT,
        ErrorCode.TOOL_TIMEOUT,
        ErrorCode.TOOL_RATE_LIMITED,
        ErrorCode.RATE_LIMITED,
        ErrorCode.EXTERNAL_SERVICE_ERROR,
    }
)


_I18N_PREFIX = "errors."


# ---------------------------------------------------------------------------
# 扩展属性（用 property 而非方法以与现有 `ChunkEnvelope.kind` 风格一致）
# ---------------------------------------------------------------------------


def _http_status(code: ErrorCode) -> int:
    return _HTTP_STATUS[code]


def _retriable(code: ErrorCode) -> bool:
    return code in _RETRIABLE


def _i18n_key(code: ErrorCode) -> str:
    return f"{_I18N_PREFIX}{code.value.lower()}"


# 把方法挂到枚举类上，避免每个实例重复包装
ErrorCode.http_status = property(_http_status)  # type: ignore[attr-defined]
ErrorCode.retriable = property(_retriable)  # type: ignore[attr-defined]
ErrorCode.i18n_key = property(_i18n_key)  # type: ignore[attr-defined]


__all__ = ["ErrorCode"]