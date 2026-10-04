"""Unit tests for the identity domain (no DB)."""

from __future__ import annotations

import re
from uuid import uuid4

import pytest

from qzdap.modules.identity.domain import (
    APIKey,
    APIKeyStatus,
    Tenant,
    TenantStatus,
    User,
    Workspace,
    WorkspaceStatus,
)
from qzdap.modules.identity.domain.errors import (
    TenantAlreadyExists,
    WorkspaceAlreadyExists,
    WorkspaceLimitReached,
    WorkspaceNotFound,
)


def test_tenant_create_validates_slug() -> None:
    with pytest.raises(ValueError, match="invalid tenant slug"):
        Tenant.create(id=uuid4(), slug="UPPER", display_name="X")
    with pytest.raises(ValueError, match="invalid tenant slug"):
        Tenant.create(id=uuid4(), slug="x", display_name="X")


def test_tenant_create_and_event() -> None:
    t = Tenant.create(id=uuid4(), slug="acme", display_name="Acme Inc")
    assert t.status is TenantStatus.ACTIVE
    e = t.raise_created_event()
    assert e.tenant_id == t.id
    assert e.slug == "acme"


def test_workspace_must_have_tenant() -> None:
    w = Workspace.create(id=uuid4(), tenant_id=uuid4(), slug="ops", display_name="Ops")
    assert w.status is WorkspaceStatus.ACTIVE
    e = w.raise_created_event()
    assert e.workspace_id == w.id


def test_user_email_validation() -> None:
    with pytest.raises(ValueError, match="invalid email"):
        User.create(
            id=uuid4(), tenant_id=uuid4(), email="not-an-email", display_name="X"
        )
    u = User.create(id=uuid4(), tenant_id=uuid4(), email="hi@x.com", display_name="Hi")
    assert u.email == "hi@x.com"
    assert u.raise_registered_event().user_id == u.id


def test_api_key_issue_then_revoke() -> None:
    raw = APIKey.generate_secret()
    k, returned_raw = APIKey.issue(
        id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=None,
        owner_user_id=uuid4(),
        name="prod",
        hashed_secret="hash",
        raw_secret=raw,
    )
    assert returned_raw == raw
    assert k.prefix == raw[:8]
    assert k.status is APIKeyStatus.ACTIVE
    revoked = k.revoke()
    assert revoked.status is APIKeyStatus.REVOKED
    assert revoked.raise_revoked_event().api_key_id == k.id


def test_api_key_generate_secret_urlsafe() -> None:
    s = APIKey.generate_secret()
    assert re.match(r"^[A-Za-z0-9_\-]{40,}$", s)


def test_error_codes() -> None:
    assert TenantAlreadyExists("x").code == "TENANT_ALREADY_EXISTS"
    assert WorkspaceAlreadyExists("x").code == "WORKSPACE_ALREADY_EXISTS"
    assert WorkspaceNotFound("x").code == "WORKSPACE_NOT_FOUND"
    assert WorkspaceLimitReached("x").code == "WORKSPACE_LIMIT_REACHED"


def test_workspace_create_validates_slug() -> None:
    with pytest.raises(ValueError):
        Workspace.create(
            id=uuid4(), tenant_id=uuid4(), slug="bad slug!", display_name="x"
        )
