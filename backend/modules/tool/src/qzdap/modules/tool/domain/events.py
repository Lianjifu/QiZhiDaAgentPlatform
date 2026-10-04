"""Domain events for the tool module. Past-tense naming convention.

Concrete events are emitted by the use cases and wrapped into
`EventEnvelope` by the application-layer event publisher adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from qzdap_kernel.events import DomainEvent


@dataclass(slots=True, frozen=True)
class ToolRegistered(DomainEvent):
    tool_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    name: str
    protocol: str

    def _as_payload_dict(self) -> dict[str, Any]:
        return {
            "tool_id": str(self.tool_id),
            "tenant_id": str(self.tenant_id),
            "workspace_id": str(self.workspace_id),
            "name": self.name,
            "protocol": self.protocol,
        }


@dataclass(slots=True, frozen=True)
class ToolUpdated(DomainEvent):
    tool_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    name: str
    version: int

    def _as_payload_dict(self) -> dict[str, Any]:
        return {
            "tool_id": str(self.tool_id),
            "tenant_id": str(self.tenant_id),
            "workspace_id": str(self.workspace_id),
            "name": self.name,
            "version": self.version,
        }


@dataclass(slots=True, frozen=True)
class ToolDeleted(DomainEvent):
    tool_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    name: str

    def _as_payload_dict(self) -> dict[str, Any]:
        return {
            "tool_id": str(self.tool_id),
            "tenant_id": str(self.tenant_id),
            "workspace_id": str(self.workspace_id),
            "name": self.name,
        }


@dataclass(slots=True, frozen=True)
class ToolInvoked(DomainEvent):
    call_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    tool_name: str

    def _as_payload_dict(self) -> dict[str, Any]:
        return {
            "call_id": str(self.call_id),
            "tenant_id": str(self.tenant_id),
            "workspace_id": str(self.workspace_id),
            "tool_name": self.tool_name,
        }


@dataclass(slots=True, frozen=True)
class ToolCompleted(DomainEvent):
    call_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    tool_name: str
    latency_ms: int

    def _as_payload_dict(self) -> dict[str, Any]:
        return {
            "call_id": str(self.call_id),
            "tenant_id": str(self.tenant_id),
            "workspace_id": str(self.workspace_id),
            "tool_name": self.tool_name,
            "latency_ms": self.latency_ms,
        }


@dataclass(slots=True, frozen=True)
class ToolFailed(DomainEvent):
    call_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    tool_name: str
    error_code: str

    def _as_payload_dict(self) -> dict[str, Any]:
        return {
            "call_id": str(self.call_id),
            "tenant_id": str(self.tenant_id),
            "workspace_id": str(self.workspace_id),
            "tool_name": self.tool_name,
            "error_code": self.error_code,
        }
