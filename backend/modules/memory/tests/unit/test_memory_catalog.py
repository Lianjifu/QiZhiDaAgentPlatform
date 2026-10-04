"""Memory catalog unit tests — admin layers + recall."""

from __future__ import annotations

import hashlib
import math
from uuid import UUID

import pytest

from qzdap.modules.memory.application.ports import (
    MemoryCatalogRepository,
    VectorHit,
    VectorSearchPort,
)
from qzdap.modules.memory.application.services import MemoryService
from qzdap.modules.memory.domain.entities import (
    L1Session,
    L2Fact,
    L3Entry,
    PromotionEvent,
    RetentionPolicy,
)
from qzdap.modules.memory.domain.errors import MemoryNotFound

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
DIM = 32


class HashEmbedding:
    def __init__(self, dim: int = DIM) -> None:
        self._dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self._dim
            for token in text.lower().split():
                digest = hashlib.md5(token.encode("utf-8")).digest()
                bucket = int.from_bytes(digest[:2], "little") % self._dim
                vec[bucket] += 1.0
            norm = math.sqrt(sum(value * value for value in vec)) or 1.0
            out.append([value / norm for value in vec])
        return out


class InMemoryVectors(VectorSearchPort):
    def __init__(self) -> None:
        self.items: dict[UUID, tuple[list[float], dict[str, str]]] = {}

    async def upsert(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        item_id: UUID,
        layer: str,
        content: str,
        embedding: list[float],
    ) -> None:
        _ = tenant_id
        self.items[item_id] = (
            list(embedding),
            {"workspace_id": str(workspace_id), "layer": layer, "content": content},
        )

    async def delete(self, ids: list[UUID]) -> None:
        for item_id in ids:
            self.items.pop(item_id, None)

    async def search(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        query_embedding: list[float],
        top_k: int,
    ) -> list[VectorHit]:
        _ = tenant_id
        qn = math.sqrt(sum(value * value for value in query_embedding)) or 1.0
        scored: list[VectorHit] = []
        for item_id, (vector, payload) in self.items.items():
            if payload["workspace_id"] != str(workspace_id):
                continue
            vn = math.sqrt(sum(value * value for value in vector)) or 1.0
            score = sum(a * b for a, b in zip(query_embedding, vector, strict=True)) / (qn * vn)
            scored.append(
                VectorHit(
                    item_id=item_id,
                    score=float(score),
                    layer=payload["layer"],
                    content=payload["content"],
                )
            )
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]


class InMemoryCatalog(MemoryCatalogRepository):
    def __init__(self) -> None:
        self.l1: dict[UUID, L1Session] = {}
        self.l2: dict[UUID, L2Fact] = {}
        self.l3: dict[UUID, L3Entry] = {}
        self.promotions: dict[UUID, PromotionEvent] = {}
        self.policies: dict[UUID, RetentionPolicy] = {}

    async def add_l1(self, item: L1Session) -> None:
        self.l1[item.id] = item

    async def get_l1(self, item_id: UUID) -> L1Session | None:
        return self.l1.get(item_id)

    async def list_l1(self, workspace_id: UUID) -> list[L1Session]:
        return [item for item in self.l1.values() if item.workspace_id == workspace_id]

    async def update_l1(self, item: L1Session) -> None:
        self.l1[item.id] = item

    async def add_l2(self, item: L2Fact) -> None:
        self.l2[item.id] = item

    async def get_l2(self, item_id: UUID) -> L2Fact | None:
        return self.l2.get(item_id)

    async def list_l2(self, workspace_id: UUID) -> list[L2Fact]:
        return [item for item in self.l2.values() if item.workspace_id == workspace_id]

    async def update_l2(self, item: L2Fact) -> None:
        self.l2[item.id] = item

    async def add_l3(self, item: L3Entry) -> None:
        self.l3[item.id] = item

    async def get_l3(self, item_id: UUID) -> L3Entry | None:
        return self.l3.get(item_id)

    async def list_l3(self, workspace_id: UUID) -> list[L3Entry]:
        return [item for item in self.l3.values() if item.workspace_id == workspace_id]

    async def add_promotion(self, item: PromotionEvent) -> None:
        self.promotions[item.id] = item

    async def list_promotions(self, workspace_id: UUID) -> list[PromotionEvent]:
        return [item for item in self.promotions.values() if item.workspace_id == workspace_id]

    async def add_policy(self, item: RetentionPolicy) -> None:
        self.policies[item.id] = item

    async def list_policies(self, workspace_id: UUID) -> list[RetentionPolicy]:
        return [item for item in self.policies.values() if item.workspace_id == workspace_id]

    async def get_policy_by_label(self, workspace_id: UUID, label: str) -> RetentionPolicy | None:
        for item in self.policies.values():
            if item.workspace_id == workspace_id and item.label == label:
                return item
        return None


def _svc() -> MemoryService:
    return MemoryService(InMemoryCatalog(), embedding=HashEmbedding(), vectors=InMemoryVectors())


@pytest.mark.asyncio
async def test_write_lists_and_policies() -> None:
    svc = _svc()
    written = await svc.write(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        owner_id=TENANT,
        content="喜欢精简答复,3 行内给结论",
        metadata={"key": "答复风格", "userName": "张文佳"},
    )
    assert written["key"] == "答复风格"
    l1 = await svc.list_l1(workspace_id=WORKSPACE)
    l2 = await svc.list_l2(workspace_id=WORKSPACE)
    assert len(l1) == 1
    assert len(l2) == 1
    detail = await svc.get_l2(UUID(l2[0]["id"]))
    assert detail["value"].find("精简") >= 0
    events = await svc.list_promotions(workspace_id=WORKSPACE)
    assert events
    policies = await svc.list_policies(tenant_id=TENANT, workspace_id=WORKSPACE)
    assert len(policies) == 3
    short = await svc.get_policy(workspace_id=WORKSPACE, label="短期记忆")
    assert short["layer"] == "l1"
    trend = await svc.trend(workspace_id=WORKSPACE)
    assert len(trend["l1Active"]) == 8


@pytest.mark.asyncio
async def test_recall_ranks_matching_fact() -> None:
    svc = _svc()
    await svc.write(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        owner_id=TENANT,
        content="订单退款需要 7 天内申请",
        metadata={"key": "退款规则"},
    )
    await svc.write(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        owner_id=TENANT,
        content="发票一律开增值税专票",
        metadata={"key": "发票规则"},
    )
    hits = await svc.recall(
        tenant_id=TENANT, workspace_id=WORKSPACE, query="退款 订单", top_k=2
    )
    assert hits
    assert "退款" in hits[0]["content"]


@pytest.mark.asyncio
async def test_missing_l3_raises() -> None:
    svc = _svc()
    with pytest.raises(MemoryNotFound):
        await svc.get_l3(UUID("00000000-0000-0000-0000-000000000099"))
