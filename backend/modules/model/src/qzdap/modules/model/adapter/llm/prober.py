"""Probe OpenAI-compatible `/models` endpoints; fall back on empty list."""

from __future__ import annotations

import httpx

from qzdap.modules.model.application.ports import CatalogProber


class HttpCatalogProber(CatalogProber):
    def __init__(self, *, timeout_seconds: float = 12.0) -> None:
        self._timeout = timeout_seconds

    async def list_models(self, *, api_key: str, base_url: str, protocol: str) -> list[str]:
        _ = protocol
        url = base_url.rstrip("/") + "/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        items = data.get("data") if isinstance(data, dict) else data
        names: list[str] = []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, str) and item.strip():
                    names.append(item.strip())
                elif isinstance(item, dict):
                    ident = item.get("id") or item.get("name")
                    if ident:
                        names.append(str(ident))
        return names


__all__ = ["HttpCatalogProber"]
