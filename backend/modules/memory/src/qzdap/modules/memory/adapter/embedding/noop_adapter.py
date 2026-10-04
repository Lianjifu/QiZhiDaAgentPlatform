"""NoOp embedding adapter.

Returns a deterministic 1536-dim zero vector for every input.  Useful
for dev environments without an OpenAI key or a running embedding_runtime.
"""

from __future__ import annotations

from qzdap.modules.memory.application.ports import EmbeddingPort
from qzdap.modules.memory.domain.entities import EMBEDDING_DIM


class NoOpEmbedding(EmbeddingPort):
    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self._dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self._dim for _ in texts]


NoOpEmbeddingAdapter = NoOpEmbedding

__all__ = ["NoOpEmbedding", "NoOpEmbeddingAdapter"]
