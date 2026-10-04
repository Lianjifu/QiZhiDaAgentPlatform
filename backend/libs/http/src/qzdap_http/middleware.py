"""Default FastAPI middleware chain in the canonical order:

    ErrorEnvelope → RequestLog → RateLimit → CORS → Auth → TenantGuard → WorkspaceGuard

Each middleware is a thin object; the order matters for security invariants
(CORS preflights must precede Auth, Auth must precede TenantGuard,
WorkspaceGuard runs last so it can use the bound tenant id).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from qzdap_auth.jwt import JWTVerifier
from qzdap_auth.middleware import AuthMiddleware
from qzdap_kernel.errors import ForbiddenError
from qzdap_observability.middleware import ObservabilityMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware as FastAPICORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from qzdap_http.cors import CORSMiddlewareConfig
from qzdap_http.error_envelope import error_envelope_middleware
from qzdap_http.rate_limit import RateLimitMiddleware, RateLimitPolicy

ASGIApp = Callable[
    [dict, Callable[[], Awaitable[dict]], Callable[[dict], Awaitable[None]]],
    Awaitable[None],
]


def _scope_tenant(scope: dict) -> UUID | None:
    state = scope.get("state") or {}
    tid = state.get("tenant_id")
    return tid if isinstance(tid, UUID) else None


def _scope_workspace(scope: dict) -> UUID | None:
    state = scope.get("state") or {}
    wid = state.get("workspace_id")
    return wid if isinstance(wid, UUID) else None


class TenantGuardMiddleware:
    """Defense in depth: X-Tenant-Id header must match the JWT-bound tenant.

    Runs AFTER Auth so it has access to `state["tenant_id"]` (which was set
    from the verified JWT claims). If both the JWT and the header are
    present and they disagree, the request is rejected with TENANT_HEADER_MISMATCH.

    Public/unauthenticated requests (no JWT, no header) are passed through
    — route-level validation decides what to do.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict,
        receive: Callable[[], Awaitable[dict]],
        send: Callable[[dict], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        bound = _scope_tenant(scope)
        headers = {k.lower(): v for k, v in (scope.get("headers") or [])}
        raw = headers.get(b"x-tenant-id", b"").decode("latin1") or None

        if bound is not None and raw:
            try:
                if UUID(raw) != bound:
                    raise ForbiddenError(
                        "X-Tenant-Id header does not match authenticated tenant",
                        code="TENANT_HEADER_MISMATCH",
                    )
            except ValueError:
                # Malformed UUID: let the route layer emit a 422.
                pass

        await self.app(scope, receive, send)


class WorkspaceGuardMiddleware:
    """Defense in depth: X-Workspace-Id header must match the JWT-bound
    workspace (when the principal has one)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict,
        receive: Callable[[], Awaitable[dict]],
        send: Callable[[dict], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        bound = _scope_workspace(scope)
        headers = {k.lower(): v for k, v in (scope.get("headers") or [])}
        raw = headers.get(b"x-workspace-id", b"").decode("latin1") or None

        if bound is not None and raw:
            try:
                if UUID(raw) != bound:
                    raise ForbiddenError(
                        "X-Workspace-Id header does not match authenticated workspace",
                        code="WORKSPACE_HEADER_MISMATCH",
                    )
            except ValueError:
                pass

        await self.app(scope, receive, send)


def build_default_middleware_chain(
    app: FastAPI,
    *,
    cors: CORSMiddlewareConfig | None = None,
    rate_limit: RateLimitPolicy | None = None,
    auth_verifier: JWTVerifier | None = None,
) -> None:
    """Mount the canonical chain on `app`. The order is fixed; callers only
    decide which optional layers to enable (cors / rate_limit / auth).

    Starlette / FastAPI wraps middleware in reverse, so the LAST
    ``add_middleware`` call is the OUTERMOST (executes first). The list
    below reads innermost → outermost, matching what actually runs.
    """
    # ── innermost: closest to the application handlers ────────────────────
    app.add_middleware(WorkspaceGuardMiddleware)
    app.add_middleware(TenantGuardMiddleware)

    if auth_verifier is not None:
        app.add_middleware(AuthMiddleware, verifier=auth_verifier)

    if cors is not None:
        app.add_middleware(
            FastAPICORSMiddleware,
            allow_origins=cors.allow_origins,
            allow_credentials=cors.allow_credentials,
            allow_methods=cors.allow_methods,
            allow_headers=cors.allow_headers,
        )

    if rate_limit is not None:
        app.add_middleware(RateLimitMiddleware, policy=rate_limit)

    # ── request log + metrics ─────────────────────────────────────────────
    app.add_middleware(ObservabilityMiddleware)

    # ── outermost: errors must be caught here so every layer below can ──
    #    raise without worrying about response formatting.
    app.add_middleware(BaseHTTPMiddleware, dispatch=error_envelope_middleware)  # type: ignore[arg-type]
