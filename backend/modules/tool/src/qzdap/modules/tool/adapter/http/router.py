"""HTTP router for the tool module: CRUD + invoke + batch_invoke.

Routes mount under `/v1/tools`. Per-request DB session + service is bound
via an async-generator dependency (`tool_dependency`); routes don't need
to remember to commit/rollback because the dependency handles it.

The router reads the per-request `ToolService` factory from
`app.state.tool_factory` (wired by the composition-root lifespan).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.responses import JSONResponse

from qzdap.modules.tool.adapter.http.dto import (
    BatchInvokeRequest,
    BatchInvokeResponse,
    InvokeToolRequest,
    RegisterToolRequest,
    ToolCallResponse,
    ToolListResponse,
    ToolResponse,
    UpdateToolRequest,
)
from qzdap.modules.tool.adapter.http.mappers import (
    auth_config_from_dto,
    tool_to_dto,
)
from qzdap.modules.tool.application.services import ToolService
from qzdap.modules.tool.application.use_cases import (
    BatchInvokeInput,
    InvalidToolSpecCallError,
)
from qzdap.modules.tool.domain import ToolProtocol


async def tool_dependency(request: Request) -> ToolService:
    """Per-request OpenSession + service binding. Mirrors agent_runtime's pattern.

    Tests inject `tool_factory_for_session` on the app state; the live
    lifespan wires `_ToolFactory` via `app.state.tool_factory`.
    """
    factory = getattr(request.app.state, "tool_factory", None)
    container = getattr(request.app.state, "container", None)
    if factory is None or container is None:
        raise HTTPException(status_code=503, detail="tool factory not wired")
    sf = container.session_factory()
    async with sf.session() as session:
        svc = factory.for_session(session)
        request.state.tool_service = svc

        # Build a per-call factory closure: opens a fresh session + service
        # for one batch item. Used by `batch_invoke_tools` since
        # SQLAlchemy async forbids concurrent ops on a shared session.
        async def _per_call_factory() -> AsyncIterator[ToolService]:
            async with sf.session() as inner_session:
                yield factory.for_session(inner_session)

        request.state.tool_service_factory = _per_call_factory
        try:
            yield svc
        except Exception:
            await session.rollback()
            raise
        await session.commit()


def build_router() -> APIRouter:
    router = APIRouter(prefix="/v1/tools", tags=["tool"])

    @router.post("", status_code=201)
    async def register_tool(
        body: RegisterToolRequest,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: ToolService = Depends(tool_dependency),  # noqa: B008
    ) -> JSONResponse:
        tool = await svc.register_tool().execute(
            tenant_id=x_tenant_id,
            workspace_id=x_workspace_id,
            owner_id=UUID("00000000-0000-0000-0000-000000000000"),
            name=body.name,
            description=body.description,
            protocol=ToolProtocol(body.protocol),
            spec=body.spec,
            auth_config=auth_config_from_dto(body.auth_config),
            rate_limit_per_minute=body.rate_limit_per_minute,
        )
        dto = tool_to_dto(tool)
        return JSONResponse(
            dto.model_dump(mode="json"),
            status_code=201,
            headers={"Location": f"/v1/tools/{tool.id}"},
        )

    @router.get("", response_model=ToolListResponse)
    async def list_tools(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        enabled: bool | None = Query(None),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        svc: ToolService = Depends(tool_dependency),  # noqa: B008
    ) -> ToolListResponse:
        tools = await svc.list_tools().execute(
            tenant_id=x_tenant_id,
            enabled=enabled,
            limit=limit,
            offset=offset,
        )
        return ToolListResponse(
            items=[tool_to_dto(t) for t in tools],
            total=len(tools),
        )

    @router.get("/{tid}", response_model=ToolResponse)
    async def get_tool(
        tid: UUID,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: ToolService = Depends(tool_dependency),  # noqa: B008
    ) -> ToolResponse:
        tool = await svc.get_tool().execute(tenant_id=x_tenant_id, tool_id=tid)
        return tool_to_dto(tool)

    @router.patch("/{tid}", response_model=ToolResponse)
    async def update_tool(
        tid: UUID,
        body: UpdateToolRequest,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        if_match: str | None = Header(None, alias="If-Match"),
        svc: ToolService = Depends(tool_dependency),  # noqa: B008
    ) -> ToolResponse:
        expected_version: int | None = None
        if if_match is not None:
            try:
                expected_version = int(if_match)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="If-Match header must be an integer"
                ) from None
        tool = await svc.update_tool().execute(
            tenant_id=x_tenant_id,
            tool_id=tid,
            expected_version=expected_version,
            description=body.description,
            spec=body.spec,
            auth_config=auth_config_from_dto(body.auth_config),
            clear_auth=body.clear_auth,
            rate_limit_per_minute=body.rate_limit_per_minute,
            clear_rate_limit=body.clear_rate_limit,
            enabled=body.enabled,
        )
        return tool_to_dto(tool)

    @router.delete("/{tid}", status_code=204)
    async def delete_tool(
        tid: UUID,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        svc: ToolService = Depends(tool_dependency),  # noqa: B008
    ) -> Response:
        await svc.delete_tool().execute(tenant_id=x_tenant_id, tool_id=tid)
        return Response(status_code=204)

    @router.post("/{name}/invoke", response_model=ToolCallResponse)
    async def invoke_tool(
        name: str,
        body: InvokeToolRequest,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: ToolService = Depends(tool_dependency),  # noqa: B008
    ) -> JSONResponse:
        try:
            call = await svc.invoke_tool().execute(
                tenant_id=x_tenant_id,
                workspace_id=x_workspace_id,
                owner_id=UUID("00000000-0000-0000-0000-000000000000"),
                tool_name=name,
                arguments=body.arguments,
            )
        except InvalidToolSpecCallError as exc:
            # OpenAPI/MCP routes without an `__operation_id` or with a
            # malformed spec surface as 422.
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        body_out = ToolCallResponse(
            tool_name=call.tool_name,
            status=200,
            result=call.result,
            latency_ms=call.latency_ms,
        )
        return JSONResponse(body_out.model_dump(mode="json"), status_code=200)

    @router.post(
        "/batch_invoke",
        response_model=BatchInvokeResponse,
        status_code=207,
    )
    async def batch_invoke_tools(
        body: BatchInvokeRequest,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        request: Request = ...,  # type: ignore[assignment]
        svc: ToolService = Depends(tool_dependency),  # noqa: B008
    ) -> BatchInvokeResponse:
        # Each batch item runs on its own DB session via the per-call
        # factory stashed on request.state by `tool_dependency`.
        factory = getattr(request.state, "tool_service_factory", None)
        if factory is None:  # defensive — dependency guarantees this.
            raise HTTPException(
                status_code=503, detail="tool service factory not wired"
            )
        results = await svc.batch_invoke_tools(factory).execute(
            tenant_id=x_tenant_id,
            workspace_id=x_workspace_id,
            owner_id=UUID("00000000-0000-0000-0000-000000000000"),
            calls=[
                BatchInvokeInput(tool_name=c.tool_name, arguments=c.arguments)
                for c in body.calls
            ],
        )
        return BatchInvokeResponse(
            items=[
                ToolCallResponse(
                    tool_name=r.tool_name,
                    status=r.status,
                    result=r.result,
                    latency_ms=r.latency_ms,
                    error=r.error,
                )
                for r in results
            ]
        )

    return router
