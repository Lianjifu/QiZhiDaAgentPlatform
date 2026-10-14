"""LLM client: OpenAI-compatible + Anthropic/DeepSeek + Router + Embeddings."""

from qzdap_llm.anthropic import AnthropicClient
from qzdap_llm.azure import AzureOpenAIClient
from qzdap_llm.client import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    LLMChunk,
    LLMClient,
    Usage,
)
from qzdap_llm.config import LLMConfig, LLMProvider
from qzdap_llm.embeddings import embed, embed_many
from qzdap_llm.google import GoogleClient
from qzdap_llm.mock import MockLLMClient
from qzdap_llm.openai_compatible import OpenAICompatibleClient
from qzdap_llm.providers import (
    ProviderSpec,
    build_provider_client,
    get_provider_spec,
    list_provider_specs,
)
from qzdap_llm.router import LLMRouter
from qzdap_llm.transport import ProviderTransportError

__all__ = [
    "AnthropicClient",
    "AzureOpenAIClient",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "GoogleClient",
    "LLMChunk",
    "LLMClient",
    "LLMConfig",
    "LLMProvider",
    "LLMRouter",
    "MockLLMClient",
    "OpenAICompatibleClient",
    "ProviderSpec",
    "ProviderTransportError",
    "Usage",
    "build_provider_client",
    "embed",
    "embed_many",
    "get_provider_spec",
    "list_provider_specs",
]
