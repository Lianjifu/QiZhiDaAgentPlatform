"""Unit tests for ApplyGuard + DirectApplyGuard + kind-specific guards."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from qzdap.modules.self_evolution.application.apply_guard import (
    ApplyGuard,
    ApplyOutcome,
    DirectApplyGuard,
    DreamGuard,
    InMemoryDraftStore,
    JsonlDraftStore,
    KindDispatchingApplyGuard,
    MemoryWorkingLayerGuard,
    RoutingDraftGuard,
    SkillDraftGuard,
)
from qzdap.modules.self_evolution.domain.entities import EvolveCandidate
from qzdap.modules.self_evolution.domain.value_objects import EvolveKind

TENANT = UUID(int=1)


def _candidate(
    *,
    kind: EvolveKind = EvolveKind.MEMORY_PROMOTE,
    payload: dict[str, Any] | None = None,
) -> EvolveCandidate:
    return EvolveCandidate.create(
        tenant_id=TENANT,  # type: ignore[arg-type]
        kind=kind,
        payload=payload or {"key": "alpha"},
        confidence=0.7,
        trigger_reason="post-turn",
    )


@pytest.mark.asyncio
async def test_direct_apply_guard_returns_outcome() -> None:
    cand = _candidate()
    outcome = await DirectApplyGuard().apply(
        tenant_id=TENANT,
        candidate=cand,  # type: ignore[arg-type]
    )
    assert isinstance(outcome, ApplyOutcome)
    assert outcome.candidate_id == cand.id
    assert outcome.kind is cand.kind
    assert outcome.summary["mode"] == "direct"
    assert outcome.summary["kind"] == "memory_promote"


@pytest.mark.asyncio
async def test_direct_apply_guard_is_swappable() -> None:
    """ApplyGuard is a Protocol — a custom impl must satisfy it."""

    class _TraceGuard(ApplyGuard):
        def __init__(self) -> None:
            self.calls: list[tuple[UUID, EvolveKind]] = []

        async def apply(  # type: ignore[override]
            self, *, tenant_id: UUID, candidate: EvolveCandidate
        ) -> ApplyOutcome:
            self.calls.append((tenant_id, candidate.kind))
            return ApplyOutcome(
                candidate_id=candidate.id,
                kind=candidate.kind,
                summary={"traced": True},
            )

    guard = _TraceGuard()
    cand = _candidate()
    out = await guard.apply(tenant_id=TENANT, candidate=cand)  # type: ignore[arg-type]
    assert guard.calls == [(TENANT, cand.kind)]
    assert out.summary == {"traced": True}


def test_apply_guard_protocol_recognises_direct() -> None:
    """``isinstance`` on a runtime_checkable Protocol returns True for direct impl."""
    assert isinstance(DirectApplyGuard(), ApplyGuard)


@pytest.mark.asyncio
async def test_apply_outcome_summary_is_isolated_per_call() -> None:
    """The summary dict in one call must not bleed into another."""
    guard = DirectApplyGuard()
    cand1 = _candidate()
    cand2 = _candidate()
    out1 = await guard.apply(tenant_id=TENANT, candidate=cand1)  # type: ignore[arg-type]
    out2 = await guard.apply(tenant_id=TENANT, candidate=cand2)  # type: ignore[arg-type]
    out1.summary["mutated"] = True  # type: ignore[arg-type]
    assert "mutated" not in out2.summary


@pytest.mark.asyncio
async def test_apply_guard_can_raise_apply_guard_rejected() -> None:
    """A guard that vetoes must surface as ``ApplyGuardRejected``."""
    from qzdap.modules.self_evolution.domain.errors import ApplyGuardRejected

    class _VetoGuard(ApplyGuard):
        async def apply(  # type: ignore[override]
            self, *, tenant_id: UUID, candidate: EvolveCandidate
        ) -> ApplyOutcome:
            raise ApplyGuardRejected(
                "draft layer missing",
                code="APPLY_GUARD_REJECTED",
                details={"reason": "draft layer missing"},
            )

    cand = _candidate()
    with pytest.raises(ApplyGuardRejected):
        await _VetoGuard().apply(tenant_id=TENANT, candidate=cand)  # type: ignore[arg-type]


_ = Any  # silence unused-import


# ── InMemoryDraftStore ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_in_memory_draft_store_appends_and_lists() -> None:
    store = InMemoryDraftStore()
    rid = await store.append(
        tenant_id=TENANT,  # type: ignore[arg-type]
        kind=EvolveKind.MEMORY_PROMOTE,
        record={"a": 1},
    )
    assert isinstance(rid, str) and len(rid) >= 8
    rows = await store.read_all(
        tenant_id=TENANT, kind=EvolveKind.MEMORY_PROMOTE  # type: ignore[arg-type]
    )
    assert len(rows) == 1
    assert rows[0]["a"] == 1
    assert rows[0]["id"] == rid
    assert "recorded_at" in rows[0]


@pytest.mark.asyncio
async def test_in_memory_draft_store_isolated_per_kind() -> None:
    store = InMemoryDraftStore()
    await store.append(
        tenant_id=TENANT, kind=EvolveKind.MEMORY_PROMOTE, record={"x": 1}  # type: ignore[arg-type]
    )
    await store.append(
        tenant_id=TENANT, kind=EvolveKind.SKILL_PATCH, record={"y": 2}  # type: ignore[arg-type]
    )
    mem = await store.read_all(
        tenant_id=TENANT, kind=EvolveKind.MEMORY_PROMOTE  # type: ignore[arg-type]
    )
    skl = await store.read_all(
        tenant_id=TENANT, kind=EvolveKind.SKILL_PATCH  # type: ignore[arg-type]
    )
    assert mem[0]["x"] == 1
    assert skl[0]["y"] == 2


# ── JsonlDraftStore ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_jsonl_draft_store_writes_and_reads(tmp_path: Path) -> None:
    store = JsonlDraftStore(base_dir=tmp_path)
    rid = await store.append(
        tenant_id=TENANT, kind=EvolveKind.MEMORY_PROMOTE, record={"k": "v"}  # type: ignore[arg-type]
    )
    path = tmp_path / str(TENANT) / "memory_promote.jsonl"
    assert path.exists()
    rows = await store.read_all(
        tenant_id=TENANT, kind=EvolveKind.MEMORY_PROMOTE  # type: ignore[arg-type]
    )
    assert len(rows) == 1
    assert rows[0]["k"] == "v"
    assert rows[0]["id"] == rid


@pytest.mark.asyncio
async def test_jsonl_draft_store_list_returns_empty_for_missing(tmp_path: Path) -> None:
    store = JsonlDraftStore(base_dir=tmp_path)
    rows = await store.read_all(
        tenant_id=TENANT, kind=EvolveKind.DREAM  # type: ignore[arg-type]
    )
    assert rows == []


@pytest.mark.asyncio
async def test_jsonl_draft_store_appends_are_durable(tmp_path: Path) -> None:
    store = JsonlDraftStore(base_dir=tmp_path)
    for i in range(3):
        await store.append(
            tenant_id=TENANT,
            kind=EvolveKind.ROUTING_HINT,
            record={"i": i},
        )
    rows = await store.read_all(
        tenant_id=TENANT, kind=EvolveKind.ROUTING_HINT  # type: ignore[arg-type]
    )
    assert [r["i"] for r in rows] == [0, 1, 2]


# ── Kind-specific guards ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_memory_working_layer_guard_writes_to_store() -> None:
    store = InMemoryDraftStore()
    guard = MemoryWorkingLayerGuard(store)
    cand = _candidate()
    outcome = await guard.apply(
        tenant_id=TENANT, candidate=cand  # type: ignore[arg-type]
    )
    assert outcome.summary["mode"] == "memory_working_layer"
    assert outcome.summary["draft_path"] == "memory.working_layer"
    rows = await store.read_all(
        tenant_id=TENANT, kind=EvolveKind.MEMORY_PROMOTE  # type: ignore[arg-type]
    )
    assert len(rows) == 1
    assert rows[0]["surface"] == "memory.working_layer"
    assert rows[0]["promotion_target"] == "draft_only"
    assert rows[0]["fingerprint"] == cand.fingerprint


@pytest.mark.asyncio
async def test_skill_draft_guard_writes_to_store() -> None:
    store = InMemoryDraftStore()
    guard = SkillDraftGuard(store)
    cand = _candidate(kind=EvolveKind.SKILL_PATCH, payload={"name": "router"})
    outcome = await guard.apply(
        tenant_id=TENANT, candidate=cand  # type: ignore[arg-type]
    )
    assert outcome.summary["mode"] == "skill_draft"
    assert outcome.summary["draft_path"] == "skill.draft_packs"
    rows = await store.read_all(
        tenant_id=TENANT, kind=EvolveKind.SKILL_PATCH  # type: ignore[arg-type]
    )
    assert rows[0]["surface"] == "skill.draft_packs"
    assert rows[0]["payload"]["name"] == "router"


@pytest.mark.asyncio
async def test_routing_draft_guard_writes_to_store() -> None:
    store = InMemoryDraftStore()
    guard = RoutingDraftGuard(store)
    cand = _candidate(kind=EvolveKind.ROUTING_HINT, payload={"hint": "use-mini"})
    outcome = await guard.apply(
        tenant_id=TENANT, candidate=cand  # type: ignore[arg-type]
    )
    assert outcome.summary["mode"] == "routing_draft"
    rows = await store.read_all(
        tenant_id=TENANT, kind=EvolveKind.ROUTING_HINT  # type: ignore[arg-type]
    )
    assert rows[0]["surface"] == "routing.draft_policies"
    assert rows[0]["payload"]["hint"] == "use-mini"


@pytest.mark.asyncio
async def test_dream_guard_writes_to_store() -> None:
    store = InMemoryDraftStore()
    guard = DreamGuard(store)
    cand = _candidate(kind=EvolveKind.DREAM, payload={"scenario": "edge-x"})
    outcome = await guard.apply(
        tenant_id=TENANT, candidate=cand  # type: ignore[arg-type]
    )
    assert outcome.summary["mode"] == "dream_artifact"
    assert outcome.summary["draft_path"] == "self_evolution.dream_artifacts"
    rows = await store.read_all(tenant_id=TENANT, kind=EvolveKind.DREAM)  # type: ignore[arg-type]
    assert rows[0]["surface"] == "self_evolution.dream_artifacts"


# ── Dispatcher ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatching_guard_routes_by_kind() -> None:
    store = InMemoryDraftStore()
    dispatcher = KindDispatchingApplyGuard(store=store)
    mem = _candidate(kind=EvolveKind.MEMORY_PROMOTE)
    skl = _candidate(kind=EvolveKind.SKILL_PATCH)
    rt = _candidate(kind=EvolveKind.ROUTING_HINT)
    dr = _candidate(kind=EvolveKind.DREAM)
    out_mem = await dispatcher.apply(tenant_id=TENANT, candidate=mem)  # type: ignore[arg-type]
    out_skl = await dispatcher.apply(tenant_id=TENANT, candidate=skl)  # type: ignore[arg-type]
    out_rt = await dispatcher.apply(tenant_id=TENANT, candidate=rt)  # type: ignore[arg-type]
    out_dr = await dispatcher.apply(tenant_id=TENANT, candidate=dr)  # type: ignore[arg-type]
    assert out_mem.summary["mode"] == "memory_working_layer"
    assert out_skl.summary["mode"] == "skill_draft"
    assert out_rt.summary["mode"] == "routing_draft"
    assert out_dr.summary["mode"] == "dream_artifact"
    # each kind landed in its own draft bucket
    assert await store.read_all(tenant_id=TENANT, kind=EvolveKind.MEMORY_PROMOTE) != []  # type: ignore[arg-type]
    assert await store.read_all(tenant_id=TENANT, kind=EvolveKind.SKILL_PATCH) != []  # type: ignore[arg-type]
    assert await store.read_all(tenant_id=TENANT, kind=EvolveKind.ROUTING_HINT) != []  # type: ignore[arg-type]
    assert await store.read_all(tenant_id=TENANT, kind=EvolveKind.DREAM) != []  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_dispatching_guard_falls_back_for_unknown_kind() -> None:
    """A hand-rolled EvolveKind value must not crash the apply path."""
    store = InMemoryDraftStore()
    dispatcher = KindDispatchingApplyGuard(store=store)
    # build a candidate whose .kind is set to a value NOT in the
    # dispatcher's known kinds — simulate by replacing the candidate
    # with a stand-in that is identity-unequal to every known kind
    from types import SimpleNamespace

    class _FakeKind(SimpleNamespace):
        value = "fantasy"

    cand_future = EvolveCandidate.create(
        tenant_id=TENANT,  # type: ignore[arg-type]
        kind=EvolveKind.MEMORY_PROMOTE,
        payload={"k": 1},
        confidence=0.5,
        trigger_reason="future",
    )
    # bypass identity check by monkey-patching the candidate's kind attr
    object.__setattr__(cand_future, "kind", _FakeKind(value="fantasy"))
    outcome = await dispatcher.apply(
        tenant_id=TENANT, candidate=cand_future  # type: ignore[arg-type]
    )
    assert outcome.summary["mode"] == "direct"
    # store untouched
    for k in EvolveKind:
        rows = await store.read_all(tenant_id=TENANT, kind=k)  # type: ignore[arg-type]
        assert rows == []


@pytest.mark.asyncio
async def test_dispatching_guard_uses_injected_guards(tmp_path: Path) -> None:
    store = JsonlDraftStore(base_dir=tmp_path)
    mem = MemoryWorkingLayerGuard(store)

    class _TraceGuard(ApplyGuard):
        def __init__(self) -> None:
            self.calls: list[UUID] = []

        async def apply(  # type: ignore[override]
            self, *, tenant_id: UUID, candidate: EvolveCandidate
        ) -> ApplyOutcome:
            self.calls.append(tenant_id)
            return ApplyOutcome(
                candidate_id=candidate.id,
                kind=candidate.kind,
                summary={"traced": True},
            )

    trace = _TraceGuard()
    dispatcher = KindDispatchingApplyGuard(
        store=store, memory=mem, fallback=trace
    )
    out = await dispatcher.apply(
        tenant_id=TENANT,  # type: ignore[arg-type]
        candidate=_candidate(),
    )
    assert out.summary["mode"] == "memory_working_layer"
    # trace was never called for the routed candidate
    assert trace.calls == []
