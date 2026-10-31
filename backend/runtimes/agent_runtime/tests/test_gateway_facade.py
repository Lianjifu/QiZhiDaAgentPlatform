"""Gateway 门面的编排测试 —— ①→②→③ 与 ④ 的三个动作。

依据：``docs/refactor/session-architecture/gateway-refactor-plan.md`` §2.3
（三条顺序规则）、§10 Stage 4a。

**顺序是硬要求**：查渠道（①）在验签（②）之前 —— 验签要用渠道的密钥；
归一化（③）在验签之后 —— 未验签的 payload 不能进解析器。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from qzdap_agent_runtime.gateway.facade import (
    ChannelDescriptor,
    Gateway,
    GatewayChannelNotFound,
    GatewayNormalizerMissing,
    scope_for,
)
from qzdap_agent_runtime.gateway.idempotency import IdempotencyGuard
from qzdap_agent_runtime.gateway.identity import (
    REASON_SERVICE_ACCOUNT_MISSING,
    Identity,
    IdentityRejected,
    ServiceAccount,
)
from qzdap_agent_runtime.gateway.normalizer import NormalizerContext
from qzdap_agent_runtime.gateway.types import (
    ActorContext,
    AuthMethod,
    ChannelCapabilities,
    ChannelType,
    IdempotencyDecision,
    IdempotencyKey,
    InboundMessage,
    KeySource,
    RawIngress,
    TrustLevel,
)

_FUTURE = datetime.now(UTC) + timedelta(days=7)
_TENANT = uuid4()
_ACTOR = uuid4()
_CHANNEL = uuid4()


class _Directory:
    """① 的端口替身 —— 记录被查过几次。"""

    def __init__(self, descriptor: ChannelDescriptor | None) -> None:
        self._descriptor = descriptor
        self.calls: list[UUID] = []

    async def get(self, channel_id: UUID) -> ChannelDescriptor | None:
        self.calls.append(channel_id)
        return self._descriptor


class _Verifier:
    """② 的端口替身 —— 记录验签材料。"""

    def __init__(self, *, actor: ActorContext | None, fail: bool = False) -> None:
        self._actor = actor
        self._fail = fail
        self.requests: list[object] = []

    async def verify(self, request) -> Identity:  # type: ignore[no-untyped-def]
        self.requests.append(request)
        if self._fail:
            raise IdentityRejected(
                "bad signature", reason_code="WEBHOOK_SIGNATURE_INVALID", trace_id=request.trace_id
            )
        return Identity(
            actor=self._actor,
            trust=TrustLevel.VERIFIED_HMAC,
            auth_method=AuthMethod.CHANNEL_SIGNATURE,
            auth_evidence="hmac",
        )


class _Normalizer:
    """③ 的端口替身。"""

    def __init__(self) -> None:
        self.contexts: list[NormalizerContext] = []

    def normalize(self, *, body, headers, context) -> InboundMessage:  # type: ignore[no-untyped-def]
        self.contexts.append(context)
        return InboundMessage(
            actor=context.actor,
            channel_type=context.channel_type,
            channel_id=context.channel_id,
            external_chat_id="c1",
            external_user_id="u1",
            explicit_agent_id=None,
            idempotency=IdempotencyKey(
                value="platform|msg-1",
                source=KeySource.PLATFORM_MESSAGE_ID,
                strength="strong",
                expires_at=_FUTURE,
            ),
            external_message_id="msg-1",
            payload_hash="hash",
            trace_id=context.trace_id,
            text="hello",
        )


class _Store:
    """④ 的端口替身。"""

    def __init__(self) -> None:
        self.claims: list[tuple] = []
        self.completed: list[tuple] = []
        self.released: list[UUID] = []

    async def claim(self, scope, key, *, payload_hash="", external_message_id=None, trace_id=""):  # type: ignore[no-untyped-def]
        self.claims.append((scope, key, payload_hash, external_message_id, trace_id))
        return IdempotencyDecision(
            outcome="new", key_strength=key.strength, row_id=uuid4(), status="claimed"
        )

    async def record_weak(self, scope, key, *, payload_hash="", trace_id=""):  # type: ignore[no-untyped-def]
        raise AssertionError("not used in this test")

    async def mark_completed(self, row_id, *, turn_id=None) -> None:  # type: ignore[no-untyped-def]
        self.completed.append((row_id, turn_id))

    async def release(self, row_id) -> None:  # type: ignore[no-untyped-def]
        self.released.append(row_id)


def _raw(**overrides) -> RawIngress:  # type: ignore[no-untyped-def]
    base = {
        "transport": "webhook",
        "channel_type": ChannelType.FEISHU,
        "channel_id": _CHANNEL,
        "capabilities": ChannelCapabilities(),
        "method": "POST",
        "path": "/v1/channels/x/webhook",
        "headers": {"x-webhook-timestamp": "1"},
        "body": b"{}",
        "query": {},
        "trace_id": "trace-1",
    }
    base.update(overrides)
    return RawIngress(**base)


def _descriptor(**overrides) -> ChannelDescriptor:  # type: ignore[no-untyped-def]
    base = {
        "channel_id": _CHANNEL,
        "channel_type": ChannelType.FEISHU,
        "tenant_id": _TENANT,
        "workspace_id": None,
        "secret": b"s3cret",
        "service_account": ServiceAccount(user_id=_ACTOR, agent_id=uuid4(), agent_version="v1"),
    }
    base.update(overrides)
    return ChannelDescriptor(**base)


def _gateway(*, directory, verifier, normalizer=None, store=None) -> tuple[Gateway, _Store]:  # type: ignore[no-untyped-def]
    the_store = store or _Store()
    gateway = Gateway(
        channels=directory,
        identity=verifier,
        normalizers={ChannelType.FEISHU: normalizer or _Normalizer()},
        idempotency=IdempotencyGuard(the_store),
    )
    return gateway, the_store


@pytest.mark.asyncio
async def test_accept_runs_channel_lookup_before_verification() -> None:
    """顺序规则 ①：**查渠道在验签之前** —— 验签要用渠道的密钥。"""
    directory = _Directory(_descriptor())
    verifier = _Verifier(actor=ActorContext(tenant_id=_TENANT, workspace_id=None, actor_id=_ACTOR))
    normalizer = _Normalizer()
    gateway, _ = _gateway(directory=directory, verifier=verifier, normalizer=normalizer)

    await gateway.accept(_raw())

    assert directory.calls == [_CHANNEL]
    request = verifier.requests[0]
    assert request.secret == b"s3cret"  # 密钥来自渠道行
    assert request.service_account is not None
    assert request.tenant_id == _TENANT


@pytest.mark.asyncio
async def test_accept_produces_the_standard_inbound_message() -> None:
    verifier = _Verifier(actor=ActorContext(tenant_id=_TENANT, workspace_id=None, actor_id=_ACTOR))
    normalizer = _Normalizer()
    gateway, _ = _gateway(
        directory=_Directory(_descriptor()), verifier=verifier, normalizer=normalizer
    )

    accepted = await gateway.accept(_raw())

    message = accepted.message
    assert message.actor.actor_id == _ACTOR
    assert message.channel_type is ChannelType.FEISHU
    assert message.channel_id == _CHANNEL
    assert message.trace_id == "trace-1"
    assert message.text == "hello"
    assert accepted.identity.trust.value == "verified_hmac"


@pytest.mark.asyncio
async def test_accept_rejects_when_the_channel_has_no_service_account() -> None:
    """渠道没登记服务账号 → **产不出标准入站消息** → 明确拒绝。"""
    verifier = _Verifier(actor=None)
    gateway, _ = _gateway(
        directory=_Directory(_descriptor(service_account=None)),
        verifier=verifier,
    )
    with pytest.raises(IdentityRejected) as excinfo:
        await gateway.accept(_raw())
    assert excinfo.value.reason_code == REASON_SERVICE_ACCOUNT_MISSING


@pytest.mark.asyncio
async def test_accept_rejects_an_unknown_channel() -> None:
    verifier = _Verifier(actor=ActorContext(tenant_id=_TENANT, workspace_id=None, actor_id=_ACTOR))
    gateway, _ = _gateway(directory=_Directory(None), verifier=verifier)
    with pytest.raises(GatewayChannelNotFound):
        await gateway.accept(_raw())


@pytest.mark.asyncio
async def test_accept_reports_a_missing_normalizer() -> None:
    verifier = _Verifier(actor=ActorContext(tenant_id=_TENANT, workspace_id=None, actor_id=_ACTOR))
    gateway = Gateway(
        channels=_Directory(_descriptor()),
        identity=verifier,
        normalizers={},
        idempotency=IdempotencyGuard(_Store()),
    )
    with pytest.raises(GatewayNormalizerMissing):
        await gateway.accept(_raw())


@pytest.mark.asyncio
async def test_claim_uses_the_scope_derived_from_the_message() -> None:
    """④ 的 claim —— 作用域由标准入站消息推导（IM 用渠道行 id，web 用渠道类型）。"""
    verifier = _Verifier(actor=ActorContext(tenant_id=_TENANT, workspace_id=None, actor_id=_ACTOR))
    gateway, store = _gateway(directory=_Directory(_descriptor()), verifier=verifier)
    accepted = await gateway.accept(_raw())

    decision = await gateway.claim(accepted.message)

    assert decision.outcome == "new"
    scope, key, payload_hash, external_message_id, trace_id = store.claims[0]
    assert scope.tenant_id == _TENANT
    assert scope.channel_id == str(_CHANNEL)
    assert key.value == "platform|msg-1"
    assert payload_hash == "hash"
    assert external_message_id == "msg-1"
    assert trace_id == "trace-1"


@pytest.mark.asyncio
async def test_complete_and_release_delegate_to_the_store() -> None:
    verifier = _Verifier(actor=ActorContext(tenant_id=_TENANT, workspace_id=None, actor_id=_ACTOR))
    gateway, store = _gateway(directory=_Directory(_descriptor()), verifier=verifier)
    accepted = await gateway.accept(_raw())
    decision = await gateway.claim(accepted.message)

    await gateway.complete(decision, turn_id=uuid4())
    assert len(store.completed) == 1

    await gateway.release(decision)
    assert len(store.released) == 1


def test_scope_for_uses_the_channel_type_when_there_is_no_channel_row() -> None:
    """web / api 没有渠道行 → 作用域用渠道类型（与 ``InboxScope.for_web`` 一致）。"""
    message = InboundMessage(
        actor=ActorContext(tenant_id=_TENANT, workspace_id=None, actor_id=_ACTOR),
        channel_type=ChannelType.WEB,
        channel_id=None,
        external_chat_id="c1",
        external_user_id="u1",
        explicit_agent_id=None,
        idempotency=IdempotencyKey(
            value="k",
            source=KeySource.CLIENT_REQUEST_ID,
            strength="strong",
            expires_at=_FUTURE,
        ),
        external_message_id=None,
        payload_hash="h",
        trace_id="t",
        text="hi",
    )
    scope = scope_for(message)
    assert scope.channel_id == "web"
    assert scope.workspace_id == UUID(int=0)  # 哨兵 —— 幂等索引的列是 NOT NULL
