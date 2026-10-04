"""Integration tests for identity module HTTP router.

These tests build a minimal FastAPI app wired to in-memory identity
adapters — no DB session — so the router-level auth header logic
(`X-Tenant-Id`, `X-User-Id`) and the `/users/me` literal-before-wildcard
ordering can be verified without the full composition stack.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from _identity_unit_in_memory import (  # type: ignore[import-not-found]
    FakeAccessTokenIssuer,
    FakeHasher,
    InMemoryAPIKeyRepository,
    InMemoryTenantRepository,
    InMemoryUserRepository,
    InMemoryWorkspaceRepository,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from qzdap.modules.identity.adapter.http.router import build_router
from qzdap.modules.identity.application.services import IdentityService
from qzdap.modules.identity.domain import Tenant, User


class _ErrorEnvelopeMiddleware(BaseHTTPMiddleware):
    """Mirrors the prod qzdap_http.error_envelope_middleware — converts
    AppError subclasses into JSON envelopes with the right status code."""

    async def dispatch(self, request, call_next):  # type: ignore[no-untyped-def]
        from qzdap_kernel.errors import AppError

        try:
            return await call_next(request)
        except AppError as e:
            from starlette.responses import JSONResponse

            return JSONResponse(
                content={
                    "code": e.code,
                    "message": e.message,
                    "trace_id": None,
                },
                status_code=e.status,
            )


def _build_app(
    hasher: FakeHasher | None = None,
) -> tuple[FastAPI, InMemoryTenantRepository, InMemoryUserRepository]:
    tenants = InMemoryTenantRepository()
    workspaces = InMemoryWorkspaceRepository()
    users = InMemoryUserRepository()
    api_keys = InMemoryAPIKeyRepository()
    active_hasher = hasher or FakeHasher()

    def factory_for_session(_session: Any) -> IdentityService:
        return IdentityService(
            tenants=tenants,
            workspaces=workspaces,
            users=users,
            api_keys=api_keys,
            hasher=active_hasher,
            issuer=FakeAccessTokenIssuer(),
        )

    class _Container:
        def session_factory(self) -> Any:
            class _NullSession:
                async def rollback(self_inner) -> None:
                    return None

                async def commit(self_inner) -> None:
                    return None

            class _Null:
                def session(self):
                    class _CM:
                        async def __aenter__(self_inner):
                            return _NullSession()

                        async def __aexit__(self_inner, *a):
                            return None

                    return _CM()

            return _Null()

    app = FastAPI()
    app.state.container = _Container()
    app.state.identity_factory = type(
        "F", (), {"for_session": staticmethod(factory_for_session)}
    )
    app.add_middleware(_ErrorEnvelopeMiddleware)
    app.include_router(build_router())
    return app, tenants, users


def _seed(
    tenants: InMemoryTenantRepository,
    users: InMemoryUserRepository,
    *,
    hashed_password: str | None = None,
) -> tuple[UUID, UUID]:
    tenant_id = uuid4()
    user_id = uuid4()
    asyncio_run = __import__("asyncio").run
    asyncio_run(
        tenants.add(
            Tenant.create(
                id=tenant_id,
                slug="acme",
                display_name="Acme",
            )
        )
    )
    asyncio_run(
        users.add(
            User.create(
                id=user_id,
                tenant_id=tenant_id,
                email="admin@acme.com",
                display_name="Admin",
                hashed_password=hashed_password,
            )
        )
    )
    return tenant_id, user_id


def test_get_users_me_returns_current_user() -> None:
    app, tenants, users = _build_app()
    tenant_id, user_id = _seed(tenants, users)
    client = TestClient(app)
    resp = client.get(
        "/v1/identity/users/me",
        headers={
            "X-Tenant-Id": str(tenant_id),
            "X-User-Id": str(user_id),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(user_id)
    assert body["tenant_id"] == str(tenant_id)
    assert body["email"] == "admin@acme.com"


def test_get_users_me_missing_user_id_header_returns_422() -> None:
    app, tenants, users = _build_app()
    tenant_id, _user_id = _seed(tenants, users)
    client = TestClient(app)
    resp = client.get(
        "/v1/identity/users/me",
        headers={"X-Tenant-Id": str(tenant_id)},
    )
    assert resp.status_code == 422


def test_get_users_me_wrong_tenant_returns_403() -> None:
    app, tenants, users = _build_app()
    _tenant_id, user_id = _seed(tenants, users)
    client = TestClient(app)
    resp = client.get(
        "/v1/identity/users/me",
        headers={
            "X-Tenant-Id": str(uuid4()),  # different tenant
            "X-User-Id": str(user_id),
        },
    )
    assert resp.status_code == 403


def test_get_users_me_nonexistent_user_returns_404() -> None:
    app, tenants, _users = _build_app()
    tenant_id, _user_id = _seed(tenants, _users)
    client = TestClient(app)
    resp = client.get(
        "/v1/identity/users/me",
        headers={
            "X-Tenant-Id": str(tenant_id),
            "X-User-Id": str(uuid4()),  # nonexistent user
        },
    )
    assert resp.status_code == 404


def test_get_tenants_current_returns_current_tenant() -> None:
    app, tenants, users = _build_app()
    tenant_id, _user_id = _seed(tenants, users)
    client = TestClient(app)
    resp = client.get(
        "/v1/identity/tenants/current",
        headers={"X-Tenant-Id": str(tenant_id)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(tenant_id)
    assert body["slug"] == "acme"
    assert body["status"] == "active"


def test_get_tenants_current_missing_tenant_returns_404() -> None:
    app, _tenants, _users = _build_app()
    client = TestClient(app)
    resp = client.get(
        "/v1/identity/tenants/current",
        headers={"X-Tenant-Id": str(uuid4())},
    )
    assert resp.status_code == 404


def test_get_tenants_current_missing_header_returns_422() -> None:
    app, _tenants, _users = _build_app()
    client = TestClient(app)
    resp = client.get("/v1/identity/tenants/current")
    assert resp.status_code == 422


def test_users_me_literal_takes_priority_over_uid_wildcard() -> None:
    """`/users/me` must match the literal handler, NOT `/users/{uid}`.

    Without the explicit ordering, FastAPI matches `/users/{uid}` first and
    422s on the non-UUID literal `me` before reaching our handler. This
    test exercises the 200 path to lock the ordering.
    """
    app, tenants, users = _build_app()
    tenant_id, user_id = _seed(tenants, users)
    client = TestClient(app)
    resp = client.get(
        "/v1/identity/users/me",
        headers={
            "X-Tenant-Id": str(tenant_id),
            "X-User-Id": str(user_id),
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == str(user_id)


def test_login_returns_user() -> None:
    """POST /login must return the resolved user payload alongside the token
    so the frontend can avoid the second /users/me round-trip."""
    hasher = FakeHasher()
    app, tenants, users = _build_app(hasher=hasher)
    tenant_id, user_id = _seed(
        tenants, users, hashed_password=hasher.hash("demo123456")
    )
    client = TestClient(app)
    resp = client.post(
        "/v1/identity/login",
        json={"email": "admin@acme.com", "password": "demo123456"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "Bearer"
    assert body["access_token"].startswith("token-")
    assert body["expires_at"] > 0
    assert body["user"]["id"] == str(user_id)
    assert body["user"]["tenant_id"] == str(tenant_id)
    assert body["user"]["email"] == "admin@acme.com"
    assert body["user"]["display_name"] == "Admin"


def test_login_with_bad_password_returns_401() -> None:
    hasher = FakeHasher()
    app, tenants, users = _build_app(hasher=hasher)
    _tenant_id, _user_id = _seed(
        tenants, users, hashed_password=hasher.hash("right")
    )
    client = TestClient(app)
    resp = client.post(
        "/v1/identity/login",
        json={"email": "admin@acme.com", "password": "wrong"},
    )
    assert resp.status_code == 401


def test_login_missing_tenant_id_field_returns_200() -> None:
    """Regression: legacy contract required tenant_id, but the login form
    never knew it. With the cross-tenant lookup the field is no longer
    required — verify the request shape is {email, password} only."""
    hasher = FakeHasher()
    app, tenants, users = _build_app(hasher=hasher)
    _tenant_id, _user_id = _seed(
        tenants, users, hashed_password=hasher.hash("demo123456")
    )
    client = TestClient(app)
    resp = client.post(
        "/v1/identity/login",
        json={"email": "admin@acme.com", "password": "demo123456"},
    )
    assert resp.status_code == 200, resp.text