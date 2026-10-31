"""Tests for the stable wire-level ErrorCode enum (Stage 1 §2.5 阻塞 5)."""

from __future__ import annotations

import pytest

from qzdap_kernel.error_codes import (
    ERROR_PROJECTION,
    ErrorCode,
    project_error,
    try_project_error,
)
from qzdap_kernel.error_codes import ErrorCode as DirectErrorCode
from qzdap_kernel.errors import AppError

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
    # Router Stage 0（决策 #7）—— 排队语义：满 / 超时，**都不得静默丢弃**。
    (ErrorCode.QUEUE_FULL, 429, True),
    (ErrorCode.QUEUE_TIMEOUT, 503, True),
    # Gateway Stage 0 · G-02b —— 收敛自各模块的自由字符串（方案 §9.0）
    (ErrorCode.CHANNEL_NOT_FOUND, 404, False),
    (ErrorCode.CHANNEL_DISABLED, 409, False),
    (ErrorCode.INBOUND_ADAPTER_MISSING, 500, False),
    (ErrorCode.OUTBOUND_ADAPTER_MISSING, 500, False),
    (ErrorCode.WEBHOOK_SIGNATURE_INVALID, 401, False),
    (ErrorCode.WEBHOOK_TIMESTAMP_SKEW, 401, False),
    (ErrorCode.DUPLICATE_REQUEST, 409, False),
    (ErrorCode.TENANT_DENIED, 403, False),
    (ErrorCode.CHANNEL_SERVICE_ACCOUNT_MISSING, 503, False),
    (ErrorCode.CHANNEL_DELIVERY_FAILED, 502, False),
    (ErrorCode.IDENTITY_REJECTED, 401, False),
    (ErrorCode.IDENTITY_CREDENTIALS_MISSING, 401, False),
    (ErrorCode.TOKEN_INVALID, 401, False),
    (ErrorCode.TOKEN_EXPIRED, 401, False),
    (ErrorCode.SERVICE_ACCOUNT_NOT_CONFIGURED, 503, False),
]


@pytest.mark.parametrize("code,expected_status,expected_retriable", NEW_CODES)
def test_new_codes_field_stability(
    code: ErrorCode, expected_status: int, expected_retriable: bool
) -> None:
    """26 个新错误码字段稳定（http_status / retriable / i18n_key）。"""
    assert code.http_status == expected_status
    assert code.retriable is expected_retriable
    assert code.i18n_key == f"errors.{code.value.lower()}"


def test_new_codes_are_distinct() -> None:
    """9 个新错误码之间互不重复。"""
    new_values = {
        c.value
        for c in (
            ErrorCode.SESSION_BUSY,
            ErrorCode.AGENT_NOT_AVAILABLE,
            ErrorCode.CONTEXT_TOO_LARGE,
            ErrorCode.REVISION_CONFLICT,
            ErrorCode.APPROVAL_EXPIRED,
            ErrorCode.APPROVAL_NOT_MATCH,
            ErrorCode.TOOL_ARGUMENT_INVALID,
            ErrorCode.TOOL_TIMEOUT,
            ErrorCode.TOOL_RATE_LIMITED,
        )
    }
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


def test_error_code_lives_in_kernel_not_schema() -> None:
    """错误码住 **kernel** ✓ —— 与错误层级在一起 ✓（2026-10-31 搬的 ✓）。

    ⚠️ `qzdap_schema` **不再持有错误码** ✓ —— 它只留线上的 DTO ✓
    （否则 base 层就得反过来依赖上层 ✗）。
    """
    assert ErrorCode is DirectErrorCode
    from qzdap_kernel.error_codes import ErrorCode as PackageErrorCode

    assert PackageErrorCode is ErrorCode

    import importlib.util

    assert importlib.util.find_spec("qzdap_schema.dtos.errors") is None


# ---------------------------------------------------------------------------
# 投影表（Gateway Stage 0 · G-02）
# ---------------------------------------------------------------------------


def test_every_error_code_resolves_through_the_projection() -> None:
    """**任何**码都要能查到一句话 —— 查不到就给兜底，不能把裸码甩给用户。"""
    for code in ErrorCode:
        for surface in ("http", "im", "web"):
            assert project_error(code, surface), f"{code} 的 {surface} 文案为空"


def test_the_projection_is_keyed_by_enum_members_only() -> None:
    """投影表的键**只能是** `ErrorCode` 成员 —— 两套码必然有一套漏。"""
    for key in ERROR_PROJECTION:
        assert isinstance(key, ErrorCode), f"投影表里有非枚举的键：{key!r}"


def test_project_error_accepts_a_plain_string_code() -> None:
    """按字符串查也要能用 —— 错误码在运行时就是字符串（`AppError.code`）。"""
    assert project_error("TENANT_DENIED", "http") == project_error(ErrorCode.TENANT_DENIED, "http")


def test_an_unknown_code_falls_back_instead_of_leaking_the_raw_code() -> None:
    """不认识的码 → 兜底文案，**不是**把裸码返回去。"""
    fallback = project_error("SOME_CODE_WE_NEVER_HEARD_OF", "http")
    assert fallback
    assert "SOME_CODE_WE_NEVER_HEARD_OF" not in fallback


def test_try_project_error_returns_none_for_an_unknown_code() -> None:
    """已有自己文案的调用方用这个 —— 投影表没登记时保留原文，不被兜底覆盖。"""
    assert try_project_error("SOME_CODE_WE_NEVER_HEARD_OF") is None
    assert try_project_error("TENANT_DENIED") is not None


def test_the_three_surfaces_can_say_different_things() -> None:
    """同一个码在三个投放面上**允许**文案不同 —— 那正是投影表的意义。"""
    copy = ERROR_PROJECTION[ErrorCode.TENANT_DENIED]
    assert copy.http != copy.im or copy.im != copy.web


def test_the_im_and_web_copy_fall_back_to_http_when_not_written() -> None:
    """少写一份文案不该让用户看到裸码。"""
    from qzdap_kernel.error_codes import ErrorCopy

    only_http = ErrorCopy(http="只有 http")
    assert only_http.for_surface("im") == "只有 http"
    assert only_http.for_surface("web") == "只有 http"
