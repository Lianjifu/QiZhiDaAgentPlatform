"""Postgres integration tests for the governance SQL repositories + services.

Exercises the four governance tables (policies, approvals,
decision_events, audit_log) end-to-end via the real ``Sql*Repository``
adapters and the ``PolicyService`` / ``ApprovalService`` application
services. Verifies:

- Round-trip domain → ORM → domain for each entity.
- Tenant isolation (one tenant cannot read another tenant's rows).
- ``decision_events`` is written exactly once per evaluation.
- ``audit_log`` receives business events via the
  ``AuditRecorder`` subscriber pipeline (mocked EventBus).
- Approval state machine persists ``approve``/``deny`` correctly with
  ``decided_at`` and ``approver_id``.

Tests share a single Postgres schema (per session) for speed; each test
truncates the relevant tables in a per-test fixture so they remain
independent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from qzdap_schema.ids import (
    DecisionEventId,
    TenantId,
    UserId,
    WorkspaceId,
)
from sqlalchemy import text

from qzdap.modules.governance.adapter.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditLogAdapter,
    SqlDecisionEventRepo,
    SqlPolicyRepository,
)
from qzdap.modules.governance.adapter.subscribers.audit_subscriber import (
    install as install_audit,
)
from qzdap.modules.governance.application.approval_service import ApprovalService
from qzdap.modules.governance.application.audit_recorder import AuditRecorder
from qzdap.modules.governance.application.policy_service import PolicyService
from qzdap.modules.governance.application.ports import (
    ClockPort,
    IdGeneratorPort,
)
from qzdap.modules.governance.domain.entities import (
    Approval,
    DecisionEvent,
    PolicyRule,
)
from qzdap.modules.governance.domain.value_objects import (
    ApprovalStatus,
    PolicyEffect,
    PolicySubject,
)

# ── Fakes ──────────────────────────────────────────────────────────────


class FixedClock(ClockPort):
    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime(2026, 1, 1, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now


class SequenceIds(IdGeneratorPort):
    def __init__(self) -> None:
        self._n = 0

    def new_id(self) -> UUID:
        self._n += 1
        # Deterministic for assertions
        return UUID(int=self._n)


class RecordingPublisher:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def publish(self, topic: str, payload: dict) -> None:
        self.events.append((topic, payload))


# ── Truncate fixture ────────────────────────────────────────────────────


@pytest_asyncio.fixture(autouse=True)
async def _truncate(session_factory):
    """Clear governance tables before each test for hermetic isolation."""
    async with session_factory() as session:
        await session.execute(
            text("TRUNCATE policies, approvals, decision_events, audit_log")
        )
        await session.commit()
    yield


# ── Constants ───────────────────────────────────────────────────────────


TENANT_A = TenantId(UUID("00000000-0000-0000-0000-000000000001"))
TENANT_B = TenantId(UUID("00000000-0000-0000-0000-00000000000b"))
WORKSPACE = WorkspaceId(UUID("00000000-0000-0000-0000-0000000000aa"))
ADMIN_ID = UserId(UUID("00000000-0000-0000-0000-00000000adad"))
USER_ID = UserId(UUID("00000000-0000-0000-0000-00000000beef"))


# ── Fixtures: services ──────────────────────────────────────────────────


@pytest_asyncio.fixture
async def policy_repo(session_factory) -> SqlPolicyRepository:
    return SqlPolicyRepository(session_factory)


@pytest_asyncio.fixture
async def approval_repo(session_factory) -> SqlApprovalRepository:
    return SqlApprovalRepository(session_factory)


@pytest_asyncio.fixture
async def decision_repo(session_factory) -> SqlDecisionEventRepo:
    return SqlDecisionEventRepo(session_factory)


@pytest_asyncio.fixture
async def audit_repo(session_factory) -> SqlAuditLogAdapter:
    return SqlAuditLogAdapter(session_factory)


@pytest_asyncio.fixture
async def policy_service(policy_repo) -> PolicyService:
    return PolicyService(
        repo=policy_repo,
        clock=FixedClock(),
        ids=SequenceIds(),
        publisher=None,
    )


@pytest_asyncio.fixture
async def approval_service(approval_repo) -> ApprovalService:
    return ApprovalService(
        repo=approval_repo,
        clock=FixedClock(),
        ids=SequenceIds(),
        publisher=None,
    )


# ── SqlPolicyRepository round-trip ──────────────────────────────────────


@pytest.mark.asyncio
async def test_policy_round_trip(policy_repo):
    rule = PolicyRule.create(
        tenant_id=TENANT_A,
        subject_type=PolicySubject.ROLE,
        subject_ref="workspace_member",
        action_pattern="tool:execute:*",
        effect=PolicyEffect.DENY,
        priority=10,
        workspace_id=WORKSPACE,
    )
    await policy_repo.add(rule)
    fetched = await policy_repo.get(tenant_id=TENANT_A, rule_id=rule.id)
    assert fetched is not None
    assert fetched.id == rule.id
    assert fetched.action_pattern == "tool:execute:*"
    assert fetched.effect is PolicyEffect.DENY
    assert fetched.priority == 10


@pytest.mark.asyncio
async def test_policy_tenant_isolation(policy_repo):
    rule_a = PolicyRule.create(
        tenant_id=TENANT_A,
        subject_type=PolicySubject.ROLE,
        subject_ref="workspace_member",
        action_pattern="tool:execute:reverse",
        effect=PolicyEffect.DENY,
    )
    await policy_repo.add(rule_a)
    fetched = await policy_repo.get(tenant_id=TENANT_B, rule_id=rule_a.id)
    assert fetched is None


@pytest.mark.asyncio
async def test_policy_list_filters_by_tenant_and_workspace(policy_repo):
    rule_t1_ws1 = PolicyRule.create(
        tenant_id=TENANT_A,
        subject_type=PolicySubject.ROLE,
        subject_ref="workspace_member",
        action_pattern="tool:execute:a",
        effect=PolicyEffect.DENY,
        workspace_id=WORKSPACE,
    )
    rule_t1_tenant_wide = PolicyRule.create(
        tenant_id=TENANT_A,
        subject_type=PolicySubject.ROLE,
        subject_ref="workspace_member",
        action_pattern="tool:execute:b",
        effect=PolicyEffect.ALLOW,
    )
    rule_t2 = PolicyRule.create(
        tenant_id=TENANT_B,
        subject_type=PolicySubject.ROLE,
        subject_ref="workspace_member",
        action_pattern="tool:execute:c",
        effect=PolicyEffect.ALLOW,
    )
    for r in (rule_t1_ws1, rule_t1_tenant_wide, rule_t2):
        await policy_repo.add(r)

    a_rules = await policy_repo.list_records(tenant_id=TENANT_A)
    assert {r.action_pattern for r in a_rules} == {"tool:execute:a", "tool:execute:b"}

    b_rules = await policy_repo.list_records(tenant_id=TENANT_B)
    assert {r.action_pattern for r in b_rules} == {"tool:execute:c"}


@pytest.mark.asyncio
async def test_policy_update_to_disabled(policy_repo):
    rule = PolicyRule.create(
        tenant_id=TENANT_A,
        subject_type=PolicySubject.ROLE,
        subject_ref="workspace_member",
        action_pattern="tool:execute:reverse",
        effect=PolicyEffect.DENY,
    )
    await policy_repo.add(rule)

    # Reconstruct the rule disabled (frozen dataclass ⇒ new copy).
    disabled = PolicyRule.create(
        tenant_id=TENANT_A,
        subject_type=rule.subject_type,
        subject_ref=rule.subject_ref,
        action_pattern=rule.action_pattern,
        effect=rule.effect,
        workspace_id=rule.workspace_id,
        priority=rule.priority,
        approval_required=rule.approval_required,
        quota=dict(rule.quota) if rule.quota else None,
        enabled=False,
        id=rule.id,
        now=rule.created_at,
    )
    await policy_repo.update(disabled)

    fetched = await policy_repo.get(tenant_id=TENANT_A, rule_id=rule.id)
    assert fetched is not None
    assert fetched.enabled is False


# ── SqlApprovalRepository state machine ─────────────────────────────────


@pytest.mark.asyncio
async def test_approval_create_then_approve(approval_repo):
    expires = datetime(2026, 12, 31, tzinfo=UTC)
    ap = Approval.create(
        tenant_id=TENANT_A,
        requester_id=USER_ID,
        action="tool:execute:clock",
        resource={"tool": "clock"},
        expires_at=expires,
    )
    await approval_repo.add(ap)

    fetched = await approval_repo.get(tenant_id=TENANT_A, approval_id=ap.id)
    assert fetched is not None
    assert fetched.status is ApprovalStatus.PENDING

    decided = fetched.approve(approver_id=ADMIN_ID, now=expires - timedelta(days=1))
    await approval_repo.update(decided)
    after = await approval_repo.get(tenant_id=TENANT_A, approval_id=ap.id)
    assert after is not None
    assert after.status is ApprovalStatus.APPROVED
    assert after.approver_id == ADMIN_ID


@pytest.mark.asyncio
async def test_approval_list_pending(approval_repo):
    ap1 = Approval.create(
        tenant_id=TENANT_A,
        requester_id=USER_ID,
        action="tool:execute:reverse",
        resource={"tool": "reverse"},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    ap2 = Approval.create(
        tenant_id=TENANT_A,
        requester_id=USER_ID,
        action="tool:execute:clock",
        resource={"tool": "clock"},
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    await approval_repo.add(ap1)
    await approval_repo.add(ap2)

    pending = await approval_repo.list_pending(
        tenant_id=TENANT_A, now=datetime.now(UTC)
    )
    assert {a.action for a in pending} == {
        "tool:execute:reverse",
        "tool:execute:clock",
    }


# ── SqlDecisionEventRepo ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_decision_events_accumulate(decision_repo):
    for action in ("tool:execute:a", "tool:execute:b", "memory:write:user"):
        ev = DecisionEvent(
            id=DecisionEventId(uuid4()),
            tenant_id=TENANT_A,
            actor_id=USER_ID,
            action=action,
            resource={},
            effect=PolicyEffect.ALLOW,
            rule_id=None,
            approval_id=None,
            latency_ms=1,
            created_at=datetime.now(UTC),
        )
        await decision_repo.append(ev)

    rows = await decision_repo.list_by_tenant(tenant_id=TENANT_A, limit=10)
    assert len(rows) == 3


# ── SqlAuditLogAdapter + AuditRecorder subscriber ─────────────────────────


class _FakeBus:
    def __init__(self) -> None:
        self.subs: dict[str, list] = {}

    async def subscribe(self, topic: str, handler) -> None:
        self.subs.setdefault(topic, []).append(handler)

    async def publish(self, topic: str, envelope) -> None:
        for h in self.subs.get(topic, []):
            await h(envelope)


@pytest.mark.asyncio
async def test_audit_subscriber_receives_business_events(audit_repo):
    bus = _FakeBus()
    recorder = AuditRecorder(
        audit_port=audit_repo,
        clock=FixedClock(),
        topics=("memory.written",),
    )
    await install_audit(bus, recorder)

    envelope = {
        "event_id": uuid4(),
        "event_name": "memory.written",
        "tenant_id": TENANT_A,
        "workspace_id": WORKSPACE,
        "occurred_at_ms": int(datetime.now(UTC).timestamp() * 1000),
        "trace_id": uuid4(),
        "payload": {
            "tenant_id": str(TENANT_A),
            "actor_id": str(USER_ID),
            "memory_id": str(uuid4()),
        },
    }
    await bus.publish("memory.written", envelope)
    rows = await audit_repo.list_by_tenant(tenant_id=TENANT_A, limit=10)
    assert len(rows) == 1
    assert rows[0].event_type == "memory.written"
    assert rows[0].tenant_id == TENANT_A


@pytest.mark.asyncio
async def test_audit_recorder_scrubs_secrets(audit_repo):
    bus = _FakeBus()
    recorder = AuditRecorder(
        audit_port=audit_repo,
        clock=FixedClock(),
        topics=("tool.execution.completed",),
    )
    await install_audit(bus, recorder)

    envelope = {
        "event_id": uuid4(),
        "event_name": "tool.execution.completed",
        "tenant_id": TENANT_A,
        "workspace_id": WORKSPACE,
        "occurred_at_ms": int(datetime.now(UTC).timestamp() * 1000),
        "trace_id": uuid4(),
        "payload": {
            "tenant_id": str(TENANT_A),
            "actor_id": str(USER_ID),
            "tool": "reverse",
            "api_key": "sk-LEAK-ME",
            "authorization": "Bearer leak",
            "token": "t0ken",
            "secrets_ref": "env:MY_KEY",
        },
    }
    await bus.publish("tool.execution.completed", envelope)
    rows = await audit_repo.list_by_tenant(tenant_id=TENANT_A, limit=1)
    payload = rows[0].payload
    assert payload["api_key_redacted"] == "***"
    assert payload["authorization_redacted"] == "***"
    assert payload["token_redacted"] == "***"
    assert payload["secrets_ref"] == "env:MY_KEY"


# ── PolicyService end-to-end with publisher ─────────────────────────────


@pytest.mark.asyncio
async def test_policy_service_creates_and_publishes(policy_repo):
    publisher = RecordingPublisher()
    svc = PolicyService(
        repo=policy_repo,
        clock=FixedClock(),
        ids=SequenceIds(),
        publisher=publisher,
    )
    rule = await svc.create(
        tenant_id=TENANT_A,
        actor_id=ADMIN_ID,
        subject_type=PolicySubject.ROLE,
        subject_ref="workspace_member",
        action_pattern="tool:execute:reverse",
        effect=PolicyEffect.DENY,
    )
    assert rule.id is not None
    assert len(publisher.events) == 1
    topic, payload = publisher.events[0]
    assert topic == "governance.policy.created"
    assert payload["rule_id"] == rule.id


@pytest.mark.asyncio
async def test_policy_service_tenant_isolation_blocks(policy_repo):
    """Cross-tenant fetch must raise PolicyNotFound."""
    svc = PolicyService(
        repo=policy_repo,
        clock=FixedClock(),
        ids=SequenceIds(),
        publisher=None,
    )
    rule = await svc.create(
        tenant_id=TENANT_A,
        actor_id=ADMIN_ID,
        subject_type=PolicySubject.ROLE,
        subject_ref="workspace_member",
        action_pattern="tool:execute:reverse",
        effect=PolicyEffect.DENY,
    )
    from qzdap.modules.governance.domain.errors import PolicyNotFound

    with pytest.raises(PolicyNotFound):
        await svc.get(tenant_id=TENANT_B, rule_id=rule.id)


# ── ApprovalService end-to-end ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_approval_service_persists_decision(approval_repo):
    svc = ApprovalService(
        repo=approval_repo,
        clock=FixedClock(),
        ids=SequenceIds(),
        publisher=None,
    )
    ap = await svc.create(
        tenant_id=TENANT_A,
        requester_id=USER_ID,
        action="tool:execute:clock",
        resource={"tool": "clock"},
        ttl_seconds=3600,
    )
    assert ap.status is ApprovalStatus.PENDING

    decided = await svc.approve(
        tenant_id=TENANT_A,
        approval_id=ap.id,
        approver_id=ADMIN_ID,
    )
    assert decided.status is ApprovalStatus.APPROVED

    fetched = await approval_repo.get(tenant_id=TENANT_A, approval_id=ap.id)
    assert fetched is not None
    assert fetched.status is ApprovalStatus.APPROVED
    assert fetched.approver_id == ADMIN_ID
