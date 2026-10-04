"""Self-evolution domain subpackage."""

from __future__ import annotations

from qzdap.modules.self_evolution.domain.entities import (
    EvolveCandidate,
    compute_fingerprint,
)
from qzdap.modules.self_evolution.domain.errors import (
    ApplyGuardRejected,
    EvolveCandidateAlreadyDecided,
    EvolveCandidateError,
    EvolveCandidateNotFound,
    InvalidEvolveCandidate,
    SignerMustDiffer,
)
from qzdap.modules.self_evolution.domain.events import (
    EvolutionCandidateApplied,
    EvolutionCandidateCreated,
    EvolutionCandidateDecided,
)
from qzdap.modules.self_evolution.domain.value_objects import (
    EvolveKind,
    EvolveStatus,
    is_terminal,
)

__all__ = [
    "ApplyGuardRejected",
    "EvolutionCandidateApplied",
    "EvolutionCandidateCreated",
    "EvolutionCandidateDecided",
    "EvolveCandidate",
    "EvolveCandidateAlreadyDecided",
    "EvolveCandidateError",
    "EvolveCandidateNotFound",
    "EvolveKind",
    "EvolveStatus",
    "InvalidEvolveCandidate",
    "SignerMustDiffer",
    "compute_fingerprint",
    "is_terminal",
]
