"""Tests for the kernel package."""

from __future__ import annotations

import pytest

from qzdap_kernel.contexts import TenantWorkspaceContext, WorkspaceContext
from qzdap_kernel.contextvars import bind_trace_id, current_trace_id, new_trace_id
from qzdap_kernel.errors import (
    AppError,
    AuthenticationError,
    BusinessRuleError,
    ConflictError,
    ExternalServiceError,
    ForbiddenError,
    InternalError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from qzdap_kernel.principal import Principal, PrincipalType

# ── contextvars ──────────────────────────────────────────────────────────────


def test_new_trace_id_format() -> None:
    tid = new_trace_id()
    assert len(tid) == 32
    assert tid == tid.lower()


def test_bind_and_current_trace_id() -> None:
    bind_trace_id("test-trace-123")
    assert current_trace_id() == "test-trace-123"


def test_bind_auto_generates() -> None:
    tid = bind_trace_id()
    assert tid is not None
    assert len(tid) == 32


# ── contexts ─────────────────────────────────────────────────────────────────


def test_workspace_context_implies_tenant() -> None:
    ctx = WorkspaceContext.__new__(WorkspaceContext)
    # Just ensure constructor shape
    from uuid import UUID

    ctx = WorkspaceContext(tenant_id=UUID(int=1), workspace_id=UUID(int=2))
    assert ctx.tenant_id.int == 1
    assert ctx.workspace_id.int == 2


def test_tenant_workspace_to_workspace_requires_workspace_id() -> None:
    from uuid import UUID

    t = UUID(int=1)
    ctx = TenantWorkspaceContext(tenant_id=t, workspace_id=None)
    with pytest.raises(ValueError):
        ctx.to_workspace()


def test_tenant_workspace_to_workspace_ok() -> None:
    from uuid import UUID

    t = UUID(int=1)
    w = UUID(int=2)
    ctx = TenantWorkspaceContext(tenant_id=t, workspace_id=w)
    ws = ctx.to_workspace()
    assert ws.tenant_id == t
    assert ws.workspace_id == w


# ── principal ────────────────────────────────────────────────────────────────


def test_user_requires_tenant() -> None:
    from uuid import UUID

    with pytest.raises(ValueError, match="requires tenant_id"):
        Principal(
            id=UUID(int=1),
            type=PrincipalType.USER,
            tenant_id=None,
            workspace_id=None,
        )


def test_system_may_have_no_tenant() -> None:

    p = Principal.system()
    assert p.type is PrincipalType.SYSTEM
    assert p.tenant_id is None
    assert p.is_platform_admin() is False


def test_with_workspace_returns_new_principal() -> None:
    from uuid import UUID

    p = Principal(
        id=UUID(int=1),
        type=PrincipalType.USER,
        tenant_id=UUID(int=1),
        workspace_id=None,
    )
    p2 = p.with_workspace(UUID(int=2))
    assert p.workspace_id is None
    assert p2.workspace_id == UUID(int=2)


def test_has_role_and_scope() -> None:
    from uuid import UUID

    p = Principal(
        id=UUID(int=1),
        type=PrincipalType.USER,
        tenant_id=UUID(int=1),
        workspace_id=None,
        roles=frozenset({"workspace_owner"}),
        scopes=frozenset({"agents:invoke"}),
    )
    assert p.has_role("workspace_owner")
    assert p.has_scope("agents:invoke")
    assert not p.has_role("platform_admin")


# ── errors ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "cls,code,status",
    [
        (ValidationError, "VALIDATION_ERROR", 400),
        (AuthenticationError, "AUTHENTICATION_FAILED", 401),
        (ForbiddenError, "FORBIDDEN", 403),
        (NotFoundError, "NOT_FOUND", 404),
        (ConflictError, "CONFLICT", 409),
        (BusinessRuleError, "BUSINESS_RULE_VIOLATED", 422),
        (RateLimitError, "RATE_LIMITED", 429),
        (ExternalServiceError, "EXTERNAL_SERVICE_ERROR", 502),
        (InternalError, "INTERNAL_ERROR", 500),
    ],
)
def test_app_error_subclass_codes(cls: type[AppError], code: str, status: int) -> None:
    e = cls("bad")
    assert e.code == code
    assert e.status == status
    env = e.to_envelope(trace_id="abc")
    assert env.code == code
    assert env.status == status
    assert env.trace_id == "abc"
    d = env.to_dict()
    assert d["code"] == code
    assert d["status"] == status


def test_custom_code_overrides() -> None:
    e = ValidationError("bad email", code="INVALID_EMAIL")
    assert e.code == "INVALID_EMAIL"


def test_details_propagate() -> None:
    e = ValidationError("bad", details={"field": "email"})
    env = e.to_envelope("t")
    assert env.details == {"field": "email"}
    assert env.to_dict()["details"] == {"field": "email"}


def test_app_error_is_exception() -> None:
    with pytest.raises(AppError):
        raise ValidationError("x")
