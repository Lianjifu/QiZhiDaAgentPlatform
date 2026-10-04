"""OpenAI embedding adapter.

Calls ``https://api.openai.com/v1/embeddings`` directly.  This is what
``embedding_runtime`` uses when ``EMBEDDING_PROVIDER=openai``.

Key resolution goes through ``qzdap_vault.VaultSecretsResolver`` — the
caller passes a resolved secret string; we do NOT touch env vars here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from qzdap.modules.memory.application.ports import EmbeddingPort
from qzdap.modules.memory.domain.entities import EMBEDDING_DIM

_OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"


@dataclass(slots=True)
class OpenAIEmbeddingAdapter(EmbeddingPort):
    api_key: str
    model: str = "text-embedding-3-small"
    dim: int = EMBEDDING_DIM
    timeout_seconds: float = 30.0
    max_batch: int = 96  # OpenAI limit per request
    base_url: str = _OPENAI_EMBEDDINGS_URL
    _client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        return self._client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if len(texts) > self.max_batch:
            raise ValueError(
                f"batch too large: {len(texts)} > max_batch={self.max_batch}"
            )

        client = self._ensure_client()
        resp = await client.post(
            "/embeddings",
            json={"input": texts, "model": self.model, "dimensions": self.dim},
        )
        resp.raise_for_status()
        body = resp.json()
        # OpenAI returns embeddings in the "data" list; preserve input order.
        data = body["data"]
        if len(data) != len(texts):
            raise RuntimeError(
                f"OpenAI returned {len(data)} embeddings for {len(texts)} inputs"
            )
        # sort by index just in case
        data.sort(key=lambda d: d["index"])
        return [d["embedding"] for d in data]

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


__all__ = ["OpenAIEmbeddingAdapter"]
