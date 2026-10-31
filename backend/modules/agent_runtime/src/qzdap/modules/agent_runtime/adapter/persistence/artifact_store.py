"""**产物**（模型生成的输出）的落库与读取 ✓（迁移 0064 ✓）。

⚠️ **为什么需要它** ✓ —— 产物之前只在 ``/tmp/qzdap-mock-artifacts`` ✓
（mock 模式的临时目录 ✓ —— 进程一退就没了 ✓）→ **真实模式没有任何存储** ✓
→ 下载端点一律 404 ✓ → 前端那张产物卡片永远点不开 ✓。

⚠️ **它不是附件** ✓ —— 附件（``copilot_attachments``）是**用户上传的输入** ✓；
产物是**模型生成的输出** ✓（归属 / 生命周期 / 大小边界都不同 ✓）。

⚠️ **有上限** ✓ —— 产物要进 SSE 事件流 ✓（``artifact_ready`` chunk ✓）→
**必须是有界的** ✓（1 MiB ✓ —— 与附件同口径 ✓ —— 前端是整块下载 ✓，
不是流式 ✓）。

⚠️ **租户隔离** ✓ —— 每一次读写都带 ``tenant_id`` / ``workspace_id`` /
``owner_id`` / ``session_id`` ✓（**四道都要对得上** ✓ —— 少一道就是越权 ✗）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.agent_runtime.adapter.persistence.models import SessionArtifactORM

#: 产物的字节上限 ✓ —— 与附件同口径 ✓（1 MiB ✓）。
MAX_ARTIFACT_BYTES = 1024 * 1024

#: 预览长度 ✓ —— 前端直接渲染 ✓（不用下载整个文件 ✓）。
SNIPPET_CHARS = 800

#: 产物类别 ✓ —— 与 chunk schema 的枚举一致 ✓（前端按它选预览方式 ✓）。
ARTIFACT_KINDS: frozenset[str] = frozenset({"markdown", "code", "html", "json", "image", "text"})


def artifact_download_path(session_id: UUID, artifact_id: UUID) -> str:
    """**产物的下载地址** ✓ —— 会话内 ✓（四道作用域在端点里对 ✓）。

    ⚠️ **路径里带会话 id** ✓ —— 下载也是**会话作用域** ✓（不是全局 id ✗✗
    —— 否则拿到 id 就能跨会话取 ✗✗✗）。
    """
    return f"/api/sessions/{session_id}/artifacts/{artifact_id}/content"


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    """一个已落库的产物 ✓。"""

    id: UUID
    name: str
    kind: str
    mime: str
    size_bytes: int
    sha256: str
    snippet: str
    content: bytes


@runtime_checkable
class ArtifactStore(Protocol):
    """产物的落库口 ✓。"""

    async def save(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        session_id: UUID,
        owner_id: UUID,
        turn_id: UUID | None,
        name: str,
        kind: str,
        mime: str,
        content: bytes,
    ) -> ArtifactRecord:
        """落一个产物 ✓ —— 返回它的元数据 ✓（含 ``id` ✓ —— 事件流要带 ✓）。"""
        ...

    async def get(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        session_id: UUID,
        owner_id: UUID,
        artifact_id: UUID,
    ) -> ArtifactRecord | None:
        """取一个产物 ✓ —— **四道作用域都要对得上** ✓（对不上就当没有 ✓）。"""
        ...


def artifact_digest(content: bytes) -> str:
    """产物的 sha256 ✓（与附件同口径 ✓）。"""
    return hashlib.sha256(content).hexdigest()


def artifact_snippet(content: bytes) -> str:
    """前 800 字预览 ✓（按字符切 ✓ —— 不是按字节切 ✓ —— 免得切坏多字节字符 ✓）。"""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("utf-8", errors="replace")
    return text[:SNIPPET_CHARS]


class PostgresArtifactStore:
    """产物落库 ✓（``session_artifacts`` ✓ —— 与轮次同库 ✓）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def save(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        session_id: UUID,
        owner_id: UUID,
        turn_id: UUID | None,
        name: str,
        kind: str,
        mime: str,
        content: bytes,
    ) -> ArtifactRecord:
        if len(content) > MAX_ARTIFACT_BYTES:
            raise ValueError("artifact exceeds the 1 MiB limit")
        if kind not in ARTIFACT_KINDS:
            kind = "text"
        row = SessionArtifactORM(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            session_id=session_id,
            owner_id=owner_id,
            turn_id=turn_id,
            name=name[:255],
            kind=kind[:16],
            mime=mime[:120],
            size_bytes=len(content),
            sha256=artifact_digest(content),
            snippet=artifact_snippet(content),
            content=content,
        )
        self._s.add(row)
        await self._s.flush()
        return ArtifactRecord(
            id=row.id,
            name=row.name,
            kind=row.kind,
            mime=row.mime,
            size_bytes=row.size_bytes,
            sha256=row.sha256,
            snippet=row.snippet,
            content=row.content,
        )

    async def get(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        session_id: UUID,
        owner_id: UUID,
        artifact_id: UUID,
    ) -> ArtifactRecord | None:
        row = await self._s.scalar(
            select(SessionArtifactORM).where(
                SessionArtifactORM.id == artifact_id,
                SessionArtifactORM.tenant_id == tenant_id,
                SessionArtifactORM.workspace_id == workspace_id,
                SessionArtifactORM.session_id == session_id,
                SessionArtifactORM.owner_id == owner_id,
            )
        )
        if row is None:
            return None
        return ArtifactRecord(
            id=row.id,
            name=row.name,
            kind=row.kind,
            mime=row.mime,
            size_bytes=row.size_bytes,
            sha256=row.sha256,
            snippet=row.snippet,
            content=row.content,
        )


__all__ = [
    "ARTIFACT_KINDS",
    "MAX_ARTIFACT_BYTES",
    "SNIPPET_CHARS",
    "ArtifactRecord",
    "ArtifactStore",
    "PostgresArtifactStore",
    "artifact_digest",
    "artifact_download_path",
    "artifact_snippet",
]
