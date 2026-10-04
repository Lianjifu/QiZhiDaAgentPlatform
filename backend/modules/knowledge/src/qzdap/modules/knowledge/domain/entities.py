"""Admin knowledge aggregates — fields match frontend `features/knowledge/schema.ts`."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Literal, Self
from uuid import UUID

KbStatus = Literal["indexed", "indexing", "paused", "failed"]
DocStatus = Literal["parsed", "parsing", "pending", "failed"]
DocType = Literal["manual", "policy", "meeting", "contract", "faq"]
SourceType = Literal[
    "notion", "slack", "web", "postgres", "s3", "api", "folder", "confluence"
]
SourceStatus = Literal["online", "syncing", "error", "paused"]
TaskStatus = Literal["pending", "running", "success", "failed", "paused"]
TaskKind = Literal["index", "reindex", "rebuild"]
EvalStatus = Literal["pass", "fail", "skipped"]
KbScope = Literal["公开", "部门", "个人"]
Tone = Literal["brand", "info", "success", "warn", "danger", "purple"]
RetrievalMode = Literal["hybrid", "semantic", "keyword"]
KnowledgeKind = Literal["制度", "项目", "指南"]

KB_STATUSES = frozenset({"indexed", "indexing", "paused", "failed"})
DOC_STATUSES = frozenset({"parsed", "parsing", "pending", "failed"})
DOC_TYPES = frozenset({"manual", "policy", "meeting", "contract", "faq"})
SOURCE_TYPES = frozenset(
    {"notion", "slack", "web", "postgres", "s3", "api", "folder", "confluence"}
)
SOURCE_STATUSES = frozenset({"online", "syncing", "error", "paused"})
TASK_STATUSES = frozenset({"pending", "running", "success", "failed", "paused"})
TASK_KINDS = frozenset({"index", "reindex", "rebuild"})
EVAL_STATUSES = frozenset({"pass", "fail", "skipped"})
KB_SCOPES = frozenset({"公开", "部门", "个人"})
TONES = frozenset({"brand", "info", "success", "warn", "danger", "purple"})
RETRIEVAL_MODES = frozenset({"hybrid", "semantic", "keyword"})
OPEN_SCOPES = frozenset({"公开", "部门"})


def _utcnow() -> datetime:
    return datetime.now(UTC)


def format_last_update(moment: datetime) -> str:
    now = _utcnow()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    seconds = max(0, (now - moment).total_seconds())
    if seconds < 120:
        return "刚刚"
    if seconds < 3600:
        return f"{int(seconds // 60)} 分钟前"
    if seconds < 86400:
        return f"{int(seconds // 3600)} 小时前"
    if seconds < 86400 * 7:
        return f"{int(seconds // 86400)} 天前"
    return moment.astimezone(UTC).strftime("%Y-%m-%d %H:%M")


def next_kb_status(current: str) -> KbStatus:
    if current == "paused":
        return "indexed"
    if current == "failed":
        return "indexing"
    if current == "indexing":
        return "paused"
    return "paused"


def map_doc_kind(doc_type: str) -> KnowledgeKind:
    if doc_type in {"policy", "contract"}:
        return "制度"
    if doc_type in {"meeting", "manual"}:
        return "项目"
    return "指南"


def is_workspace_visible(scope: str) -> bool:
    return scope in OPEN_SCOPES


@dataclass(slots=True)
class DocChunk:
    index: int
    snippet: str
    citations: int = 0
    tokens: int = 0
    heading: str = ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "index": self.index,
            "snippet": self.snippet,
            "citations": self.citations,
            "tokens": self.tokens,
        }
        if self.heading:
            out["heading"] = self.heading
        return out

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Self:
        return cls(
            index=int(raw.get("index") or 0),
            snippet=str(raw.get("snippet") or ""),
            citations=int(raw.get("citations") or 0),
            tokens=int(raw.get("tokens") or 0),
            heading=str(raw.get("heading") or ""),
        )


@dataclass(slots=True)
class KnowledgeBase:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    name: str
    description: str
    owner: str
    scope: KbScope
    status: KbStatus
    updated_at: datetime
    created_at: datetime
    doc_count: int = 0
    vector_count: int = 0
    tags: list[str] = field(default_factory=list)
    tone: Tone = "info"
    eval_hit_rate: float = 0.0
    bound_sources: list[str] = field(default_factory=list)
    retrieval: RetrievalMode = "hybrid"
    top_k: int = 8

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        name: str,
        description: str,
        owner: str,
        scope: KbScope,
        bound_sources: list[str],
        retrieval: RetrievalMode,
        top_k: int,
    ) -> Self:
        now = _utcnow()
        return cls(
            id=id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name.strip() or "未命名知识库",
            description=description,
            owner=owner,
            scope=scope if scope in KB_SCOPES else "部门",
            status="indexing",
            updated_at=now,
            created_at=now,
            bound_sources=list(bound_sources),
            retrieval=retrieval if retrieval in RETRIEVAL_MODES else "hybrid",
            top_k=max(1, min(int(top_k or 8), 50)),
        )

    def toggle_status(self) -> Self:
        return replace(self, status=next_kb_status(self.status), updated_at=_utcnow())

    def pause(self) -> Self:
        return replace(self, status="paused", updated_at=_utcnow())

    def rebuild(self) -> Self:
        return replace(self, status="indexing", updated_at=_utcnow())

    def to_admin_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "owner": self.owner,
            "scope": self.scope,
            "status": self.status,
            "docCount": self.doc_count,
            "vectorCount": self.vector_count,
            "updatedAt": format_last_update(self.updated_at),
            "tags": list(self.tags),
            "tone": self.tone,
            "evalHitRate": self.eval_hit_rate,
        }


@dataclass(slots=True)
class IndexedChunk:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    kb_id: UUID
    doc_id: UUID
    ordinal: int
    content: str
    heading: str = ""
    tokens: int = 0


@dataclass(slots=True)
class KnowledgeDoc:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    name: str
    type: DocType
    kb_id: UUID
    status: DocStatus
    updated_at: datetime
    created_at: datetime
    source_id: str | None = None
    size_kb: int = 0
    chunks: int = 0
    citations: int = 0
    chunks_preview: list[DocChunk] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        kb_id: UUID,
        name: str,
        doc_type: str,
        source_id: str | None,
        chunks_preview: list[DocChunk],
        chunk_count: int,
        size_kb: int,
    ) -> Self:
        now = _utcnow()
        kind: DocType = doc_type if doc_type in DOC_TYPES else "manual"  # type: ignore[assignment]
        return cls(
            id=id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name.strip() or "未命名文档",
            type=kind,
            kb_id=kb_id,
            status="parsed",
            updated_at=now,
            created_at=now,
            source_id=source_id,
            size_kb=max(0, size_kb),
            chunks=chunk_count,
            chunks_preview=list(chunks_preview),
        )

    def to_admin_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": str(self.id),
            "name": self.name,
            "type": self.type,
            "kbId": str(self.kb_id),
            "status": self.status,
            "sizeKb": self.size_kb,
            "chunks": self.chunks,
            "updatedAt": format_last_update(self.updated_at),
            "citations": self.citations,
        }
        if self.source_id:
            out["sourceId"] = self.source_id
        if self.chunks_preview:
            out["chunksPreview"] = [item.to_dict() for item in self.chunks_preview]
        return out

    def to_catalog_dict(self, kb: KnowledgeBase) -> dict[str, Any]:
        excerpt = ""
        if self.chunks_preview:
            first = self.chunks_preview[0]
            excerpt = first.snippet or first.heading
        return {
            "id": str(self.id),
            "title": self.name,
            "kind": map_doc_kind(self.type),
            "description": kb.description or self.name,
            "owner": kb.owner or "知识管理",
            "updated": format_last_update(self.updated_at),
            "tags": list(kb.tags) if kb.tags else [self.type],
            "excerpt": excerpt or kb.description or "暂无摘要",
        }


@dataclass(slots=True)
class KnowledgeSource:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    name: str
    type: SourceType
    status: SourceStatus
    updated_at: datetime
    created_at: datetime
    schedule: str = ""
    item_count: int = 0
    last_error: str = ""

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        name: str,
        type: SourceType,
        schedule: str,
    ) -> Self:
        now = _utcnow()
        source_type: SourceType = type if type in SOURCE_TYPES else "api"
        return cls(
            id=id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name.strip() or "未命名数据源",
            type=source_type,
            status="online",
            updated_at=now,
            created_at=now,
            schedule=schedule,
        )

    def to_admin_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": str(self.id),
            "name": self.name,
            "type": self.type,
            "status": self.status,
            "lastSync": format_last_update(self.updated_at),
            "schedule": self.schedule,
            "itemCount": self.item_count,
        }
        if self.last_error:
            out["lastError"] = self.last_error
        return out


@dataclass(slots=True)
class KnowledgeTask:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    name: str
    kind: TaskKind
    kb_id: UUID
    status: TaskStatus
    updated_at: datetime
    created_at: datetime
    source_id: str | None = None
    progress: int = 0
    items: int = 0
    duration: str = ""
    failure_reason: str = ""

    def to_admin_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": str(self.id),
            "name": self.name,
            "kind": self.kind,
            "kbId": str(self.kb_id),
            "status": self.status,
            "progress": self.progress,
            "items": self.items,
            "startedAt": format_last_update(self.created_at),
            "duration": self.duration,
        }
        if self.source_id:
            out["sourceId"] = self.source_id
        if self.failure_reason:
            out["failureReason"] = self.failure_reason
        return out


@dataclass(slots=True)
class KnowledgeEvalCase:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    name: str
    query: str
    expected_kb: str
    actual_kb: str
    status: EvalStatus
    latency: int
    mrr: float
    updated_at: datetime
    created_at: datetime

    def to_admin_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "query": self.query,
            "expectedKb": self.expected_kb,
            "actualKb": self.actual_kb,
            "status": self.status,
            "latency": self.latency,
            "mrr": self.mrr,
        }


__all__ = [
    "DocChunk",
    "IndexedChunk",
    "KnowledgeBase",
    "KnowledgeDoc",
    "KnowledgeEvalCase",
    "KnowledgeSource",
    "KnowledgeTask",
    "format_last_update",
    "is_workspace_visible",
    "map_doc_kind",
    "next_kb_status",
]
