"""HTTP factory type alias for observability module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from qzdap.modules.observability_module.application.services import (
    ObservabilityService,
)


@runtime_checkable
class ObservabilityServiceFactory(Protocol):
    """Per-request factory exposed by composition via ``app.state``."""

    def for_session(self) -> ObservabilityService: ...


__all__ = ["ObservabilityServiceFactory"]
