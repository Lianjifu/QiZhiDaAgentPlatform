"""web 入口的 ② 与 ③ —— 身份与归一化。

依据：``docs/refactor/session-architecture/gateway-refactor-plan.md`` §3.2
（web 的信任模型）、§3.3（标准入站数据）、§4.2（幂等键阶梯）。
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from qzdap_agent_runtime.gateway.identity import (
    REASON_CREDENTIALS_MISSING,
    IdentityRejected,
    IdentityRequest,
)
from qzdap_agent_runtime.gateway.normalizer import NormalizerContext
from qzdap_agent_runtime.gateway.types import ActorContext, ChannelType, TrustLevel
from qzdap_agent_runtime.gateway.web import WebChatNormalizer, WebIdentityVerifier

_TENANT = uuid4()
_WORKSPACE = uuid4()
_USER = uuid4()

_HEADERS = {
    "x-tenant-id": str(_TENANT),
    "x-workspace-id": str(_WORKSPACE),
    "x-user-id": str(_USER),
}


def _request(**overrides) -> IdentityRequest:  # type: ignore[no-untyped-def]
    base = {
        "trace_id": "trace-1",
        "headers": _HEADERS,
        "body": b"{}",
    }
    base.update(overrides)
    return IdentityRequest(**base)


def _context(**overrides) -> NormalizerContext:  # type: ignore[no-untyped-def]
    base = {
        "actor": ActorContext(
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            actor_id=_USER,
            roles=("user",),
            actor_kind="user",
        ),
        "channel_type": ChannelType.WEB,
        "trace_id": "trace-1",
        "external_chat_id": "session-1",
    }
    base.update(overrides)
    return NormalizerContext(**base)


# ── ② 身份 ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_principal_wins_over_the_user_header() -> None:
    """principal 优先 —— 它是**验过 JWT** 的那个（认证中间件验的）。"""
    principal_id = uuid4()
    identity = await WebIdentityVerifier().verify(
        _request(actor_id=principal_id, roles=("platform_admin",))
    )
    assert identity.actor is not None
    assert identity.actor.actor_id == principal_id
    assert identity.actor.tenant_id == _TENANT
    assert identity.actor.workspace_id == _WORKSPACE
    assert identity.actor.roles == ("platform_admin",)
    assert identity.trust is TrustLevel.JWT


@pytest.mark.asyncio
async def test_without_a_principal_the_headers_are_the_identity() -> None:
    """没有 principal（内部调用 / 开发壳）→ 租户头兜底，信任级别最低。"""
    identity = await WebIdentityVerifier().verify(_request())
    assert identity.actor is not None
    assert identity.actor.actor_id == _USER
    assert identity.actor.tenant_id == _TENANT
    assert identity.trust is TrustLevel.INTERNAL


@pytest.mark.asyncio
async def test_an_incomplete_identity_is_rejected() -> None:
    verifier = WebIdentityVerifier()
    with pytest.raises(IdentityRejected) as excinfo:
        await verifier.verify(_request(headers={"x-user-id": str(_USER)}))
    assert excinfo.value.reason_code == REASON_CREDENTIALS_MISSING


# ── ③ 归一化 ─────────────────────────────────────────────────────────────


def test_the_body_becomes_the_standard_message() -> None:
    message = WebChatNormalizer().normalize(
        body=b'{"content":"hello","clientRequestId":"req-1"}',
        headers={},
        context=_context(),
    )
    assert message.text == "hello"
    assert message.external_chat_id == "session-1"  # 外部会话标识 = session_id
    assert message.external_user_id == str(_USER)
    assert message.channel_type is ChannelType.WEB
    assert message.trace_id == "trace-1"


def test_a_client_request_id_gives_a_strong_key() -> None:
    message = WebChatNormalizer().normalize(
        body=b'{"content":"hello","clientRequestId":"req-1"}',
        headers={},
        context=_context(),
    )
    assert message.idempotency.source.value == "client_request_id"
    assert message.idempotency.strength == "strong"
    assert message.idempotency.value == "req-1"
    assert message.unprotected is False


def test_without_a_client_request_id_the_key_is_weak_and_the_turn_is_unprotected() -> None:
    """没有 clientRequestId → 内容指纹（**weak**：只记录不抑制，决策 #5）。"""
    message = WebChatNormalizer().normalize(
        body=b'{"content":"hello"}',
        headers={},
        context=_context(),
    )
    assert message.idempotency.source.value == "payload_fingerprint"
    assert message.idempotency.strength == "weak"
    assert message.unprotected is True


def test_the_payload_hash_covers_the_body() -> None:
    message = WebChatNormalizer().normalize(
        body=b'{"content":"hello"}',
        headers={},
        context=_context(),
    )
    assert len(message.payload_hash) == 64
