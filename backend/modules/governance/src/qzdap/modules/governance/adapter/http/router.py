"""Governance HTTP router — /v1/policies/* + /v1/approvals/*.

Routes are thin: parse DTO → call service → convert response.  All
policy/approval transitions go through the application services so
events + decision_events are written exactly once.

Requires:
- ``PolicyService`` + ``ApprovalService`` + ``PolicyGuard`` registered
  via FastAPI dependencies (composition root).
- An admin-only ``require_role("admin")`` dependency for mutating routes;
  read routes accept any authenticated principal.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from qzdap_schema.ids import ApprovalId, PolicyId
from qzdap_vault.actor import ActorContext
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from qzdap.modules.governance.adapter.http.dto import (
    ApprovalDecisionRequest,
    ApprovalListResponse,
    ApprovalResponse,
    CreatePolicyRequest,
    PolicyListResponse,
    PolicyResponse,
    UpdatePolicyRequest,
)
from qzdap.modules.governance.adapter.http.factory import (
    make_approval_service,
    make_policy_service,
)
from qzdap.modules.governance.adapter.http.mappers import (
    approval_to_response,
    policy_to_response,
)
from qzdap.modules.governance.application.approval_service import ApprovalService
from qzdap.modules.governance.application.policy_service import PolicyService

router = APIRouter(tags=["governance"])


# ── helpers (composition root swaps with auth dependencies) ─────────────


async def _require_actor() -> ActorContext:  # placeholder
    raise HTTPException(status_code=401, detail="not authenticated")


async def _require_admin() -> ActorContext:  # placeholder
    raise HTTPException(status_code=401, detail="not authenticated")


ActorDep = Annotated[ActorContext, Depends(_require_actor)]
AdminDep = Annotated[ActorContext, Depends(_require_admin)]


# ── /v1/policies ──────────────────────────────────────────────────────


@router.post(
    "/v1/policies",
    response_model=PolicyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_policy(
    body: CreatePolicyRequest,
    actor: AdminDep,
    svc: Annotated[PolicyService, Depends(make_policy_service)],
) -> PolicyResponse:
    rule = await svc.create(
        tenant_id=actor.tenant_id,
        actor_id=actor.principal_id,  # type: ignore[arg-type]
        subject_type=body.subject_type,
        subject_ref=body.subject_ref,
        action_pattern=body.action_pattern,
        effect=body.effect,
        workspace_id=body.workspace_id,
        priority=body.priority,
        approval_required=body.approval_required,
        quota=body.quota,
        enabled=body.enabled,
    )
    return policy_to_response(rule)


@router.get("/v1/policies", response_model=PolicyListResponse)
async def list_policies(
    actor: ActorDep,
    svc: Annotated[PolicyService, Depends(make_policy_service)],
    workspace_id: UUID | None = Query(default=None),  # noqa: B008 — FastAPI idiom
    enabled_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    cursor: str | None = Query(default=None),
) -> PolicyListResponse:
    rules = await svc.list(
        tenant_id=actor.tenant_id,
        workspace_id=workspace_id,
        enabled_only=enabled_only,
        limit=limit,
        cursor=cursor,
    )
    return PolicyListResponse(items=[policy_to_response(r) for r in rules])


@router.get("/v1/policies/{rule_id}", response_model=PolicyResponse)
async def get_policy(
    rule_id: UUID,
    actor: ActorDep,
    svc: Annotated[PolicyService, Depends(make_policy_service)],
) -> PolicyResponse:
    rule = await svc.get(tenant_id=actor.tenant_id, rule_id=PolicyId(rule_id))  # type: ignore[arg-type]
    return policy_to_response(rule)


@router.patch("/v1/policies/{rule_id}", response_model=PolicyResponse)
async def update_policy(
    rule_id: UUID,
    body: UpdatePolicyRequest,
    actor: AdminDep,
    svc: Annotated[PolicyService, Depends(make_policy_service)],
) -> PolicyResponse:
    rule = await svc.update(
        tenant_id=actor.tenant_id,
        actor_id=actor.principal_id,  # type: ignore[arg-type]
        rule_id=PolicyId(rule_id),  # type: ignore[arg-type]
        enabled=body.enabled,
        priority=body.priority,
        effect=body.effect,
        action_pattern=body.action_pattern,
    )
    return policy_to_response(rule)


@router.delete(
    "/v1/policies/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_policy(
    rule_id: UUID,
    actor: AdminDep,
    svc: Annotated[PolicyService, Depends(make_policy_service)],
) -> Response:
    await svc.delete(
        tenant_id=actor.tenant_id,
        actor_id=actor.principal_id,  # type: ignore[arg-type]
        rule_id=PolicyId(rule_id),  # type: ignore[arg-type]
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── /v1/approvals ────────────────────────────────────────────────────


@router.get("/v1/approvals", response_model=ApprovalListResponse)
async def list_approvals(
    actor: ActorDep,
    svc: Annotated[ApprovalService, Depends(make_approval_service)],
    pending_only: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
) -> ApprovalListResponse:
    if pending_only:
        approvals = await svc.list_pending(tenant_id=actor.tenant_id, limit=limit)
    else:
        # ``pending_only=false`` returns every approval for the tenant
        # (PENDING + APPROVED + DENIED + EXPIRED). Goes through the
        # service so audit events / clock tick / row-bounded limit are
        # applied consistently with the rest of the codebase.
        approvals = await svc.list_all(tenant_id=actor.tenant_id, limit=limit)
    return ApprovalListResponse(items=[approval_to_response(a) for a in approvals])


@router.get("/v1/approvals/{approval_id}", response_model=ApprovalResponse)
async def get_approval(
    approval_id: UUID,
    actor: ActorDep,
    svc: Annotated[ApprovalService, Depends(make_approval_service)],
) -> ApprovalResponse:
    ap = await svc.get(
        tenant_id=actor.tenant_id,
        approval_id=ApprovalId(approval_id),  # type: ignore[arg-type]
    )
    return approval_to_response(ap)


@router.post("/v1/approvals/{approval_id}/approve", response_model=ApprovalResponse)
async def approve(
    approval_id: UUID,
    actor: AdminDep,
    svc: Annotated[ApprovalService, Depends(make_approval_service)],
) -> ApprovalResponse:
    decided = await svc.approve(
        tenant_id=actor.tenant_id,
        approval_id=ApprovalId(approval_id),  # type: ignore[arg-type]
        approver_id=actor.principal_id,  # type: ignore[arg-type]
    )
    return approval_to_response(decided)


@router.post("/v1/approvals/{approval_id}/deny", response_model=ApprovalResponse)
async def deny(
    approval_id: UUID,
    body: ApprovalDecisionRequest,
    actor: AdminDep,
    svc: Annotated[ApprovalService, Depends(make_approval_service)],
) -> ApprovalResponse:
    decided = await svc.deny(
        tenant_id=actor.tenant_id,
        approval_id=ApprovalId(approval_id),  # type: ignore[arg-type]
        approver_id=actor.principal_id,  # type: ignore[arg-type]
        reason=body.reason,
    )
    return approval_to_response(decided)


__all__ = ["router"]
