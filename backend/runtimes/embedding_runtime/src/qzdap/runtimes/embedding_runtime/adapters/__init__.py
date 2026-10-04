"""Embedding adapter Protocol for the runtime sidecar.

The runtime selects one concrete adapter (``OpenAI`` / ``SBERT`` /
``NoOp``) at startup time based on the ``EMBEDDING_PROVIDER`` env var.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingAdapter(Protocol):
    """Converts text → fixed-dim vector.

    The runtime always calls ``embed([text, ...])``; the implementation
    may batch internally.
    """

    model_name: str
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


__all__ = ["EmbeddingAdapter"]
