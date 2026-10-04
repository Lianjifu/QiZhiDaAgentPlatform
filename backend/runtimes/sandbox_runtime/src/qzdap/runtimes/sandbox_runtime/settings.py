"""Settings for the sandbox runtime sidecar (QZDAP_-prefixed env)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_IMAGE = "qzdap/sandbox-python:latest"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="QZDAP_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    sandbox_executor: Literal["gvisor", "stub"] = "gvisor"
    sandbox_runtime_secret: str = "dev-sandbox-runtime-secret-change-me"
    sandbox_images: str = DEFAULT_IMAGE
    sandbox_default_image: str = DEFAULT_IMAGE
    sandbox_docker_socket: str = "/var/run/docker.sock"
    sandbox_docker_api: str = "v1.43"
    sandbox_max_output_bytes: int = 64 * 1024
    sandbox_max_file_bytes: int = 200 * 1024
    sandbox_max_timeout_ms: int = 120_000
    env: Literal["development", "test", "ci", "staging", "production"] = "development"

    def image_whitelist(self) -> frozenset[str]:
        items = [item.strip() for item in self.sandbox_images.split(",") if item.strip()]
        return frozenset(items or [self.sandbox_default_image])


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def reset_settings_cache() -> None:
    get_settings.cache_clear()


__all__ = ["DEFAULT_IMAGE", "Settings", "get_settings", "reset_settings_cache"]
