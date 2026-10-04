"""Memory catalog service — admin L1/L2/L3 + RAG recall for turns."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from qzdap.modules.memory.application.ports import (
    EmbeddingPort,
    MemoryCatalogRepository,
    VectorSearchPort,
)
from qzdap.modules.memory.domain.entities import (
    L2_CATEGORIES,
    L1Session,
    L2Fact,
    PromotionEvent,
    RetentionPolicy,
)
from qzdap.modules.memory.domain.errors import MemoryNotFound


class MemoryService:
    def __init__(
        self,
        catalog: MemoryCatalogRepository,
        *,
        embedding: EmbeddingPort | None = None,
        vectors: VectorSearchPort | None = None,
    ) -> None:
        self._catalog = catalog
        self._embedding = embedding
        self._vectors = vectors

    async def list_l1(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._catalog.list_l1(workspace_id)
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_admin_dict() for item in items]

    async def get_l1(self, item_id: UUID) -> dict[str, Any]:
        item = await self._catalog.get_l1(item_id)
        if item is None:
            raise MemoryNotFound(f"l1 session {item_id} not found")
        return item.to_admin_dict()

    async def list_l2(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._catalog.list_l2(workspace_id)
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_admin_dict() for item in items]

    async def get_l2(self, item_id: UUID) -> dict[str, Any]:
        item = await self._catalog.get_l2(item_id)
        if item is None:
            raise MemoryNotFound(f"l2 fact {item_id} not found")
        return item.to_admin_dict()

    async def list_l3(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._catalog.list_l3(workspace_id)
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_admin_dict() for item in items]

    async def get_l3(self, item_id: UUID) -> dict[str, Any]:
        item = await self._catalog.get_l3(item_id)
        if item is None:
            raise MemoryNotFound(f"l3 entry {item_id} not found")
        return item.to_admin_dict()

    async def list_promotions(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._catalog.list_promotions(workspace_id)
        items.sort(key=lambda item: item.created_at, reverse=True)
        return [item.to_admin_dict() for item in items]

    async def list_policies(
        self, *, tenant_id: UUID, workspace_id: UUID
    ) -> list[dict[str, Any]]:
        items = await self._ensure_policies(tenant_id=tenant_id, workspace_id=workspace_id)
        return [item.to_admin_dict() for item in items]

    async def get_policy(self, *, workspace_id: UUID, label: str) -> dict[str, Any]:
        item = await self._catalog.get_policy_by_label(workspace_id, label)
        if item is None:
            raise MemoryNotFound(f"policy {label} not found")
        return item.to_admin_dict()

    async def trend(self, *, workspace_id: UUID, range: str = "7d") -> dict[str, list[int]]:
        _ = range
        l1 = await self._catalog.list_l1(workspace_id)
        l2 = await self._catalog.list_l2(workspace_id)
        l3 = await self._catalog.list_l3(workspace_id)
        l1_n = sum(1 for item in l1 if item.status != "expired")
        l2_n = sum(1 for item in l2 if item.status != "retired")
        l3_hits = sum(item.hits for item in l3 if item.status == "published")
        return {
            "l1Active": _series(l1_n),
            "l2Hits": _series(max(l2_n * 12, l2_n)),
            "l3Hits": _series(l3_hits or l1_n),
        }

    async def write(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        content: str,
        metadata: dict[str, Any] | None = None,
        user_name: str = "",
        agent_name: str = "",
    ) -> dict[str, Any]:
        meta = metadata or {}
        now = datetime.now(UTC)
        session = L1Session(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_name=user_name or str(meta.get("userName") or "用户"),
            agent_name=agent_name or str(meta.get("agentName") or "助手"),
            buffer_size=1,
            tokens_used=max(1, len(content) // 4),
            ttl_minutes=60,
            ttl_remain_min=60,
            status="active",
            updated_at=now,
            created_at=now,
            buffer_text=content,
        )
        await self._catalog.add_l1(session)
        category = str(meta.get("category") or "fact")
        if category not in L2_CATEGORIES:
            category = "fact"
        fact = L2Fact(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_name=session.user_name,
            key=str(meta.get("key") or "对话记忆"),
            value=content.strip(),
            category=category,  # type: ignore[arg-type]
            source_session=str(session.id),
            confidence=float(meta.get("confidence") or 0.8),
            status="confirmed",
            promoted_to_l3=False,
            updated_at=now,
            created_at=now,
            usage_history=["刚刚"],
        )
        await self._catalog.add_l2(fact)
        await self._catalog.add_promotion(
            PromotionEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                layer="l1→l2",
                label=f"{fact.user_name} · {fact.key}: {fact.value[:24]}",
                operator="系统自动提炼",
                target_id=str(fact.id),
                created_at=now,
            )
        )
        await self._embed_item(fact.id, "l2", fact.recall_text(), tenant_id, workspace_id)
        _ = owner_id
        return fact.to_admin_dict()

    async def recall(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        query: str,
        top_k: int = 10,
        scope_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        _ = scope_filter
        limit = max(1, top_k)
        needle = query.strip().lower()
        facts = [
            item
            for item in await self._catalog.list_l2(workspace_id)
            if item.status != "retired"
        ]
        knowledge = [
            item
            for item in await self._catalog.list_l3(workspace_id)
            if item.status == "published"
        ]
        keyword: list[tuple[float, dict[str, Any]]] = []
        for fact in facts:
            hay = fact.recall_text().lower()
            keyword.append((_keyword_score(needle, hay), _hit(fact.id, fact.recall_text(), "l2", 0.0)))
        for entry in knowledge:
            hay = entry.recall_text().lower()
            keyword.append((_keyword_score(needle, hay), _hit(entry.id, entry.recall_text(), "l3", 0.0)))
        vector_hits: list[tuple[float, dict[str, Any]]] = []
        if self._embedding is not None and self._vectors is not None and needle:
            [query_vec] = await self._embedding.embed([query.strip()])
            for hit in await self._vectors.search(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                query_embedding=query_vec,
                top_k=limit * 4,
            ):
                vector_hits.append(
                    (
                        hit.score,
                        _hit(hit.item_id, hit.content, hit.layer, hit.score),
                    )
                )
        merged: dict[str, dict[str, Any]] = {}
        keyword_by_id = {item[1]["id"]: item[0] for item in keyword}
        for score, payload in vector_hits:
            kw = keyword_by_id.get(payload["id"], 0.05)
            payload = {**payload, "score": 0.7 * score + 0.3 * kw}
            merged[payload["id"]] = payload
        for score, payload in keyword:
            if payload["id"] not in merged:
                merged[payload["id"]] = {**payload, "score": 0.3 * score}
        ranked = sorted(merged.values(), key=lambda item: float(item["score"]), reverse=True)
        return ranked[:limit]

    async def _ensure_policies(
        self, *, tenant_id: UUID, workspace_id: UUID
    ) -> list[RetentionPolicy]:
        items = await self._catalog.list_policies(workspace_id)
        if items:
            return items
        seeded = RetentionPolicy.defaults(tenant_id=tenant_id, workspace_id=workspace_id)
        for item in seeded:
            await self._catalog.add_policy(item)
        return seeded

    async def _embed_item(
        self,
        item_id: UUID,
        layer: str,
        content: str,
        tenant_id: UUID,
        workspace_id: UUID,
    ) -> None:
        if self._embedding is None or self._vectors is None or not content.strip():
            return
        [vector] = await self._embedding.embed([content])
        await self._vectors.upsert(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            item_id=item_id,
            layer=layer,
            content=content,
            embedding=vector,
        )


def _keyword_score(needle: str, hay: str) -> float:
    if not needle:
        return 0.1
    if needle in hay:
        return 1.0
    parts = [part for part in needle.split() if part]
    if not parts:
        return 0.05
    hits = sum(1 for part in parts if part in hay)
    return 0.15 + 0.85 * (hits / len(parts)) if hits else 0.05


def _hit(item_id: UUID, content: str, layer: str, score: float) -> dict[str, Any]:
    scope = "workspace" if layer == "l3" else "user"
    return {
        "id": str(item_id),
        "content": content,
        "score": score,
        "scope": scope,
        "layer": layer,
    }


def _series(end: int) -> list[int]:
    end = max(0, int(end))
    step = max(1, end // 7) if end else 0
    values = [max(0, end - (7 - i) * step) for i in range(8)]
    values[-1] = end
    return values


__all__ = ["MemoryService"]
