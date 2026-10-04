"""ApplyGuard protocol + kind-specific guards + dispatching guard.

The :class:`ApplyGuard` is the single chokepoint through which an approved
candidate becomes effective. Production deployments MUST replace
``DirectApplyGuard`` with a guard that targets the specific kind:

- :class:`MemoryWorkingLayerGuard` for ``EvolveKind.MEMORY_PROMOTE`` —
  only writes the working-layer draft store, never the live memory
  table or pgvector index.
- :class:`SkillDraftGuard` for ``EvolveKind.SKILL_PATCH`` — only writes
  draft skill packs, never active installs.
- :class:`RoutingDraftGuard` for ``EvolveKind.ROUTING_HINT`` — only
  writes draft routing policies, never the live routing table.
- :class:`DreamGuard` for ``EvolveKind.DREAM`` — only writes dream
  artifacts (synthetic scenarios, replay corpora) for offline review.

All four guard implementations share a single ``DraftStore`` (an
append-only JSONL file under ``evolution_drafts_dir/<tenant>/<kind>.jsonl``).
The store is *write-only*: applying a candidate never reads from the
canonical surfaces it would mutate. Promotion to the live surface
requires a separate, audited operator workflow that is out of scope
for the self-evolution pipeline.

``DirectApplyGuard`` is the no-op fallback kept for local dev and unit
tests. :class:`KindDispatchingApplyGuard` is the production choice —
it routes each candidate to its kind-specific guard based on
``candidate.kind`` and falls back to ``DirectApplyGuard`` for any
unknown kind so new ``EvolveKind`` values don't crash the apply path.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from qzdap_schema.ids import TenantId

from qzdap.modules.self_evolution.domain.entities import EvolveCandidate
from qzdap.modules.self_evolution.domain.value_objects import EvolveKind

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True, frozen=True)
class ApplyOutcome:
    """Structured summary of an apply operation.

    ``summary`` is a free-form dict so each guard can return its own
    domain-specific detail (e.g. memory working-layer row ids, skill
    draft ids, routing policy versions).
    """

    candidate_id: Any  # EvolveCandidateId; Any to keep dataclass slotted
    kind: EvolveKind
    summary: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ApplyGuard(Protocol):
    """Single chokepoint for ``EvolutionCandidateService.apply()``."""

    async def apply(
        self, *, tenant_id: TenantId, candidate: EvolveCandidate
    ) -> ApplyOutcome: ...


@runtime_checkable
class DraftStore(Protocol):
    """Append-only draft surface shared by the kind-specific guards.

    Each kind writes to a separate file rooted at the store's base
    directory: ``<base>/<tenant_id>/<kind>.jsonl``. Writes are atomic
    (write-temp + rename) so a crash mid-append cannot corrupt an
    existing record.
    """

    async def append(
        self,
        *,
        tenant_id: TenantId,
        kind: EvolveKind,
        record: dict[str, Any],
    ) -> str: ...

    async def read_all(
        self, *, tenant_id: TenantId, kind: EvolveKind
    ) -> list[dict[str, Any]]: ...


class JsonlDraftStore:
    """Filesystem-backed ``DraftStore`` — one JSONL file per (tenant, kind)."""

    def __init__(self, *, base_dir: Path | str) -> None:
        self._base_dir = Path(base_dir)

    async def append(
        self,
        *,
        tenant_id: TenantId,
        kind: EvolveKind,
        record: dict[str, Any],
    ) -> str:
        path = self._path_for(tenant_id, kind)
        record_id = uuid.uuid4().hex
        payload = {"id": record_id, "recorded_at": _utcnow_iso(), **record}
        line = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        await asyncio.to_thread(self._append_sync, path, line)
        return record_id

    async def read_all(
        self, *, tenant_id: TenantId, kind: EvolveKind
    ) -> list[dict[str, Any]]:
        path = self._path_for(tenant_id, kind)
        return await asyncio.to_thread(self._read_all_sync, path)

    def _path_for(self, tenant_id: TenantId, kind: EvolveKind) -> Path:
        tenant_dir = self._base_dir / str(tenant_id)
        tenant_dir.mkdir(parents=True, exist_ok=True)
        return tenant_dir / f"{kind.value}.jsonl"

    @staticmethod
    def _append_sync(path: Path, line: str) -> None:
        # atomic append: write the new line to a sibling tempfile, fsync
        # it, then rename over the target so the existing record is
        # preserved and a crash mid-append cannot corrupt it.
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                # preserve any prior content; rename-replace requires us
                # to write the full payload back
                if path.exists():
                    with path.open("r", encoding="utf-8") as prev:
                        tmp.write(prev.read())
                tmp.write(line)
                tmp.write("\n")
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

    @staticmethod
    def _read_all_sync(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        out: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning(
                        "evolution_drafts: skipping malformed line in %s", path
                    )
        return out


class InMemoryDraftStore:
    """In-memory ``DraftStore`` for unit tests and ephemeral dev runs."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], list[dict[str, Any]]] = {}

    async def append(
        self,
        *,
        tenant_id: TenantId,
        kind: EvolveKind,
        record: dict[str, Any],
    ) -> str:
        record_id = uuid.uuid4().hex
        payload = {"id": record_id, "recorded_at": _utcnow_iso(), **record}
        key = (str(tenant_id), kind.value)
        self._records.setdefault(key, []).append(payload)
        return record_id

    async def read_all(
        self, *, tenant_id: TenantId, kind: EvolveKind
    ) -> list[dict[str, Any]]:
        return list(self._records.get((str(tenant_id), kind.value), []))


# ── Kind-specific guards ──────────────────────────────────────────────────


def _candidate_payload(candidate: EvolveCandidate) -> dict[str, Any]:
    """Snapshot of the fields each kind-specific guard persists."""
    return {
        "candidate_id": str(candidate.id),
        "tenant_id": str(candidate.tenant_id),
        "workspace_id": str(candidate.workspace_id) if candidate.workspace_id else None,
        "kind": candidate.kind.value,
        "payload": dict(candidate.payload),
        "confidence": candidate.confidence,
        "trigger_reason": candidate.trigger_reason,
        "fingerprint": candidate.fingerprint,
        "requester_id": str(candidate.requester_id) if candidate.requester_id else None,
        "approver_id": str(candidate.approver_id) if candidate.approver_id else None,
    }


class MemoryWorkingLayerGuard:
    """Apply ``EvolveKind.MEMORY_PROMOTE`` to the working-layer draft store.

    The working layer is a tenant-scoped JSONL that surfaces only to
    offline / replay tooling — never to live ``MemoryRepository`` or
    ``pgvector``. Promotion to the canonical memory table requires a
    separate audited workflow (out of scope for self-evolution).
    """

    def __init__(self, store: DraftStore) -> None:
        self._store = store

    async def apply(
        self, *, tenant_id: TenantId, candidate: EvolveCandidate
    ) -> ApplyOutcome:
        record_id = await self._store.append(
            tenant_id=tenant_id,
            kind=EvolveKind.MEMORY_PROMOTE,
            record={
                **_candidate_payload(candidate),
                "surface": "memory.working_layer",
                "promotion_target": "draft_only",
            },
        )
        return ApplyOutcome(
            candidate_id=candidate.id,
            kind=candidate.kind,
            summary={
                "mode": "memory_working_layer",
                "tenant_id": str(tenant_id),
                "kind": candidate.kind.value,
                "fingerprint": candidate.fingerprint,
                "draft_record_id": record_id,
                "draft_path": "memory.working_layer",
            },
        )


class SkillDraftGuard:
    """Apply ``EvolveKind.SKILL_PATCH`` to the draft skill-pack store.

    Draft skill packs are JSONL-archived per tenant — promotion to the
    live skill registry requires the existing ``SkillInstalled`` /
    signing + vetter flow, which is *not* triggered here.
    """

    def __init__(self, store: DraftStore) -> None:
        self._store = store

    async def apply(
        self, *, tenant_id: TenantId, candidate: EvolveCandidate
    ) -> ApplyOutcome:
        record_id = await self._store.append(
            tenant_id=tenant_id,
            kind=EvolveKind.SKILL_PATCH,
            record={
                **_candidate_payload(candidate),
                "surface": "skill.draft_packs",
                "promotion_target": "draft_only",
            },
        )
        return ApplyOutcome(
            candidate_id=candidate.id,
            kind=candidate.kind,
            summary={
                "mode": "skill_draft",
                "tenant_id": str(tenant_id),
                "kind": candidate.kind.value,
                "fingerprint": candidate.fingerprint,
                "draft_record_id": record_id,
                "draft_path": "skill.draft_packs",
            },
        )


class RoutingDraftGuard:
    """Apply ``EvolveKind.ROUTING_HINT`` to the draft routing-policy store.

    Draft routing policies are written to the per-tenant JSONL and
    surfaced to offline replay tooling. The live ``RoutingPolicyRepository``
    is never touched — promotion is an operator-driven workflow.
    """

    def __init__(self, store: DraftStore) -> None:
        self._store = store

    async def apply(
        self, *, tenant_id: TenantId, candidate: EvolveCandidate
    ) -> ApplyOutcome:
        record_id = await self._store.append(
            tenant_id=tenant_id,
            kind=EvolveKind.ROUTING_HINT,
            record={
                **_candidate_payload(candidate),
                "surface": "routing.draft_policies",
                "promotion_target": "draft_only",
            },
        )
        return ApplyOutcome(
            candidate_id=candidate.id,
            kind=candidate.kind,
            summary={
                "mode": "routing_draft",
                "tenant_id": str(tenant_id),
                "kind": candidate.kind.value,
                "fingerprint": candidate.fingerprint,
                "draft_record_id": record_id,
                "draft_path": "routing.draft_policies",
            },
        )


class DreamGuard:
    """Apply ``EvolveKind.DREAM`` to the dream-artifact store.

    Dream artifacts (synthetic scenarios, replay corpora, red-team
    batches) are tenant-scoped JSONL records meant for offline
    review — they never enter the live agent runtime path.
    """

    def __init__(self, store: DraftStore) -> None:
        self._store = store

    async def apply(
        self, *, tenant_id: TenantId, candidate: EvolveCandidate
    ) -> ApplyOutcome:
        record_id = await self._store.append(
            tenant_id=tenant_id,
            kind=EvolveKind.DREAM,
            record={
                **_candidate_payload(candidate),
                "surface": "self_evolution.dream_artifacts",
                "promotion_target": "draft_only",
            },
        )
        return ApplyOutcome(
            candidate_id=candidate.id,
            kind=candidate.kind,
            summary={
                "mode": "dream_artifact",
                "tenant_id": str(tenant_id),
                "kind": candidate.kind.value,
                "fingerprint": candidate.fingerprint,
                "draft_record_id": record_id,
                "draft_path": "self_evolution.dream_artifacts",
            },
        )


# ── Dispatcher + fallback ────────────────────────────────────────────────


class KindDispatchingApplyGuard:
    """Route each candidate to its kind-specific guard.

    Unknown ``EvolveKind`` values fall back to :class:`DirectApplyGuard`
    so adding a new enum member never crashes the apply path — the
    candidate will still be marked ``applied`` and the audit trail
    will show ``mode: "direct"`` instead of ``mode: "<kind>"``.
    """

    def __init__(
        self,
        *,
        store: DraftStore,
        memory: MemoryWorkingLayerGuard | None = None,
        skill: SkillDraftGuard | None = None,
        routing: RoutingDraftGuard | None = None,
        dream: DreamGuard | None = None,
        fallback: ApplyGuard | None = None,
    ) -> None:
        self._memory = memory or MemoryWorkingLayerGuard(store)
        self._skill = skill or SkillDraftGuard(store)
        self._routing = routing or RoutingDraftGuard(store)
        self._dream = dream or DreamGuard(store)
        self._fallback = fallback or DirectApplyGuard()

    async def apply(
        self, *, tenant_id: TenantId, candidate: EvolveCandidate
    ) -> ApplyOutcome:
        guard: ApplyGuard
        if candidate.kind is EvolveKind.MEMORY_PROMOTE:
            guard = self._memory
        elif candidate.kind is EvolveKind.SKILL_PATCH:
            guard = self._skill
        elif candidate.kind is EvolveKind.ROUTING_HINT:
            guard = self._routing
        elif candidate.kind is EvolveKind.DREAM:
            guard = self._dream
        else:
            logger.warning(
                "evolution: unknown kind=%s — falling back to DirectApplyGuard",
                candidate.kind,
            )
            guard = self._fallback
        return await guard.apply(tenant_id=tenant_id, candidate=candidate)


class DirectApplyGuard:
    """Placeholder guard — records the apply but does NOT mutate any
    production surface. Used as the default for unknown kinds and in
    unit tests that don't care about the draft side-effect.
    """

    async def apply(
        self, *, tenant_id: TenantId, candidate: EvolveCandidate
    ) -> ApplyOutcome:
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


__all__ = [
    "ApplyGuard",
    "ApplyOutcome",
    "DirectApplyGuard",
    "DraftStore",
    "DreamGuard",
    "InMemoryDraftStore",
    "JsonlDraftStore",
    "KindDispatchingApplyGuard",
    "MemoryWorkingLayerGuard",
    "RoutingDraftGuard",
    "SkillDraftGuard",
]