"""X14 跨用户泄漏的回归测试 —— 工作区内的记忆必须按用户隔离。

背景：``MemoryService.write`` 过去把 ``owner_id`` 直接丢掉（``_ = owner_id``），
``recall`` 又忽略作用域、只按 workspace 拉全量 → 同工作区的 A 能召回到 B 的记忆。

修复（Memory 决策 #11 / #2）：
- 写入侧持久化 ``owner_id`` → ``admin_memory_l2.user_id``；
- 召回时按 ``user_id`` 过滤（关键词与向量两条路径都过滤）；
- 归属不明（``user_id IS NULL``）的存量行**不召回** —— 宁可不可见，也不要串号。
"""

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

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
USER_A = UUID("00000000-0000-0000-0000-00000000000a")
USER_B = UUID("00000000-0000-0000-0000-00000000000b")
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
    """对齐 pgvector 的 payload 过滤语义：`payload->>'k' = :v`，NULL 永不匹配。"""

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
        user_id: UUID | None = None,
    ) -> None:
        _ = tenant_id
        payload = {
            "workspace_id": str(workspace_id),
            "layer": layer,
            "content": content,
        }
        if user_id is not None:
            payload["user_id"] = str(user_id)
        self.items[item_id] = (list(embedding), payload)

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
        user_id: UUID | None = None,
    ) -> list[VectorHit]:
        _ = tenant_id
        qn = math.sqrt(sum(value * value for value in query_embedding)) or 1.0
        scored: list[VectorHit] = []
        for item_id, (vector, payload) in self.items.items():
            if payload["workspace_id"] != str(workspace_id):
                continue
            if user_id is not None and payload.get("user_id") != str(user_id):
                continue
            vn = math.sqrt(sum(value * value for value in vector)) or 1.0
            score = sum(a * b for a, b in zip(query_embedding, vector, strict=True)) / (
                qn * vn
            )
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

    async def list_l2(
        self, workspace_id: UUID, *, user_id: UUID | None = None
    ) -> list[L2Fact]:
        items = [item for item in self.l2.values() if item.workspace_id == workspace_id]
        if user_id is not None:
            items = [item for item in items if item.user_id == user_id]
        return items

    async def update_l2(self, item: L2Fact) -> None:
        self.l2[item.id] = item

    async def add_l3(self, item: L3Entry) -> None:
        self.l3[item.id] = item

    async def get_l3(self, item_id: UUID) -> L3Entry | None:
        return self.l3.get(item_id)

    async def list_l3(self, workspace_id: UUID) -> list[L3Entry]:
        return [item for item in self.l3.values() if item.workspace_id == workspace_id]

    async def update_l3(self, item: L3Entry) -> None:
        self.l3[item.id] = item

    async def add_promotion(self, item: PromotionEvent) -> None:
        self.promotions[item.id] = item

    async def list_promotions(self, workspace_id: UUID) -> list[PromotionEvent]:
        return [i for i in self.promotions.values() if i.workspace_id == workspace_id]

    async def add_policy(self, item: RetentionPolicy) -> None:
        self.policies[item.id] = item

    async def list_policies(self, workspace_id: UUID) -> list[RetentionPolicy]:
        return [i for i in self.policies.values() if i.workspace_id == workspace_id]

    async def get_policy_by_label(
        self, workspace_id: UUID, label: str
    ) -> RetentionPolicy | None:
        for item in self.policies.values():
            if item.workspace_id == workspace_id and item.label == label:
                return item
        return None


def _svc() -> tuple[MemoryService, InMemoryCatalog]:
    catalog = InMemoryCatalog()
    return (
        MemoryService(catalog, embedding=HashEmbedding(), vectors=InMemoryVectors()),
        catalog,
    )


async def _seed(svc: MemoryService, owner_id: UUID, content: str, key: str) -> None:
    await svc.write(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        owner_id=owner_id,
        content=content,
        metadata={"key": key, "userName": "用户"},
    )


@pytest.mark.asyncio
async def test_write_persists_owner_id() -> None:
    svc, catalog = _svc()
    await _seed(svc, USER_A, "A 的私密内容", "A的偏好")

    stored = list(catalog.l2.values())
    assert len(stored) == 1
    assert stored[0].user_id == USER_A


@pytest.mark.asyncio
async def test_recall_does_not_leak_across_users() -> None:
    svc, _ = _svc()
    await _seed(svc, USER_A, "张三的报销额度是五千元", "报销额度")
    await _seed(svc, USER_B, "李四的客户名单在另一个系统", "客户名单")

    hits_a = await svc.recall(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        query="额度 名单",
        top_k=10,
        user_id=USER_A,
    )
    hits_b = await svc.recall(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        query="额度 名单",
        top_k=10,
        user_id=USER_B,
    )

    assert [h["content"] for h in hits_a] == ["报销额度: 张三的报销额度是五千元"]
    assert [h["content"] for h in hits_b] == ["客户名单: 李四的客户名单在另一个系统"]

    joined_a = " ".join(str(h["content"]) for h in hits_a)
    joined_b = " ".join(str(h["content"]) for h in hits_b)
    assert "李四" not in joined_a
    assert "张三" not in joined_b


@pytest.mark.asyncio
async def test_unowned_memories_are_not_recalled() -> None:
    """决策 #11：存量自动沉淀的记忆归属不明 → 对任何用户都不可见。"""
    svc, catalog = _svc()
    await _seed(svc, USER_A, "有归属的记忆", "有归属")
    orphan = L2Fact(
        id=UUID("00000000-0000-0000-0000-0000000000ff"),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        user_name="用户",
        user_id=None,
        key="无归属",
        value="存量自动沉淀的记忆",
        category="fact",
        source_session="s1",
        confidence=0.8,
        status="confirmed",
        promoted_to_l3=False,
        updated_at=None,  # type: ignore[arg-type]
        created_at=None,  # type: ignore[arg-type]
    )
    await catalog.add_l2(orphan)

    hits = await svc.recall(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        query="记忆 沉淀",
        top_k=10,
        user_id=USER_A,
    )
    assert all("存量自动沉淀" not in str(h["content"]) for h in hits)


@pytest.mark.asyncio
async def test_admin_scope_still_sees_every_user() -> None:
    """管理端是 admin 作用域（user_id 不给 = 不过滤），不应被这次的修复影响。"""
    svc, _ = _svc()
    await _seed(svc, USER_A, "A 的内容", "A")
    await _seed(svc, USER_B, "B 的内容", "B")

    hits = await svc.recall(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        query="内容",
        top_k=10,
    )
    assert len(hits) == 2
