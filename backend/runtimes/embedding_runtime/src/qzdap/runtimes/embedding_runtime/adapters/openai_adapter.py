"""OpenAI embedding adapter for the runtime sidecar.

The API key is passed in by the composition root — it should be a
plain string resolved via ``qzdap_vault.VaultSecretsResolver``.  We do
NOT read ``OPENAI_API_KEY`` directly here; the secrets resolver owns
that.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx


@dataclass(slots=True)
class OpenAIAdapter:
    api_key: str
    model_name: str = "text-embedding-3-small"
    dim: int = 1536
    timeout_seconds: float = 30.0
    max_batch: int = 96
    base_url: str = "https://api.openai.com/v1"
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
            json={"input": texts, "model": self.model_name, "dimensions": self.dim},
        )
        resp.raise_for_status()
        body = resp.json()
        data = body["data"]
        if len(data) != len(texts):
            raise RuntimeError(
                f"OpenAI returned {len(data)} embeddings for {len(texts)} inputs"
            )
        data.sort(key=lambda d: d["index"])
        return [d["embedding"] for d in data]

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


__all__ = ["OpenAIAdapter"]
