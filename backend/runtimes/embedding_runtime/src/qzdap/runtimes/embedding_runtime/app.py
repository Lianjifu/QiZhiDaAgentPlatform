"""FastAPI app factory for the embedding runtime sidecar.

Composition root pattern: ``create_app()`` builds an app with the
selected provider wired into ``app.state.embedding_adapter``.

All configuration flows through :class:`Settings` (pydantic-settings
with the ``QZDAP_`` prefix) so the ``QZDAP_OPENAI_API_KEY_REF`` indirection
that the main composition app uses actually wires through. Tests
pass ``adapter=`` directly to skip the provider resolver.
"""

from __future__ import annotations

from fastapi import FastAPI

from qzdap.runtimes.embedding_runtime.adapters import EmbeddingAdapter
from qzdap.runtimes.embedding_runtime.adapters.noop_adapter import NoOpAdapter
from qzdap.runtimes.embedding_runtime.adapters.openai_adapter import OpenAIAdapter
from qzdap.runtimes.embedding_runtime.routes import build_router
from qzdap.runtimes.embedding_runtime.settings import get_settings


def _build_adapter(
    *,
    provider: str,
    openai_api_key: str,
    openai_base_url: str,
    openai_model: str,
    openai_dim: int,
) -> EmbeddingAdapter:
    p = provider.lower()
    if p == "noop":
        return NoOpAdapter()
    if p == "openai":
        if not openai_api_key:
            raise RuntimeError(
                "QZDAP_OPENAI_API_KEY required when QZDAP_EMBEDDING_PROVIDER=openai"
            )
        return OpenAIAdapter(
            api_key=openai_api_key,
            base_url=openai_base_url,
            model_name=openai_model,
            dim=openai_dim,
        )
    if p == "sbert":
        from qzdap.runtimes.embedding_runtime.adapters.sbert_adapter import (
            SBERTAdapter,
        )

        return SBERTAdapter()
    raise RuntimeError(f"unknown QZDAP_EMBEDDING_PROVIDER: {provider!r}")


def create_app(
    *,
    provider: str | None = None,
    openai_api_key: str | None = None,
    adapter: EmbeddingAdapter | None = None,
) -> FastAPI:
    """Build the embedding runtime FastAPI app.

    Tests pass ``adapter=`` directly; production passes ``provider=`` and
    ``openai_api_key=`` resolved from the secrets resolver — both fall
    back to the Settings values so a misconfigured pod still has a
    consistent default behaviour.
    """
    app = FastAPI(title="qzdap-embedding-runtime", version="0.1.0")
    if adapter is None:
        settings = get_settings()
        resolved_provider = provider or settings.embedding_provider
        resolved_key = openai_api_key or settings.openai_api_key
        adapter = _build_adapter(
            provider=resolved_provider,
            openai_api_key=resolved_key,
            openai_base_url=settings.openai_base_url,
            openai_model=settings.openai_model,
            openai_dim=settings.openai_dim,
        )
    app.state.embedding_adapter = adapter
    app.include_router(build_router())
    return app


__all__ = ["create_app"]
