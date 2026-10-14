"""Discover model IDs from provider catalogs, never a static local list."""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit, urlunsplit

import httpx
from qzdap_llm.providers import get_provider_spec

from qzdap.modules.model.adapter.llm.connectivity_tester import (
    PublicNetworkTransport,
    validate_provider_url,
)
from qzdap.modules.model.application.ports import (
    CatalogDiscoveryUnsupported,
    CatalogProber,
)

ANTHROPIC_VERSION = "2023-06-01"
_MAX_PAGES = 50


class HttpCatalogProber(CatalogProber):
    def __init__(self, *, timeout_seconds: float = 12.0) -> None:
        self._timeout = timeout_seconds

    async def list_models(
        self, *, api_key: str, base_url: str, protocol: str
    ) -> list[str]:
        protocol = protocol.lower()
        spec = get_provider_spec(protocol)
        base_url = base_url.strip() or spec.default_base_url
        validate_provider_url(base_url, protocol)
        if protocol in {"azure", "glm"}:
            raise CatalogDiscoveryUnsupported("供应商没有可用的自动目录契约。")
        async with asyncio.timeout(self._timeout):
            async with httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=False,
                trust_env=False,
                transport=PublicNetworkTransport(),
            ) as client:
                if protocol == "google":
                    return await self._google(client, api_key, base_url)
                if protocol == "qwen":
                    return await self._qwen(client, api_key, base_url)
                if protocol in {"anthropic", "anthropic-compatible"}:
                    return await self._anthropic(client, api_key, base_url, protocol)
                return await self._openai(client, api_key, base_url)

    async def _openai(
        self, client: httpx.AsyncClient, key: str, base: str
    ) -> list[str]:
        data = await _get_json(
            client, _endpoint(base, "/models"), {"Authorization": f"Bearer {key}"}
        )
        items = data.get("data") if isinstance(data, dict) else data
        return _extract_ids(items)

    async def _anthropic(
        self, client: httpx.AsyncClient, key: str, base: str, protocol: str
    ) -> list[str]:
        parts = urlsplit(base)
        path = parts.path.rstrip("/").removesuffix("/v1")
        # DeepSeek exposes the catalog separately from its Messages endpoint.
        if protocol == "anthropic-compatible" and (
            parts.scheme == "https"
            and parts.hostname == "api.deepseek.com"
            and parts.port in {None, 443}
            and path == "/anthropic"
        ):
            root = urlunsplit(parts._replace(path="", query="", fragment=""))
            return await self._openai(client, key, root)
        url = urlunsplit(parts._replace(path=path + "/v1/models"))
        headers = {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION}
        models: list[str] = []
        params: dict[str, str] = {}
        seen: set[str] = set()
        for _ in range(_MAX_PAGES):
            data = await _get_json(client, url, headers, params)
            if not isinstance(data, dict):
                raise TypeError("invalid catalog")
            models.extend(_extract_ids(data.get("data")))
            if not data.get("has_more"):
                return list(dict.fromkeys(models))
            last_id = data.get("last_id")
            if not isinstance(last_id, str) or not last_id or last_id in seen:
                raise ValueError("invalid catalog pagination")
            seen.add(last_id)
            params["after_id"] = last_id
        raise ValueError("catalog exceeds pagination budget")

    async def _google(
        self, client: httpx.AsyncClient, key: str, base: str
    ) -> list[str]:
        models: list[str] = []
        params = {"pageSize": "100"}
        seen: set[str] = set()
        for _ in range(_MAX_PAGES):
            data = await _get_json(
                client, _endpoint(base, "/models"), {"x-goog-api-key": key}, params
            )
            if not isinstance(data, dict) or not isinstance(data.get("models"), list):
                raise TypeError("invalid catalog")
            for item in data["models"]:
                if not isinstance(item, dict) or "generateContent" not in item.get(
                    "supportedGenerationMethods", []
                ):
                    continue
                name = item.get("name")
                if isinstance(name, str) and name.strip():
                    models.append(name.removeprefix("models/"))
            token = data.get("nextPageToken")
            if not token:
                return list(dict.fromkeys(models))
            if not isinstance(token, str) or token in seen:
                raise ValueError("invalid catalog pagination")
            seen.add(token)
            params["pageToken"] = token
        raise ValueError("catalog exceeds pagination budget")

    async def _qwen(self, client: httpx.AsyncClient, key: str, base: str) -> list[str]:
        parts = urlsplit(base)
        host = parts.hostname or ""
        if not (
            host.endswith(".maas.aliyuncs.com")
            or host
            in {
                "dashscope.aliyuncs.com",
                "dashscope-intl.aliyuncs.com",
                "dashscope-us.aliyuncs.com",
            }
        ):
            raise CatalogDiscoveryUnsupported("Qwen目录需要官方区域或工作区地址。")
        url = urlunsplit(parts._replace(path="/api/v1/models", query=""))
        headers = {"Authorization": f"Bearer {key}"}
        models: list[str] = []
        for page in range(1, _MAX_PAGES + 1):
            data = await _get_json(
                client,
                url,
                headers,
                {
                    "providers": "qwen",
                    "capabilities": "TG",
                    "page_no": str(page),
                    "page_size": "100",
                },
            )
            output = data.get("output") if isinstance(data, dict) else None
            if not isinstance(output, dict) or not isinstance(
                output.get("models"), list
            ):
                raise TypeError("invalid catalog")
            items = output["models"]
            models.extend(_extract_ids(items, id_keys=("model",)))
            total = output.get("total")
            if not isinstance(total, int) or total < 0:
                raise ValueError("invalid catalog pagination")
            if page * 100 >= total:
                return list(dict.fromkeys(models))
            if not items:
                raise ValueError("incomplete catalog")
        raise ValueError("catalog exceeds pagination budget")


async def _get_json(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    params: dict[str, str] | None = None,
) -> object:
    response = await client.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()


def _endpoint(base: str, suffix: str) -> str:
    parts = urlsplit(base)
    return urlunsplit(parts._replace(path=parts.path.rstrip("/") + suffix))


def _extract_ids(
    items: object, *, id_keys: tuple[str, ...] = ("id", "name")
) -> list[str]:
    if not isinstance(items, list):
        raise TypeError("invalid catalog")
    names: list[str] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
        elif isinstance(item, dict):
            for key in id_keys:
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    names.append(value.strip())
                    break
    return list(dict.fromkeys(names))


__all__ = ["CatalogDiscoveryUnsupported", "HttpCatalogProber"]
