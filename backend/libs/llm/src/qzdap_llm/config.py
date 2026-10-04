"""LLM configuration + provider enum."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LLMProvider(StrEnum):
    MOCK = "mock"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    CUSTOM = "custom"


@dataclass(slots=True, frozen=True)
class LLMConfig:
    provider: LLMProvider = LLMProvider.MOCK
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    default_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    timeout_seconds: int = 30
    mock_latency_ms: int = 50
    failover_providers: tuple[LLMProvider, ...] = ()
