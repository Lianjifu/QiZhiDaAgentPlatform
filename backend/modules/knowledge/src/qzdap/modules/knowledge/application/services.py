"""Knowledge catalog service — admin CRUD, ingest, and RAG retrieval."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

from qzdap.modules.knowledge.application.chunker import split_text
from qzdap.modules.knowledge.application.ports import (
    EmbeddingPort,
    KnowledgeCatalogRepository,
    VectorHit,
    VectorSearchPort,
)
from qzdap.modules.knowledge.domain.entities import (
    KB_SCOPES,
    RETRIEVAL_MODES,
    SOURCE_TYPES,
    DocChunk,
    IndexedChunk,
    KnowledgeBase,
    KnowledgeDoc,
    KnowledgeSource,
    is_workspace_visible,
)
from qzdap.modules.knowledge.domain.errors import KnowledgeNotFound


class KnowledgeService:
    def __init__(
        self,
        catalog: KnowledgeCatalogRepository,
        *,
        embedding: EmbeddingPort | None = None,
        vectors: VectorSearchPort | None = None,
        chunk_size: int = 800,
        chunk_overlap: int = 80,
    ) -> None:
        self._catalog = catalog
        self._embedding = embedding
        self._vectors = vectors
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    async def list_kbs(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._catalog.list_kbs(workspace_id)
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_admin_dict() for item in items]

    async def get_kb(self, kb_id: UUID) -> dict[str, Any]:
        kb = await self._require_kb(kb_id)
        return kb.to_admin_dict()

    async def create_kb(
        self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any], owner: str
    ) -> dict[str, Any]:
        scope = body.get("scope") if body.get("scope") in KB_SCOPES else "部门"
        retrieval = body.get("retrieval") if body.get("retrieval") in RETRIEVAL_MODES else "hybrid"
        kb = KnowledgeBase.create(
            id=_parse_id(body.get("id")),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=str(body.get("name") or "未命名知识库"),
            description=str(body.get("description") or ""),
            owner=owner,
            scope=scope,
            bound_sources=[str(item) for item in (body.get("boundSources") or [])],
            retrieval=retrieval,
            top_k=int(body.get("topK") or 8),
        )
        await self._catalog.add_kb(kb)
        return kb.to_admin_dict()

    async def toggle_kb_status(self, kb_id: UUID) -> dict[str, Any]:
        kb = await self._require_kb(kb_id)
        updated = kb.toggle_status()
        await self._catalog.update_kb(updated)
        return updated.to_admin_dict()

    async def batch_kbs(self, *, ids: list[str], action: str) -> dict[str, int]:
        affected = 0
        for raw in ids:
            try:
                kb_id = UUID(str(raw))
            except ValueError:
                continue
            kb = await self._catalog.get_kb(kb_id)
            if kb is None:
                continue
            if action == "pause":
                if kb.status == "paused":
                    continue
                updated = kb.pause()
                await self._catalog.update_kb(updated)
            elif action == "rebuild":
                await self._reindex_kb(kb)
            else:
                affected += 1
                continue
            affected += 1
        return {"affected": affected}

    async def list_docs(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._catalog.list_docs(workspace_id)
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_admin_dict() for item in items]

    async def ingest_doc(
        self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]
    ) -> dict[str, Any]:
        kb_raw = body.get("kbId") or body.get("kb_id")
        if not kb_raw:
            raise KnowledgeNotFound("knowledge base id is required")
        kb = await self._require_kb(_parse_id(kb_raw))
        if kb.tenant_id != tenant_id or kb.workspace_id != workspace_id:
            raise KnowledgeNotFound("knowledge base not in this workspace")
        content = str(body.get("content") or body.get("text") or "").strip()
        name = str(body.get("name") or "未命名文档")
        if not content:
            content = name
        pieces = split_text(content, size=self._chunk_size, overlap=self._chunk_overlap)
        if not pieces:
            pieces = [name]
        preview = [
            DocChunk(index=i + 1, snippet=piece[:240], tokens=max(1, len(piece) // 4))
            for i, piece in enumerate(pieces[:8])
        ]
        existing_id = body.get("id")
        doc_id = _parse_id(existing_id) if existing_id else uuid4()
        existing = await self._catalog.get_doc(doc_id) if existing_id else None
        doc = KnowledgeDoc.create(
            id=doc_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            kb_id=kb.id,
            name=name,
            doc_type=str(body.get("type") or "manual"),
            source_id=str(body.get("sourceId") or "") or None,
            chunks_preview=preview,
            chunk_count=len(pieces),
            size_kb=max(1, len(content.encode("utf-8")) // 1024),
        )
        if existing is None:
            await self._catalog.add_doc(doc)
            kb = replace(kb, doc_count=kb.doc_count + 1)
        else:
            await self._catalog.update_doc(doc)
        await self._embed_and_store(kb, doc, pieces)
        vector_count = await self._catalog.count_chunks(kb.id)
        kb = replace(kb, vector_count=vector_count, status="indexed")
        await self._catalog.update_kb(kb)
        return doc.to_admin_dict()

    async def list_sources(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._catalog.list_sources(workspace_id)
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_admin_dict() for item in items]

    async def create_source(
        self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]
    ) -> dict[str, Any]:
        source_type = body.get("type") if body.get("type") in SOURCE_TYPES else "api"
        source = KnowledgeSource.create(
            id=_parse_id(body.get("id")),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=str(body.get("name") or "未命名数据源"),
            type=source_type,
            schedule=str(body.get("schedule") or ""),
        )
        await self._catalog.add_source(source)
        return source.to_admin_dict()

    async def list_tasks(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._catalog.list_tasks(workspace_id)
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_admin_dict() for item in items]

    async def list_eval_cases(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._catalog.list_eval_cases(workspace_id)
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_admin_dict() for item in items]

    async def list_catalog(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        kbs = {kb.id: kb for kb in await self._catalog.list_kbs(workspace_id)}
        docs = await self._catalog.list_docs(workspace_id)
        out: list[dict[str, Any]] = []
        for doc in docs:
            kb = kbs.get(doc.kb_id)
            if kb is None:
                continue
            if kb.status != "indexed" or not is_workspace_visible(kb.scope):
                continue
            if doc.status != "parsed":
                continue
            out.append(doc.to_catalog_dict(kb))
        return out

    async def ask(
        self, *, workspace_id: UUID, question: str, tenant_id: UUID | None = None
    ) -> dict[str, Any]:
        kbs = await self._catalog.list_kbs(workspace_id)
        tid = tenant_id or (kbs[0].tenant_id if kbs else None)
        if tid is None:
            return {"question": question, "resourceId": ""}
        hits = await self.search_query(
            tenant_id=tid, workspace_id=workspace_id, query=question, top_k=1
        )
        return {"question": question, "resourceId": hits[0]["asset_id"] if hits else ""}

    async def search_query(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        query: str,
        top_k: int,
        package_ids: tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        kbs = {
            kb.id: kb
            for kb in await self._catalog.list_kbs(workspace_id)
            if kb.status == "indexed" and is_workspace_visible(kb.scope)
        }
        allowed = {UUID(str(item)) for item in package_ids if item} if package_ids else None
        if allowed is not None:
            kbs = {kid: kb for kid, kb in kbs.items() if kid in allowed}
        if not kbs:
            return []
        limit = max(1, top_k)
        modes = {kb.retrieval for kb in kbs.values()}
        use_vector = self._embedding is not None and self._vectors is not None and (
            "semantic" in modes or "hybrid" in modes
        )
        keyword_hits = await self._keyword_hits(
            workspace_id=workspace_id, kbs=kbs, query=query, top_k=limit * 4
        )
        vector_hits: list[VectorHit] = []
        if use_vector and query.strip():
            [query_vec] = await self._embedding.embed([query.strip()])
            vector_hits = await self._vectors.search(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                query_embedding=query_vec,
                top_k=limit * 4,
                kb_ids=tuple(str(kid) for kid in kbs),
            )
        merged = _merge_hits(kbs=kbs, vector_hits=vector_hits, keyword_hits=keyword_hits)
        return merged[:limit]

    async def _keyword_hits(
        self,
        *,
        workspace_id: UUID,
        kbs: dict[UUID, KnowledgeBase],
        query: str,
        top_k: int,
    ) -> list[tuple[float, dict[str, Any]]]:
        needle = query.strip().lower()
        docs = {doc.id: doc for doc in await self._catalog.list_docs(workspace_id)}
        chunks = await self._catalog.list_chunks(workspace_id, kb_ids=tuple(kbs))
        scored: list[tuple[float, dict[str, Any]]] = []
        if chunks:
            for chunk in chunks:
                kb = kbs.get(chunk.kb_id)
                doc = docs.get(chunk.doc_id)
                if kb is None or doc is None or doc.status != "parsed":
                    continue
                hay = f"{doc.name} {chunk.heading} {chunk.content}".lower()
                score = _keyword_score(needle, hay)
                scored.append(
                    (
                        score,
                        _hit_dict(
                            chunk_id=str(chunk.id),
                            doc=doc,
                            kb=kb,
                            content=chunk.content or chunk.heading or doc.name,
                            ordinal=chunk.ordinal,
                            score=score,
                        ),
                    )
                )
        else:
            for doc in docs.values():
                kb = kbs.get(doc.kb_id)
                if kb is None or doc.status != "parsed":
                    continue
                snippets = list(doc.chunks_preview) or [
                    DocChunk(index=0, snippet=f"{doc.name} {kb.description}")
                ]
                for chunk in snippets:
                    hay = f"{doc.name} {chunk.heading} {chunk.snippet}".lower()
                    score = _keyword_score(needle, hay)
                    scored.append(
                        (
                            score,
                            _hit_dict(
                                chunk_id=f"{doc.id}:{chunk.index}",
                                doc=doc,
                                kb=kb,
                                content=chunk.snippet or chunk.heading or doc.name,
                                ordinal=chunk.index,
                                score=score,
                            ),
                        )
                    )
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[:top_k]

    async def _reindex_kb(self, kb: KnowledgeBase) -> None:
        docs = [doc for doc in await self._catalog.list_docs(kb.workspace_id) if doc.kb_id == kb.id]
        for doc in docs:
            pieces = [
                f"{item.heading} {item.snippet}".strip()
                for item in doc.chunks_preview
                if (item.heading or item.snippet).strip()
            ]
            if not pieces:
                pieces = [doc.name]
            await self._embed_and_store(kb, doc, pieces)
        vector_count = await self._catalog.count_chunks(kb.id)
        await self._catalog.update_kb(replace(kb, status="indexed", vector_count=vector_count))

    async def _embed_and_store(
        self, kb: KnowledgeBase, doc: KnowledgeDoc, pieces: list[str]
    ) -> None:
        indexed = [
            IndexedChunk(
                id=uuid4(),
                tenant_id=doc.tenant_id,
                workspace_id=doc.workspace_id,
                kb_id=kb.id,
                doc_id=doc.id,
                ordinal=index,
                content=piece,
                tokens=max(1, len(piece) // 4),
            )
            for index, piece in enumerate(pieces)
        ]
        stale = await self._catalog.replace_chunks(doc_id=doc.id, chunks=indexed)
        if self._vectors is not None and stale:
            await self._vectors.delete(stale)
        if self._embedding is None or self._vectors is None or not indexed:
            return
        embeddings = await self._embedding.embed([item.content for item in indexed])
        await self._vectors.upsert(
            tenant_id=doc.tenant_id,
            workspace_id=doc.workspace_id,
            items=indexed,
            embeddings=embeddings,
            package_name=kb.name,
            asset_name=doc.name,
        )

    async def _require_kb(self, kb_id: UUID) -> KnowledgeBase:
        kb = await self._catalog.get_kb(kb_id)
        if kb is None:
            raise KnowledgeNotFound(f"knowledge base {kb_id} not found")
        return kb


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


def _hit_dict(
    *,
    chunk_id: str,
    doc: KnowledgeDoc,
    kb: KnowledgeBase,
    content: str,
    ordinal: int,
    score: float,
) -> dict[str, Any]:
    return {
        "id": chunk_id,
        "asset_id": str(doc.id),
        "package_id": str(kb.id),
        "package_name": kb.name,
        "asset_name": doc.name,
        "content": content,
        "score": score,
        "ordinal": ordinal,
    }


def _merge_hits(
    *,
    kbs: dict[UUID, KnowledgeBase],
    vector_hits: list[VectorHit],
    keyword_hits: list[tuple[float, dict[str, Any]]],
) -> list[dict[str, Any]]:
    keyword_by_id = {item[1]["id"]: item for item in keyword_hits}
    merged: dict[str, dict[str, Any]] = {}
    for hit in vector_hits:
        try:
            kb = kbs[UUID(hit.kb_id)]
        except (ValueError, KeyError):
            continue
        mode = kb.retrieval
        if mode == "keyword":
            continue
        keyword = keyword_by_id.get(str(hit.chunk_id), (0.05, None))[0]
        score = hit.score if mode == "semantic" else (0.7 * hit.score + 0.3 * keyword)
        merged[str(hit.chunk_id)] = {
            "id": str(hit.chunk_id),
            "asset_id": hit.doc_id,
            "package_id": hit.kb_id,
            "package_name": hit.package_name or kb.name,
            "asset_name": hit.asset_name,
            "content": hit.content,
            "score": score,
            "ordinal": hit.ordinal,
        }
    for score, payload in keyword_hits:
        kb = kbs.get(UUID(payload["package_id"]))
        if kb is None:
            continue
        if kb.retrieval == "semantic":
            if payload["id"] not in merged and not vector_hits:
                merged[payload["id"]] = payload
            continue
        if kb.retrieval == "keyword":
            merged[payload["id"]] = {**payload, "score": score}
            continue
        if payload["id"] not in merged:
            merged[payload["id"]] = {**payload, "score": 0.3 * score}
    ranked = list(merged.values())
    ranked.sort(key=lambda item: float(item["score"]), reverse=True)
    return ranked


def _parse_id(raw: Any) -> UUID:
    if raw:
        try:
            return UUID(str(raw))
        except ValueError:
            pass
    return uuid4()


__all__ = ["KnowledgeService"]
