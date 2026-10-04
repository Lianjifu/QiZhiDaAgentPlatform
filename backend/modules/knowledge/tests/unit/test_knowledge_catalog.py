"""Knowledge catalog unit tests — admin KBs + RAG retrieval."""

from __future__ import annotations

import hashlib
import math
from uuid import UUID

import pytest

from qzdap.modules.knowledge.application.ports import (
    KnowledgeCatalogRepository,
    VectorHit,
    VectorSearchPort,
)
from qzdap.modules.knowledge.application.services import KnowledgeService
from qzdap.modules.knowledge.domain.entities import (
    DocChunk,
    IndexedChunk,
    KnowledgeBase,
    KnowledgeDoc,
    KnowledgeEvalCase,
    KnowledgeSource,
    KnowledgeTask,
)
from qzdap.modules.knowledge.domain.errors import KnowledgeNotFound

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
        items: list[IndexedChunk],
        embeddings: list[list[float]],
        package_name: str,
        asset_name: str,
    ) -> None:
        _ = tenant_id, workspace_id
        for chunk, vector in zip(items, embeddings, strict=True):
            self.items[chunk.id] = (
                list(vector),
                {
                    "workspace_id": str(chunk.workspace_id),
                    "kb_id": str(chunk.kb_id),
                    "doc_id": str(chunk.doc_id),
                    "ordinal": str(chunk.ordinal),
                    "content": chunk.content,
                    "heading": chunk.heading,
                    "package_name": package_name,
                    "asset_name": asset_name,
                },
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
        kb_ids: tuple[str, ...] = (),
    ) -> list[VectorHit]:
        _ = tenant_id
        allowed = set(kb_ids)
        scored: list[VectorHit] = []
        qn = math.sqrt(sum(value * value for value in query_embedding)) or 1.0
        for chunk_id, (vector, payload) in self.items.items():
            if payload["workspace_id"] != str(workspace_id):
                continue
            if allowed and payload["kb_id"] not in allowed:
                continue
            vn = math.sqrt(sum(value * value for value in vector)) or 1.0
            score = sum(a * b for a, b in zip(query_embedding, vector, strict=True)) / (qn * vn)
            scored.append(
                VectorHit(
                    chunk_id=chunk_id,
                    score=float(score),
                    kb_id=payload["kb_id"],
                    doc_id=payload["doc_id"],
                    ordinal=int(payload["ordinal"]),
                    content=payload["content"],
                    heading=payload["heading"],
                    asset_name=payload["asset_name"],
                    package_name=payload["package_name"],
                )
            )
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]


class InMemoryCatalog(KnowledgeCatalogRepository):
    def __init__(self) -> None:
        self.kbs: dict[UUID, KnowledgeBase] = {}
        self.docs: dict[UUID, KnowledgeDoc] = {}
        self.sources: dict[UUID, KnowledgeSource] = {}
        self.tasks: dict[UUID, KnowledgeTask] = {}
        self.evals: dict[UUID, KnowledgeEvalCase] = {}
        self.chunks: dict[UUID, IndexedChunk] = {}

    async def add_kb(self, kb: KnowledgeBase) -> None:
        self.kbs[kb.id] = kb

    async def get_kb(self, kb_id: UUID) -> KnowledgeBase | None:
        return self.kbs.get(kb_id)

    async def list_kbs(self, workspace_id: UUID) -> list[KnowledgeBase]:
        return [item for item in self.kbs.values() if item.workspace_id == workspace_id]

    async def update_kb(self, kb: KnowledgeBase) -> None:
        self.kbs[kb.id] = kb

    async def add_doc(self, doc: KnowledgeDoc) -> None:
        self.docs[doc.id] = doc

    async def update_doc(self, doc: KnowledgeDoc) -> None:
        self.docs[doc.id] = doc

    async def get_doc(self, doc_id: UUID) -> KnowledgeDoc | None:
        return self.docs.get(doc_id)

    async def list_docs(self, workspace_id: UUID) -> list[KnowledgeDoc]:
        return [item for item in self.docs.values() if item.workspace_id == workspace_id]

    async def add_source(self, source: KnowledgeSource) -> None:
        self.sources[source.id] = source

    async def list_sources(self, workspace_id: UUID) -> list[KnowledgeSource]:
        return [item for item in self.sources.values() if item.workspace_id == workspace_id]

    async def list_tasks(self, workspace_id: UUID) -> list[KnowledgeTask]:
        return [item for item in self.tasks.values() if item.workspace_id == workspace_id]

    async def list_eval_cases(self, workspace_id: UUID) -> list[KnowledgeEvalCase]:
        return [item for item in self.evals.values() if item.workspace_id == workspace_id]

    async def replace_chunks(self, *, doc_id: UUID, chunks: list[IndexedChunk]) -> list[UUID]:
        stale = [cid for cid, chunk in list(self.chunks.items()) if chunk.doc_id == doc_id]
        for cid in stale:
            del self.chunks[cid]
        for chunk in chunks:
            self.chunks[chunk.id] = chunk
        return stale

    async def list_chunks(
        self, workspace_id: UUID, *, kb_ids: tuple[UUID, ...] = ()
    ) -> list[IndexedChunk]:
        allowed = set(kb_ids)
        return [
            chunk
            for chunk in self.chunks.values()
            if chunk.workspace_id == workspace_id and (not allowed or chunk.kb_id in allowed)
        ]

    async def count_chunks(self, kb_id: UUID) -> int:
        return sum(1 for chunk in self.chunks.values() if chunk.kb_id == kb_id)


def _svc() -> tuple[KnowledgeService, InMemoryCatalog, InMemoryVectors]:
    catalog = InMemoryCatalog()
    vectors = InMemoryVectors()
    return (
        KnowledgeService(catalog, embedding=HashEmbedding(), vectors=vectors, chunk_size=40, chunk_overlap=8),
        catalog,
        vectors,
    )


@pytest.mark.asyncio
async def test_create_list_toggle_and_batch() -> None:
    svc, _catalog, _vectors = _svc()
    created = await svc.create_kb(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "产品手册", "description": "对外说明", "scope": "公开"},
        owner="产品团队",
    )
    assert created["status"] == "indexing"
    listed = await svc.list_kbs(workspace_id=WORKSPACE)
    assert len(listed) == 1
    kb_id = UUID(created["id"])
    toggled = await svc.toggle_kb_status(kb_id)
    assert toggled["status"] == "paused"
    batch = await svc.batch_kbs(ids=[str(kb_id)], action="rebuild")
    assert batch["affected"] == 1
    again = await svc.get_kb(kb_id)
    assert again["status"] == "indexed"


@pytest.mark.asyncio
async def test_catalog_only_indexed_visible_parsed_docs() -> None:
    svc, catalog, _vectors = _svc()
    created = await svc.create_kb(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "员工手册", "description": "人事制度", "scope": "部门"},
        owner="人力资源",
    )
    kb_id = UUID(created["id"])
    kb = await catalog.get_kb(kb_id)
    assert kb is not None
    await catalog.update_kb(kb.pause())
    hidden_doc = KnowledgeDoc(
        id=UUID("00000000-0000-0000-0000-0000000000aa"),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        name="隐藏文档.pdf",
        type="policy",
        kb_id=kb_id,
        status="parsed",
        updated_at=kb.updated_at,
        created_at=kb.created_at,
        chunks_preview=[DocChunk(index=1, snippet="年假规则")],
    )
    await catalog.add_doc(hidden_doc)
    assert await svc.list_catalog(workspace_id=WORKSPACE) == []

    open_kb = await svc.create_kb(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "术语表", "description": "业务名词", "scope": "公开"},
        owner="产品团队",
    )
    ingested = await svc.ingest_doc(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"kbId": open_kb["id"], "name": "业务术语.md", "type": "faq", "content": "智能体即 Agent"},
    )
    catalog_rows = await svc.list_catalog(workspace_id=WORKSPACE)
    assert len(catalog_rows) == 1
    assert catalog_rows[0]["title"] == "业务术语.md"
    asked = await svc.ask(workspace_id=WORKSPACE, question="智能体", tenant_id=TENANT)
    assert asked["resourceId"] == ingested["id"]


@pytest.mark.asyncio
async def test_create_source_and_missing_kb() -> None:
    svc, _catalog, _vectors = _svc()
    source = await svc.create_source(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "Notion 空间", "type": "notion", "schedule": "每小时"},
    )
    assert source["status"] == "online"
    with pytest.raises(KnowledgeNotFound):
        await svc.get_kb(UUID("00000000-0000-0000-0000-000000000099"))


@pytest.mark.asyncio
async def test_rag_search_ranks_semantic_match() -> None:
    svc, _catalog, vectors = _svc()
    kb = await svc.create_kb(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={
            "name": "客服 FAQ",
            "description": "常见问题",
            "scope": "部门",
            "retrieval": "semantic",
            "topK": 3,
        },
        owner="客服",
    )
    await svc.ingest_doc(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"kbId": kb["id"], "name": "退款.md", "content": "7 天内订单如何退款 退货"},
    )
    await svc.ingest_doc(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"kbId": kb["id"], "name": "发票.md", "content": "如何开增值税专票 发票抬头"},
    )
    assert vectors.items
    hits = await svc.search_query(
        tenant_id=TENANT, workspace_id=WORKSPACE, query="订单退款", top_k=2
    )
    assert hits
    assert "退款" in hits[0]["content"] or hits[0]["asset_name"] == "退款.md"


@pytest.mark.asyncio
async def test_keyword_mode_ignores_unrelated_vector_neighbor() -> None:
    svc, catalog, _vectors = _svc()
    kb = await svc.create_kb(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "制度", "description": "规章", "scope": "公开", "retrieval": "keyword"},
        owner="法务",
    )
    await svc.ingest_doc(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"kbId": kb["id"], "name": "考勤.md", "content": "迟到三次记过"},
    )
    stored = await catalog.get_kb(UUID(kb["id"]))
    assert stored is not None
    hits = await svc.search_query(
        tenant_id=TENANT, workspace_id=WORKSPACE, query="迟到", top_k=3
    )
    assert hits
    assert "迟到" in hits[0]["content"]
