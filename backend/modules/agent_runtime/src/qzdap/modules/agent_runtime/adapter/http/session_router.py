"""Copilot HTTP — /api/sessions aligned with the web client."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from qzdap.modules.agent_runtime.adapter.http.sse import sse_stream
from qzdap.modules.agent_runtime.application.copilot import CopilotSessionService


def _owner_id(request: Request, fallback: UUID) -> UUID:
    principal = getattr(request.state, "principal", None)
    pid = getattr(principal, "id", None)
    if pid is None:
        return fallback
    return UUID(str(pid))


async def copilot_dependency(request: Request) -> CopilotSessionService:
    factory = getattr(request.app.state, "copilot_factory", None)
    container = getattr(request.app.state, "container", None)
    if factory is None or container is None:
        raise HTTPException(status_code=503, detail="copilot factory not wired")
    sf = container.session_factory()
    async with sf.session() as session:
        svc = factory.for_session(session)
        tenant_raw = request.headers.get("x-tenant-id")
        workspace_raw = request.headers.get("x-workspace-id")
        if tenant_raw and workspace_raw:
            from qzdap_schema.ids import TenantId, UserId, WorkspaceId

            from qzdap.modules.agent_runtime.adapter.sandbox import SandboxRuntimeAdapter
            from qzdap.modules.agent_runtime.adapter.skills import SkillServiceAdapter

            tenant_id = TenantId(UUID(tenant_raw))
            workspace_id = WorkspaceId(UUID(workspace_raw))
            owner_id = UserId(_owner_id(request, UUID(int=0)))
            skill_factory = getattr(request.app.state, "skill_factory", None)
            if skill_factory is not None:
                svc._graph._skill_port = SkillServiceAdapter(  # noqa: SLF001
                    svc=skill_factory.for_session(session),
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_id=owner_id,
                )
            sandbox_client = getattr(request.app.state, "sandbox_client", None)
            if sandbox_client is not None:
                svc._graph._sandbox_port = SandboxRuntimeAdapter(  # noqa: SLF001
                    sandbox_client,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    agent_id=None,
                )
        try:
            yield svc
        except Exception:
            await session.rollback()
            raise
        await session.commit()


def build_session_router() -> APIRouter:
    router = APIRouter(tags=["sessions"])

    @router.get("/api/sessions")
    async def list_sessions(
        request: Request,
        search: str = Query(default=""),
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: CopilotSessionService = Depends(copilot_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_sessions(owner_id=_owner_id(request, x_user_id), search=search)

    @router.post("/api/sessions", status_code=201)
    async def create_session(
        body: dict[str, Any],
        request: Request,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: CopilotSessionService = Depends(copilot_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        agent_id = body.get("agentId") or body.get("agent_id")
        if not agent_id:
            raise HTTPException(status_code=400, detail="agentId is required")
        return await svc.create_session(
            tenant_id=x_tenant_id,
            workspace_id=x_workspace_id,
            owner_id=_owner_id(request, x_user_id),
            agent_id=UUID(str(agent_id)),
            title=str(body.get("title") or ""),
        )

    @router.get("/api/sessions/{session_id}")
    async def get_session(
        session_id: UUID,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: CopilotSessionService = Depends(copilot_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.get_session(tenant_id=x_tenant_id, session_id=session_id)

    @router.delete("/api/sessions/{session_id}")
    async def delete_session(
        session_id: UUID,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: CopilotSessionService = Depends(copilot_dependency),  # noqa: B008
    ) -> Response:
        await svc.close_session(tenant_id=x_tenant_id, session_id=session_id)
        return Response(status_code=204)

    @router.post("/api/sessions/{session_id}/turns/stream")
    async def stream_turn(
        session_id: UUID,
        body: dict[str, Any],
        request: Request,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: CopilotSessionService = Depends(copilot_dependency),  # noqa: B008
    ) -> StreamingResponse:
        content = str(body.get("content") or body.get("message") or "").strip()
        if not content:
            raise HTTPException(status_code=400, detail="content is required")
        chunks = svc.stream_turn(
            tenant_id=x_tenant_id,
            workspace_id=x_workspace_id,
            owner_id=_owner_id(request, x_user_id),
            session_id=session_id,
            user_input=content,
            model=body.get("model"),
        )
        aiterator = chunks.__aiter__()
        first = await aiterator.__anext__()

        async def safe_stream() -> AsyncIterator[bytes]:
            async for piece in sse_stream(_chain(first, aiterator)):
                yield piece

        return StreamingResponse(
            safe_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/api/sessions/{session_id}/approvals/{approval_id}/approve")
    async def approve_tool(
        session_id: UUID,
        approval_id: UUID,
        request: Request,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: CopilotSessionService = Depends(copilot_dependency),  # noqa: B008
    ) -> StreamingResponse:
        return await _resume(svc, request, session_id, approval_id, x_tenant_id, x_workspace_id, x_user_id, True)

    @router.post("/api/sessions/{session_id}/approvals/{approval_id}/deny")
    async def deny_tool(
        session_id: UUID,
        approval_id: UUID,
        request: Request,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: CopilotSessionService = Depends(copilot_dependency),  # noqa: B008
    ) -> StreamingResponse:
        return await _resume(svc, request, session_id, approval_id, x_tenant_id, x_workspace_id, x_user_id, False)

    @router.get("/v1/sessions")
    async def list_v1(
        request: Request,
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: CopilotSessionService = Depends(copilot_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_sessions(owner_id=_owner_id(request, x_user_id))

    return router


async def _resume(
    svc: CopilotSessionService,
    request: Request,
    session_id: UUID,
    approval_id: UUID,
    tenant_id: UUID,
    workspace_id: UUID,
    x_user_id: UUID,
    approved: bool,
) -> StreamingResponse:
    approval_service = None
    factory = getattr(request.app.state, "approval_service", None)
    if factory is None:
        container = getattr(request.app.state, "container", None)
        if container is not None:
            try:
                approval_service = container.approval_service()
            except Exception:  # noqa: BLE001
                approval_service = None
    else:
        approval_service = factory
    chunks = svc.decide_approval(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        owner_id=_owner_id(request, x_user_id),
        session_id=session_id,
        approval_id=approval_id,
        approved=approved,
        approval_service=approval_service,
    )
    aiterator = chunks.__aiter__()
    first = await aiterator.__anext__()

    async def safe_stream() -> AsyncIterator[bytes]:
        async for piece in sse_stream(_chain(first, aiterator)):
            yield piece

    return StreamingResponse(
        safe_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _chain(first, aiterator):
    yield first
    async for item in aiterator:
        yield item


__all__ = ["build_session_router"]
