"""Self-evolution HTTP subpackage."""

from __future__ import annotations

from qzdap.modules.self_evolution.adapter.http.factory import (
    make_evolution_service,
)
from qzdap.modules.self_evolution.adapter.http.router import router

__all__ = ["make_evolution_service", "router"]
