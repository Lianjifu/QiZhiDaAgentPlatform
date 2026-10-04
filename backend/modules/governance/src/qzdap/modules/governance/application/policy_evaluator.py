"""PolicyEvaluator — the hot-path decision engine.

Order:
1. Fetch enabled rules for the tenant (cached; TTL invalidated on policy
   create/update/delete via the audit_subscriber and use-case hooks).
2. Filter to those matching ``match(actor, rule, action, resource)``.
3. Sort by effect precedence (deny < approval < allow) then priority asc.
4. Pick the first.  If ``REQUIRE_APPROVAL``, mint an ``Approval`` and
   persist it through the ``ApprovalService``.
5. Append a ``DecisionEvent`` so the audit trail captures the verdict even
   if the caller was denied.

Default-deny when no rule matches? **No** — we default-allow and rely on
operators to add explicit ``DENY`` rules for sensitive actions.  This
matches every other zero-trust system the org already runs (the kernel
auth layer has its own role gating, so the policy layer is *additive*
defense, not the first line).
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from qzdap_vault.actor import ActorContext

from qzdap.modules.governance.application.ports import (
    ApprovalRepository,
    ClockPort,
    DecisionEventRepo,
    IdGeneratorPort,
    PolicyEventPublisher,
    PolicyRepository,
)
from qzdap.modules.governance.domain.entities import (
    Approval,
    DecisionEvent,
    DecisionRecord,
)
from qzdap.modules.governance.domain.errors import InvalidApproval
from qzdap.modules.governance.domain.policy_match import action_precedence, match
from qzdap.modules.governance.domain.value_objects import (
    PolicyEffect,
)

_log = logging.getLogger(__name__)


_DEFAULT_TTL_SECONDS = 30
_DEFAULT_APPROVAL_TTL_SECONDS = 3600


class _RuleCache:
    """Tiny TTL cache keyed by tenant_id.

    The hot path is one evaluate() per request, so a per-tenant dict
    keyed by (tenant_id, fetched_at) is enough — no need for LRU
    semantics; rules are small.
    """

    __slots__ = ("_store", "_ttl_seconds")

    def __init__(self, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        self._ttl_seconds = ttl_seconds
        self._store: dict[Any, tuple[float, list]] = {}

    def get(self, key: Any) -> list | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        fetched_at, value = entry
        if (time.monotonic() - fetched_at) > self._ttl_seconds:
            return None
        return value

    def put(self, key: Any, value: list) -> None:
        self._store[key] = (time.monotonic(), value)

    def invalidate(self, key: Any) -> None:
        self._store.pop(key, None)


class PolicyEvaluator:
    def __init__(
        self,
        *,
        policy_repo: PolicyRepository,
        approval_repo: ApprovalRepository,
        decision_repo: DecisionEventRepo,
        clock: ClockPort,
        ids: IdGeneratorPort,
        publisher: PolicyEventPublisher | None = None,
        cache_ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        approval_ttl_seconds: int = _DEFAULT_APPROVAL_TTL_SECONDS,
    ) -> None:
        self._policies = policy_repo
        self._approvals = approval_repo
        self._decisions = decision_repo
        self._clock = clock
        self._ids = ids
        self._publisher = publisher
        self._approval_ttl = approval_ttl_seconds
        self._cache = _RuleCache(cache_ttl_seconds)

    # ── cache control ────────────────────────────────────────────────

    def invalidate(self, *, tenant_id: Any) -> None:
        self._cache.invalidate(tenant_id)

    # ── public API ───────────────────────────────────────────────────

    async def evaluate(
        self,
        *,
        actor: ActorContext,
        action: str,
        resource: dict[str, Any] | None = None,
    ) -> DecisionRecord:
        started = time.monotonic()
        res = dict(resource or {})

        candidates = await self._fetch_enabled(actor.tenant_id)
        matched: list = []
        for rule in candidates:
            if match(actor, rule, action, res):
                matched.append(rule)

        if not matched:
            latency_ms = int((time.monotonic() - started) * 1000)
            rec = DecisionRecord(
                effect=PolicyEffect.ALLOW,
                rule_id=None,
                reason="no matching rule (default allow)",
                latency_ms=latency_ms,
            )
            await self._decisions.append(
                DecisionEvent(
                    id=self._ids.new_id(),
                    tenant_id=actor.tenant_id,
                    actor_id=actor.principal_id or _zero_user_id(),
                    action=action,
                    effect=PolicyEffect.ALLOW,
                    resource=res,
                    rule_id=None,
                    approval_id=None,
                    latency_ms=latency_ms,
                )
            )
            return rec

        matched.sort(
            key=lambda r: (action_precedence(r.effect.value), r.priority, str(r.id))
        )
        winner = matched[0]
        latency_ms = int((time.monotonic() - started) * 1000)

        if winner.effect is PolicyEffect.DENY:
            rec = DecisionRecord(
                effect=PolicyEffect.DENY,
                rule_id=winner.id,
                reason=f"matched rule {winner.id} (deny)",
                latency_ms=latency_ms,
            )
        elif winner.effect is PolicyEffect.REQUIRE_APPROVAL:
            approval = await self._mint_approval(
                actor=actor, action=action, resource=res
            )
            rec = DecisionRecord(
                effect=PolicyEffect.REQUIRE_APPROVAL,
                rule_id=winner.id,
                reason=f"matched rule {winner.id} (require approval)",
                approval_id=approval.id,
                latency_ms=latency_ms,
            )
        else:
            rec = DecisionRecord(
                effect=PolicyEffect.ALLOW,
                rule_id=winner.id,
                reason=f"matched rule {winner.id} (allow)",
                latency_ms=latency_ms,
            )

        await self._decisions.append(
            DecisionEvent(
                id=self._ids.new_id(),
                tenant_id=actor.tenant_id,
                actor_id=actor.principal_id or _zero_user_id(),
                action=action,
                effect=rec.effect,
                resource=res,
                rule_id=rec.rule_id,
                approval_id=rec.approval_id,
                latency_ms=latency_ms,
            )
        )

        _log.debug(
            "policy decision",
            extra={
                "tenant_id": str(actor.tenant_id),
                "actor": str(actor.principal_id),
                "action": action,
                "effect": rec.effect.value,
                "rule_id": str(rec.rule_id) if rec.rule_id else None,
                "approval_id": str(rec.approval_id) if rec.approval_id else None,
                "latency_ms": latency_ms,
            },
        )
        return rec

    # ── helpers ─────────────────────────────────────────────────────────

    async def _fetch_enabled(self, tenant_id: Any) -> list:
        cached = self._cache.get(tenant_id)
        if cached is not None:
            return cached
        rules = await self._policies.list_enabled(tenant_id=tenant_id)
        self._cache.put(tenant_id, rules)
        return rules

    async def _mint_approval(
        self,
        *,
        actor: ActorContext,
        action: str,
        resource: dict[str, Any],
    ) -> Approval:
        if actor.principal_id is None:
            raise InvalidApproval(
                "cannot require approval for an anonymous actor",
                code="INVALID_APPROVAL",
            )
        now = self._clock.now()
        expires_at = now + timedelta(seconds=self._approval_ttl)
        approval = Approval.create(
            tenant_id=actor.tenant_id,
            requester_id=actor.principal_id,
            action=action,
            resource=resource,
            expires_at=expires_at,
            now=now,
        )
        await self._approvals.add(approval)
        if self._publisher is not None:
            await self._publisher.publish(
                "governance.approval.requested",
                {
                    "tenant_id": str(approval.tenant_id),
                    "requester_id": str(approval.requester_id),
                    "approval_id": str(approval.id),
                    "action": approval.action,
                    "resource": approval.resource,
                    "occurred_at": now.isoformat(),
                },
            )
        return approval


def _zero_user_id() -> Any:
    from uuid import UUID

    return UUID("00000000-0000-0000-0000-000000000000")


__all__ = ["PolicyEvaluator"]
