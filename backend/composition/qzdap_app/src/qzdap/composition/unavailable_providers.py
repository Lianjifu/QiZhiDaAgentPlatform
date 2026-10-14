"""Fail on invocation without preventing catalog and database APIs from booting."""

from collections.abc import AsyncIterator

from qzdap.modules.memory.application.ports import EmbeddingPort
from qzdap_kernel.errors import AppError
from qzdap_llm.client import ChatRequest, ChatResponse, LLMChunk, LLMClient


class ProviderUnavailable(AppError):
    code = "PROVIDER_UNAVAILABLE"
    status = 503


class UnavailableLLMClient(LLMClient):
    name = "unavailable"

    async def chat(self, req: ChatRequest) -> ChatResponse:
        raise ProviderUnavailable("开发模式不允许 Mock LLM，请配置真实模型供应商")

    async def stream(self, req: ChatRequest) -> AsyncIterator[LLMChunk]:
        raise ProviderUnavailable("开发模式不允许 Mock LLM，请配置真实模型供应商")
        yield  # Makes this an async generator; invocation always raises.

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise ProviderUnavailable("开发模式不允许 Mock 嵌入，请配置真实嵌入供应商")


class UnavailableEmbeddingAdapter(EmbeddingPort):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise ProviderUnavailable("未配置真实嵌入供应商，开发模式不允许生成零向量")
