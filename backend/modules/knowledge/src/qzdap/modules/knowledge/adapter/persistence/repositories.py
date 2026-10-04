from __future__ import annotations

from uuid import UUID

from qzdap_persistence.tenant_guard import current_tenant_id
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.knowledge.adapter.persistence.models import (
    KnowledgeBaseORM,
    KnowledgeChunkORM,
    KnowledgeDocORM,
    KnowledgeEvalCaseORM,
    KnowledgeSourceORM,
    KnowledgeTaskORM,
)
from qzdap.modules.knowledge.application.ports import KnowledgeCatalogRepository
from qzdap.modules.knowledge.domain.entities import (
    DocChunk,
    IndexedChunk,
    KnowledgeBase,
    KnowledgeDoc,
    KnowledgeEvalCase,
    KnowledgeSource,
    KnowledgeTask,
)


def _cross_tenant(row: object) -> bool:
    bound = current_tenant_id()
    if bound is None:
        return False
    return getattr(row, "tenant_id", None) != bound


def _kb_to_domain(row: KnowledgeBaseORM) -> KnowledgeBase:
    return KnowledgeBase(
        id=row.id,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        name=row.name,
        description=row.description,
        owner=row.owner,
        scope=row.scope,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        updated_at=row.updated_at,
        created_at=row.created_at,
        doc_count=row.doc_count,
        vector_count=row.vector_count,
        tags=list(row.tags or []),
        tone=row.tone,  # type: ignore[arg-type]
        eval_hit_rate=row.eval_hit_rate,
        bound_sources=list(row.bound_sources or []),
        retrieval=row.retrieval,  # type: ignore[arg-type]
        top_k=row.top_k,
    )


def _apply_kb(row: KnowledgeBaseORM, kb: KnowledgeBase) -> None:
    row.name = kb.name
    row.description = kb.description
    row.owner = kb.owner
    row.scope = kb.scope
    row.status = kb.status
    row.doc_count = kb.doc_count
    row.vector_count = kb.vector_count
    row.tags = list(kb.tags)
    row.tone = kb.tone
    row.eval_hit_rate = kb.eval_hit_rate
    row.bound_sources = list(kb.bound_sources)
    row.retrieval = kb.retrieval
    row.top_k = kb.top_k
    row.updated_at = kb.updated_at


def _doc_to_domain(row: KnowledgeDocORM) -> KnowledgeDoc:
    return KnowledgeDoc(
        id=row.id,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        name=row.name,
        type=row.type,  # type: ignore[arg-type]
        kb_id=row.kb_id,
        status=row.status,  # type: ignore[arg-type]
        updated_at=row.updated_at,
        created_at=row.created_at,
        source_id=row.source_id or None,
        size_kb=row.size_kb,
        chunks=row.chunks,
        citations=row.citations,
        chunks_preview=[DocChunk.from_dict(item) for item in (row.chunks_preview or [])],
    )


def _source_to_domain(row: KnowledgeSourceORM) -> KnowledgeSource:
    return KnowledgeSource(
        id=row.id,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        name=row.name,
        type=row.type,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        updated_at=row.updated_at,
        created_at=row.created_at,
        schedule=row.schedule,
        item_count=row.item_count,
        last_error=row.last_error,
    )


def _task_to_domain(row: KnowledgeTaskORM) -> KnowledgeTask:
    return KnowledgeTask(
        id=row.id,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        name=row.name,
        kind=row.kind,  # type: ignore[arg-type]
        kb_id=row.kb_id,
        status=row.status,  # type: ignore[arg-type]
        updated_at=row.updated_at,
        created_at=row.created_at,
        source_id=row.source_id or None,
        progress=row.progress,
        items=row.items,
        duration=row.duration,
        failure_reason=row.failure_reason,
    )


def _eval_to_domain(row: KnowledgeEvalCaseORM) -> KnowledgeEvalCase:
    return KnowledgeEvalCase(
        id=row.id,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        name=row.name,
        query=row.query,
        expected_kb=row.expected_kb,
        actual_kb=row.actual_kb,
        status=row.status,  # type: ignore[arg-type]
        latency=row.latency,
        mrr=row.mrr,
        updated_at=row.updated_at,
        created_at=row.created_at,
    )


class SqlKnowledgeCatalogRepository(KnowledgeCatalogRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add_kb(self, kb: KnowledgeBase) -> None:
        row = KnowledgeBaseORM(
            id=kb.id,
            tenant_id=kb.tenant_id,
            workspace_id=kb.workspace_id,
            created_at=kb.created_at,
            updated_at=kb.updated_at,
        )
        _apply_kb(row, kb)
        self._s.add(row)

    async def get_kb(self, kb_id: UUID) -> KnowledgeBase | None:
        row = await self._s.get(KnowledgeBaseORM, kb_id)
        if row is None or _cross_tenant(row):
            return None
        return _kb_to_domain(row)

    async def list_kbs(self, workspace_id: UUID) -> list[KnowledgeBase]:
        result = await self._s.execute(
            select(KnowledgeBaseORM).where(KnowledgeBaseORM.workspace_id == workspace_id)
        )
        return [_kb_to_domain(row) for row in result.scalars().all() if not _cross_tenant(row)]

    async def update_kb(self, kb: KnowledgeBase) -> None:
        row = await self._s.get(KnowledgeBaseORM, kb.id)
        if row is None or _cross_tenant(row):
            return
        _apply_kb(row, kb)

    async def add_doc(self, doc: KnowledgeDoc) -> None:
        self._s.add(
            KnowledgeDocORM(
                id=doc.id,
                tenant_id=doc.tenant_id,
                workspace_id=doc.workspace_id,
                kb_id=doc.kb_id,
                name=doc.name,
                type=doc.type,
                status=doc.status,
                source_id=doc.source_id or "",
                size_kb=doc.size_kb,
                chunks=doc.chunks,
                citations=doc.citations,
                chunks_preview=[item.to_dict() for item in doc.chunks_preview],
                created_at=doc.created_at,
                updated_at=doc.updated_at,
            )
        )

    async def get_doc(self, doc_id: UUID) -> KnowledgeDoc | None:
        row = await self._s.get(KnowledgeDocORM, doc_id)
        if row is None or _cross_tenant(row):
            return None
        return _doc_to_domain(row)

    async def update_doc(self, doc: KnowledgeDoc) -> None:
        row = await self._s.get(KnowledgeDocORM, doc.id)
        if row is None or _cross_tenant(row):
            return
        row.name = doc.name
        row.type = doc.type
        row.status = doc.status
        row.source_id = doc.source_id or ""
        row.size_kb = doc.size_kb
        row.chunks = doc.chunks
        row.citations = doc.citations
        row.chunks_preview = [item.to_dict() for item in doc.chunks_preview]
        row.updated_at = doc.updated_at

    async def list_docs(self, workspace_id: UUID) -> list[KnowledgeDoc]:
        result = await self._s.execute(
            select(KnowledgeDocORM).where(KnowledgeDocORM.workspace_id == workspace_id)
        )
        return [_doc_to_domain(row) for row in result.scalars().all() if not _cross_tenant(row)]

    async def add_source(self, source: KnowledgeSource) -> None:
        self._s.add(
            KnowledgeSourceORM(
                id=source.id,
                tenant_id=source.tenant_id,
                workspace_id=source.workspace_id,
                name=source.name,
                type=source.type,
                status=source.status,
                schedule=source.schedule,
                item_count=source.item_count,
                last_error=source.last_error,
                created_at=source.created_at,
                updated_at=source.updated_at,
            )
        )

    async def list_sources(self, workspace_id: UUID) -> list[KnowledgeSource]:
        result = await self._s.execute(
            select(KnowledgeSourceORM).where(KnowledgeSourceORM.workspace_id == workspace_id)
        )
        return [_source_to_domain(row) for row in result.scalars().all() if not _cross_tenant(row)]

    async def list_tasks(self, workspace_id: UUID) -> list[KnowledgeTask]:
        result = await self._s.execute(
            select(KnowledgeTaskORM).where(KnowledgeTaskORM.workspace_id == workspace_id)
        )
        return [_task_to_domain(row) for row in result.scalars().all() if not _cross_tenant(row)]

    async def list_eval_cases(self, workspace_id: UUID) -> list[KnowledgeEvalCase]:
        result = await self._s.execute(
            select(KnowledgeEvalCaseORM).where(KnowledgeEvalCaseORM.workspace_id == workspace_id)
        )
        return [_eval_to_domain(row) for row in result.scalars().all() if not _cross_tenant(row)]

    async def replace_chunks(self, *, doc_id: UUID, chunks: list[IndexedChunk]) -> list[UUID]:
        existing = await self._s.execute(
            select(KnowledgeChunkORM.id).where(KnowledgeChunkORM.doc_id == doc_id)
        )
        stale = [row[0] for row in existing.all()]
        await self._s.execute(delete(KnowledgeChunkORM).where(KnowledgeChunkORM.doc_id == doc_id))
        for chunk in chunks:
            self._s.add(
                KnowledgeChunkORM(
                    id=chunk.id,
                    tenant_id=chunk.tenant_id,
                    workspace_id=chunk.workspace_id,
                    kb_id=chunk.kb_id,
                    doc_id=chunk.doc_id,
                    ordinal=chunk.ordinal,
                    heading=chunk.heading,
                    content=chunk.content,
                    tokens=chunk.tokens,
                )
            )
        return stale

    async def list_chunks(
        self, workspace_id: UUID, *, kb_ids: tuple[UUID, ...] = ()
    ) -> list[IndexedChunk]:
        stmt = select(KnowledgeChunkORM).where(KnowledgeChunkORM.workspace_id == workspace_id)
        if kb_ids:
            stmt = stmt.where(KnowledgeChunkORM.kb_id.in_(kb_ids))
        result = await self._s.execute(stmt)
        out: list[IndexedChunk] = []
        for row in result.scalars().all():
            if _cross_tenant(row):
                continue
            out.append(
                IndexedChunk(
                    id=row.id,
                    tenant_id=row.tenant_id,
                    workspace_id=row.workspace_id,
                    kb_id=row.kb_id,
                    doc_id=row.doc_id,
                    ordinal=row.ordinal,
                    content=row.content,
                    heading=row.heading,
                    tokens=row.tokens,
                )
            )
        return out

    async def count_chunks(self, kb_id: UUID) -> int:
        result = await self._s.execute(
            select(func.count()).select_from(KnowledgeChunkORM).where(KnowledgeChunkORM.kb_id == kb_id)
        )
        return int(result.scalar_one() or 0)
