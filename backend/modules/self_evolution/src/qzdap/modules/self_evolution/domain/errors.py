"""Self-evolution domain errors.

All errors subclass ``AppError`` so the HTTP error envelope middleware
maps them to RFC-9457 envelopes with the right ``code`` + ``status``.
The four kernel categories (NotFound / Conflict / Forbidden / Validation)
are reused for the four state-code mappings (404 / 409 / 403 / 422).
"""

from __future__ import annotations

from qzdap_kernel.errors import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)


class EvolveCandidateError(AppError):
    """Base for all self-evolution errors."""


class EvolveCandidateNotFound(EvolveCandidateError, NotFoundError):
    code = "EVOLVE_CANDIDATE_NOT_FOUND"
    status = 404


class EvolveCandidateAlreadyDecided(EvolveCandidateError, ConflictError):
    """Candidate has already been approved / rejected / applied — no further
    transition is allowed from the current state."""

    code = "EVOLVE_CANDIDATE_ALREADY_DECIDED"
    status = 409


class SignerMustDiffer(EvolveCandidateError, ForbiddenError):
    """The approver's UserId matches the requester — admin must differ."""

    code = "EVOLVE_SIGNER_MUST_DIFFER"
    status = 403


class InvalidEvolveCandidate(EvolveCandidateError, ValidationError):
    code = "INVALID_EVOLVE_CANDIDATE"
    status = 422


class ApplyGuardRejected(EvolveCandidateError, ValidationError):
    """The :class:`ApplyGuard` refused to apply this candidate. The exception
    payload carries the structured reason for callers + audit log."""

    code = "APPLY_GUARD_REJECTED"
    status = 422


__all__ = [
    "ApplyGuardRejected",
    "EvolveCandidateAlreadyDecided",
    "EvolveCandidateError",
    "EvolveCandidateNotFound",
    "InvalidEvolveCandidate",
    "SignerMustDiffer",
]
