"""SQL integration tests for SqlEvolutionCandidateRepository.

Requires a live Postgres. ``tests/integration/conftest.py`` provides the
``postgres_session`` dependency (testcontainers). Migration 0015 must be
applied via ``alembic upgrade head`` before this test file runs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from qzdap.modules.self_evolution.adapter.persistence.mappers import (
    candidate_to_orm,
)
from qzdap.modules.self_evolution.adapter.persistence.models import (
    EvolveCandidateORM,
)
from qzdap.modules.self_evolution.adapter.persistence.repositories import (
    SqlEvolutionCandidateRepository,
)
from qzdap.modules.self_evolution.domain.entities import EvolveCandidate
from qzdap.modules.self_evolution.domain.value_objects import (
    EvolveKind,
    EvolveStatus,
)

TENANT = UUID(int=1)
TENANT_OTHER = UUID(int=2)
USER_ADMIN = UUID(int=10)


def _candidate(
    *,
    tenant_id: UUID = TENANT,
    confidence: float = 0.7,
    trigger_reason: str = "post-turn",
    payload: dict | None = None,
) -> EvolveCandidate:
    return EvolveCandidate.create(
        tenant_id=tenant_id,  # type: ignore[arg-type]
        kind=EvolveKind.MEMORY_PROMOTE,
        payload=payload if payload is not None else {"k": "v"},
        confidence=confidence,
        trigger_reason=trigger_reason,
    )


@pytest.fixture
def repo(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> SqlEvolutionCandidateRepository:
    return SqlEvolutionCandidateRepository(postgres_session_factory)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_add_and_get_roundtrip(
    repo: SqlEvolutionCandidateRepository,
) -> None:
    cand = _candidate()
    await repo.add(cand)
    fetched = await repo.get(
        tenant_id=TENANT,
        candidate_id=cand.id,  # type: ignore[arg-type]
    )
    assert fetched is not None
    assert fetched.id == cand.id
    assert fetched.kind == cand.kind
    assert fetched.fingerprint == cand.fingerprint
    assert fetched.status is EvolveStatus.PENDING


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_returns_none_for_cross_tenant(
    repo: SqlEvolutionCandidateRepository,
) -> None:
    cand = _candidate()
    await repo.add(cand)
    fetched = await repo.get(
        tenant_id=TENANT_OTHER,
        candidate_id=cand.id,  # type: ignore[arg-type]
    )
    assert fetched is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_persists_status_change(
    repo: SqlEvolutionCandidateRepository,
) -> None:
    cand = _candidate()
    await repo.add(cand)
    approved = cand.approve(approver_id=USER_ADMIN)  # type: ignore[arg-type]
    await repo.update(approved)
    fetched = await repo.get(
        tenant_id=TENANT,
        candidate_id=cand.id,  # type: ignore[arg-type]
    )
    assert fetched is not None
    assert fetched.status is EvolveStatus.APPROVED
    assert fetched.approver_id == USER_ADMIN  # type: ignore[arg-type]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_pending_returns_only_pending_unexpired(
    repo: SqlEvolutionCandidateRepository,
) -> None:
    pending = _candidate(trigger_reason="pending", payload={"k": "pending"})
    approved = _candidate(trigger_reason="approved", payload={"k": "approved"})
    expired = _candidate(trigger_reason="expired", payload={"k": "expired"})
    await repo.add(pending)
    await repo.add(approved)
    await repo.add(expired)
    # transition one to APPROVED
    await repo.update(approved.approve(approver_id=USER_ADMIN))  # type: ignore[arg-type]
    # transition one to a state with expires_at in the past
    past = expired
    # Use repo to expire by direct update
    expired_orm = candidate_to_orm(past)
    async with repo._sf() as session:  # type: ignore[attr-defined]
        row = await session.get(EvolveCandidateORM, expired_orm.id)
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(hours=1)
        await session.commit()

    now = datetime.now(UTC)
    rows = await repo.list_pending(tenant_id=TENANT, now=now, limit=100)
    ids = [r.id for r in rows]
    assert pending.id in ids
    assert approved.id not in ids  # approved is terminal
    assert past.id not in ids  # expired is filtered out


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_by_status_returns_matching_only(
    repo: SqlEvolutionCandidateRepository,
) -> None:
    a = _candidate(trigger_reason="a", payload={"k": "a"})
    b = _candidate(trigger_reason="b", payload={"k": "b"})
    await repo.add(a)
    await repo.add(b)
    await repo.update(a.approve(approver_id=USER_ADMIN))  # type: ignore[arg-type]

    approved = await repo.list_by_status(
        tenant_id=TENANT, status=EvolveStatus.APPROVED, limit=10
    )
    assert {c.id for c in approved} == {a.id}

    pending = await repo.list_by_status(
        tenant_id=TENANT, status=EvolveStatus.PENDING, limit=10
    )
    assert {c.id for c in pending} == {b.id}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unique_fingerprint_blocks_duplicate(
    repo: SqlEvolutionCandidateRepository,
) -> None:
    """The UQ (tenant_id, fingerprint) constraint must dedupe."""
    import sqlalchemy.exc

    cand_a = _candidate(trigger_reason="dup")
    cand_b = EvolveCandidate.create(
        tenant_id=TENANT,  # type: ignore[arg-type]
        kind=EvolveKind.MEMORY_PROMOTE,
        payload=cand_a.payload,
        confidence=0.5,
        trigger_reason="dup",
    )
    # same payload → same fingerprint → second add must fail
    assert cand_a.fingerprint == cand_b.fingerprint
    await repo.add(cand_a)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        await repo.add(cand_b)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_isolated_by_tenant(
    repo: SqlEvolutionCandidateRepository,
) -> None:
    cand = _candidate()
    await repo.add(cand)
    # Cross-tenant update should not affect the row because of the tenant filter
    foreign = EvolveCandidate(
        id=cand.id,  # type: ignore[arg-type]
        tenant_id=TENANT_OTHER,  # type: ignore[arg-type]
        workspace_id=None,
        kind=cand.kind,
        payload=cand.payload,
        confidence=cand.confidence,
        trigger_reason=cand.trigger_reason,
        fingerprint=cand.fingerprint,
        status=EvolveStatus.APPROVED,
        requester_id=cand.requester_id,
        approver_id=USER_ADMIN,
        reviewed_at=datetime.now(UTC),
        applied_at=None,
        correlation_id=None,
        expires_at=cand.expires_at,
        created_at=cand.created_at,
    )
    await repo.update(foreign)
    fetched = await repo.get(
        tenant_id=TENANT,
        candidate_id=cand.id,  # type: ignore[arg-type]
    )
    assert fetched is not None
    assert fetched.status is EvolveStatus.PENDING


_ = candidate_to_orm  # silence unused-import warning
