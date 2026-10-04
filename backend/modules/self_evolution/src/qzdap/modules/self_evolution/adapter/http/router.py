"""Self-evolution HTTP router — /v1/evolve/candidates/*.

Routes are thin: parse DTO → call service → convert response. All
candidate transitions go through ``EvolutionCandidateService`` so
events are written exactly once.

Requires:
- ``EvolutionCandidateService`` registered via FastAPI dependencies
  (composition root).
- An admin-only ``require_role("admin")`` dependency for mutating
  routes; read routes accept any authenticated principal.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from qzdap_schema.ids import EvolveCandidateId
from qzdap_vault.actor import ActorContext
from fastapi import APIRouter, Depends, HTTPException, Query, status

from qzdap.modules.self_evolution.adapter.http.dto import (
    CandidateAppliedResponse,
    CandidateDecisionRequest,
    CandidateListResponse,
    CandidateResponse,
    CreateCandidateRequest,
)
from qzdap.modules.self_evolution.adapter.http.factory import (
    make_evolution_service,
)
from qzdap.modules.self_evolution.adapter.http.mappers import (
    candidate_to_response,
)
from qzdap.modules.self_evolution.application.evolution_service import (
    EvolutionCandidateService,
)

router = APIRouter(tags=["self-evolution"])


# ── helpers (composition root swaps with auth dependencies) ─────────────


async def _require_actor() -> ActorContext:  # placeholder
    raise HTTPException(status_code=401, detail="not authenticated")


async def _require_admin() -> ActorContext:  # placeholder
    raise HTTPException(status_code=401, detail="not authenticated")


ActorDep = Annotated[ActorContext, Depends(_require_actor)]
AdminDep = Annotated[ActorContext, Depends(_require_admin)]


# ── /v1/evolve/candidates ──────────────────────────────────────────────


@router.post(
    "/v1/evolve/candidates",
    response_model=CandidateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_candidate(
    body: CreateCandidateRequest,
    actor: AdminDep,
    svc: Annotated[EvolutionCandidateService, Depends(make_evolution_service)],
) -> CandidateResponse:
    cand = await svc.create(
        tenant_id=actor.tenant_id,
        kind=body.kind,
        payload=body.payload,
        confidence=body.confidence,
        trigger_reason=body.trigger_reason,
        workspace_id=body.workspace_id,  # type: ignore[arg-type]
        requester_id=actor.principal_id,  # type: ignore[arg-type]
        ttl_seconds=body.ttl_seconds,
    )
    return candidate_to_response(cand)


@router.get("/v1/evolve/candidates", response_model=CandidateListResponse)
async def list_candidates(
    actor: ActorDep,
    svc: Annotated[EvolutionCandidateService, Depends(make_evolution_service)],
    status_filter: str = Query(default="pending", alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
) -> CandidateListResponse:
    from qzdap.modules.self_evolution.domain.value_objects import EvolveStatus

    try:
        parsed = EvolveStatus(status_filter)
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=f"unknown status '{status_filter}'",
        ) from e
    items = await svc.list_by_status(
        tenant_id=actor.tenant_id, status=parsed, limit=limit
    )
    return CandidateListResponse(items=[candidate_to_response(c) for c in items])


@router.get(
    "/v1/evolve/candidates/{candidate_id}",
    response_model=CandidateResponse,
)
async def get_candidate(
    candidate_id: UUID,
    actor: ActorDep,
    svc: Annotated[EvolutionCandidateService, Depends(make_evolution_service)],
) -> CandidateResponse:
    cand = await svc.get(
        tenant_id=actor.tenant_id,
        candidate_id=EvolveCandidateId(candidate_id),  # type: ignore[arg-type]
    )
    return candidate_to_response(cand)


@router.post(
    "/v1/evolve/candidates/{candidate_id}/approve",
    response_model=CandidateResponse,
)
async def approve_candidate(
    candidate_id: UUID,
    actor: AdminDep,
    svc: Annotated[EvolutionCandidateService, Depends(make_evolution_service)],
) -> CandidateResponse:
    decided = await svc.approve(
        tenant_id=actor.tenant_id,
        candidate_id=EvolveCandidateId(candidate_id),  # type: ignore[arg-type]
        approver_id=actor.principal_id,  # type: ignore[arg-type]
    )
    return candidate_to_response(decided)


@router.post(
    "/v1/evolve/candidates/{candidate_id}/reject",
    response_model=CandidateResponse,
)
async def reject_candidate(
    candidate_id: UUID,
    body: CandidateDecisionRequest,
    actor: AdminDep,
    svc: Annotated[EvolutionCandidateService, Depends(make_evolution_service)],
) -> CandidateResponse:
    decided = await svc.reject(
        tenant_id=actor.tenant_id,
        candidate_id=EvolveCandidateId(candidate_id),  # type: ignore[arg-type]
        approver_id=actor.principal_id,  # type: ignore[arg-type]
        reason=body.reason,
    )
    return candidate_to_response(decided)


@router.post(
    "/v1/evolve/candidates/{candidate_id}/apply",
    response_model=CandidateAppliedResponse,
)
async def apply_candidate(
    candidate_id: UUID,
    actor: AdminDep,
    svc: Annotated[EvolutionCandidateService, Depends(make_evolution_service)],
) -> CandidateAppliedResponse:
    applied, outcome = await svc.apply(
        tenant_id=actor.tenant_id,
        candidate_id=EvolveCandidateId(candidate_id),  # type: ignore[arg-type]
    )
    return CandidateAppliedResponse(
        candidate=candidate_to_response(applied, applied_summary=outcome.summary),
        applied_summary=dict(outcome.summary),
    )


__all__ = ["router"]
