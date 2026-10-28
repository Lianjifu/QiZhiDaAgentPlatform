"""Copilot HTTP — /api/sessions aligned with the web client."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from qzdap.modules.agent_runtime.adapter.http.dto import (
    CreateSessionRequest,
    InteractiveAnswerRequest,
    RunTurnRequest,
    SessionResponse,
    TurnResponse,
)
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

            from qzdap.modules.agent_runtime.adapter.sandbox import (
                SandboxRuntimeAdapter,
            )
            from qzdap.modules.agent_runtime.adapter.skills import SkillServiceAdapter

            tenant_id = TenantId(UUID(tenant_raw))
            workspace_id = WorkspaceId(UUID(workspace_raw))
            owner_id = UserId(_owner_id(request, UUID(int=0)))
            skill_factory = getattr(request.app.state, "skill_factory", None)
            if skill_factory is not None:
                svc._graph._skill_port = SkillServiceAdapter(
                    svc=skill_factory.for_session(session),
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_id=owner_id,
                )
            sandbox_client = getattr(request.app.state, "sandbox_client", None)
            if sandbox_client is not None:
                svc._graph._sandbox_port = SandboxRuntimeAdapter(
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
    from qzdap.modules.agent_runtime.adapter.http.attachments import (
        build_attachment_router,
    )

    router.include_router(build_attachment_router())

    @router.get("/api/sessions")
    async def list_sessions(
        request: Request,
        search: str = Query(default=""),
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: CopilotSessionService = Depends(copilot_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_sessions(
            owner_id=_owner_id(request, x_user_id), search=search
        )

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

    # ── 我的任务 (Round-8 dev-mode) ─────────────────────────────────
    # 用户侧「我的任务」列表 — 派生自 owner=me 的 agent_sessions, 翻译 session 状态
    # → 前端 Task 状态 (待处理/执行中/已完成/异常)。不新建表, 仅暴露派生视图。

    @router.get("/api/tasks")
    async def list_tasks(
        request: Request,
        q: str = Query(default=""),
        status: str = Query(default="all"),
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: CopilotSessionService = Depends(copilot_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_tasks(
            owner_id=_owner_id(request, x_user_id),
            workspace_id=x_workspace_id,
            q=q,
            status=status,
        )

    @router.post("/api/tasks/{task_id}")
    async def update_task(
        task_id: UUID,
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: CopilotSessionService = Depends(copilot_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        action = str(body.get("action") or "")
        if action == "complete":
            await svc.close_session(tenant_id=x_tenant_id, session_id=task_id)
        elif action == "archive":
            await svc.archive_session(tenant_id=x_tenant_id, session_id=task_id)
        elif action == "retry":
            # 不重启已有 turn (那是 copilot 的事), 仅返回最新状态供前端刷新
            return await svc.get_session(tenant_id=x_tenant_id, session_id=task_id)
        else:
            raise HTTPException(status_code=400, detail=f"unknown action: {action!r}")
        return {"ok": True, "id": str(task_id), "action": action}

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
        from qzdap.modules.agent_runtime.adapter.http.attachments import (
            attachment_session,
            resolve_attachment_context,
        )

        if body.get("attachmentIds") or "[附件:" in content:
            from contextlib import aclosing

            async with aclosing(attachment_session(request)) as attachment_scope:
                async for attachment_db in attachment_scope:
                    content = await resolve_attachment_context(
                        attachment_db,
                        request,
                        session_id,
                        content,
                        body.get("attachmentIds"),
                    )
                    break
        # Phase 12: optional route_id (UUID) — 走策略路由 (Phase 7)
        route_id_raw = body.get("route_id")
        route_id_uuid = None
        if route_id_raw:
            import logging

            try:
                from qzdap_schema.ids import ModelId

                route_id_uuid = ModelId(UUID(str(route_id_raw)))
            except (ValueError, TypeError, AttributeError) as exc:
                logging.getLogger(__name__).warning(
                    "phase12_route_id_parse_failed: %s", exc
                )
        chunks = svc.stream_turn(
            tenant_id=x_tenant_id,
            workspace_id=x_workspace_id,
            owner_id=_owner_id(request, x_user_id),
            session_id=session_id,
            user_input=content,
            model=body.get("model"),
            route_id=route_id_uuid,
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
        return await _resume(
            svc,
            request,
            session_id,
            approval_id,
            x_tenant_id,
            x_workspace_id,
            x_user_id,
            True,
        )

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
        return await _resume(
            svc,
            request,
            session_id,
            approval_id,
            x_tenant_id,
            x_workspace_id,
            x_user_id,
            False,
        )

    @router.post(
        "/api/sessions/{session_id}/interactive/answer",
        status_code=202,
    )
    async def submit_interactive_answer(
        session_id: UUID,
        body: InteractiveAnswerRequest,
        request: Request,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: CopilotSessionService = Depends(copilot_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        """Record user's answer to a frontend-coupled stub tool.

        The stub tool already returned a synthetic answer to the LLM
        (so the LLM stream continues without pause). The frontend posts
        the user's *real* answer here for:
          1. audit log row (tool.interactive_answer)
          2. session transcript record (for replay / debugging)

        The frontend then drives a follow-up user turn via
        POST /api/sessions/{id}/turns/stream so the LLM is told the
        user's actual pick in the next turn.
        """
        actor = _owner_id(request, x_user_id)
        # Audit log (best-effort; never raises).
        try:
            from qzdap.modules.governance.adapter.persistence.models import (
                AuditLogORM,
            )
            container = getattr(request.app.state, "container", None)
            if container is not None:
                sf = container.session_factory()
                async with sf.session() as session:
                    session.add(AuditLogORM(
                        id=__import__("uuid").uuid4(),
                        tenant_id=x_tenant_id,
                        actor_id=actor,
                        event_type="tool.interactive_answer",
                        payload={
                            "session_id": str(session_id),
                            "call_id": body.call_id,
                            "action": body.action,
                            "payload": body.payload,
                        },
                    ))
                    await session.commit()
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning(
                "interactive_answer audit_log write failed", exc_info=True,
            )
        return {"accepted": True, "call_id": body.call_id, "action": body.action}

    # ------------------------------------------------------------------
    # Round-7 增量: 计划批准 / 拒绝 + 产物下载
    # ------------------------------------------------------------------

    @router.post("/api/sessions/{session_id}/plans/{plan_id}/approve")
    async def approve_plan(
        session_id: UUID,
        plan_id: UUID,
        request: Request,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
    ) -> dict[str, Any]:
        """批准 plan. 真实续传 run_turn 下一轮做, 这里先 ack."""
        _ = (session_id, plan_id, x_tenant_id, x_workspace_id, x_user_id, request)
        return {"ok": True, "plan_id": str(plan_id), "decision": "approved"}

    @router.post("/api/sessions/{session_id}/plans/{plan_id}/deny")
    async def deny_plan(
        session_id: UUID,
        plan_id: UUID,
        request: Request,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
    ) -> dict[str, Any]:
        _ = (session_id, plan_id, x_tenant_id, x_workspace_id, x_user_id, request)
        return {"ok": True, "plan_id": str(plan_id), "decision": "denied"}

    @router.get("/api/artifacts/{artifact_id}/content")
    async def download_artifact(
        artifact_id: UUID,
        request: Request,
    ) -> Response:
        """下载 **mock 模式**生成的产物.

        这条路由只服务于 ``QZDAP_ENV=test`` 下的 ``MockLLMClient`` ——
        它把产物写进 ``/tmp/qzdap-mock-artifacts``, 前端再按
        ``download_path`` 来取.

        其它环境一律 404: 真实模式的产物走 ``session_artifacts`` 表,
        不该再从一个 mock 目录里读. 之前这里是"目录不存在就 404",
        看起来像是坏了; 现在是**明确地**不支持.
        """
        container = getattr(request.app.state, "container", None)
        env = getattr(getattr(container, "settings", None), "env", "")
        if env != "test":
            raise HTTPException(
                status_code=404,
                detail="artifact content is only available in mock (test) mode",
            )
        # 防 path traversal: artifact_id 是 UUID
        root = Path("/tmp/qzdap-mock-artifacts").resolve()
        target = (root / f"{artifact_id}.md").resolve()
        if not str(target).startswith(str(root)) or not target.exists():
            raise HTTPException(status_code=404, detail="artifact not found")
        data = target.read_bytes()
        return Response(
            content=data,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{artifact_id}.md"'},
        )

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
