"""Gateway ② Auth Identity —— 单元测试（无 DB）。

覆盖三种实现：web（JWT）/ IM（HMAC）/ internal。
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from qzdap_agent_runtime.gateway.identity import (
    REASON_CREDENTIALS_MISSING,
    REASON_SERVICE_ACCOUNT_MISSING,
    REASON_SIGNATURE_INVALID,
    REASON_TIMESTAMP_SKEW,
    REASON_TOKEN_INVALID,
    HmacWebhookVerifier,
    IdentityRejected,
    IdentityRequest,
    InternalIdentityVerifier,
    JwtIdentityVerifier,
    ServiceAccount,
)
from qzdap_kernel.errors import AuthenticationError

_SECRET = b"topsecret"
_BODY = b'{"text":"hello"}'


def _sign(secret: bytes, ts: int, body: bytes) -> str:
    return hmac.new(secret, f"{ts}.".encode() + body, hashlib.sha256).hexdigest()


def _now_ts() -> int:
    return int(datetime.now(UTC).timestamp())


def _request(**overrides) -> IdentityRequest:
    base = {
        "trace_id": "trace-1",
        "headers": {},
        "body": _BODY,
        "secret": _SECRET,
        "tolerance_seconds": 300,
        "tenant_id": uuid4(),
        "workspace_id": uuid4(),
    }
    base.update(overrides)
    return IdentityRequest(**base)


# ── ServiceAccount ───────────────────────────────────────────────────────


def test_service_account_parses_a_valid_mapping() -> None:
    user_id, agent_id = uuid4(), uuid4()
    account = ServiceAccount.from_mapping(
        {
            "user_id": str(user_id),
            "agent_id": str(agent_id),
            "agent_version": "v1",
            "roles": ["im"],
        }
    )
    assert account is not None
    assert account.user_id == user_id
    assert account.agent_id == agent_id
    assert account.agent_version == "v1"
    assert account.roles == ("im",)


def test_service_account_returns_none_for_missing_or_broken_config() -> None:
    assert ServiceAccount.from_mapping(None) is None
    assert ServiceAccount.from_mapping({}) is None
    assert ServiceAccount.from_mapping({"user_id": "not-a-uuid"}) is None
    assert ServiceAccount.from_mapping({"user_id": str(uuid4()), "agent_id": "nope"}) is None


def test_service_account_round_trips_through_a_mapping() -> None:
    account = ServiceAccount(user_id=uuid4(), agent_id=uuid4(), agent_version="v2")
    assert ServiceAccount.from_mapping(account.to_mapping()) == account


def test_the_service_account_carries_the_business_line() -> None:
    """⚠️ **渠道的业务线** ✓（Router 方案 §3.1 规则 3 的输入 ✓）。

    **渠道的属性** ✓ —— 与 ``roles`` 同一层 ✓（不是用户的 ✓）。
    没配 = 空串 ✓（**不猜** ✓ —— 规则 3 不命中 ✓）。
    """
    account = ServiceAccount.from_mapping(
        {
            "user_id": str(uuid4()),
            "agent_id": str(uuid4()),
            "business_line": "客服",
        }
    )
    assert account is not None
    assert account.business_line == "客服"
    # 没配就是空 ✓
    bare = ServiceAccount.from_mapping({"user_id": str(uuid4()), "agent_id": str(uuid4())})
    assert bare is not None
    assert bare.business_line == ""


# ── HmacWebhookVerifier ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_valid_signature_yields_the_service_account_actor() -> None:
    user_id, agent_id = uuid4(), uuid4()
    account = ServiceAccount(user_id=user_id, agent_id=agent_id, roles=("im",))
    ts = _now_ts()
    identity = await HmacWebhookVerifier().verify(
        _request(
            headers={
                "x-webhook-timestamp": str(ts),
                "x-webhook-signature": f"sha256={_sign(_SECRET, ts, _BODY)}",
            },
            service_account=account,
        )
    )
    assert identity.actor is not None
    assert identity.actor.actor_id == user_id
    assert identity.actor.actor_kind == "service_account"
    assert identity.actor.roles == ("im",)
    assert identity.trust.value == "verified_hmac"
    assert identity.auth_method.value == "channel_signature"


@pytest.mark.asyncio
async def test_a_forged_signature_is_rejected_with_the_trace_id() -> None:
    ts = _now_ts()
    with pytest.raises(IdentityRejected) as excinfo:
        await HmacWebhookVerifier().verify(
            _request(
                headers={
                    "x-webhook-timestamp": str(ts),
                    "x-webhook-signature": "sha256=deadbeef",
                },
                trace_id="trace-forged",
            )
        )
    assert excinfo.value.reason_code == REASON_SIGNATURE_INVALID
    assert excinfo.value.trace_id == "trace-forged"


@pytest.mark.asyncio
async def test_a_stale_timestamp_is_rejected() -> None:
    ts = _now_ts() - 3600
    with pytest.raises(IdentityRejected) as excinfo:
        await HmacWebhookVerifier().verify(
            _request(
                headers={
                    "x-webhook-timestamp": str(ts),
                    "x-webhook-signature": f"sha256={_sign(_SECRET, ts, _BODY)}",
                }
            )
        )
    assert excinfo.value.reason_code == REASON_TIMESTAMP_SKEW


@pytest.mark.asyncio
async def test_missing_signature_headers_are_rejected() -> None:
    with pytest.raises(IdentityRejected) as excinfo:
        await HmacWebhookVerifier().verify(_request(headers={}))
    assert excinfo.value.reason_code == REASON_SIGNATURE_INVALID


@pytest.mark.asyncio
async def test_a_non_integer_timestamp_is_rejected() -> None:
    with pytest.raises(IdentityRejected) as excinfo:
        await HmacWebhookVerifier().verify(
            _request(
                headers={
                    "x-webhook-timestamp": "not-a-number",
                    "x-webhook-signature": "sha256=abc",
                }
            )
        )
    assert excinfo.value.reason_code == REASON_SIGNATURE_INVALID


@pytest.mark.asyncio
async def test_a_channel_without_a_service_account_still_verifies() -> None:
    """验签成功但没有服务账号 → **请求可信，只是没有身份**。

    「渠道没登记服务账号」是**配置问题**，不是**请求问题** —— 不能因此拒掉
    这一批请求（服务账号在派发那一步才被需要）。
    """
    ts = _now_ts()
    identity = await HmacWebhookVerifier().verify(
        _request(
            headers={
                "x-webhook-timestamp": str(ts),
                "x-webhook-signature": f"sha256={_sign(_SECRET, ts, _BODY)}",
            },
            service_account=None,
        )
    )
    assert identity.actor is None
    assert identity.trust.value == "verified_hmac"


@pytest.mark.asyncio
async def test_a_channel_without_a_secret_only_checks_the_timestamp() -> None:
    """web 渠道可以不配密钥（不签名）—— 此时只校验时间戳。"""
    ts = _now_ts()
    identity = await HmacWebhookVerifier().verify(
        _request(
            headers={
                "x-webhook-timestamp": str(ts),
                "x-webhook-signature": "sha256=whatever",
            },
            secret=b"",
        )
    )
    assert identity.trust.value == "verified_hmac"


# ── JwtIdentityVerifier ──────────────────────────────────────────────────


class _FakeJwtVerifier:
    def __init__(self, claims: dict | Exception) -> None:
        self._claims = claims

    def verify(self, token: str) -> dict:
        if isinstance(self._claims, Exception):
            raise self._claims
        return self._claims


@pytest.mark.asyncio
async def test_a_valid_jwt_yields_a_user_actor() -> None:
    tenant_id, user_id, workspace_id = uuid4(), uuid4(), uuid4()
    verifier = JwtIdentityVerifier(
        _FakeJwtVerifier(
            {
                "sub": str(user_id),
                "tid": str(tenant_id),
                "wid": str(workspace_id),
                "roles": ["admin"],
            }
        )
    )
    identity = await verifier.verify(_request(headers={"authorization": f"Bearer {uuid4()}"}))
    assert identity.actor is not None
    assert identity.actor.actor_id == user_id
    assert identity.actor.tenant_id == tenant_id
    assert identity.actor.workspace_id == workspace_id
    assert identity.actor.actor_kind == "user"
    assert identity.trust.value == "jwt"


@pytest.mark.asyncio
async def test_a_missing_bearer_token_is_rejected() -> None:
    verifier = JwtIdentityVerifier(_FakeJwtVerifier({}))
    with pytest.raises(IdentityRejected) as excinfo:
        await verifier.verify(_request(headers={}))
    assert excinfo.value.reason_code == REASON_CREDENTIALS_MISSING


@pytest.mark.asyncio
async def test_an_invalid_token_is_rejected() -> None:
    verifier = JwtIdentityVerifier(
        _FakeJwtVerifier(AuthenticationError("token expired", code="TOKEN_EXPIRED"))
    )
    with pytest.raises(IdentityRejected) as excinfo:
        await verifier.verify(_request(headers={"authorization": "Bearer abc"}))
    assert excinfo.value.reason_code == REASON_TOKEN_INVALID


@pytest.mark.asyncio
async def test_a_token_without_sub_or_tid_is_rejected() -> None:
    verifier = JwtIdentityVerifier(_FakeJwtVerifier({"sub": str(uuid4())}))
    with pytest.raises(IdentityRejected) as excinfo:
        await verifier.verify(_request(headers={"authorization": "Bearer abc"}))
    assert excinfo.value.reason_code == REASON_TOKEN_INVALID


# ── InternalIdentityVerifier ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_internal_call_without_an_actor_is_rejected() -> None:
    with pytest.raises(IdentityRejected) as excinfo:
        await InternalIdentityVerifier().verify(_request(actor_id=None))
    assert excinfo.value.reason_code == REASON_CREDENTIALS_MISSING


@pytest.mark.asyncio
async def test_an_internal_call_yields_internal_trust() -> None:
    actor_id = uuid4()
    identity = await InternalIdentityVerifier().verify(_request(actor_id=actor_id))
    assert identity.actor is not None
    assert identity.actor.actor_id == actor_id
    assert identity.trust.value == "internal"
    assert identity.auth_method.value == "internal"


def test_the_service_account_reason_code_is_stable() -> None:
    """派发那一步用它拒绝「渠道没登记服务账号」—— code 必须稳定。"""
    assert REASON_SERVICE_ACCOUNT_MISSING == "SERVICE_ACCOUNT_NOT_CONFIGURED"


_ = UUID
