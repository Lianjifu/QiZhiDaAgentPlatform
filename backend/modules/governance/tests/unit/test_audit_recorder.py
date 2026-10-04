"""Tests for ``AuditRecorder`` and the bus subscription install path."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from _governance_unit_in_memory import FixedClock, InMemoryAuditLog
from qzdap_schema.ids import TenantId

from qzdap.modules.governance.adapter.subscribers import audit_subscriber
from qzdap.modules.governance.application.audit_recorder import (
    AuditRecorder,
    build_default_topics,
)

TID = TenantId(UUID("00000000-0000-0000-0000-000000000001"))


@dataclass
class _FakeBus:
    handlers: dict[str, list] = field(default_factory=lambda: defaultdict(list))

    async def subscribe(self, topic: str, handler) -> None:
        self.handlers[topic].append(handler)

    async def publish(self, envelope) -> None:  # not used here
        for h in self.handlers.get(envelope.event_name, []):
            await h(envelope)


from collections import defaultdict


@dataclass
class _Envelope:
    event_name: str
    tenant_id: UUID
    payload: dict[str, Any]


async def test_handle_records_event():
    audit = InMemoryAuditLog()
    rec = AuditRecorder(audit_port=audit, clock=FixedClock(), topics=())
    await rec.handle(
        _Envelope(
            event_name="tool.execution.completed",
            tenant_id=TID,
            payload={"tenant_id": str(TID), "actor_id": str(uuid4()), "tool": "echo"},
        )
    )
    assert len(audit.rows) == 1
    assert audit.rows[0].event_type == "tool.execution.completed"


async def test_handle_drops_payload_missing_tenant():
    audit = InMemoryAuditLog()
    rec = AuditRecorder(audit_port=audit, clock=FixedClock(), topics=())
    await rec.handle(
        _Envelope(event_name="x", tenant_id=TID, payload={"event_name": "x"})
    )
    assert len(audit.rows) == 0


async def test_handle_scrubs_secrets():
    audit = InMemoryAuditLog()
    rec = AuditRecorder(audit_port=audit, clock=FixedClock(), topics=())
    await rec.handle(
        _Envelope(
            event_name="tool.execution.completed",
            tenant_id=TID,
            payload={
                "tenant_id": str(TID),
                "actor_id": str(uuid4()),
                "api_key": "raw-secret",
                "authorization": "Bearer xyz",
                "secrets_ref": "env:OPENAI_API_KEY",
                "token": "abc",
                "password": "pw",
                "secret": "shh",
            },
        )
    )
    p = audit.rows[0].payload
    # secrets are redacted
    assert p["api_key_redacted"] == "***"
    assert p["authorization_redacted"] == "***"
    assert p["token_redacted"] == "***"
    assert p["password_redacted"] == "***"
    assert p["secret_redacted"] == "***"
    # secrets_ref pointer preserved (caller still needs to look it up in vault)
    assert p["secrets_ref"] == "env:OPENAI_API_KEY"


async def test_handle_swallows_audit_append_failure():
    """Audit must never raise back to the EventBus handler."""

    class _BrokenAudit:
        async def append(self, **_):
            raise RuntimeError("db is down")

    rec = AuditRecorder(audit_port=_BrokenAudit(), clock=FixedClock(), topics=())
    # should not raise
    await rec.handle(
        _Envelope(
            event_name="tool.execution.completed",
            tenant_id=TID,
            payload={"tenant_id": str(TID), "actor_id": str(uuid4())},
        )
    )


async def test_install_subscribes_to_all_default_topics():
    audit = InMemoryAuditLog()
    rec = AuditRecorder(
        audit_port=audit,
        clock=FixedClock(),
        topics=build_default_topics(),
    )
    bus = _FakeBus()
    await audit_subscriber.install(bus, rec)
    # Every default topic has at least one handler attached.
    for topic in build_default_topics():
        assert topic in bus.handlers, topic


async def test_install_attaches_cache_invalidator_for_policy_changes():
    audit = InMemoryAuditLog()
    rec = AuditRecorder(
        audit_port=audit, clock=FixedClock(), topics=build_default_topics()
    )
    invalidated: list[UUID] = []

    def _invalidate(tenant_id) -> None:
        invalidated.append(tenant_id)

    bus = _FakeBus()
    await audit_subscriber.install(bus, rec, cache_invalidator=_invalidate)

    # Simulate a policy.created event arriving; invalidator should fire.
    # The recorder is the first handler; the cache-invalidator is the second.
    await bus.handlers["governance.policy.created"][1](
        _Envelope(
            event_name="governance.policy.created",
            tenant_id=TID,
            payload={"tenant_id": str(TID), "actor_id": str(uuid4())},
        )
    )
    assert invalidated == [TID]
