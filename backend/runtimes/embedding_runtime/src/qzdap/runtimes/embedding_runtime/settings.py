"""Settings for the embedding runtime sidecar (QZDAP_-prefixed env).

Centralises every env var the embedding_runtime reads so the boot
path does not touch ``os.environ`` directly. Mirrors the pattern
used by ``composition/qzdap_app/.../settings.py`` — pydantic-settings
``BaseSettings`` with the ``QZDAP_`` prefix.

Previously the runtime read ``OPENAI_API_KEY`` and
``EMBEDDING_PROVIDER`` without the prefix, which silently bypassed
the QZDAP_*_REF indirection that the main app uses to inject secrets
from CSI / Vault / file / env. The fix is to standardise on
``QZDAP_EMBEDDING_PROVIDER`` / ``QZDAP_OPENAI_API_KEY`` everywhere so
``QZDAP_OPENAI_API_KEY_REF=vault:...`` actually wires through.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="QZDAP_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    embedding_provider: Literal["noop", "openai", "sbert"] = "noop"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "text-embedding-3-small"
    openai_dim: int = 1536


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def reset_settings_cache() -> None:
    get_settings.cache_clear()


__all__ = ["Settings", "get_settings", "reset_settings_cache"]