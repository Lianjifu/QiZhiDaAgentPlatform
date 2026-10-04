"""NoOp embedding adapter for the runtime sidecar."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class NoOpAdapter:
    model_name: str = "noop"
    dim: int = 1536

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self.dim for _ in texts]


__all__ = ["NoOpAdapter"]
