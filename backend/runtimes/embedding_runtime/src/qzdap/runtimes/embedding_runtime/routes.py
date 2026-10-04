"""HTTP routes for the embedding runtime sidecar."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from qzdap.runtimes.embedding_runtime.adapters import EmbeddingAdapter


class EmbedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: list[str] = Field(min_length=1, max_length=96)
    model: str | None = None
    dim: int | None = None


class EmbedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embeddings: list[list[float]]
    model: str
    dim: int


class HealthResponse(BaseModel):
    status: str
    provider: str


def adapter_dependency(request: Request) -> EmbeddingAdapter:
    adapter: EmbeddingAdapter | None = getattr(
        request.app.state, "embedding_adapter", None
    )
    if adapter is None:
        raise RuntimeError("embedding adapter not wired")
    return adapter


def build_router() -> APIRouter:
    router = APIRouter()

    @router.post("/embed", response_model=EmbedResponse)
    async def embed(
        body: EmbedRequest,
        adapter: Annotated[EmbeddingAdapter, Depends(adapter_dependency)],
    ) -> EmbedResponse:
        # honour per-request model/dim override only when caller matches defaults
        # we keep it simple for P4: ignore body.model/dim and use the wired adapter
        vectors = await adapter.embed(body.input)
        return EmbedResponse(
            embeddings=vectors, model=adapter.model_name, dim=adapter.dim
        )

    @router.get("/healthz", response_model=HealthResponse)
    async def healthz(
        adapter: Annotated[EmbeddingAdapter, Depends(adapter_dependency)],
    ) -> HealthResponse:
        from qzdap.runtimes.embedding_runtime.settings import get_settings

        return HealthResponse(
            status="ok", provider=get_settings().embedding_provider
        )

    return router


__all__ = ["EmbedRequest", "EmbedResponse", "HealthResponse", "build_router"]
