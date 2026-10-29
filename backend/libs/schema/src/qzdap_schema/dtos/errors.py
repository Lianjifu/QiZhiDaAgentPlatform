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

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Literal


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
    # Router Stage 0（决策 #7）—— 排队语义：
    # 队列满 / 等待超时。⚠️ 两者都**不静默丢弃**：轮次落 cancelled 且可查。
    QUEUE_FULL = "QUEUE_FULL"
    QUEUE_TIMEOUT = "QUEUE_TIMEOUT"
    # Gateway Stage 0 · G-02b（方案 §9.0 的「收敛」）——
    # 这些码原先是**各模块 domain/errors.py 里的自由字符串**，
    # 现在提升为枚举成员：投影表（`ERROR_PROJECTION`）按码查文案，
    # 码散落在两套体系里必然有一套漏。
    #
    # ⚠️ 方案 §9.0 的表列了 7 个 —— **实施时又发现 6 个**（Gateway Stage 2/4a
    # 自己新增的：服务账号缺失 / 投递失败 / 出站适配器缺失 / 鉴权拒绝原因）。
    # 收敛只做一半等于没做 —— **按实况补齐**（方案 §9.0 的表已同步更新）。
    CHANNEL_NOT_FOUND = "CHANNEL_NOT_FOUND"
    CHANNEL_DISABLED = "CHANNEL_DISABLED"
    INBOUND_ADAPTER_MISSING = "INBOUND_ADAPTER_MISSING"
    OUTBOUND_ADAPTER_MISSING = "OUTBOUND_ADAPTER_MISSING"
    WEBHOOK_SIGNATURE_INVALID = "WEBHOOK_SIGNATURE_INVALID"
    WEBHOOK_TIMESTAMP_SKEW = "WEBHOOK_TIMESTAMP_SKEW"
    DUPLICATE_REQUEST = "DUPLICATE_REQUEST"
    TENANT_DENIED = "TENANT_DENIED"
    # Gateway Stage 2（服务账号物化）与 Stage 4a（出站 sink）新增的码
    CHANNEL_SERVICE_ACCOUNT_MISSING = "CHANNEL_SERVICE_ACCOUNT_MISSING"
    CHANNEL_DELIVERY_FAILED = "CHANNEL_DELIVERY_FAILED"
    IDENTITY_REJECTED = "IDENTITY_REJECTED"
    IDENTITY_CREDENTIALS_MISSING = "IDENTITY_CREDENTIALS_MISSING"
    TOKEN_INVALID = "TOKEN_INVALID"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    # Gateway ② 的**拒绝原因码**（审计事件里的 reason_code）—— 与 API 错误码
    # 是两套词汇，都登记进枚举（投影表要覆盖它们），但**不互相替代**。
    SERVICE_ACCOUNT_NOT_CONFIGURED = "SERVICE_ACCOUNT_NOT_CONFIGURED"
    # Session Stage 0 · S-04 —— 审批人不能是发起人（自审批拦截 ✓）。
    APPROVER_MUST_DIFFER = "APPROVER_MUST_DIFFER"


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
    # Router 排队语义
    ErrorCode.QUEUE_FULL: 429,
    ErrorCode.QUEUE_TIMEOUT: 503,
    # Gateway Stage 0 · G-02b —— 收敛自各模块的自由字符串（方案 §9.0 的表）
    ErrorCode.CHANNEL_NOT_FOUND: 404,
    ErrorCode.CHANNEL_DISABLED: 409,
    ErrorCode.INBOUND_ADAPTER_MISSING: 500,
    ErrorCode.OUTBOUND_ADAPTER_MISSING: 500,
    ErrorCode.WEBHOOK_SIGNATURE_INVALID: 401,
    ErrorCode.WEBHOOK_TIMESTAMP_SKEW: 401,
    ErrorCode.DUPLICATE_REQUEST: 409,
    ErrorCode.TENANT_DENIED: 403,
    ErrorCode.CHANNEL_SERVICE_ACCOUNT_MISSING: 503,
    ErrorCode.CHANNEL_DELIVERY_FAILED: 502,
    ErrorCode.IDENTITY_REJECTED: 401,
    ErrorCode.IDENTITY_CREDENTIALS_MISSING: 401,
    ErrorCode.TOKEN_INVALID: 401,
    ErrorCode.TOKEN_EXPIRED: 401,
    ErrorCode.SERVICE_ACCOUNT_NOT_CONFIGURED: 503,
    ErrorCode.APPROVER_MUST_DIFFER: 403,
}


_RETRIABLE: frozenset[ErrorCode] = frozenset(
    {
        ErrorCode.SESSION_BUSY,
        ErrorCode.REVISION_CONFLICT,
        ErrorCode.TOOL_TIMEOUT,
        ErrorCode.TOOL_RATE_LIMITED,
        ErrorCode.RATE_LIMITED,
        ErrorCode.EXTERNAL_SERVICE_ERROR,
        ErrorCode.QUEUE_FULL,
        ErrorCode.QUEUE_TIMEOUT,
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


# ---------------------------------------------------------------------------
# 投影表：ErrorCode → 三个投放面的文案（Gateway Stage 0 · G-02）
# ---------------------------------------------------------------------------

#: 投放面 —— 同一个错误在**不同地方**要说得不一样。
#:
#: - ``http``：HTTP 错误信封的 ``message``（给 API 调用方 / 脚本看）；
#: - ``im``：IM 渠道回给群里用户的那条消息；
#: - ``web``：web 对话页展示给用户的那条消息。
ErrorSurface = Literal["http", "im", "web"]


@dataclass(frozen=True, slots=True)
class ErrorCopy:
    """一个错误码在各投放面上的文案。

    ⚠️ ``im`` / ``web`` 留空时**回落到 ``http``** —— 少写一份文案不会
    让用户看到裸码。
    """

    http: str
    im: str = ""
    web: str = ""

    def for_surface(self, surface: ErrorSurface) -> str:
        if surface == "im":
            return self.im or self.http
        if surface == "web":
            return self.web or self.http
        return self.http


#: 兜底文案 —— 表里没有的码用它。
#:
#: **为什么要有兜底**：投影表按码查文案，码会一直增加（每层都在加码）。
#: 没有兜底就会退化成「把裸码甩给用户」—— 那不是文案，是甩锅。
_FALLBACK_COPY = ErrorCopy(
    http="请求处理失败",
    im="出错了，请稍后重试。",
    web="操作未完成，请稍后重试。",
)

#: **按码查文案**的投影表（Gateway 方案 §9.0 的 G-02）。
#:
#: 只登记 **Gateway 层会产生 / 关心**的码；其余码走兜底。
#: ⚠️ **键只能是 `ErrorCode` 成员** —— 码散落在两套体系（枚举 + 模块自由
#: 字符串）里，这张表就得维护两套码，而其中一套必然漏（G-02b 收敛的动因）。
ERROR_PROJECTION: Mapping[ErrorCode, ErrorCopy] = {
    ErrorCode.VALIDATION_ERROR: ErrorCopy(
        http="请求参数不合法",
        im="请求内容不合法，请检查后重试。",
        web="请求内容不合法，请检查后重试。",
    ),
    ErrorCode.AUTHENTICATION_FAILED: ErrorCopy(
        http="身份校验失败",
        im="身份校验失败，请重新登录。",
        web="登录状态已失效，请重新登录。",
    ),
    ErrorCode.FORBIDDEN: ErrorCopy(
        http="无权访问该资源",
        im="你没有权限执行这个操作。",
        web="你没有权限执行这个操作。",
    ),
    ErrorCode.RATE_LIMITED: ErrorCopy(
        http="请求过于频繁，请稍后重试",
        im="请求太频繁了，稍等一会儿再试。",
        web="请求太频繁了，稍等一会儿再试。",
    ),
    ErrorCode.INTERNAL_ERROR: ErrorCopy(
        http="服务内部错误",
        im="服务出错了，请稍后重试。",
        web="服务出错了，请稍后重试。",
    ),
    ErrorCode.CONTEXT_TOO_LARGE: ErrorCopy(
        http="上下文超出模型上限",
        im="这次的内容太长了，请分几次问。",
        web="这次的内容太长了，请分几次问。",
    ),
    ErrorCode.AGENT_NOT_AVAILABLE: ErrorCopy(
        http="没有可用的智能体",
        im="暂时没有可用的智能体，请稍后再试。",
        web="暂时没有可用的智能体，请稍后再试。",
    ),
    ErrorCode.SESSION_BUSY: ErrorCopy(
        http="该会话已有进行中的轮次",
        im="这个会话还在处理上一条消息，请稍等。",
        web="这个会话还在处理上一条消息，请稍等。",
    ),
    ErrorCode.CHANNEL_NOT_FOUND: ErrorCopy(
        http="渠道不存在",
        im="找不到对应的渠道，请检查配置。",
        web="找不到对应的渠道，请检查配置。",
    ),
    ErrorCode.CHANNEL_DISABLED: ErrorCopy(
        http="渠道已停用",
        im="该渠道已停用，暂时无法处理消息。",
        web="该渠道已停用，暂时无法处理消息。",
    ),
    ErrorCode.INBOUND_ADAPTER_MISSING: ErrorCopy(
        http="该渠道类型未注册入站解析器",
        im="这个渠道类型暂时无法接收消息。",
        web="这个渠道类型暂时无法接收消息。",
    ),
    ErrorCode.WEBHOOK_SIGNATURE_INVALID: ErrorCopy(
        http="Webhook 签名校验失败",
        im="消息来源校验未通过。",
        web="消息来源校验未通过。",
    ),
    ErrorCode.WEBHOOK_TIMESTAMP_SKEW: ErrorCopy(
        http="Webhook 时间戳超出允许偏差",
        im="消息时间戳超出允许偏差。",
        web="消息时间戳超出允许偏差。",
    ),
    ErrorCode.DUPLICATE_REQUEST: ErrorCopy(
        http="请求重复，已被幂等拦截",
        im="这条消息已经处理过了。",
        web="这条消息已经处理过了。",
    ),
    ErrorCode.TENANT_DENIED: ErrorCopy(
        http="跨租户访问被拒绝",
        im="无权访问该资源。",
        web="无权访问该资源。",
    ),
    ErrorCode.CHANNEL_SERVICE_ACCOUNT_MISSING: ErrorCopy(
        http="渠道未登记服务账号",
        im="这个渠道还没配置服务账号，暂时无法自动回复。",
        web="这个渠道还没配置服务账号，暂时无法自动回复。",
    ),
    ErrorCode.CHANNEL_DELIVERY_FAILED: ErrorCopy(
        http="渠道投递失败",
        im="消息发送失败了，请稍后重试。",
        web="消息发送失败了，请稍后重试。",
    ),
    ErrorCode.OUTBOUND_ADAPTER_MISSING: ErrorCopy(
        http="该渠道类型未注册出站适配器",
        im="这个渠道类型暂时无法发送消息。",
        web="这个渠道类型暂时无法发送消息。",
    ),
    ErrorCode.IDENTITY_REJECTED: ErrorCopy(
        http="身份校验失败",
        im="身份校验失败，请重新登录。",
        web="登录状态已失效，请重新登录。",
    ),
    ErrorCode.IDENTITY_CREDENTIALS_MISSING: ErrorCopy(
        http="缺少身份凭证",
        im="缺少身份凭证，请重新登录。",
        web="缺少身份凭证，请重新登录。",
    ),
    ErrorCode.TOKEN_INVALID: ErrorCopy(
        http="登录凭证无效",
        im="登录凭证无效，请重新登录。",
        web="登录凭证无效，请重新登录。",
    ),
    ErrorCode.TOKEN_EXPIRED: ErrorCopy(
        http="登录凭证已过期",
        im="登录已过期，请重新登录。",
        web="登录已过期，请重新登录。",
    ),
    ErrorCode.SERVICE_ACCOUNT_NOT_CONFIGURED: ErrorCopy(
        http="渠道未登记服务账号",
        im="这个渠道还没配置服务账号，暂时无法自动回复。",
        web="这个渠道还没配置服务账号，暂时无法自动回复。",
    ),
    ErrorCode.APPROVER_MUST_DIFFER: ErrorCopy(
        http="审批人不能是发起人",
        im="这个操作需要别人来确认，不能自己批。",
        web="这个操作需要别人来确认，不能自己批。",
    ),
}

_BY_VALUE: Mapping[str, ErrorCode] = {code.value: code for code in ErrorCode}


def try_project_error(
    code: str | ErrorCode, surface: ErrorSurface = "http"
) -> str | None:
    """码在表里才给文案；不认识就返回 ``None``。

    ⚠️ 给**已经有自己文案**的调用方用 —— 投影表没登记这个码时，调用方宁可
    保留原文，也不要被兜底文案覆盖（兜底会盖掉有用的细节）。
    """
    resolved = code if isinstance(code, ErrorCode) else _BY_VALUE.get(code)
    copy = ERROR_PROJECTION.get(resolved) if resolved is not None else None
    if copy is None:
        return None
    return copy.for_surface(surface)


def project_error(code: str | ErrorCode, surface: ErrorSurface = "http") -> str:
    """按错误码 + 投放面取文案。

    ⚠️ **码不认识就返回兜底文案**，不是把裸码返回去 —— 裸码对用户毫无意义
    （对日志毫无意义，但日志里另有 ``code`` 字段 ✓）。
    """
    resolved = code if isinstance(code, ErrorCode) else _BY_VALUE.get(code)
    copy = ERROR_PROJECTION.get(resolved) if resolved is not None else None
    if copy is None:
        return _FALLBACK_COPY.for_surface(surface)
    return copy.for_surface(surface)


def project_error_message(
    code: str, message: str, surface: ErrorSurface = "http"
) -> str:
    """**没有自己的消息时**用投影文案；有自己的消息就保留。

    ⚠️ 判据是「消息为空，或消息就是码本身」（`AppError.__init__` 是
    ``message or self.code``）—— 那说明调用方**没写消息**，信封里装的是
    **裸码**。有具体消息的**一律保留** —— 投影文案不覆盖有用的细节。
    """
    if not message or message == code:
        return project_error(code, surface)
    return message


__all__ = [
    "ERROR_PROJECTION",
    "ErrorCode",
    "ErrorCopy",
    "ErrorSurface",
    "project_error",
    "project_error_message",
    "try_project_error",
]
