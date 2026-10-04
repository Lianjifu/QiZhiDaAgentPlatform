"""Embedding runtime — FastAPI sidecar exposing ``POST /embed`` and ``GET /healthz``.

Three providers (selected via ``EMBEDDING_PROVIDER`` env var):
  - ``openai``  → calls OpenAI ``/v1/embeddings`` directly using an API key
                  resolved via ``qzdap_vault.VaultSecretsResolver``.
  - ``sbert``   → loads sentence-transformers locally (P10).
  - ``noop``    → returns 1536-dim zero vectors; dev only.

P10 will move this process out of the main backend pod into a true
sidecar; P4 only ships the skeleton + ``openai`` + ``noop`` providers.
"""

from qzdap.runtimes.embedding_runtime.app import create_app
from qzdap.runtimes.embedding_runtime.routes import build_router

__all__ = ["build_router", "create_app"]
