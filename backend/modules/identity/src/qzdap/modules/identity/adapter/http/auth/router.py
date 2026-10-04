"""HTTP router: auth (login) subpackage — POST /v1/identity/login.

Mounted by ``adapter/http/router.py`` via ``router.include_router`` so the
login contract stays scoped to this subfolder.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import APIRouter, Depends

from qzdap.modules.identity.adapter.http.auth.dto import LoginRequest, LoginResponse
from qzdap.modules.identity.adapter.http.deps import get_identity_service
from qzdap.modules.identity.adapter.http.mappers import user_domain_to_response
from qzdap.modules.identity.application.services import IdentityService


def build_auth_router(
    identity_service_dep: Callable[..., Coroutine[Any, Any, IdentityService]] = get_identity_service,
) -> APIRouter:
    # No prefix here — the parent router (adapter/http/router.py) already
    # mounts the `/v1/identity` prefix; nested routers that re-prefix cause
    # `/v1/identity/v1/identity/login` 404s.
    #
    # Bind the parent's per-request IdentityService dep at the router level so
    # subrouter routes get the same request.state binding the parent routes do.
    router = APIRouter(
        tags=["identity"],
        dependencies=[Depends(identity_service_dep)],
    )

    @router.post("/login", response_model=LoginResponse)
    async def login(
        body: LoginRequest,
        svc: IdentityService = Depends(identity_service_dep),  # noqa: B008
    ) -> LoginResponse:
        # Cross-tenant password auth — email uniqueness is enforced upstream
        # by the registration flow (see UserRepository.get_by_email_global).
        result = await svc.login().execute(email=body.email, password=body.password)
        return LoginResponse(
            access_token=result.token,
            expires_at=result.expires_at,
            user=user_domain_to_response(
                result.user, workspace_id=result.workspace_id
            ),
        )

    return router


# Module-level instance — included by the main identity router aggregator.
auth_router = build_auth_router()