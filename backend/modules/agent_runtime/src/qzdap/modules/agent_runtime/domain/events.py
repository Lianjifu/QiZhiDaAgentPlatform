"""Domain events for the agent runtime. Past-tense naming convention.

Concrete events are emitted by the use cases and wrapped into
`EventEnvelope` by the application-layer event publisher adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from qzdap_kernel.events import DomainEvent


@dataclass(slots=True, frozen=True)
class SessionOpened(DomainEvent):
    session_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    owner_id: UUID
    agent_id: UUID
    agent_version: str

    def _as_payload_dict(self) -> dict[str, Any]:
        return {
            "session_id": str(self.session_id),
            "tenant_id": str(self.tenant_id),
            "workspace_id": str(self.workspace_id),
            "owner_id": str(self.owner_id),
            "agent_id": str(self.agent_id),
            "agent_version": self.agent_version,
        }


@dataclass(slots=True, frozen=True)
class SessionClosed(DomainEvent):
    session_id: UUID
    tenant_id: UUID

    def _as_payload_dict(self) -> dict[str, Any]:
        return {
            "session_id": str(self.session_id),
            "tenant_id": str(self.tenant_id),
        }


@dataclass(slots=True, frozen=True)
class TurnStarted(DomainEvent):
    turn_id: UUID
    session_id: UUID
    tenant_id: UUID
    workspace_id: UUID

    def _as_payload_dict(self) -> dict[str, Any]:
        return {
            "turn_id": str(self.turn_id),
            "session_id": str(self.session_id),
            "tenant_id": str(self.tenant_id),
            "workspace_id": str(self.workspace_id),
        }


@dataclass(slots=True, frozen=True)
class TurnCompleted(DomainEvent):
    turn_id: UUID
    session_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    input_tokens: int
    output_tokens: int
    final_message_length: int

    def _as_payload_dict(self) -> dict[str, Any]:
        return {
            "turn_id": str(self.turn_id),
            "session_id": str(self.session_id),
            "tenant_id": str(self.tenant_id),
            "workspace_id": str(self.workspace_id),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "final_message_length": self.final_message_length,
        }


@dataclass(slots=True, frozen=True)
class TurnFailed(DomainEvent):
    turn_id: UUID
    session_id: UUID
    tenant_id: UUID
    code: str
    message: str

    def _as_payload_dict(self) -> dict[str, Any]:
        return {
            "turn_id": str(self.turn_id),
            "session_id": str(self.session_id),
            "tenant_id": str(self.tenant_id),
            "code": self.code,
            "message": self.message,
        }
