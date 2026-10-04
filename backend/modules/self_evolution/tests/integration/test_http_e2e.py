"""End-to-end HTTP tests for the self-evolution router.

Exercises the full request → DTO → service → response path via
``httpx.ASGITransport`` (no real network). In-memory ports from
``unit/_self_evolution_in_memory.py`` (registered under the
``_self_evolution_unit_in_memory`` alias by the root conftest) are wired
through ``app.dependency_overrides`` for the ``make_evolution_service``
factory; the auth placeholders ``_require_actor`` / ``_require_admin``
are overridden to return a per-test actor.

Complements ``tests/integration/test_sql_evolution_candidates.py``
(Postgres persistence) by exercising the HTTP layer + business
orchestration end-to-end.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from _self_evolution_unit_in_memory import (
    CapturingEventPublisher,
    FixedClock,
    InMemoryEvolutionCandidateRepository,
    Uuid4IdGenerator,
)
from qzdap_http.error_envelope import error_envelope_middleware
from qzdap_schema.ids import TenantId, UserId, WorkspaceId
from qzdap_vault.actor import ActorContext
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.middleware.base import BaseHTTPMiddleware

from qzdap.modules.self_evolution.adapter.http.factory import (
    make_evolution_service,
)
from qzdap.modules.self_evolution.adapter.http.router import (
    _require_actor,
    _require_admin,
)
from qzdap.modules.self_evolution.adapter.http.router import (
    router as evolution_router,
)
from qzdap.modules.self_evolution.application.evolution_service import (
    EvolutionCandidateService,
)

# ── Constants ──────────────────────────────────────────────────────────


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


# ── App builder ────────────────────────────────────────────────────────


def _build_test_app() -> tuple[FastAPI, dict]:
    """Wire the self-evolution router against in-memory ports."""
    repo = InMemoryEvolutionCandidateRepository()
    clock = FixedClock()
    ids = Uuid4IdGenerator()
    publisher = CapturingEventPublisher()

    svc = EvolutionCandidateService(
        repo=repo,
        clock=clock,
        ids=ids,
        apply_guard=_DirectApplyGuardStub(),
        publisher=publisher,
        default_ttl_seconds=3600,
    )

    app = FastAPI(title="self-evolution-e2e")
    # Mirror the production wiring: error envelope middleware converts
    # AppError subclasses (EvolveCandidateNotFound → 404, AlreadyDecided →
    # 409, SignerMustDiffer → 403, InvalidEvolveCandidate → 422) into
    # JSON envelopes so the test app behaves like the real app.
    app.add_middleware(
        BaseHTTPMiddleware,
        dispatch=error_envelope_middleware,  # type: ignore[arg-type]
    )
    app.include_router(evolution_router)

    async def _provide_svc() -> EvolutionCandidateService:
        return svc

    async def _admin_dep() -> ActorContext:
        return _admin_actor()

    async def _actor_dep() -> ActorContext:
        return _user_actor()

    app.dependency_overrides[make_evolution_service] = _provide_svc
    app.dependency_overrides[_require_actor] = _actor_dep
    app.dependency_overrides[_require_admin] = _admin_dep

    return app, {
        "svc": svc,
        "repo": repo,
        "clock": clock,
        "publisher": publisher,
    }


class _DirectApplyGuardStub:
    """Stub that mirrors the production :class:`DirectApplyGuard`
    contract but adds a recorded ``apply`` call list for assertions.
    """

    def __init__(self) -> None:
        self.applies: list[tuple[UUID, UUID, str]] = []

    async def apply(self, *, tenant_id: TenantId, candidate) -> object:
        from qzdap.modules.self_evolution.application.apply_guard import (
            ApplyOutcome,
        )

        self.applies.append(
            (UUID(str(tenant_id)), UUID(str(candidate.id)), candidate.kind.value)
        )
        return ApplyOutcome(
            candidate_id=candidate.id,
            kind=candidate.kind,
            summary={
                "mode": "direct",
                "tenant_id": str(tenant_id),
                "kind": candidate.kind.value,
                "fingerprint": candidate.fingerprint,
            },
        )


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


# ── /v1/evolve/candidates create + read ────────────────────────────────


@pytest.mark.asyncio
async def test_create_candidate_returns_201_and_persists() -> None:
    app, ctx = _build_test_app()
    async with _client(app) as c:
        resp = await c.post(
            "/v1/evolve/candidates",
            json={
                "kind": "memory_promote",
                "payload": {"memory_id": "m-1", "target_layer": "working"},
                "confidence": 0.9,
                "trigger_reason": "post-turn:high-confidence",
                "workspace_id": str(WORKSPACE),
            },
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kind"] == "memory_promote"
    assert body["status"] == "pending"
    assert body["confidence"] == 0.9
    assert body["workspace_id"] == str(WORKSPACE)
    assert body["tenant_id"] == str(TENANT_A)
    assert body["requester_id"] == str(ADMIN_ID)
    assert body["fingerprint"]  # sha256 hex, non-empty
    # Persisted
    rows = await ctx["repo"].list_by_status(
        tenant_id=TENANT_A,
        status=__import__(
            "qzdap.modules.self_evolution.domain.value_objects",
            fromlist=["EvolveStatus"],
        ).EvolveStatus.PENDING,
    )
    assert len(rows) == 1
    # Published a created event
    topics = [t for t, _ in ctx["publisher"].events]
    assert any("created" in t for t in topics)


@pytest.mark.asyncio
async def test_create_candidate_validation_422_when_confidence_out_of_range() -> None:
    app, _ctx = _build_test_app()
    async with _client(app) as c:
        resp = await c.post(
            "/v1/evolve/candidates",
            json={
                "kind": "memory_promote",
                "payload": {"k": "v"},
                "confidence": 1.5,
                "trigger_reason": "post-turn",
            },
        )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_create_candidate_validation_422_when_trigger_reason_blank() -> None:
    app, _ctx = _build_test_app()
    async with _client(app) as c:
        resp = await c.post(
            "/v1/evolve/candidates",
            json={
                "kind": "memory_promote",
                "payload": {"k": "v"},
                "confidence": 0.7,
                "trigger_reason": "",
            },
        )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_get_candidate_returns_200_when_present() -> None:
    app, _ctx = _build_test_app()
    async with _client(app) as c:
        created = (
            await c.post(
                "/v1/evolve/candidates",
                json={
                    "kind": "skill_patch",
                    "payload": {"skill_id": "s-1"},
                    "confidence": 0.5,
                    "trigger_reason": "post-turn",
                },
            )
        ).json()
        cand_id = created["id"]

        fetched = await c.get(f"/v1/evolve/candidates/{cand_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == cand_id


@pytest.mark.asyncio
async def test_get_candidate_returns_404_when_missing() -> None:
    app, _ctx = _build_test_app()
    missing = UUID("00000000-0000-0000-0000-000000000404")
    async with _client(app) as c:
        resp = await c.get(f"/v1/evolve/candidates/{missing}")
    assert resp.status_code == 404


# ── Approval + reject flow ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_returns_200_and_transitions_to_approved() -> None:
    app, ctx = _build_test_app()
    # Seed via the service directly so requester_id ≠ approver_id
    # (SignerMustDiffer guard). HTTP approve/apply stays the test subject.
    cand = await ctx["svc"].create(
        tenant_id=TENANT_A,
        kind=__import__(
            "qzdap.modules.self_evolution.domain.value_objects",
            fromlist=["EvolveKind"],
        ).EvolveKind.ROUTING_HINT,
        payload={"route": "r-1"},
        confidence=0.8,
        trigger_reason="post-turn",
        requester_id=USER_ID,
    )
    cand_id = str(cand.id)
    async with _client(app) as c:
        approved = await c.post(f"/v1/evolve/candidates/{cand_id}/approve")
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "approved"
    assert body["approver_id"] == str(ADMIN_ID)
    assert body["reviewed_at"] is not None
    # Published a decided event
    topics = [t for t, _ in ctx["publisher"].events]
    assert any("decided" in t or "approved" in t for t in topics)


@pytest.mark.asyncio
async def test_approve_returns_409_when_already_approved() -> None:
    app, ctx = _build_test_app()
    cand = await ctx["svc"].create(
        tenant_id=TENANT_A,
        kind=__import__(
            "qzdap.modules.self_evolution.domain.value_objects",
            fromlist=["EvolveKind"],
        ).EvolveKind.ROUTING_HINT,
        payload={"route": "r-2"},
        confidence=0.8,
        trigger_reason="post-turn",
        requester_id=USER_ID,
    )
    cand_id = str(cand.id)
    async with _client(app) as c:
        first = await c.post(f"/v1/evolve/candidates/{cand_id}/approve")
        assert first.status_code == 200
        second = await c.post(f"/v1/evolve/candidates/{cand_id}/approve")
    assert second.status_code == 409, second.text


@pytest.mark.asyncio
async def test_reject_returns_200_and_transitions_to_rejected() -> None:
    app, ctx = _build_test_app()
    cand = await ctx["svc"].create(
        tenant_id=TENANT_A,
        kind=__import__(
            "qzdap.modules.self_evolution.domain.value_objects",
            fromlist=["EvolveKind"],
        ).EvolveKind.DREAM,
        payload={"topic": "t-1"},
        confidence=0.3,
        trigger_reason="post-turn",
        requester_id=USER_ID,
    )
    cand_id = str(cand.id)
    async with _client(app) as c:
        rejected = await c.post(
            f"/v1/evolve/candidates/{cand_id}/reject",
            json={"reason": "low confidence"},
        )
    assert rejected.status_code == 200
    body = rejected.json()
    assert body["status"] == "rejected"
    assert body["approver_id"] == str(ADMIN_ID)


# ── Apply flow ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_apply_returns_200_with_summary_after_approval() -> None:
    app, ctx = _build_test_app()
    cand = await ctx["svc"].create(
        tenant_id=TENANT_A,
        kind=__import__(
            "qzdap.modules.self_evolution.domain.value_objects",
            fromlist=["EvolveKind"],
        ).EvolveKind.MEMORY_PROMOTE,
        payload={"memory_id": "m-2"},
        confidence=0.9,
        trigger_reason="post-turn",
        requester_id=USER_ID,
    )
    cand_id = str(cand.id)
    async with _client(app) as c:
        await c.post(f"/v1/evolve/candidates/{cand_id}/approve")
        applied = await c.post(f"/v1/evolve/candidates/{cand_id}/apply")
    assert applied.status_code == 200, applied.text
    body = applied.json()
    assert body["candidate"]["status"] == "applied"
    assert body["candidate"]["applied_at"] is not None
    assert body["applied_summary"]["mode"] == "direct"
    assert body["applied_summary"]["kind"] == "memory_promote"
    # Guard was actually invoked
    assert len(ctx["svc"]._guard.applies) == 1  # type: ignore[attr-defined]
    # Publish an applied event
    topics = [t for t, _ in ctx["publisher"].events]
    assert any("applied" in t for t in topics)


@pytest.mark.asyncio
async def test_apply_returns_409_when_not_yet_approved() -> None:
    app, ctx = _build_test_app()
    cand = await ctx["svc"].create(
        tenant_id=TENANT_A,
        kind=__import__(
            "qzdap.modules.self_evolution.domain.value_objects",
            fromlist=["EvolveKind"],
        ).EvolveKind.MEMORY_PROMOTE,
        payload={"memory_id": "m-3"},
        confidence=0.5,
        trigger_reason="post-turn",
        requester_id=USER_ID,
    )
    cand_id = str(cand.id)
    async with _client(app) as c:
        # No approve → apply should be rejected
        applied = await c.post(f"/v1/evolve/candidates/{cand_id}/apply")
    assert applied.status_code == 409


# ── Cross-tenant isolation ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_tenant_get_returns_404() -> None:
    app, _ctx = _build_test_app()
    async with _client(app) as c:
        created = (
            await c.post(
                "/v1/evolve/candidates",
                json={
                    "kind": "memory_promote",
                    "payload": {"memory_id": "m-4"},
                    "confidence": 0.5,
                    "trigger_reason": "post-turn",
                },
            )
        ).json()
        cand_id = created["id"]

    async def _tenant_b_admin() -> ActorContext:
        return ActorContext(
            tenant_id=TenantId(TENANT_B),
            workspace_id=WorkspaceId(WORKSPACE),
            principal_id=UserId(ADMIN_ID),
            roles=frozenset({"admin"}),
        )

    app.dependency_overrides[_require_actor] = _tenant_b_admin
    app.dependency_overrides[_require_admin] = _tenant_b_admin
    async with _client(app) as c:
        resp = await c.get(f"/v1/evolve/candidates/{cand_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_returns_only_tenant_filtered_items() -> None:
    app, _ctx = _build_test_app()
    async with _client(app) as c:
        await c.post(
            "/v1/evolve/candidates",
            json={
                "kind": "memory_promote",
                "payload": {"memory_id": "m-a"},
                "confidence": 0.5,
                "trigger_reason": "post-turn",
            },
        )

    async def _tenant_b_admin() -> ActorContext:
        return ActorContext(
            tenant_id=TenantId(TENANT_B),
            workspace_id=WorkspaceId(WORKSPACE),
            principal_id=UserId(ADMIN_ID),
            roles=frozenset({"admin"}),
        )

    app.dependency_overrides[_require_actor] = _tenant_b_admin
    app.dependency_overrides[_require_admin] = _tenant_b_admin
    async with _client(app) as c:
        resp = await c.get("/v1/evolve/candidates?status=pending")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


# ── ApplyGuard swap ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_apply_uses_injected_guard_not_default_direct() -> None:
    """If composition swaps the guard (e.g. production swaps to a
    kind-specific guard), the stub guard's ``applies`` list records the
    call and the summary reflects its return value, not the default
    placeholder's. The router must reach into the service's
    ``_apply_guard`` attribute — the wiring layer (composition root)
    owns the substitution.
    """

    class _CountingGuard:
        def __init__(self) -> None:
            self.calls = 0

        async def apply(self, *, tenant_id: TenantId, candidate) -> object:
            from qzdap.modules.self_evolution.application.apply_guard import (
                ApplyOutcome,
            )

            self.calls += 1
            return ApplyOutcome(
                candidate_id=candidate.id,
                kind=candidate.kind,
                summary={"mode": "counted", "calls": self.calls},
            )

    repo = InMemoryEvolutionCandidateRepository()
    publisher = CapturingEventPublisher()
    guard = _CountingGuard()
    svc = EvolutionCandidateService(
        repo=repo,
        clock=FixedClock(),
        ids=Uuid4IdGenerator(),
        apply_guard=guard,
        publisher=publisher,
    )
    # Round-trip through the service directly (the HTTP layer is already
    # covered above — this test pins the swap contract).
    cand = await svc.create(
        tenant_id=TENANT_A,
        kind=__import__(
            "qzdap.modules.self_evolution.domain.value_objects",
            fromlist=["EvolveKind"],
        ).EvolveKind.MEMORY_PROMOTE,
        payload={"memory_id": "m-x"},
        confidence=0.9,
        trigger_reason="post-turn",
    )
    approved = await svc.approve(
        tenant_id=TENANT_A, candidate_id=cand.id, approver_id=ADMIN_ID
    )
    applied, outcome = await svc.apply(tenant_id=TENANT_A, candidate_id=approved.id)
    assert guard.calls == 1
    assert outcome.summary == {"mode": "counted", "calls": 1}
    assert applied.status.value == "applied"
