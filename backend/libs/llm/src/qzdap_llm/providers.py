"""Explicit provider registry and protocol-aware client factory.

Base URLs denote API roots, not individual endpoints. A configured URL always
wins over a default; no region is inferred for Qwen. Azure model IDs denote
deployment names. Injected HTTP clients are borrowed, not closed by adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

import httpx

from qzdap_llm.anthropic import AnthropicClient
from qzdap_llm.azure import AzureOpenAIClient
from qzdap_llm.client import LLMClient
from qzdap_llm.config import LLMConfig, LLMProvider
from qzdap_llm.google import GoogleClient
from qzdap_llm.openai_compatible import OpenAICompatibleClient


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    protocol: str
    transport: Literal["openai", "anthropic", "google", "azure"]
    default_base_url: str = ""
    requires_base_url: bool = False
    requires_api_version: bool = False


PROVIDER_REGISTRY = MappingProxyType(
    {
        spec.protocol: spec
        for spec in (
            ProviderSpec("openai", "openai", "https://api.openai.com/v1"),
            ProviderSpec("anthropic", "anthropic", "https://api.anthropic.com"),
            ProviderSpec(
                "google", "google", "https://generativelanguage.googleapis.com/v1beta"
            ),
            ProviderSpec("deepseek", "openai", "https://api.deepseek.com"),
            ProviderSpec("glm", "openai", "https://open.bigmodel.cn/api/paas/v4"),
            ProviderSpec("kimi", "openai", "https://api.moonshot.ai/v1"),
            ProviderSpec("qwen", "openai", requires_base_url=True),
            ProviderSpec("minimax", "openai", "https://api.minimax.io/v1"),
            ProviderSpec("openai-compatible", "openai", requires_base_url=True),
            ProviderSpec("anthropic-compatible", "anthropic", requires_base_url=True),
            ProviderSpec(
                "azure", "azure", requires_base_url=True, requires_api_version=True
            ),
        )
    }
)


def get_provider_spec(protocol: str) -> ProviderSpec:
    """Return a registered protocol; unknown protocols fail rather than fall back."""
    try:
        return PROVIDER_REGISTRY[protocol]
    except KeyError:
        raise ValueError("Unknown LLM provider protocol") from None


def list_provider_specs() -> tuple[ProviderSpec, ...]:
    return tuple(PROVIDER_REGISTRY.values())


def build_provider_client(
    *,
    protocol: str,
    api_key: str,
    base_url: str = "",
    api_version: str = "",
    timeout_seconds: float = 30,
    http: httpx.AsyncClient | None = None,
) -> LLMClient:
    spec = get_provider_spec(protocol)
    url = base_url.strip() or spec.default_base_url
    if not url:
        raise ValueError("Provider requires an explicit base_url")
    parsed = httpx.URL(url)
    if (
        parsed.scheme not in ("https", "http")
        or not parsed.host
        or parsed.query
        or parsed.fragment
        or parsed.userinfo
    ):
        raise ValueError(
            "base_url must be an HTTP(S) API root without credentials, query or fragment"
        )
    if spec.requires_api_version and not api_version.strip():
        raise ValueError("Azure requires api_version")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    config = LLMConfig(
        provider=LLMProvider.CUSTOM,
        api_key=api_key,
        base_url=url,
        timeout_seconds=timeout_seconds,
    )
    if spec.transport == "anthropic":
        return AnthropicClient(config, http=http)
    if spec.transport == "google":
        return GoogleClient(config, http=http)
    if spec.transport == "azure":
        return AzureOpenAIClient(config, api_version=api_version, http=http)
    return OpenAICompatibleClient(config, http=http)
