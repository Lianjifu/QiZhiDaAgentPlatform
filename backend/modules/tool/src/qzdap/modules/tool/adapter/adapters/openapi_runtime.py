"""OpenAPI runtime adapter.

Given an operation `(method, path, operation_id)` extracted at registration,
construct the outbound HTTP request, inject auth headers (no raw secrets
in JSONB — `secrets_ref` is resolved by `SecretsResolver`), and dispatch.

Argument routing rules:
  - `arguments["path"]` (dict) merged into the URL path placeholders
  - `arguments["query"]` (dict) → query string
  - `arguments["body"]` (dict) → JSON body (for non-GET methods)
  - everything else → also folded into the JSON body

If the spec has no body the call returns a JSON-parsed response body.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote

import httpx
from qzdap_vault.actor import ActorContext
from qzdap_vault.errors import VaultError
from qzdap_vault.resolver import VaultSecretsResolver as SecretsResolver

from qzdap.modules.tool.domain import AuthConfig, AuthConfigType, SpecOperation

# Adapter from the qzdap_vault Protocol to the legacy Callable-style resolver
# that the OpenAPI/MCP runtimes already accept.  Resolves ``secrets_ref``
# using the env/file vault layer (P5 step 8 wiring).
VaultSecretsCallable = Callable[[str, ActorContext], Awaitable[dict[str, str]]]


async def _no_op_secrets_resolver(ref: str, actor: ActorContext) -> dict[str, str]:
    return {}


def _adapter(resolver: SecretsResolver) -> VaultSecretsCallable:
    """Wrap an qzdap_vault ``VaultSecretsResolver`` Protocol impl.

    Accepts either:
    - an object with an async ``resolve(ref, *, actor)`` method, or
    - a bare async function ``async def f(ref, *, actor)``.
    """

    async def _call(ref: str, actor: ActorContext) -> dict[str, str]:
        try:
            if hasattr(resolver, "resolve"):
                payload = await resolver.resolve(ref, actor=actor)  # type: ignore[attr-defined]
            else:
                payload = await resolver(ref, actor=actor)  # type: ignore[operator,call-arg]
            # vault may return a dict or a bare string (legacy callers)
            if isinstance(payload, str):
                return {"value": payload}
            return dict(payload) if payload else {}
        except VaultError:
            # Vault lookup failed (ref / perm / network) → surface as
            # empty payload so the openapi call can proceed without
            # secrets. Other exceptions (programming errors) propagate.
            return {}

    return _call


def _inject_path(path: str, params: dict[str, Any]) -> str:
    out = path
    for k, v in params.items():
        out = out.replace("{" + k + "}", quote(str(v), safe=""))
    return out


class OpenAPIRuntimeAdapter:
    def __init__(
        self,
        *,
        http: httpx.AsyncClient,
        secrets_resolver: SecretsResolver | None = None,
    ) -> None:
        self._http = http
        self._secrets = (
            _adapter(secrets_resolver)
            if secrets_resolver is not None
            else _no_op_secrets_resolver
        )

    async def invoke(
        self,
        *,
        base_url: str,
        operation: SpecOperation,
        auth: AuthConfig | None,
        arguments: dict,
        timeout: float,
        actor: ActorContext | None = None,
    ) -> dict:
        path_params = arguments.get("path") or {}
        query_params = arguments.get("query") or {}
        body: Any = arguments.get("body")
        if body is None:
            extra = {
                k: v for k, v in arguments.items() if k not in {"path", "query", "body"}
            }
            if extra:
                body = extra

        url = _inject_path(base_url.rstrip("/") + operation.path, path_params)
        headers: dict[str, str] = {"Accept": "application/json"}
        if auth is not None:
            ctx = actor or ActorContext.anonymous(
                tenant_id=__import__("uuid").UUID(int=0)
            )
            headers.update(await self._inject_auth(auth, ctx))

        method = operation.method.upper()
        kwargs: dict[str, Any] = {
            "headers": headers,
            "params": query_params,
            "timeout": timeout,
        }
        if body is not None and method != "GET":
            kwargs["json"] = body
        elif body is not None and method == "GET":
            extra_q = kwargs.get("params") or {}
            if isinstance(body, dict):
                extra_q.update(body)
            kwargs["params"] = extra_q

        resp = await self._http.request(method, url, **kwargs)
        resp.raise_for_status()
        if not resp.content:
            return {}
        return resp.json()

    async def _inject_auth(
        self, auth: AuthConfig, actor: ActorContext
    ) -> dict[str, str]:
        headers: dict[str, str] = {}
        if auth.type is AuthConfigType.NONE or not auth.secrets_ref:
            return headers
        secret = await self._secrets(auth.secrets_ref, actor)
        if auth.type is AuthConfigType.BEARER:
            token = secret.get("token") or secret.get("value", "")
            if token:
                headers["Authorization"] = f"Bearer {token}"
        elif auth.type is AuthConfigType.API_KEY:
            header_name = secret.get("header", "X-Api-Key")
            api_key = secret.get("api_key") or secret.get("value", "")
            if api_key:
                headers[header_name] = api_key
        elif auth.type is AuthConfigType.OAUTH2:
            token = secret.get("access_token") or secret.get("value", "")
            if token:
                headers["Authorization"] = f"Bearer {token}"
        return headers
