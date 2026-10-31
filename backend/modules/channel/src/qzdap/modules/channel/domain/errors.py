"""Channel domain errors.

Each error carries a stable ``code`` for the public API envelope and
inherits an HTTP status from ``qzdap_kernel.errors``. Use cases raise the
narrow subclass; the HTTP layer maps the status via
``qzdap_http.error_envelope_middleware``.
"""

from __future__ import annotations

from qzdap_kernel.error_codes import ErrorCode
from qzdap_kernel.errors import (
    AppError,
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
)


class ChannelError(AppError):
    """Base for every channel-domain failure."""


class ChannelNotFound(ChannelError, NotFoundError):
    code = ErrorCode.CHANNEL_NOT_FOUND.value


class ChannelDisabled(ChannelError, ForbiddenError):
    code = ErrorCode.CHANNEL_DISABLED.value
    status = 403


class WebhookSignatureInvalid(ChannelError, AuthenticationError):
    code = ErrorCode.WEBHOOK_SIGNATURE_INVALID.value
    status = 401


class WebhookTimestampSkew(ChannelError, AuthenticationError):
    code = ErrorCode.WEBHOOK_TIMESTAMP_SKEW.value
    status = 401


class ChannelServiceAccountMissing(ChannelError, AppError):
    """渠道没登记服务账号 —— 产不出标准入站消息（③ 需要身份）。

    这是**渠道配置问题**，不是请求问题：调用方改不了，只有管理员能给渠道登记
    服务账号。因此状态码是 503（服务暂时不可用），不是 4xx。
    """

    code = ErrorCode.CHANNEL_SERVICE_ACCOUNT_MISSING.value
    status = 503


class ChannelDeliveryFailed(ChannelError, AppError):
    code = ErrorCode.CHANNEL_DELIVERY_FAILED.value
    status = 502


__all__ = [
    "ChannelDeliveryFailed",
    "ChannelDisabled",
    "ChannelError",
    "ChannelNotFound",
    "ChannelServiceAccountMissing",
    "WebhookSignatureInvalid",
    "WebhookTimestampSkew",
]
