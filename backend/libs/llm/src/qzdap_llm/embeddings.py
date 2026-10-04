"""Convenience: top-level embed() / embed_many() against a default client."""

from __future__ import annotations

from qzdap_kernel.errors import ExternalServiceError

from qzdap_llm.client import LLMClient

_default: LLMClient | None = None


def set_default_client(client: LLMClient) -> None:
    global _default
    _default = client


def get_default_client() -> LLMClient:
    if _default is None:
        raise ExternalServiceError(
            "no default LLM client configured", code="LLM_NOT_CONFIGURED"
        )
    return _default


async def embed(texts: list[str]) -> list[list[float]]:
    return await get_default_client().embed(texts)


async def embed_many(text: str) -> list[float]:
    return (await embed([text]))[0]
