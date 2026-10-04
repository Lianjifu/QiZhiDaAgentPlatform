"""Build an LLM client from catalog protocol + decrypted credential."""

from __future__ import annotations

from dataclasses import dataclass

from qzdap_llm import LLMClient, LLMConfig, OpenAICompatibleClient

from qzdap.modules.model.application.ports import ModelClientFactory

_DEFAULT_BASE = {
    "openai": "https://api.openai.com/v1",
    "azure": "https://example.openai.azure.com",
    "anthropic": "https://api.anthropic.com",
    "openai-compatible": "https://api.openai.com/v1",
}


@dataclass(slots=True, frozen=True)
class _DefaultClientFactory(ModelClientFactory):
    request_timeout_seconds: float = 30.0

    def build(self, *, protocol: str, api_key: str, base_url: str | None) -> LLMClient:
        resolved = (base_url or "").rstrip("/") or _DEFAULT_BASE.get(protocol, "https://api.openai.com/v1")
        return OpenAICompatibleClient(
            LLMConfig(
                base_url=resolved,
                api_key=api_key,
                timeout_seconds=int(self.request_timeout_seconds),
            )
        )


def build_default_client_factory(*, request_timeout_seconds: float = 30.0) -> ModelClientFactory:
    return _DefaultClientFactory(request_timeout_seconds=request_timeout_seconds)


__all__ = ["_DefaultClientFactory", "build_default_client_factory"]
