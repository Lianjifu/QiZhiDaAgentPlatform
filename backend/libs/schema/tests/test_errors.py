"""Tests for the stable wire-level ErrorCode enum (Stage 1 §2.5 阻塞 5)."""

from __future__ import annotations

import pytest

from qzdap_kernel.errors import AppError

from qzdap_schema.dtos import ErrorCode
from qzdap_schema.dtos.errors import ErrorCode as DirectErrorCode


# ---------------------------------------------------------------------------
# 既有错误码（与 kernel `AppError.code` 字面值一致）
# ---------------------------------------------------------------------------


def test_legacy_codes_match_kernel_apperror_literals() -> None:
    assert ErrorCode.VALIDATION_ERROR.value == "VALIDATION_ERROR"
    assert ErrorCode.CONFLICT.value == "CONFLICT"
    assert ErrorCode.RATE_LIMITED.value == "RATE_LIMITED"
    assert ErrorCode.EXTERNAL_SERVICE_ERROR.value == "EXTERNAL_SERVICE_ERROR"


def test_legacy_codes_has_stable_http_status() -> None:
    assert ErrorCode.VALIDATION_ERROR.http_status == 400
    assert ErrorCode.AUTHENTICATION_FAILED.http_status == 401
    assert ErrorCode.FORBIDDEN.http_status == 403
    assert ErrorCode.APPROVAL_REQUIRED.http_status == 202
    assert ErrorCode.NOT_FOUND.http_status == 404
    assert ErrorCode.CONFLICT.http_status == 409
    assert ErrorCode.RATE_LIMITED.http_status == 429
    assert ErrorCode.INTERNAL_ERROR.http_status == 500


# ---------------------------------------------------------------------------
# 新增错误码（Stage 1 §2.5 阻塞 5）
# ---------------------------------------------------------------------------


NEW_CODES = [
    (ErrorCode.SESSION_BUSY, 409, True),
    (ErrorCode.AGENT_NOT_AVAILABLE, 502, False),
    (ErrorCode.CONTEXT_TOO_LARGE, 413, False),
    (ErrorCode.REVISION_CONFLICT, 409, True),
    (ErrorCode.APPROVAL_EXPIRED, 410, False),
    (ErrorCode.APPROVAL_NOT_MATCH, 409, False),
    (ErrorCode.TOOL_ARGUMENT_INVALID, 400, False),
    (ErrorCode.TOOL_TIMEOUT, 504, True),
    (ErrorCode.TOOL_RATE_LIMITED, 429, True),
]


@pytest.mark.parametrize("code,expected_status,expected_retriable", NEW_CODES)
def test_new_codes_field_stability(
    code: ErrorCode, expected_status: int, expected_retriable: bool
) -> None:
    """9 个新错误码字段稳定（http_status / retriable / i18n_key）。"""
    assert code.http_status == expected_status
    assert code.retriable is expected_retriable
    assert code.i18n_key == f"errors.{code.value.lower()}"


def test_new_codes_are_distinct() -> None:
    """9 个新错误码之间互不重复。"""
    new_values = {c.value for c in (
        ErrorCode.SESSION_BUSY,
        ErrorCode.AGENT_NOT_AVAILABLE,
        ErrorCode.CONTEXT_TOO_LARGE,
        ErrorCode.REVISION_CONFLICT,
        ErrorCode.APPROVAL_EXPIRED,
        ErrorCode.APPROVAL_NOT_MATCH,
        ErrorCode.TOOL_ARGUMENT_INVALID,
        ErrorCode.TOOL_TIMEOUT,
        ErrorCode.TOOL_RATE_LIMITED,
    )}
    assert len(new_values) == 9


# ---------------------------------------------------------------------------
# 与 kernel AppError 的兼容性
# ---------------------------------------------------------------------------


def test_errorcode_is_str_subclass() -> None:
    """ErrorCode 必须为 str 子类，以便直接赋给 AppError.code。"""
    assert isinstance(ErrorCode.SESSION_BUSY, str)
    assert ErrorCode.SESSION_BUSY == "SESSION_BUSY"


def test_apperror_accepts_errorcode_value() -> None:
    """`AppError(code=ErrorCode.X.value)` 必须可正常构造。"""
    err = AppError(
        "session busy",
        code=ErrorCode.SESSION_BUSY.value,
        status=ErrorCode.SESSION_BUSY.http_status,
    )
    assert err.code == "SESSION_BUSY"
    assert err.status == 409


def test_apperror_direct_code_string_assignment() -> None:
    """直接传字符串字面值也必须工作（兼容旧调用点）。"""
    err = AppError("conflict", code="REVISION_CONFLICT")
    assert err.code == "REVISION_CONFLICT"
    assert err.status == 500  # AppError 默认 status


# ---------------------------------------------------------------------------
# 序列化往返
# ---------------------------------------------------------------------------


def test_errorcode_serialization_roundtrip() -> None:
    """枚举值在 str / repr / JSON 序列化下都稳定。"""
    code = ErrorCode.SESSION_BUSY
    assert str(code) == "ErrorCode.SESSION_BUSY"
    assert f"{code}" == "ErrorCode.SESSION_BUSY"
    assert code.value == "SESSION_BUSY"
    # JSON 序列化保持字符串
    import json
    assert json.loads(json.dumps(code.value)) == "SESSION_BUSY"


def test_errorcode_lookup_by_value() -> None:
    """通过字符串值能找回对应枚举。"""
    assert ErrorCode("SESSION_BUSY") is ErrorCode.SESSION_BUSY
    assert ErrorCode("REVISION_CONFLICT") is ErrorCode.REVISION_CONFLICT


def test_errorcode_unknown_value_raises() -> None:
    """未登记的错误码字符串必须抛 ValueError，不允许静默接受。"""
    with pytest.raises(ValueError):
        ErrorCode("UNREGISTERED_CODE_XYZ")


# ---------------------------------------------------------------------------
# 导入面（验证 `__init__.py` 已正确 re-export）
# ---------------------------------------------------------------------------


def test_dtos_package_exports_errorcode() -> None:
    """ErrorCode 必须从 `qzdap_schema.dtos` 直接可导入。"""
    assert ErrorCode is DirectErrorCode
    from qzdap_schema.dtos import ErrorCode as PackageErrorCode  # noqa: F401
    assert PackageErrorCode is ErrorCode