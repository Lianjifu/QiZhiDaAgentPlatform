"""End-to-end HTTP tests for the governance router + PolicyGuard flow.

Exercises the full request → DTO → service → response path via
``httpx.ASGITransport`` (no real network). In-memory ports from
``unit/_governance_in_memory.py`` (registered under the
``_governance_unit_in_memory`` alias by the root conftest) are wired
through ``app.dependency_overrides`` for the policy / approval /
evaluator factories; the auth placeholders ``_require_actor`` /
``_require_admin`` are overridden to return a per-test actor.

These tests complement the ``tests/integration/test_sql_repositories.py``
Postgres tests — those exercise the persistence layer; these exercise
the HTTP layer + business orchestration end-to-end.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from _governance_unit_in_memory import (
    FixedClock,
    InMemoryApprovalRepository,
    InMemoryAuditLog,
    InMemoryDecisionEventRepo,
    InMemoryPolicyRepository,
    SequenceIds,
)
from qzdap_http.error_envelope import error_envelope_middleware
from qzdap_kernel.errors import ActionDeniedError, ApprovalRequiredError
from qzdap_schema.ids import TenantId, UserId, WorkspaceId
from qzdap_vault.actor import ActorContext
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.middleware.base import BaseHTTPMiddleware

from qzdap.modules.governance.adapter.guard.policy_guard import PolicyGuard
from qzdap.modules.governance.adapter.http import factory as gov_factory
from qzdap.modules.governance.adapter.http.router import (
    _require_actor,
    _require_admin,
)
from qzdap.modules.governance.adapter.http.router import (
    router as governance_router,
)
from qzdap.modules.governance.application.approval_service import ApprovalService
from qzdap.modules.governance.application.policy_evaluator import PolicyEvaluator
from qzdap.modules.governance.application.policy_service import PolicyService
from qzdap.modules.governance.application.ports import PolicyEventPublisher

# ── Constants ───────────────────────────────────────────────────────────


TENANT_A = UUID("00000000-0000-0000-0000-000000000001")
TENANT_B = UUID("00000000-0000-0000-0000-00000000000b")
WORKSPACE = UUID("00000000-0000-0000-0000-0000000000aa")
ADMIN_ID = UUID("00000000-0000-0000-0000-00000000adad")
USER_ID = UUID("00000000-0000-0000-0000-00000000beef")


def _admin_actor() -> ActorContext:
    return ActorContext(
        tenant_id=TenantId(TENANT_A),
        workspace_id=WorkspaceId(WORKSPACE),
        principal_id=UserId(ADMIN_ID),
        roles=frozenset({"admin"}),
    )


def _user_actor() -> ActorContext:
    return ActorContext(
        tenant_id=TenantId(TENANT_A),
        workspace_id=WorkspaceId(WORKSPACE),
        principal_id=UserId(USER_ID),
        roles=frozenset({"workspace_member"}),
    )


# ── App builder ─────────────────────────────────────────────────────────


class _NoopPublisher(PolicyEventPublisher):
    async def publish(self, topic: str, payload: dict) -> None:
        return None


def _build_test_app() -> tuple[FastAPI, dict]:
    """Wire governance router against in-memory ports.

    The router's ``make_policy_service`` / ``make_approval_service`` /
    ``make_policy_evaluator`` factories are overridden; the auth
    placeholders ``_require_actor`` / ``_require_admin`` are replaced
    by per-test dependencies that return the admin or user actor.
    """
    policy_repo = InMemoryPolicyRepository()
    approval_repo = InMemoryApprovalRepository()
    decision_repo = InMemoryDecisionEventRepo()
    audit = InMemoryAuditLog()

    clock = FixedClock()
    ids = SequenceIds()

    publisher = _NoopPublisher()
    policy_svc = PolicyService(
        repo=policy_repo, clock=clock, ids=ids, publisher=publisher
    )
    approval_svc = ApprovalService(
        repo=approval_repo, clock=clock, ids=ids, publisher=publisher
    )
    evaluator = PolicyEvaluator(
        policy_repo=policy_repo,
        approval_repo=approval_repo,
        decision_repo=decision_repo,
        clock=clock,
        ids=ids,
        publisher=publisher,
    )
    guard = PolicyGuard(evaluator=evaluator)

    app = FastAPI(title="governance-e2e")
    # Mirror the production wiring: error envelope middleware converts
    # AppError subclasses (PolicyNotFound → 404, ActionDenied → 403,
    # ApprovalRequired → 202) into JSON envelopes so the test app
    # behaves like the real app.
    app.add_middleware(BaseHTTPMiddleware, dispatch=error_envelope_middleware)  # type: ignore[arg-type]
    app.include_router(governance_router)

    async def _provide_policy() -> PolicyService:
        return policy_svc

    async def _provide_approval() -> ApprovalService:
        return approval_svc

    async def _provide_evaluator() -> PolicyEvaluator:
        return evaluator

    async def _admin_dep() -> ActorContext:
        return _admin_actor()

    async def _actor_dep() -> ActorContext:
        return _user_actor()

    app.dependency_overrides[gov_factory.make_policy_service] = _provide_policy
    app.dependency_overrides[gov_factory.make_approval_service] = _provide_approval
    app.dependency_overrides[gov_factory.make_policy_evaluator] = _provide_evaluator
    app.dependency_overrides[_require_actor] = _actor_dep
    app.dependency_overrides[_require_admin] = _admin_dep

    return app, {
        "policy_svc": policy_svc,
        "approval_svc": approval_svc,
        "evaluator": evaluator,
        "guard": guard,
        "policy_repo": policy_repo,
        "approval_repo": approval_repo,
        "audit": audit,
    }


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


# ── /v1/policies CRUD ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_policy_returns_201_and_persists() -> None:
    app, ctx = _build_test_app()
    async with _client(app) as c:
        resp = await c.post(
            "/v1/policies",
            json={
                "subject_type": "role",
                "subject_ref": "workspace_member",
                "action_pattern": "tool:execute:reverse",
                "effect": "deny",
                "priority": 50,
            },
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["effect"] == "deny"
    assert body["priority"] == 50
    assert body["action_pattern"] == "tool:execute:reverse"
    # Persisted in repo
    listed = await ctx["policy_repo"].list_records(tenant_id=TENANT_A)
    assert len(listed) == 1


@pytest.mark.asyncio
async def test_list_policies_returns_all_for_tenant() -> None:
    app, _ctx = _build_test_app()
    async with _client(app) as c:
        # workspace-scoped rule
        await c.post(
            "/v1/policies",
            json={
                "subject_type": "role",
                "subject_ref": "workspace_member",
                "action_pattern": "tool:execute:a",
                "effect": "deny",
                "workspace_id": str(WORKSPACE),
            },
        )
        # tenant-wide rule
        await c.post(
            "/v1/policies",
            json={
                "subject_type": "role",
                "subject_ref": "workspace_member",
                "action_pattern": "tool:execute:b",
                "effect": "allow",
            },
        )

    async with _client(app) as c:
        all_rules = await c.get("/v1/policies")
        assert all_rules.status_code == 200
        body = all_rules.json()
        actions = {r["action_pattern"] for r in body["items"]}
        assert actions == {"tool:execute:a", "tool:execute:b"}


@pytest.mark.asyncio
async def test_update_policy_changes_effect() -> None:
    app, _ctx = _build_test_app()
    async with _client(app) as c:
        created = (
            await c.post(
                "/v1/policies",
                json={
                    "subject_type": "role",
                    "subject_ref": "workspace_member",
                    "action_pattern": "tool:execute:reverse",
                    "effect": "deny",
                },
            )
        ).json()

    rule_id = created["id"]
    async with _client(app) as c:
        patched = await c.patch(
            f"/v1/policies/{rule_id}",
            json={"effect": "allow", "priority": 10},
        )
    assert patched.status_code == 200
    assert patched.json()["effect"] == "allow"
    assert patched.json()["priority"] == 10


@pytest.mark.asyncio
async def test_delete_policy_returns_204() -> None:
    app, _ctx = _build_test_app()
    async with _client(app) as c:
        created = (
            await c.post(
                "/v1/policies",
                json={
                    "subject_type": "role",
                    "subject_ref": "workspace_member",
                    "action_pattern": "tool:execute:reverse",
                    "effect": "deny",
                },
            )
        ).json()
        rule_id = created["id"]

        deleted = await c.delete(f"/v1/policies/{rule_id}")
        assert deleted.status_code == 204

    # Should be gone — GET on the deleted rule returns 404 via the
    # error envelope middleware mapping PolicyNotFound → 404.
    async with _client(app) as c:
        missing = await c.get(f"/v1/policies/{rule_id}")
        assert missing.status_code == 404


# ── PolicyGuard end-to-end (the public behavior) ────────────────────────


@pytest.mark.asyncio
async def test_guard_default_allow_when_no_rules() -> None:
    """No matching rule → allow (default policy)."""
    _app, ctx = _build_test_app()
    guard = ctx["guard"]
    rec = await guard.check(
        actor=_user_actor(), action="tool:execute:reverse", resource={}
    )
    assert rec.effect.value == "allow"
    assert rec.rule_id is None


@pytest.mark.asyncio
async def test_guard_deny_raises_action_denied() -> None:
    app, ctx = _build_test_app()
    async with _client(app) as c:
        await c.post(
            "/v1/policies",
            json={
                "subject_type": "role",
                "subject_ref": "workspace_member",
                "action_pattern": "tool:execute:reverse",
                "effect": "deny",
                "priority": 50,
            },
        )

    guard = ctx["guard"]
    ctx["evaluator"].invalidate(tenant_id=TenantId(TENANT_A))
    with pytest.raises(ActionDeniedError) as ei:
        await guard.check(
            actor=_user_actor(), action="tool:execute:reverse", resource={}
        )
    assert ei.value.code == "ACTION_DENIED"
    assert ei.value.status == 403


@pytest.mark.asyncio
async def test_guard_approval_raises_approval_required() -> None:
    app, ctx = _build_test_app()
    async with _client(app) as c:
        await c.post(
            "/v1/policies",
            json={
                "subject_type": "role",
                "subject_ref": "workspace_member",
                "action_pattern": "tool:execute:clock",
                "effect": "approval",
                "priority": 50,
            },
        )

    guard = ctx["guard"]
    ctx["evaluator"].invalidate(tenant_id=TenantId(TENANT_A))
    with pytest.raises(ApprovalRequiredError) as ei:
        await guard.check(actor=_user_actor(), action="tool:execute:clock", resource={})
    assert ei.value.code == "APPROVAL_REQUIRED"
    assert ei.value.status == 202
    # approval_id surfaced via details so HTTP layer can attach Location
    assert ei.value.details.get("approval_id") is not None


# ── Approvals flow ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_approval_flow_guard_then_admin_approves() -> None:
    """End-to-end: rule = approval → guard.check() raises
    ApprovalRequiredError → admin approves via the approval endpoint →
    the approval row transitions to APPROVED with ``approver_id``.
    """
    app, ctx = _build_test_app()
    async with _client(app) as c:
        await c.post(
            "/v1/policies",
            json={
                "subject_type": "role",
                "subject_ref": "workspace_member",
                "action_pattern": "tool:execute:clock",
                "effect": "approval",
            },
        )

    guard = ctx["guard"]
    ctx["evaluator"].invalidate(tenant_id=TenantId(TENANT_A))

    # First check raises ApprovalRequiredError; an approval row is created.
    with pytest.raises(ApprovalRequiredError) as ei:
        await guard.check(
            actor=_user_actor(),
            action="tool:execute:clock",
            resource={"tool": "clock"},
        )
    approval_id = ei.value.details["approval_id"]

    # Admin approves via the HTTP endpoint.
    async with _client(app) as c:
        resp = await c.post(f"/v1/approvals/{approval_id}/approve")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["approver_id"] == str(ADMIN_ID)
    assert body["decided_at"] is not None


@pytest.mark.asyncio
async def test_cross_tenant_policy_isolation() -> None:
    """Tenant B must not see Tenant A's policies via the HTTP list."""
    app, _ctx = _build_test_app()
    async with _client(app) as c:
        await c.post(
            "/v1/policies",
            json={
                "subject_type": "role",
                "subject_ref": "workspace_member",
                "action_pattern": "tool:execute:reverse",
                "effect": "deny",
            },
        )

    # Switch the actor to tenant B for both placeholders.
    async def _tenant_b_actor() -> ActorContext:
        return ActorContext(
            tenant_id=TenantId(TENANT_B),
            workspace_id=WorkspaceId(WORKSPACE),
            principal_id=UserId(USER_ID),
            roles=frozenset({"workspace_member"}),
        )

    app.dependency_overrides[_require_actor] = _tenant_b_actor
    app.dependency_overrides[_require_admin] = _tenant_b_actor

    async with _client(app) as c:
        resp = await c.get("/v1/policies")
    body = resp.json()
    # Tenant B sees zero policies (Tenant A's rules are isolated).
    assert body["items"] == []


@pytest.mark.asyncio
async def test_list_pending_approvals_filter_by_tenant() -> None:
    app, ctx = _build_test_app()
    # Tenant A creates an approval
    ap_a = await ctx["approval_svc"].create(
        tenant_id=TenantId(TENANT_A),
        requester_id=UserId(USER_ID),
        action="tool:execute:clock",
        resource={"tool": "clock"},
        ttl_seconds=3600,
    )
    # Tenant B creates one too
    await ctx["approval_svc"].create(
        tenant_id=TenantId(TENANT_B),
        requester_id=UserId(USER_ID),
        action="tool:execute:clock",
        resource={"tool": "clock"},
        ttl_seconds=3600,
    )

    # Tenant A is the actor; pending list (default pending_only=True)
    # should show only Tenant A's approval.
    async with _client(app) as c:
        resp = await c.get("/v1/approvals")
    assert resp.status_code == 200
    body = resp.json()
    ids = {item["id"] for item in body["items"]}
    assert str(ap_a.id) in ids
