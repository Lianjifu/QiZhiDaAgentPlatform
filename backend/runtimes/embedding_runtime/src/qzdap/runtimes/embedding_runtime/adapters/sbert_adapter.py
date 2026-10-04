"""SBERT (sentence-transformers) adapter — stub for P10.

P4 only registers the module + factory; the actual model loading is left
to P10.  Importing torch + transformers is heavy, so we lazy-load.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SBERTAdapter:
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    dim: int = (
        384  # MiniLM is 384-dim; doc 12 keeps 1536 default for text-embedding-3-small
    )
    _model: object = field(default=None, init=False, repr=False)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(
            "SBERT embedding provider ships in P10; set EMBEDDING_PROVIDER=openai or noop"
        )


__all__ = ["SBERTAdapter"]
