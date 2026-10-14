"""Build the saved provider's protocol-specific runtime client."""

from __future__ import annotations

from dataclasses import dataclass

from qzdap_llm import LLMClient
from qzdap_llm.providers import build_provider_client

from qzdap.modules.model.application.ports import ModelClientFactory


@dataclass(slots=True, frozen=True)
class _DefaultClientFactory(ModelClientFactory):
    request_timeout_seconds: float = 30.0

    def build(
        self,
        *,
        protocol: str,
        api_key: str,
        base_url: str | None,
        api_version: str = "",
    ) -> LLMClient:
        return build_provider_client(
            protocol=protocol,
            api_key=api_key,
            base_url=base_url or "",
            api_version=api_version,
            timeout_seconds=self.request_timeout_seconds,
        )


def build_default_client_factory(
    *, request_timeout_seconds: float = 30.0
) -> ModelClientFactory:
    return _DefaultClientFactory(request_timeout_seconds=request_timeout_seconds)


__all__ = ["_DefaultClientFactory", "build_default_client_factory"]
