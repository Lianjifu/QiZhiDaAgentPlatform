"""In-memory test doubles for the channel application ports.

These fakes implement the Protocols from
``qzdap.modules.channel.application.ports`` so use cases can be
unit-tested without SQLAlchemy / cryptography / httpx. Mirrors
``_memory_in_memory.py`` so the test-side shape is consistent
across modules.

The factory functions in :mod:`qzdap.modules.channel.application.services`
take these three repos (plus cipher / publisher / adapters); tests
can mix-and-match — e.g. ``InMemoryChannelRepo`` with the SQL
``WebhookSecretRepository`` — when only some paths are under test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from qzdap.modules.channel.application.ports import (
    ChannelDeliveryRepository,
    ChannelRepository,
    WebhookSecretRepository,
)
from qzdap.modules.channel.domain.value_objects import (
    ChannelStatus,
    ChannelType,
)

if TYPE_CHECKING:
    from qzdap.modules.channel.domain.entities import Channel, ChannelDelivery
    from qzdap_schema.ids import ChannelId, TenantId

# ── ChannelRepository ──────────────────────────────────────────────────────


class InMemoryChannelRepo(ChannelRepository):
    """Dict-backed ChannelRepository for unit tests.

    - ``add`` upserts by id (last write wins)
    - ``list`` returns tenant-scoped rows, optionally filtered by
      workspace + ``enabled_only`` (``status == ACTIVE``)
    - ``delete`` is idempotent; returns ``False`` when the row was
      absent or belongs to another tenant
    """

    def __init__(self) -> None:
        self.rows: dict[UUID, Channel] = {}

    async def add(self, channel: Channel) -> None:
        self.rows[channel.id] = channel

    async def get(
        self, *, tenant_id: TenantId, channel_id: ChannelId
    ) -> Channel | None:
        row = self.rows.get(channel_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return row

    async def get_by_id(self, channel_id: ChannelId) -> Channel | None:
        return self.rows.get(channel_id)

    async def list(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: UUID | None = None,
        enabled_only: bool = False,
        limit: int = 100,
    ) -> list[Channel]:
        items: list[Channel] = [
            r for r in self.rows.values() if r.tenant_id == tenant_id
        ]
        if workspace_id is not None:
            items = [
                r
                for r in items
                if r.workspace_id is None or r.workspace_id == workspace_id
            ]
        if enabled_only:
            items = [r for r in items if r.status is ChannelStatus.ACTIVE]
        return items[:limit]

    async def update(self, channel: Channel) -> None:
        self.rows[channel.id] = channel

    async def delete(self, *, tenant_id: TenantId, channel_id: ChannelId) -> bool:
        row = self.rows.get(channel_id)
        if row is None or row.tenant_id != tenant_id:
            return False
        self.rows.pop(channel_id)
        return True


# ── ChannelDeliveryRepository ──────────────────────────────────────────────


class InMemoryDeliveryRepo(ChannelDeliveryRepository):
    """Dict-backed ChannelDeliveryRepository for unit tests.

    The service layer uses ``add`` to record new deliveries and
    ``update`` after the dispatcher reports a terminal status; ``list_for_channel``
    returns rows in insertion order (no DB ordering semantics).
    """

    def __init__(self) -> None:
        self.rows: dict[UUID, ChannelDelivery] = {}

    async def add(self, delivery: ChannelDelivery) -> None:
        self.rows[delivery.id] = delivery

    async def get(
        self, *, tenant_id: TenantId, delivery_id: UUID
    ) -> ChannelDelivery | None:
        row = self.rows.get(delivery_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return row

    async def list_for_channel(
        self,
        *,
        tenant_id: TenantId,
        channel_id: ChannelId,
        limit: int = 50,
    ) -> list[ChannelDelivery]:
        return [
            r
            for r in self.rows.values()
            if r.tenant_id == tenant_id and r.channel_id == channel_id
        ][:limit]

    async def update(self, delivery: ChannelDelivery) -> None:
        self.rows[delivery.id] = delivery


# ── WebhookSecretRepository ────────────────────────────────────────────────


class InMemorySecretRepo(WebhookSecretRepository):
    """Dict-backed WebhookSecretRepository.

    ``add`` returns a deterministic id derived from a monotonic
    counter so test assertions can pin the returned id without
    monkey-patching ``uuid4``. The encrypted payload is stored
    verbatim — the cipher is exercised by the service layer, not by
    this fake.
    """

    def __init__(self) -> None:
        self.rows: dict[UUID, bytes] = {}
        self._counter: int = 0

    async def add(
        self,
        *,
        tenant_id: TenantId,
        channel_type: ChannelType,
        label: str,
        encrypted_payload: bytes,
        key_version: int = 1,
    ) -> UUID:
        self._counter += 1
        # ``+ 1000`` keeps the id comfortably above the SequenceIds
        # UUID space so the two don't collide when a test wires
        # them together.
        sid = UUID(int=self._counter + 1000)
        _ = tenant_id
        _ = channel_type
        _ = label
        _ = key_version
        self.rows[sid] = encrypted_payload
        return sid

    async def get(self, *, tenant_id: TenantId, secret_id: UUID) -> bytes | None:
        _ = tenant_id
        return self.rows.get(secret_id)

    async def delete(self, *, tenant_id: TenantId, secret_id: UUID) -> bool:
        _ = tenant_id
        return self.rows.pop(secret_id, None) is not None


# ── Clock / IdGenerator / Cipher fakes (re-exported for convenience) ───────


@dataclass(slots=True)
class FixedClock:
    """A test clock that returns the same ``now`` until ``advance`` is called."""

    fixed: datetime = field(
        default_factory=lambda: datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    )

    def now(self) -> datetime:
        return self.fixed

    def advance(self, seconds: int) -> None:
        self.fixed = self.fixed + timedelta(seconds=seconds)


@dataclass(slots=True)
class SequenceIds:
    """Returns ``UUID(int=n)`` where n increments per call."""

    _n: int = 0

    def new_id(self) -> UUID:
        self._n += 1
        return UUID(int=self._n)


@dataclass(slots=True)
class NoopCipher:
    """Prefix-flip cipher — enough to prove the cipher port is exercised."""

    prefix: bytes = b"ENC:"

    def encrypt(self, plaintext: bytes) -> bytes:
        return self.prefix + plaintext

    def decrypt(self, blob: bytes) -> bytes:
        if not blob.startswith(self.prefix):
            raise ValueError("bad envelope")
        return blob[len(self.prefix) :]


@dataclass(slots=True)
class CollectingPublisher:
    """Records every event for later assertions.

    Stores ``(topic, payload)`` tuples so the test can assert both
    the routing topic and the marshalled body. ``topic`` comes from
    ``event.TOPIC`` when present (legacy governance / model) and
    falls back to the class name (the kernel convention).
    """

    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def publish(
        self,
        event: object,
        *,
        tenant_id: TenantId,
        workspace_id: UUID | None,
        trace_id: str | None = None,
    ) -> None:
        _ = tenant_id
        _ = workspace_id
        _ = trace_id
        topic = getattr(event, "TOPIC", type(event).__name__)
        payload = getattr(event, "to_payload", lambda: {})()
        self.events.append((topic, payload))


__all__ = [
    "CollectingPublisher",
    "FixedClock",
    "InMemoryChannelRepo",
    "InMemoryDeliveryRepo",
    "InMemorySecretRepo",
    "NoopCipher",
    "SequenceIds",
]
