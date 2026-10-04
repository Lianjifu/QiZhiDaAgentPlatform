"""Per-call factory for the evolution service (mirrors governance factory)."""

from __future__ import annotations

from qzdap.modules.self_evolution.application.evolution_service import (
    EvolutionCandidateService,
)


def make_evolution_service() -> EvolutionCandidateService:
    """Real dependency — overridden by composition root via Depends overrides."""
    raise RuntimeError(
        "EvolutionCandidateService dependency not wired; composition root must override"
    )


__all__ = ["make_evolution_service"]
