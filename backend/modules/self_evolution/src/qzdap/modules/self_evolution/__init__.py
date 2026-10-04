"""Self-evolution module — EvolveCandidate lifecycle + apply guard (A4)."""

from __future__ import annotations

from qzdap.modules.self_evolution.domain.entities import EvolveCandidate
from qzdap.modules.self_evolution.domain.errors import (
    ApplyGuardRejected,
    EvolveCandidateAlreadyDecided,
    EvolveCandidateError,
    EvolveCandidateNotFound,
    InvalidEvolveCandidate,
    SignerMustDiffer,
)
from qzdap.modules.self_evolution.domain.value_objects import EvolveKind, EvolveStatus

__all__ = [
    "ApplyGuardRejected",
    "EvolveCandidate",
    "EvolveCandidateAlreadyDecided",
    "EvolveCandidateError",
    "EvolveCandidateNotFound",
    "EvolveKind",
    "EvolveStatus",
    "InvalidEvolveCandidate",
    "SignerMustDiffer",
]
