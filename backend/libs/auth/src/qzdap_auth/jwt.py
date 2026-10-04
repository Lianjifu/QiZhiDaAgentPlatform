"""JWT issuer + verifier.

`JWTIssuer.issue_access_token(...)` returns a signed compact JWS carrying
`sub`, `tid` (tenant), `wid` (workspace), `roles`, `scopes`, `exp`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import jwt
from qzdap_kernel.errors import AuthenticationError


@dataclass(slots=True, frozen=True)
class JWTConfig:
    secret: str
    algorithm: str = "HS256"
    issuer: str = "qzdap-dev"
    audience: str = "qzdap-api"
    access_ttl_seconds: int = 3600

    def __post_init__(self) -> None:
        if self.algorithm != "HS256" and self.secret.startswith("dev-"):
            raise ValueError(
                "Refusing to use a dev-prefixed secret with a non-HS256 algorithm. "
                "Configure a real secret via secret manager before deploying."
            )


@dataclass(slots=True, frozen=True)
class JWTIssuer:
    config: JWTConfig

    def issue_access_token(
        self,
        *,
        principal_id: UUID,
        tenant_id: UUID,
        workspace_id: UUID | None,
        roles: frozenset[str],
        scopes: frozenset[str] | None = None,
        ttl_seconds: int | None = None,
    ) -> tuple[str, int]:
        now = int(time.time())
        exp = now + (ttl_seconds or self.config.access_ttl_seconds)
        payload: dict[str, Any] = {
            "sub": str(principal_id),
            "tid": str(tenant_id),
            "wid": str(workspace_id) if workspace_id else None,
            "roles": list(roles),
            "scopes": list(scopes or []),
            "iss": self.config.issuer,
            "aud": self.config.audience,
            "iat": now,
            "exp": exp,
            "jti": str(uuid4()),
        }
        token = jwt.encode(payload, self.config.secret, algorithm=self.config.algorithm)
        return token, exp


@dataclass(slots=True, frozen=True)
class JWTVerifier:
    config: JWTConfig

    def verify(self, token: str) -> dict[str, Any]:
        try:
            return jwt.decode(
                token,
                self.config.secret,
                algorithms=[self.config.algorithm],
                audience=self.config.audience,
                issuer=self.config.issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.ExpiredSignatureError as e:
            raise AuthenticationError("token expired", code="TOKEN_EXPIRED") from e
        except jwt.InvalidTokenError as e:
            raise AuthenticationError("invalid token", code="TOKEN_INVALID") from e


def issue_access_token(issuer: JWTIssuer, **kwargs: Any) -> str:
    return issuer.issue_access_token(**kwargs)[0]


# Imported at top of file; kept here for lazy use in callers
from uuid import uuid4
