"""Channel domain errors.

Each error carries a stable ``code`` for the public API envelope and
inherits an HTTP status from ``qzdap_kernel.errors``. Use cases raise the
narrow subclass; the HTTP layer maps the status via
``qzdap_http.error_envelope_middleware``.
"""

from __future__ import annotations

from qzdap_kernel.errors import (
    AppError,
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
)


class ChannelError(AppError):
    """Base for every channel-domain failure."""


class ChannelNotFound(ChannelError, NotFoundError):  # noqa: N818
    code = "CHANNEL_NOT_FOUND"


class ChannelDisabled(ChannelError, ForbiddenError):  # noqa: N818
    code = "CHANNEL_DISABLED"
    status = 403


class WebhookSignatureInvalid(ChannelError, AuthenticationError):  # noqa: N818
    code = "WEBHOOK_SIGNATURE_INVALID"
    status = 401


class WebhookTimestampSkew(ChannelError, AuthenticationError):  # noqa: N818
    code = "WEBHOOK_TIMESTAMP_SKEW"
    status = 401


class ChannelServiceAccountMissing(ChannelError, AppError):  # noqa: N818
    """渠道没登记服务账号 —— 产不出标准入站消息（③ 需要身份）。

    这是**渠道配置问题**，不是请求问题：调用方改不了，只有管理员能给渠道登记
    服务账号。因此状态码是 503（服务暂时不可用），不是 4xx。
    """

    code = "CHANNEL_SERVICE_ACCOUNT_MISSING"
    status = 503


class ChannelDeliveryFailed(ChannelError, AppError):  # noqa: N818
    code = "CHANNEL_DELIVERY_FAILED"
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
