"""Authentication: JWT, API keys, FastAPI auth dependency."""

from qzdap_auth.api_key import ApiKeyHasher, hash_api_key, verify_api_key
from qzdap_auth.dependencies import (
    AuthenticatedPrincipal,
    get_principal,
    require_authenticated,
    require_role,
    require_scope,
)
from qzdap_auth.jwt import JWTConfig, JWTIssuer, JWTVerifier, issue_access_token
from qzdap_auth.middleware import AuthMiddleware
from qzdap_auth.workspace_guard_dep import _require_active_workspace

__all__ = [
    "ApiKeyHasher",
    "AuthMiddleware",
    "AuthenticatedPrincipal",
    "JWTConfig",
    "JWTIssuer",
    "JWTVerifier",
    "_require_active_workspace",
    "get_principal",
    "hash_api_key",
    "issue_access_token",
    "require_authenticated",
    "require_role",
    "require_scope",
    "verify_api_key",
]
