"""HTTP factory type alias for agent_factory module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from qzdap.modules.agent_factory.application.services import AgentFactoryService


@runtime_checkable
class AgentFactoryServiceFactory(Protocol):
    """Per-request factory exposed by composition via ``app.state``."""

    def for_session(self) -> AgentFactoryService: ...


__all__ = ["AgentFactoryServiceFactory"]
