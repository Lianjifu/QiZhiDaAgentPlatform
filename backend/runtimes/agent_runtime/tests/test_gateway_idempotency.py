"""Gateway ④ 幂等守卫 —— 键阶梯与编排的单元测试（无 DB）。

真库 + 真并发的验证在 ``modules/agent_runtime/tests/integration/test_idempotency_store.py``。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from qzdap_agent_runtime.gateway.idempotency import (
    CLIENT_REQUEST_TTL,
    PLATFORM_MESSAGE_TTL,
    WEAK_TTL,
    IdempotencyGuard,
    InboxScope,
    approval_key,
    client_request_key,
    payload_fingerprint_key,
    platform_message_key,
)
from qzdap_agent_runtime.gateway.types import (
    ChannelType,
    IdempotencyDecision,
    KeySource,
)


def _scope() -> InboxScope:
    return InboxScope.for_web(tenant_id=uuid4(), workspace_id=uuid4(), channel=ChannelType.WEB)


class _RecordingStore:
    def __init__(self) -> None:
        self.claimed: list[str] = []
        self.weak: list[str] = []
        self.completed: list[UUID] = []
        self.released: list[UUID] = []

    async def claim(self, scope, key, *, payload_hash="", external_message_id=None, trace_id=""):
        self.claimed.append(key.value)
        return IdempotencyDecision(
            outcome="new", key_strength=key.strength, row_id=uuid4(), status="claimed"
        )

    async def record_weak(self, scope, key, *, payload_hash="", trace_id=""):
        self.weak.append(key.value)
        return IdempotencyDecision(
            outcome="new", key_strength="weak", row_id=uuid4(), status="received"
        )

    async def mark_completed(self, row_id, *, turn_id=None):
        self.completed.append(row_id)

    async def release(self, row_id):
        self.released.append(row_id)


def test_client_request_key_is_strong_with_24h_ttl() -> None:
    key = client_request_key("req-1")
    assert key.strength == "strong"
    assert key.source is KeySource.CLIENT_REQUEST_ID
    assert key.expires_at - datetime.now(UTC) <= CLIENT_REQUEST_TTL
    assert key.expires_at - datetime.now(UTC) > CLIENT_REQUEST_TTL - timedelta(minutes=1)


def test_platform_message_key_is_strong_with_7d_ttl() -> None:
    key = platform_message_key("evt-1")
    assert key.strength == "strong"
    assert key.source is KeySource.PLATFORM_MESSAGE_ID
    assert key.expires_at - datetime.now(UTC) <= PLATFORM_MESSAGE_TTL


def test_payload_fingerprint_is_weak_and_never_suppresses() -> None:
    now = datetime.now(UTC)
    a = payload_fingerprint_key(channel="web", chat_id="s1", user_id="u1", text="好的", now=now)
    b = payload_fingerprint_key(channel="web", chat_id="s1", user_id="u1", text="好的", now=now)
    assert a.strength == "weak"
    assert a.source is KeySource.PAYLOAD_FINGERPRINT
    assert a.value == b.value
    assert a.expires_at - now == WEAK_TTL


def test_payload_fingerprint_changes_across_time_buckets() -> None:
    now = datetime.now(UTC)
    a = payload_fingerprint_key(channel="web", chat_id="s1", user_id="u1", text="好的", now=now)
    b = payload_fingerprint_key(
        channel="web",
        chat_id="s1",
        user_id="u1",
        text="好的",
        now=now + timedelta(seconds=61),
    )
    assert a.value != b.value


def test_approval_key_is_stable_per_approval_and_differs_per_decision() -> None:
    approve = approval_key("ap-1", "approved")
    again = approval_key("ap-1", "approved")
    deny = approval_key("ap-1", "denied")
    other = approval_key("ap-2", "approved")

    assert approve.strength == "strong"
    assert approve.source is KeySource.APPROVAL_DECISION
    assert approve.value == again.value
    assert approve.value != deny.value
    assert approve.value != other.value


def test_approval_key_does_not_depend_on_the_previous_turn_state() -> None:
    """审批恢复时原轮次的状态已经推进 —— 键只能由审批自身的标识派生。"""
    first = approval_key("ap-1", "approved")
    later = approval_key("ap-1", "approved")
    assert first.value == later.value
    assert first.value == "approval|ap-1|approved"


def test_overlong_keys_are_hashed_not_truncated() -> None:
    key = client_request_key("x" * 500)
    assert len(key.value) == 64
    other = client_request_key("x" * 499 + "y")
    assert key.value != other.value


def test_scope_uses_the_sentinel_workspace_when_missing() -> None:
    scope = InboxScope.for_web(tenant_id=uuid4(), workspace_id=None, channel=ChannelType.WEB)
    assert scope.workspace_id.int == 0
    assert scope.channel_id == "web"


async def test_guard_routes_strong_to_claim_and_weak_to_record() -> None:
    store = _RecordingStore()
    guard = IdempotencyGuard(store)
    scope = _scope()

    await guard.accept(scope, client_request_key("req-1"))
    await guard.accept(
        scope,
        payload_fingerprint_key(channel="web", chat_id="s1", user_id="u1", text="好的"),
    )

    assert store.claimed == ["req-1"]
    assert len(store.weak) == 1


async def test_guard_completes_and_releases_only_handled_rows() -> None:
    store = _RecordingStore()
    guard = IdempotencyGuard(store)

    handled = IdempotencyDecision(
        outcome="new", key_strength="strong", row_id=uuid4(), status="claimed"
    )
    duplicate = IdempotencyDecision(
        outcome="duplicate", key_strength="strong", row_id=uuid4(), status="completed"
    )

    await guard.complete(handled, turn_id=uuid4())
    await guard.release(handled)
    await guard.complete(duplicate)
    await guard.release(duplicate)

    assert store.completed == [handled.row_id]
    assert store.released == [handled.row_id]
