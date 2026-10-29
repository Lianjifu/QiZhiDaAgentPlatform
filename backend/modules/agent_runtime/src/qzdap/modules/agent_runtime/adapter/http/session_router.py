"""Copilot HTTP — /api/sessions aligned with the web client."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from opentelemetry import trace as _trace
from qzdap_agent_runtime.gateway.channels import capabilities_for
from qzdap_agent_runtime.gateway.types import ChannelType, RawIngress
from qzdap_kernel.contextvars import current_trace_id
from qzdap_observability.metrics import record_legacy_call
from qzdap_observability.tracing import get_tracer

from qzdap.modules.agent_runtime.adapter.http.dto import (
    InteractiveAnswerRequest,
)
from qzdap.modules.agent_runtime.adapter.http.sse import sse_stream
from qzdap.modules.agent_runtime.application.copilot import CopilotSessionService
from qzdap.modules.agent_runtime.domain.errors import DuplicateRequestError

_tracer = get_tracer("qzdap.agent_runtime")


def _owner_id(request: Request, fallback: UUID) -> UUID:
    principal = getattr(request.state, "principal", None)
    pid = getattr(principal, "id", None)
    if pid is None:
        return fallback
    return UUID(str(pid))


async def _write_audit(
    request: Request,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Best-effort audit row. Never raises — audit must not break the flow."""
    try:
        from qzdap.modules.governance.adapter.persistence.models import AuditLogORM

        container = getattr(request.app.state, "container", None)
        if container is None:
            return
        sf = container.session_factory()
        async with sf.session() as session:
            session.add(
                AuditLogORM(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    event_type=event_type,
                    payload=payload,
                )
            )
            await session.commit()
    except Exception:
        logging.getLogger(__name__).warning(
            "audit_log write failed event=%s", event_type, exc_info=True
        )


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
            from qzdap.modules.agent_runtime.adapter.tools import ToolServiceAdapter

            tenant_id = TenantId(UUID(tenant_raw))
            workspace_id = WorkspaceId(UUID(workspace_raw))
            owner_id = UserId(_owner_id(request, UUID(int=0)))
            skill_port = None
            skill_factory = getattr(request.app.state, "skill_factory", None)
            if skill_factory is not None:
                skill_port = SkillServiceAdapter(
                    svc=skill_factory.for_session(session),
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_id=owner_id,
                )
            sandbox_port = None
            sandbox_client = getattr(request.app.state, "sandbox_client", None)
            if sandbox_client is not None:
                sandbox_port = SandboxRuntimeAdapter(
                    sandbox_client,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    agent_id=None,
                )
            tool_port = None
            tool_factory = getattr(request.app.state, "tool_factory", None)
            if tool_factory is not None:
                tool_port = ToolServiceAdapter(
                    tool_service=tool_factory.for_session(session),
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_id=owner_id,
                )
            svc.bind_ports(
                skill_port=skill_port,
                sandbox_port=sandbox_port,
                tool_port=tool_port,
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
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: CopilotSessionService = Depends(copilot_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_sessions(
            tenant_id=x_tenant_id,
            owner_id=_owner_id(request, x_user_id),
            search=search,
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
        record_legacy_call("R2")  # agentId 直取（无任何策略）
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
            tenant_id=x_tenant_id,
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
    ) -> Response:  # 重复请求走 202 降级路径（不是流）
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
        # ①②③ —— **web 入口也走同一个门面**（§10 Stage 4a）。
        # 身份与幂等键因此只有**一个**来源：认证中间件的 principal（兜底租户头）
        # + Gateway 的键阶梯（§4.2）。
        gateway = getattr(request.app.state, "web_gateway", None)
        if gateway is None:
            raise HTTPException(status_code=503, detail="gateway not configured")
        principal = getattr(request.state, "principal", None)
        principal_id = getattr(principal, "id", None)
        accepted = await gateway.accept(
            RawIngress(
                transport="http",
                channel_type=ChannelType.WEB,
                channel_id=None,
                capabilities=capabilities_for(ChannelType.WEB),
                method="POST",
                path="/api/sessions/{session_id}/turns/stream",
                headers={key.lower(): value for key, value in request.headers.items()},
                # 正文是**附件解析之后**的（附件上下文在这一层注入）——
                # 归一化器看到的必须是真正要发出去的那段文字。
                body=json.dumps({**body, "content": content}).encode(),
                query={},
                trace_id=current_trace_id() or "",
                # 外部会话标识 = session_id（§3.3：web 的 chat id 填 session_id）。
                ingress_ref=str(session_id),
            ),
            actor_id=UUID(str(principal_id)) if principal_id else None,
            roles=tuple(getattr(principal, "roles", ()) or ()),
        )
        message = accepted.message

        # 整个 HTTP 请求一个 span —— 它是 agent.turn 的父 span.
        try:
            return await _sse_response(
                _tracer.start_span("http.chat.stream"),
                route="/api/sessions/{session_id}/turns/stream",
                session_id=session_id,
                tenant_id=message.actor.tenant_id,
                workspace_id=message.actor.workspace_id or x_workspace_id,
                build=lambda span_ctx: svc.stream_turn(
                    tenant_id=message.actor.tenant_id,
                    workspace_id=message.actor.workspace_id or x_workspace_id,
                    owner_id=message.actor.actor_id,
                    session_id=session_id,
                    user_input=message.text,
                    model=body.get("model"),
                    route_id=route_id_uuid,
                    # 幂等键由 Gateway ③ 派生（前端每次发送带一个唯一 id，
                    # 重复到达时不跑第二轮）。
                    idempotency_key=message.idempotency,
                    parent_span_context=span_ctx,
                ),
            )
        except DuplicateRequestError as exc:
            # ⚠️ **重复请求不是错误**（Gateway 方案 §4.5）：命中重复 → 降级为
            # 「202 + 上次 turn_id + replay_unavailable」。
            # **不得静默丢弃**（丢掉了客户端就不知道这一轮到底跑没跑）。
            # 无感重放要等 ``session_events`` 真写真读（Session Stage 4），
            # 届时由 Gateway Stage 4b 接管。
            return JSONResponse(
                status_code=202,
                content={
                    "code": exc.code,
                    "turnId": str(exc.turn_id) if exc.turn_id else None,
                    "replayUnavailable": exc.replay_unavailable,
                },
            )

    @router.post("/api/sessions/{session_id}/feedback", status_code=201)
    async def submit_feedback(
        session_id: UUID,
        body: dict[str, Any],
        request: Request,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: CopilotSessionService = Depends(copilot_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        """用户对一轮回答的反馈 —— 写进平台的反馈池 (feedback.list).

        反馈池是管理侧已经在用的集合, 这里直接写进去, 管理员在
        「管理 → 反馈池」就能看到对话里的真实反馈.
        """
        owner_id = _owner_id(request, x_user_id)
        session = await svc.require_owned_session(
            tenant_id=x_tenant_id, session_id=session_id, owner_id=owner_id
        )
        rating = int(body.get("rating") or 0)
        if rating not in (1, 5):
            raise HTTPException(status_code=422, detail="rating must be 1 (踩) or 5 (赞)")
        comment = str(body.get("comment") or "")[:2000]
        topic = str(body.get("topic") or "对话质量")[:64]
        tags = [str(item)[:32] for item in (body.get("tags") or [])][:8]
        principal = getattr(request.state, "principal", None)
        display_name = str(getattr(principal, "display_name", "") or "")[:64]
        payload = {
            "agent": str(session.metadata.get("agentName") or "智能体")[:64],
            "user": display_name or str(owner_id)[:8],
            "session": f"会话 #{str(session_id)[:8]}",
            "sessionId": str(session_id),
            "turnId": str(body.get("turnId") or ""),
            "type": "thumbs",
            "rating": rating,
            "sentiment": "positive" if rating == 5 else "negative",
            "status": "new",
            "priority": "low" if rating == 5 else "high",
            "topic": topic,
            "comment": comment,
            "submittedAt": datetime.now(UTC).isoformat(),
            "tags": tags,
        }
        factory = getattr(request.app.state, "admin_ops_factory", None)
        container = getattr(request.app.state, "container", None)
        if factory is None or container is None:
            raise HTTPException(status_code=503, detail="feedback storage not wired")
        sf = container.session_factory()
        async with sf.session() as fb_session:
            ops = factory.for_session(fb_session)
            doc = await ops.create(
                tenant_id=x_tenant_id,
                workspace_id=x_workspace_id,
                collection="feedback.list",
                prefix="fb",
                body=payload,
            )
            await fb_session.commit()
        await _write_audit(
            request,
            tenant_id=x_tenant_id,
            actor_id=owner_id,
            event_type="chat.feedback",
            payload={
                "session_id": str(session_id),
                "turn_id": payload["turnId"],
                "rating": rating,
            },
        )
        return {"ok": True, "feedback_id": str(doc.get("id") or ""), "rating": rating}

    @router.post("/api/sessions/{session_id}/cancel")
    async def cancel_turn(
        session_id: UUID,
        request: Request,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: CopilotSessionService = Depends(copilot_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        """请求停止当前轮次.

        停止标记写在 session 行上, 因此能跨 worker 送达真正在跑那一轮的进程.
        """
        live = await svc.request_cancel(
            tenant_id=x_tenant_id,
            session_id=session_id,
        )
        return {"ok": True, "cancelled": live}

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
        await _write_audit(
            request,
            tenant_id=x_tenant_id,
            actor_id=actor,
            event_type="tool.interactive_answer",
            payload={
                "session_id": str(session_id),
                "call_id": body.call_id,
                "action": body.action,
                "payload": body.payload,
            },
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
        svc: CopilotSessionService = Depends(copilot_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        """批准 plan — 决策落库到 session.graph_state, 并写一行审计."""
        await svc.decide_plan(
            tenant_id=x_tenant_id,
            session_id=session_id,
            plan_id=plan_id,
            decision="approved",
        )
        await _write_audit(
            request,
            tenant_id=x_tenant_id,
            actor_id=_owner_id(request, x_user_id),
            event_type="agent.plan_approved",
            payload={"session_id": str(session_id), "plan_id": str(plan_id)},
        )
        return {"ok": True, "plan_id": str(plan_id), "decision": "approved"}

    @router.post("/api/sessions/{session_id}/plans/{plan_id}/deny")
    async def deny_plan(
        session_id: UUID,
        plan_id: UUID,
        request: Request,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: CopilotSessionService = Depends(copilot_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        """拒绝 plan — 决策落库到 session.graph_state, 并写一行审计."""
        await svc.decide_plan(
            tenant_id=x_tenant_id,
            session_id=session_id,
            plan_id=plan_id,
            decision="denied",
        )
        await _write_audit(
            request,
            tenant_id=x_tenant_id,
            actor_id=_owner_id(request, x_user_id),
            event_type="agent.plan_denied",
            payload={"session_id": str(session_id), "plan_id": str(plan_id)},
        )
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
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_user_id: UUID = Header(default=UUID(int=0), alias="X-User-Id"),  # noqa: B008
        svc: CopilotSessionService = Depends(copilot_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        record_legacy_call("G8")  # GET /v1/sessions 列表别名
        # 租户是**必填**：列表查询必须显式按租户过滤（§10 Stage 2）。
        return await svc.list_sessions(
            tenant_id=x_tenant_id, owner_id=_owner_id(request, x_user_id)
        )

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
    return await _sse_response(
        _tracer.start_span("http.chat.stream"),
        route="/api/sessions/{session_id}/approvals/{approval_id}",
        session_id=session_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        build=lambda span_ctx: svc.decide_approval(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=_owner_id(request, x_user_id),
            session_id=session_id,
            approval_id=approval_id,
            approved=approved,
            approval_service=approval_service,
            parent_span_context=span_ctx,
        ),
    )


async def _sse_response(
    span: Any,
    *,
    route: str,
    session_id: UUID,
    tenant_id: UUID,
    workspace_id: UUID,
    build: Callable[[Any], AsyncIterator[Any]],
) -> StreamingResponse:
    """SSE 响应 + 一层 ``http.chat.stream`` span.

    span 覆盖整个请求: 首 chunk 预取 + 后续流式输出. ``build`` 收到
    span context, 用来把下游的 ``agent.turn`` 挂到这个 span 底下.

    注意: 不用 ``start_as_current_span`` —— 它靠 ContextVar 的 token 复位,
    而异步生成器每次恢复可能跑在不同的 Context 里, 退出时会抛
    "created in a different Context". 这里全程显式传 context.
    """
    span.set_attribute("http.method", "POST")
    span.set_attribute("http.route", route)
    span.set_attribute("session.id", str(session_id))
    span.set_attribute("tenant.id", str(tenant_id))
    span.set_attribute("workspace.id", str(workspace_id))
    span_ctx = _trace.set_span_in_context(span)
    try:
        chunks = build(span_ctx)
        aiterator = chunks.__aiter__()
        first = await aiterator.__anext__()
    except Exception as exc:
        span.set_status(_trace.Status(_trace.StatusCode.ERROR))
        span.record_exception(exc)
        span.end()
        raise

    async def safe_stream() -> AsyncIterator[bytes]:
        try:
            async for piece in sse_stream(_chain(first, aiterator)):
                yield piece
        except asyncio.CancelledError:
            # 客户端断开 —— 记一笔, 别让 APM 里看起来像正常结束.
            span.set_status(
                _trace.Status(_trace.StatusCode.ERROR, "client disconnected")
            )
            raise
        except Exception as exc:
            span.set_status(_trace.Status(_trace.StatusCode.ERROR))
            span.record_exception(exc)
            raise
        finally:
            span.end()

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
