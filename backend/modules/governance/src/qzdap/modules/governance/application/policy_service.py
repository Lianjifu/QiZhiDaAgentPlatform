"""PolicyService — CRUD + lifecycle for PolicyRule aggregates.

A thin orchestrator over the repository + event publisher.  Used by
``adapter/http/router.py`` for HTTP exposure and by the audit
subscriber to invalidate the cache on policy lifecycle events.
"""

from __future__ import annotations

from typing import Any

from qzdap_schema.ids import PolicyId, TenantId, UserId, WorkspaceId

from qzdap.modules.governance.application.ports import (
    ClockPort,
    IdGeneratorPort,
    PolicyEventPublisher,
    PolicyRepository,
)
from qzdap.modules.governance.domain.entities import PolicyRule
from qzdap.modules.governance.domain.errors import PolicyNotFound
from qzdap.modules.governance.domain.events import (
    PolicyCreated,
    PolicyDeleted,
    PolicyUpdated,
)
from qzdap.modules.governance.domain.value_objects import PolicyEffect, PolicySubject


class PolicyService:
    def __init__(
        self,
        *,
        repo: PolicyRepository,
        clock: ClockPort,
        ids: IdGeneratorPort,
        publisher: PolicyEventPublisher | None = None,
    ) -> None:
        self._repo = repo
        self._clock = clock
        self._ids = ids
        self._publisher = publisher

    async def create(
        self,
        *,
        tenant_id: TenantId,
        actor_id: UserId,
        subject_type: PolicySubject,
        subject_ref: str,
        action_pattern: str,
        effect: PolicyEffect,
        workspace_id: WorkspaceId | None = None,
        priority: int = 100,
        approval_required: bool = False,
        quota: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> PolicyRule:
        now = self._clock.now()
        rule = PolicyRule.create(
            tenant_id=tenant_id,
            subject_type=subject_type,
            subject_ref=subject_ref,
            action_pattern=action_pattern,
            effect=effect,
            workspace_id=workspace_id,
            priority=priority,
            approval_required=approval_required,
            quota=quota,
            enabled=enabled,
            now=now,
        )
        await self._repo.add(rule)
        await self._publish(
            "governance.policy.created",
            PolicyCreated(
                tenant_id=tenant_id,
                actor_id=actor_id,
                rule_id=rule.id,
                effect=rule.effect,
                action_pattern=rule.action_pattern,
                occurred_at=now,
            ),
        )
        return rule

    async def get(self, *, tenant_id: TenantId, rule_id: PolicyId) -> PolicyRule:
        rule = await self._repo.get(tenant_id=tenant_id, rule_id=rule_id)
        if rule is None:
            raise PolicyNotFound(
                f"policy {rule_id} not found",
                code="POLICY_NOT_FOUND",
                details={"rule_id": str(rule_id)},
            )
        return rule

    async def list(
        self,
        *,
        tenant_id: TenantId,
        workspace_id: WorkspaceId | None = None,
        enabled_only: bool = False,
        limit: int = 100,
        cursor: str | None = None,
    ) -> list[PolicyRule]:
        return await self._repo.list_records(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            enabled_only=enabled_only,
            limit=limit,
            cursor=cursor,
        )

    async def update(
        self,
        *,
        tenant_id: TenantId,
        actor_id: UserId,
        rule_id: PolicyId,
        enabled: bool | None = None,
        priority: int | None = None,
        effect: PolicyEffect | None = None,
        action_pattern: str | None = None,
    ) -> PolicyRule:
        existing = await self.get(tenant_id=tenant_id, rule_id=rule_id)
        from dataclasses import replace

        now = self._clock.now()
        next_rule = replace(
            existing,
            enabled=enabled if enabled is not None else existing.enabled,
            priority=priority if priority is not None else existing.priority,
            effect=effect if effect is not None else existing.effect,
            action_pattern=action_pattern or existing.action_pattern,
            updated_at=now,
            version_lock=existing.version_lock + 1,
        )
        await self._repo.update(next_rule)
        await self._publish(
            "governance.policy.updated",
            PolicyUpdated(
                tenant_id=tenant_id,
                actor_id=actor_id,
                rule_id=next_rule.id,
                enabled=next_rule.enabled,
                occurred_at=now,
            ),
        )
        return next_rule

    async def delete(
        self,
        *,
        tenant_id: TenantId,
        actor_id: UserId,
        rule_id: PolicyId,
    ) -> None:
        await self.get(tenant_id=tenant_id, rule_id=rule_id)
        deleted = await self._repo.delete(tenant_id=tenant_id, rule_id=rule_id)
        if not deleted:
            raise PolicyNotFound(
                f"policy {rule_id} not found",
                code="POLICY_NOT_FOUND",
                details={"rule_id": str(rule_id)},
            )
        now = self._clock.now()
        await self._publish(
            "governance.policy.deleted",
            PolicyDeleted(
                tenant_id=tenant_id,
                actor_id=actor_id,
                rule_id=rule_id,
                occurred_at=now,
            ),
        )

    async def _publish(self, topic: str, event: Any) -> None:
        if self._publisher is None:
            return
        await self._publisher.publish(
            topic,
            {
                "event_name": topic,
                "tenant_id": str(event.tenant_id),
                "actor_id": str(event.actor_id),
                "occurred_at": event.occurred_at.isoformat(),
                "event_id": str(event.event_id),
                **{
                    k: getattr(event, k)
                    for k in ("rule_id", "effect", "action_pattern", "enabled")
                    if hasattr(event, k)
                },
            },
        )


__all__ = ["PolicyService"]
