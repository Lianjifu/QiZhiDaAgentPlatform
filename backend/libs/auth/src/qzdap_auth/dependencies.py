"""FastAPI dependency: extract Principal from Authorization header.

Usage:
    @app.get("/me", dependencies=[Depends(require_authenticated)])
    async def me(principal: Principal = Depends(get_principal)):
        return principal
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from qzdap_kernel.errors import AuthenticationError, ForbiddenError
from qzdap_kernel.principal import Principal, PrincipalType

from qzdap_auth.jwt import JWTVerifier


@dataclass(slots=True, frozen=True)
class AuthenticatedPrincipal:
    """HTTP-layer wrapper carrying the request's tenant/workspace scopes.

    Why a wrapper instead of the bare Principal? The tenant/workspace are
    also derivable from headers (`X-Tenant-Id`, `X-Workspace-Id`) and we
    want a single object the middleware can stamp onto `request.state`.
    """

    principal: Principal
    raw_token: str

    @property
    def tenant_id(self) -> UUID:
        assert self.principal.tenant_id is not None
        return self.principal.tenant_id

    @property
    def workspace_id(self) -> UUID | None:
        return self.principal.workspace_id


def _principal_from_jwt(claims: dict, raw: str) -> Principal:
    return Principal(
        id=UUID(claims["sub"]),
        type=PrincipalType.USER,
        tenant_id=UUID(claims["tid"]),
        workspace_id=UUID(claims["wid"]) if claims.get("wid") else None,
        roles=frozenset(claims.get("roles") or []),
        scopes=frozenset(claims.get("scopes") or []),
    )


async def get_principal(
    verifier: JWTVerifier, authorization: str | None = None
) -> AuthenticatedPrincipal:
    """Resolve the current Principal from `Authorization: Bearer <jwt>`.

    The composition root wires `verifier` as a request-scoped dependency;
    see `composition/qzdap_app/container.py`.

    `JWTVerifier.verify` performs HMAC + JSON parse synchronously; we run it
    in a thread so it cannot block the event loop under concurrent load.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("missing bearer token", code="MISSING_TOKEN")
    token = authorization.split(" ", 1)[1].strip()
    claims = await asyncio.to_thread(verifier.verify, token)
    principal = _principal_from_jwt(claims, token)
    return AuthenticatedPrincipal(principal=principal, raw_token=token)


def require_authenticated(_: AuthenticatedPrincipal) -> AuthenticatedPrincipal:
    return _  # marker dependency; real check happens in get_principal


def require_role(role: str):
    def _check(p: AuthenticatedPrincipal) -> AuthenticatedPrincipal:
        if not p.principal.has_role(role):
            raise ForbiddenError(f"role {role} required", code="INSUFFICIENT_ROLE")
        return p

    return _check


def require_scope(scope: str):
    def _check(p: AuthenticatedPrincipal) -> AuthenticatedPrincipal:
        if not p.principal.has_scope(scope):
            raise ForbiddenError(f"scope {scope} required", code="INSUFFICIENT_SCOPE")
        return p

    return _check
