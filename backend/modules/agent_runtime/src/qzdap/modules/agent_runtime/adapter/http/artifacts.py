"""**产物的下载端点** ✓（会话作用域 ✓）。

⚠️ **为什么单独一个路由** ✓ —— 产物是**会话的输出** ✓（附件是输入 ✓）——
归属 / 生命周期 / 大小边界都不同 ✓。

⚠️ **四道作用域都要对得上** ✓（租户 ✓ / 工作区 ✓ / 会话 ✓ / 属主 ✓）——
**对不上就 404** ✓（不是 403 ✓ —— 不告诉调用方「它存在」 ✓✓）。
"""

from __future__ import annotations

from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.agent_runtime.adapter.persistence.models import SessionArtifactORM


async def artifact_session(request: Request):
    """**一次请求一个会话** ✓（读 ✓ —— 产物是只读的 ✓）。"""
    container = getattr(request.app.state, "container", None)
    if container is None:
        raise HTTPException(503, "database not configured")
    async with container.session_factory().session() as session:
        yield session


def build_artifact_router():
    router = APIRouter(tags=["sessions"])

    @router.get("/api/sessions/{session_id}/artifacts/{artifact_id}/content")
    async def download(
        session_id: UUID,
        artifact_id: UUID,
        request: Request,
        session: AsyncSession = Depends(artifact_session),
    ) -> Response:
        """**下载产物** ✓ —— 会话内 ✓（四道作用域 ✓）。

        ⚠️ **归属由会话决定** ✓ —— 产物行自己带租户 / 工作区 / 属主 ✓
        —— 直接按行上的四列过滤 ✓（不 JOIN 会话表 ✓ —— 会话被删时产物也
        没了 ✓ —— 外键 CASCADE ✓）。
        """
        principal = getattr(request.state, "principal", None)
        principal = getattr(principal, "principal", principal)
        if principal is None or getattr(principal, "type", None) != "user":
            raise HTTPException(401, "authenticated user required")
        for header, expected in [
            ("x-tenant-id", principal.tenant_id),
            ("x-user-id", principal.id),
            ("x-workspace-id", principal.workspace_id),
        ]:
            if (
                request.headers.get(header)
                and expected is not None
                and request.headers[header] != str(expected)
            ):
                raise HTTPException(403, "artifact scope mismatch")
        workspace_raw = request.headers.get("x-workspace-id") or principal.workspace_id
        try:
            workspace = UUID(str(workspace_raw))
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, "workspace required") from exc
        row = await session.scalar(
            select(SessionArtifactORM).where(
                SessionArtifactORM.id == artifact_id,
                SessionArtifactORM.tenant_id == principal.tenant_id,
                SessionArtifactORM.workspace_id == workspace,
                SessionArtifactORM.session_id == session_id,
                SessionArtifactORM.owner_id == principal.id,
            )
        )
        if row is None:
            raise HTTPException(404, "artifact not found")
        return Response(
            row.content,
            media_type=row.mime,
            headers={
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": _content_disposition(row.name),
            },
        )

    return router


def _content_disposition(name: str) -> str:
    """**产物名进响应头** ✓ —— 中文名要转义 ✓（HTTP 头是 latin-1 ✓）。

    ⚠️ **两个名字都给** ✓ —— ``filename`` 给老客户端 ✓（ASCII 兜底 ✓），
    ``filename*`` 给认 RFC 5987 的 ✓（中文原样 ✓）。
    """
    fallback = name.encode("ascii", "ignore").decode("ascii").strip() or "artifact"
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name)}"


__all__ = ["build_artifact_router"]
