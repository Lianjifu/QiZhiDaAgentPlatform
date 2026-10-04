"""ASGI middleware that resolves Principal from headers and stamps request.state.

Headers expected:
    Authorization: Bearer <jwt>
    X-Tenant-Id:    <uuid>
    X-Workspace-Id: <uuid>  (optional)
    X-Trace-Id:     <id>     (optional — falls back to generated)

Sets on `scope["state"]`: `principal`, `tenant_id`, `workspace_id`, `trace_id`.
Downstream `TenantGuard` and `WorkspaceGuard` middleware validate that
the matching headers agree with these bound values.

Mount via ``app.add_middleware(AuthMiddleware, verifier=...)``; the
standard Starlette/FastAPI middleware protocol handles wrapping the app.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from qzdap_kernel.contextvars import bind_trace_id_token, reset_trace_id
from qzdap_kernel.errors import AuthenticationError
from qzdap_persistence.tenant_guard import bind_tenant_to_session, reset_tenant_to_session

from qzdap_auth.dependencies import get_principal
from qzdap_auth.jwt import JWTVerifier


class AuthMiddleware:
    """Pure ASGI middleware. Verifies JWT (if a verifier is configured) and
    binds the resolved tenant/workspace into both `scope["state"]` and the
    `tenant_id_var` context var used by the ORM auto-filter.

    Routes that require an authenticated user should declare
    `Depends(require_authenticated)` so the missing-token case surfaces as
    a 401 rather than silently passing through.
    """

    def __init__(self, app: Callable, *, verifier: JWTVerifier | None = None) -> None:
        self.app = app
        self.verifier = verifier

    async def __call__(
        self,
        scope: dict,
        receive: Callable[[], Awaitable[dict]],
        send: Callable[[dict], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in (scope.get("headers") or [])}
        auth = headers.get(b"authorization", b"").decode("latin1") or None
        trace_id = headers.get(b"x-trace-id", b"").decode("latin1") or None
        _trace_id_value, trace_token = bind_trace_id_token(trace_id)

        tenant_token = None
        try:
            scope_state = scope.get("state")
            if scope_state is None:
                scope["state"] = {}
                scope_state = scope["state"]

            if self.verifier is not None and auth:
                try:
                    ap = await get_principal(self.verifier, auth)
                except AuthenticationError:
                    # No valid JWT — let the route decide (public healthz
                    # endpoints stay reachable; protected routes will raise
                    # 401 via `require_authenticated`).
                    tenant_token = None
                else:
                    tenant_token = bind_tenant_to_session(ap.tenant_id)
                    scope_state["principal"] = ap.principal
                    scope_state["tenant_id"] = ap.tenant_id
                    scope_state["workspace_id"] = ap.workspace_id
                    scope_state["trace_id"] = trace_id

            await self.app(scope, receive, send)
        finally:
            if tenant_token is not None:
                reset_tenant_to_session(tenant_token)
            reset_trace_id(trace_token)
