"""Azure OpenAI deployment transport; api-version is explicit and mandatory."""

from __future__ import annotations

from urllib.parse import quote

import httpx

from qzdap_kernel.error_codes import ErrorCode
from qzdap_llm.config import LLMConfig
from qzdap_llm.openai_compatible import OpenAICompatibleClient
from qzdap_llm.retry import RetryPolicy
from qzdap_llm.transport import ProviderTransportError


class AzureOpenAIClient(OpenAICompatibleClient):
    name = "azure"

    def __init__(
        self,
        config: LLMConfig,
        *,
        api_version: str,
        http: httpx.AsyncClient | None = None,
        retry_policy: RetryPolicy | None = None,
    ):
        if not api_version:
            raise ValueError("Azure requires api_version")
        super().__init__(config, http=http, retry_policy=retry_policy)
        self._headers = {"api-key": config.api_key}
        self._api_version = api_version

    def _deployment_path(self, model: str, action: str) -> str:
        prefix = "" if self._base_url.endswith("/openai") else "openai/"
        return f"{prefix}deployments/{quote(model, safe='')}/{action}?api-version={quote(self._api_version, safe='')}"

    def _chat_path(self, model: str) -> str:
        return self._deployment_path(model, "chat/completions")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        data = await self._post(
            self._deployment_path(self._cfg.embedding_model, "embeddings"),
            {"input": texts},
        )
        try:
            return [item["embedding"] for item in data["data"]]
        except (KeyError, TypeError):
            raise ProviderTransportError(code=ErrorCode.LLM_INVALID_RESPONSE.value) from None
