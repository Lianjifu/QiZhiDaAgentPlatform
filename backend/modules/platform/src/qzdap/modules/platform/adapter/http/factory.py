"""Per-request PlatformService factory protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from qzdap.modules.platform.application.services import PlatformService


@runtime_checkable
class PlatformServiceFactory(Protocol):
    def for_session(self) -> PlatformService: ...


__all__ = ["PlatformServiceFactory"]
