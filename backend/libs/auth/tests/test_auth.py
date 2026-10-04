"""Tests for auth."""

from __future__ import annotations

from uuid import uuid4

import jwt
import pytest
from qzdap_kernel.errors import AuthenticationError, ForbiddenError
from qzdap_kernel.principal import PrincipalType

from qzdap_auth.api_key import ApiKeyHasher, hash_api_key, verify_api_key
from qzdap_auth.dependencies import (
    AuthenticatedPrincipal,
    get_principal,
    require_role,
    require_scope,
)
from qzdap_auth.jwt import JWTConfig, JWTIssuer, JWTVerifier


@pytest.fixture
def cfg() -> JWTConfig:
    return JWTConfig(
        secret="unit-test-secret-not-for-production-use",
        algorithm="HS256",
        issuer="qzdap-test",
        audience="qzdap-api",
        access_ttl_seconds=60,
    )


@pytest.fixture
def issuer(cfg: JWTConfig) -> JWTIssuer:
    return JWTIssuer(cfg)


@pytest.fixture
def verifier(cfg: JWTConfig) -> JWTVerifier:
    return JWTVerifier(cfg)


def test_issue_and_verify_round_trip(issuer: JWTIssuer, verifier: JWTVerifier) -> None:
    token, exp = issuer.issue_access_token(
        principal_id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=uuid4(),
        roles=frozenset({"workspace_owner"}),
        scopes=frozenset({"agents:invoke"}),
    )
    claims = verifier.verify(token)
    assert claims["roles"] == ["workspace_owner"]
    assert exp > 0


def test_verify_rejects_expired(verifier: JWTVerifier) -> None:
    payload = {
        "sub": str(uuid4()),
        "tid": str(uuid4()),
        "iss": "qzdap-test",
        "aud": "qzdap-api",
        "iat": 0,
        "exp": 1,
        "roles": [],
        "scopes": [],
    }
    token = jwt.encode(
        payload, "unit-test-secret-not-for-production-use", algorithm="HS256"
    )
    with pytest.raises(AuthenticationError) as exc:
        verifier.verify(token)
    assert exc.value.code == "TOKEN_EXPIRED"


def test_get_principal_requires_bearer(verifier: JWTVerifier) -> None:
    with pytest.raises(AuthenticationError):
        asyncio_get_principal(verifier, None)


def test_get_principal_parses_claims(issuer: JWTIssuer, verifier: JWTVerifier) -> None:
    uid, tid = uuid4(), uuid4()
    token, _ = issuer.issue_access_token(
        principal_id=uid,
        tenant_id=tid,
        workspace_id=None,
        roles=frozenset({"workspace_owner"}),
    )
    ap = asyncio_get_principal(verifier, f"Bearer {token}")
    assert isinstance(ap, AuthenticatedPrincipal)
    assert ap.principal.id == uid
    assert ap.tenant_id == tid
    assert ap.principal.type is PrincipalType.USER


def test_require_role_blocks_wrong_role(
    issuer: JWTIssuer, verifier: JWTVerifier
) -> None:
    token, _ = issuer.issue_access_token(
        principal_id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=None,
        roles=frozenset({"workspace_member"}),
    )
    ap = asyncio_get_principal(verifier, f"Bearer {token}")
    with pytest.raises(ForbiddenError):
        require_role("platform_admin")(ap)


def test_require_scope_blocks_missing_scope(
    issuer: JWTIssuer, verifier: JWTVerifier
) -> None:
    token, _ = issuer.issue_access_token(
        principal_id=uuid4(),
        tenant_id=uuid4(),
        workspace_id=None,
        roles=frozenset(),
        scopes=frozenset(),
    )
    ap = asyncio_get_principal(verifier, f"Bearer {token}")
    with pytest.raises(ForbiddenError):
        require_scope("tools:invoke")(ap)


def test_api_key_hash_round_trip() -> None:
    h = hash_api_key("raw_secret_value")
    assert verify_api_key("raw_secret_value", h)
    assert not verify_api_key("wrong_value", h)


def test_api_key_hasher_default_rounds() -> None:
    h = ApiKeyHasher()
    ph = h.hash("k")
    assert ph.startswith("$argon2id$")


# Helper: pytest-asyncio is configured in pyproject; provide a sync shim
def asyncio_get_principal(
    verifier: JWTVerifier, authorization: str | None
) -> AuthenticatedPrincipal:
    import asyncio

    return asyncio.run(get_principal(verifier, authorization))
