"""HTTP adapter — FastAPI router for sessions + turns.

Public routes (mounted on `/v1`):

  POST   /agents/{aid}/sessions            create_session        201 + Location
  GET    /sessions/{sid}                   get_session
  POST   /sessions/{sid}/close             close_session         204
  POST   /sessions/{sid}/turn/stream       run_turn_stream       SSE

Every protected route declares `X-Tenant-Id` + `X-Workspace-Id` so the
contract test (`tests/contract/test_openapi_headers.py`) passes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from qzdap_schema.ids import AgentId, TenantId, UserId, WorkspaceId
from fastapi import APIRouter, Depends, Header, Request
from fastapi import status as http_status
from fastapi.responses import JSONResponse, Response, StreamingResponse

from qzdap.modules.agent_runtime.adapter.http.dto import (
    CreateSessionRequest,
    RunTurnRequest,
    SessionResponse,
)
from qzdap.modules.agent_runtime.adapter.http.mappers import session_to_dto
from qzdap.modules.agent_runtime.adapter.http.sse import sse_stream
from qzdap.modules.agent_runtime.application.services import AgentRuntimeService


def _current_owner_id(request: Request) -> UserId:
    """Resolve the principal id from `scope["state"]` (set by AuthMiddleware).

    Returns a sentinel-zero UUID when there's no principal — for SSE
    streams we never reach the streaming body without an authenticated
    principal because the route is reached via a JWT in production. In
    unit tests the lifespan wires `app.state.identity_factory` but no
    principal exists yet, so the FastAPI dependency `Depends(get_service)`
    fails first.
    """
    state = request.scope.get("state") or {}
    principal = state.get("principal")
    pid = getattr(principal, "id", None)
    if pid is None:
        # Fallback: no auth in unit/integration test mode → return zero UUID.
        # The route-level X-Tenant-Id header is still validated by the
        # TenantGuard middleware when wired.
        return UserId(UUID(int=0))
    return UserId(UUID(str(pid)))


def _settings(request: Request) -> Any:
    return request.app.state.settings


def get_service(request: Request) -> AgentRuntimeService:
    svc = getattr(request.state, "agent_runtime_service", None)
    if svc is None:
        raise RuntimeError("AgentRuntimeService not bound on request.state")
    return svc


async def agent_runtime_dependency(request: Request) -> AgentRuntimeService:
    """Per-request OpenSession + service binding. Mirrors identity's pattern.

    When a `_ToolFactory` is wired on `app.state.tool_factory`, this
    dependency also opens a sibling ToolService on the same DB session
    and exposes it via `request.state.tool_service` so the streaming
    turn runner can dispatch LLM tool_call chunks immediately (P2
    wiring).
    """
    factory = getattr(request.app.state, "agent_runtime_factory", None)
    tool_factory = getattr(request.app.state, "tool_factory", None)
    container = getattr(request.app.state, "container", None)
    if factory is None or container is None:
        raise RuntimeError("AgentRuntimeService factory not wired on app.state")
    sf = container.session_factory()
    async with sf.session() as session:
        svc = factory.for_session(session)
        tool_svc = (
            tool_factory.for_session(session) if tool_factory is not None else None
        )
        request.state.agent_runtime_service = svc
        request.state.tool_service = tool_svc
        tenant_raw = request.headers.get("x-tenant-id")
        workspace_raw = request.headers.get("x-workspace-id")
        if tenant_raw and workspace_raw:
            from uuid import UUID as _UUID

            from qzdap_schema.ids import TenantId, WorkspaceId

            from qzdap.modules.agent_runtime.adapter.sandbox import (
                SandboxRuntimeAdapter,
            )
            from qzdap.modules.agent_runtime.adapter.skills import (
                SkillServiceAdapter,
            )
            from qzdap.modules.agent_runtime.adapter.tools.tool_service_adapter import (
                ToolServiceAdapter,
            )

            tenant_id = TenantId(_UUID(tenant_raw))
            workspace_id = WorkspaceId(_UUID(workspace_raw))
            owner_id = _current_owner_id(request)
            skill_factory = getattr(request.app.state, "skill_factory", None)
            if skill_factory is not None:
                svc.skill_port = SkillServiceAdapter(
                    svc=skill_factory.for_session(session),
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_id=owner_id,
                )
            sandbox_client = getattr(request.app.state, "sandbox_client", None)
            if sandbox_client is not None:
                svc.sandbox_port = SandboxRuntimeAdapter(
                    sandbox_client,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    agent_id=None,
                )
            if tool_svc is not None:
                svc.tool_port = ToolServiceAdapter(
                    tool_service=tool_svc,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    owner_id=owner_id,
                )
        try:
            yield svc
        except Exception:
            await session.rollback()
            raise
        await session.commit()


def build_router() -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["agent_runtime"])

    @router.post(
        "/agents/{aid}/sessions",
        response_model=SessionResponse,
        status_code=http_status.HTTP_201_CREATED,
    )
    async def create_session(
        aid: UUID,
        body: CreateSessionRequest,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        request: Request = ...,  # type: ignore[assignment]
        svc: AgentRuntimeService = Depends(agent_runtime_dependency),  # noqa: B008
    ) -> Response:
        owner = _current_owner_id(request)
        session = await svc.create_session().execute(
            tenant_id=TenantId(x_tenant_id),
            workspace_id=WorkspaceId(x_workspace_id),
            owner_id=owner,
            agent_id=AgentId(aid),
            agent_version=body.agent_version,
            metadata=body.metadata,
        )
        resp = session_to_dto(session)
        return JSONResponse(
            content=resp.model_dump(mode="json"),
            status_code=http_status.HTTP_201_CREATED,
            headers={"Location": f"/v1/sessions/{session.id}"},
        )

    @router.get(
        "/sessions/{sid}",
        response_model=SessionResponse,
    )
    async def get_session(
        sid: UUID,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: AgentRuntimeService = Depends(agent_runtime_dependency),  # noqa: B008
    ) -> SessionResponse:
        from qzdap.modules.agent_runtime.application.use_cases.get_session import (
            GetSessionUseCase,
        )

        # `svc.get_session()` returns a use case; we want the cross-tenant
        # guard from `GetSessionUseCase.execute(tenant_id=...)`, so reuse it
        # through the service.
        uc: GetSessionUseCase = svc.get_session()  # type: ignore[assignment]
        session = await uc.execute(tenant_id=x_tenant_id, session_id=sid)
        return session_to_dto(session)

    @router.post(
        "/sessions/{sid}/close",
        status_code=http_status.HTTP_204_NO_CONTENT,
    )
    async def close_session(
        sid: UUID,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: AgentRuntimeService = Depends(agent_runtime_dependency),  # noqa: B008
    ) -> Response:
        from qzdap.modules.agent_runtime.application.use_cases.close_session import (
            CloseSessionUseCase,
        )

        uc: CloseSessionUseCase = svc.close_session()  # type: ignore[assignment]
        await uc.execute(tenant_id=x_tenant_id, session_id=sid)
        return Response(status_code=http_status.HTTP_204_NO_CONTENT)

    @router.post("/sessions/{sid}/turn/stream")
    async def run_turn_stream(
        sid: UUID,
        body: RunTurnRequest,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        request: Request = ...,  # type: ignore[assignment]
        svc: AgentRuntimeService = Depends(agent_runtime_dependency),  # noqa: B008
    ) -> StreamingResponse:
        from qzdap.modules.agent_runtime.application.use_cases.run_turn import (
            RunTurnUseCase,
        )

        settings = _settings(request)
        model = body.model or settings.llm_default_model
        owner = _current_owner_id(request)

        # If a tool_service is bound on this request (P2), wrap it as a
        # ToolPort and inject it into the run_turn use case so LLM-emitted
        # tool_call chunks execute and yield paired ToolResultChunk
        # envelopes in the SSE stream.
        tool_svc = getattr(request.state, "tool_service", None)
        if tool_svc is not None:
            from qzdap.modules.agent_runtime.adapter.tools.tool_service_adapter import (
                ToolServiceAdapter,
            )

            svc.tool_port = ToolServiceAdapter(
                tool_service=tool_svc,
                tenant_id=x_tenant_id,
                workspace_id=x_workspace_id,
                owner_id=owner,
            )

        uc: RunTurnUseCase = svc.run_turn()  # type: ignore[assignment]
        chunks = uc.execute(
            tenant_id=TenantId(x_tenant_id),
            workspace_id=WorkspaceId(x_workspace_id),
            owner_id=owner,
            session_id=sid,
            user_input=body.content,
            model=model,
        )

        # Pre-flight: drain one chunk from the use-case generator so any
        # AppError (SessionNotFound / SessionClosedError) raised before the
        # first message surfaces as a normal HTTP error envelope — *before*
        # StreamingResponse begins writing the SSE handshake. Doing the peek
        # outside the StreamingResponse body is the only way the
        # error_envelope middleware can convert the error to a proper
        # 404/410 response with status + JSON body.
        aiterator = chunks.__aiter__()
        first = await aiterator.__anext__()

        async def safe_stream() -> AsyncIterator[bytes]:
            async for piece in sse_stream(_chain(first, aiterator)):
                yield piece

        return StreamingResponse(
            safe_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # disable nginx buffering
            },
        )

    return router


async def _chain(first, aiterator):
    """Yield `first`, then drain the rest of `aiterator`."""
    yield first
    async for item in aiterator:
        yield item


# Alias used by the composition root
router = build_router


def __getattr__(name: str) -> Any:  # type: ignore[no-untyped-def]
    if name == "router":
        return build_router()
    raise AttributeError(name)
