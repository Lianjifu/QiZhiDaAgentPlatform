"""Probe provider `/models` endpoints for OpenAI-compatible and Anthropic protocols."""

from __future__ import annotations

import httpx

from qzdap.modules.model.application.ports import CatalogProber

# Anthropic's `/v1/models` requires this version header on every call.
ANTHROPIC_VERSION = "2023-06-01"


class HttpCatalogProber(CatalogProber):
    def __init__(self, *, timeout_seconds: float = 12.0) -> None:
        self._timeout = timeout_seconds

    async def list_models(self, *, api_key: str, base_url: str, protocol: str) -> list[str]:
        protocol = (protocol or "").lower()
        if protocol == "anthropic":
            return await self._list_anthropic(api_key=api_key, base_url=base_url)
        return await self._list_openai_compatible(api_key=api_key, base_url=base_url)

    async def _list_openai_compatible(self, *, api_key: str, base_url: str) -> list[str]:
        url = base_url.rstrip("/") + "/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        items = data.get("data") if isinstance(data, dict) else data
        return _extract_ids(items)

    async def _list_anthropic(self, *, api_key: str, base_url: str) -> list[str]:
        url = base_url.rstrip("/") + "/v1/models"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        items = data.get("data") if isinstance(data, dict) else None
        return _extract_ids(items, id_keys=("id", "name"))


def _extract_ids(items: object, *, id_keys: tuple[str, ...] = ("id", "name")) -> list[str]:
    names: list[str] = []
    if not isinstance(items, list):
        return names
    for item in items:
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
        elif isinstance(item, dict):
            ident: str | None = None
            for key in id_keys:
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    ident = value.strip()
                    break
            if ident:
                names.append(ident)
    return names


__all__ = ["HttpCatalogProber"]
