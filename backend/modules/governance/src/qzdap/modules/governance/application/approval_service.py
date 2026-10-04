"""ApprovalService — create / approve / deny / expire.

Mirrors the in-memory state machine of ``Approval`` but talks to the
repository and emits ``governance.approval.*`` events on transitions.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from qzdap_schema.ids import ApprovalId, TenantId, UserId

from qzdap.modules.governance.application.ports import (
    ApprovalRepository,
    ClockPort,
    IdGeneratorPort,
    PolicyEventPublisher,
)
from qzdap.modules.governance.domain.entities import Approval
from qzdap.modules.governance.domain.errors import (
    ApprovalAlreadyDecided,
    ApprovalExpired,
    ApprovalNotFound,
    ApproverMustDiffer,
)
from qzdap.modules.governance.domain.events import ApprovalDecided
from qzdap.modules.governance.domain.value_objects import ApprovalStatus


class ApprovalService:
    def __init__(
        self,
        *,
        repo: ApprovalRepository,
        clock: ClockPort,
        ids: IdGeneratorPort,
        publisher: PolicyEventPublisher | None = None,
        default_ttl_seconds: int = 3600,
    ) -> None:
        self._repo = repo
        self._clock = clock
        self._ids = ids
        self._publisher = publisher
        self._default_ttl = default_ttl_seconds

    async def create(
        self,
        *,
        tenant_id: TenantId,
        requester_id: UserId,
        action: str,
        resource: dict[str, Any],
        ttl_seconds: int | None = None,
        correlation_id: UUID | None = None,
    ) -> Approval:
        now = self._clock.now()
        expires_at = now + timedelta(seconds=ttl_seconds or self._default_ttl)
        approval = Approval.create(
            tenant_id=tenant_id,
            requester_id=requester_id,
            action=action,
            resource=resource,
            expires_at=expires_at,
            correlation_id=correlation_id,
            now=now,
        )
        await self._repo.add(approval)
        await self._publish(
            "governance.approval.requested",
            tenant_id=tenant_id,
            requester_id=requester_id,
            approval_id=approval.id,
            status=approval.status,
            action=action,
            resource=resource,
            occurred_at=now,
        )
        return approval

    async def get(self, *, tenant_id: TenantId, approval_id: ApprovalId) -> Approval:
        approval = await self._repo.get(tenant_id=tenant_id, approval_id=approval_id)
        if approval is None:
            raise ApprovalNotFound(
                f"approval {approval_id} not found",
                code="APPROVAL_NOT_FOUND",
                details={"approval_id": str(approval_id)},
            )
        return approval

    async def approve(
        self, *, tenant_id: TenantId, approval_id: ApprovalId, approver_id: UserId
    ) -> Approval:
        approval = await self.get(tenant_id=tenant_id, approval_id=approval_id)
        self._ensure_pending(approval)
        self._ensure_not_expired(approval)
        if approver_id == approval.requester_id:
            raise ApproverMustDiffer(
                "approver must differ from requester",
                code="APPROVER_MUST_DIFFER",
            )
        decided = approval.approve(approver_id=approver_id, now=self._clock.now())
        await self._repo.update(decided)
        await self._publish_decision(decided, approver_id=approver_id)
        return decided

    async def deny(
        self,
        *,
        tenant_id: TenantId,
        approval_id: ApprovalId,
        approver_id: UserId,
        reason: str = "",
    ) -> Approval:
        approval = await self.get(tenant_id=tenant_id, approval_id=approval_id)
        self._ensure_pending(approval)
        self._ensure_not_expired(approval)
        if approver_id == approval.requester_id:
            raise ApproverMustDiffer(
                "denier must differ from requester",
                code="APPROVER_MUST_DIFFER",
            )
        decided = approval.deny(
            approver_id=approver_id, reason=reason, now=self._clock.now()
        )
        await self._repo.update(decided)
        await self._publish_decision(decided, approver_id=approver_id)
        return decided

    async def expire_if_due(
        self, *, tenant_id: TenantId, approval_id: ApprovalId
    ) -> Approval | None:
        approval = await self.get(tenant_id=tenant_id, approval_id=approval_id)
        if approval.status is not ApprovalStatus.PENDING:
            return None
        now = self._clock.now()
        if approval.expires_at > now:
            return None
        expired = approval.expire(now=now)
        await self._repo.update(expired)
        await self._publish_decision(
            expired, approver_id=expired.requester_id, force_actor=True
        )
        return expired

    async def list_pending(
        self, *, tenant_id: TenantId, limit: int = 200
    ) -> list[Approval]:
        return await self._repo.list_pending(
            tenant_id=tenant_id, now=self._clock.now(), limit=limit
        )

    async def list_all(
        self, *, tenant_id: TenantId, limit: int = 200
    ) -> list[Approval]:
        """Return every approval for the tenant regardless of status.

        Backs ``GET /v1/approvals?pending_only=false`` — used by admin
        dashboards to render the full decision history. Implemented by
        fan-out across the canonical :class:`ApprovalStatus` values
        because the underlying SQL repo has only ``list_pending`` /
        ``list_by_status`` (no ``OFFSET`` cursor — the data volume is
        bounded by the active workspace so this is cheap enough).
        """
        seen: dict[UUID, Approval] = {}
        for status in (
            ApprovalStatus.PENDING,
            ApprovalStatus.APPROVED,
            ApprovalStatus.DENIED,
            ApprovalStatus.EXPIRED,
        ):
            for approval in await self._repo.list_by_status(
                tenant_id=tenant_id, status=status, limit=limit
            ):
                seen[approval.id] = approval
        approvals = list(seen.values())
        # Sort newest-first so the response is deterministic regardless
        # of which fan-out branch produced each row.
        approvals.sort(key=lambda a: a.created_at, reverse=True)
        return approvals[:limit]

    # ── helpers ────────────────────────────────────────────────────────

    def _ensure_pending(self, approval: Approval) -> None:
        if approval.status is not ApprovalStatus.PENDING:
            raise ApprovalAlreadyDecided(
                f"approval {approval.id} already {approval.status.value}",
                code="APPROVAL_ALREADY_DECIDED",
            )

    def _ensure_not_expired(self, approval: Approval) -> None:
        if approval.expires_at <= self._clock.now():
            raise ApprovalExpired(
                f"approval {approval.id} has expired",
                code="APPROVAL_EXPIRED",
                details={"expires_at": approval.expires_at.isoformat()},
            )

    async def _publish(
        self,
        topic: str,
        *,
        tenant_id: TenantId,
        requester_id: UserId,
        approval_id: ApprovalId,
        status: ApprovalStatus,
        action: str,
        resource: dict[str, Any],
        occurred_at: datetime,
    ) -> None:
        if self._publisher is None:
            return
        await self._publisher.publish(
            topic,
            {
                "event_name": topic,
                "tenant_id": str(tenant_id),
                "requester_id": str(requester_id),
                "approval_id": str(approval_id),
                "status": status.value,
                "action": action,
                "resource": resource,
                "occurred_at": occurred_at.isoformat(),
            },
        )

    async def _publish_decision(
        self,
        approval: Approval,
        *,
        approver_id: UserId,
        force_actor: bool = False,
    ) -> None:
        if self._publisher is None:
            return
        event = ApprovalDecided(
            tenant_id=approval.tenant_id,
            approver_id=approver_id,
            approval_id=approval.id,
            status=approval.status,
            occurred_at=self._clock.now(),
        )
        await self._publisher.publish(
            "governance.approval.decided",
            {
                "event_name": event.topic,
                "tenant_id": str(event.tenant_id),
                "approver_id": str(event.approver_id),
                "approval_id": str(event.approval_id),
                "status": event.status.value,
                "occurred_at": event.occurred_at.isoformat(),
                "event_id": str(event.event_id),
            },
        )


__all__ = ["ApprovalService"]
