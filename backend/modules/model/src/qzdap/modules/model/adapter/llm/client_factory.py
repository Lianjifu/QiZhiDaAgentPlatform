"""Build the saved provider's protocol-specific runtime client."""

from __future__ import annotations

from dataclasses import dataclass

from qzdap.modules.model.application.ports import ModelClientFactory
from qzdap_llm import LLMClient
from qzdap_llm.providers import build_provider_client
from qzdap_llm.retry import RetryPolicy


@dataclass(slots=True, frozen=True)
class _DefaultClientFactory(ModelClientFactory):
    request_timeout_seconds: float = 30.0
    retry_policy: RetryPolicy | None = None

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
            retry_policy=self.retry_policy,
        )


def build_default_client_factory(
    *,
    request_timeout_seconds: float = 30.0,
    retry_policy: RetryPolicy | None = None,
) -> ModelClientFactory:
    return _DefaultClientFactory(
        request_timeout_seconds=request_timeout_seconds,
        retry_policy=retry_policy,
    )


__all__ = ["_DefaultClientFactory", "build_default_client_factory"]
