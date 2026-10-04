"""LLM client: OpenAI-compatible + Anthropic/DeepSeek + Router + Embeddings."""

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
from qzdap_llm.mock import MockLLMClient
from qzdap_llm.openai_compatible import OpenAICompatibleClient
from qzdap_llm.router import LLMRouter

__all__ = [
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "LLMChunk",
    "LLMClient",
    "LLMConfig",
    "LLMProvider",
    "LLMRouter",
    "MockLLMClient",
    "OpenAICompatibleClient",
    "Usage",
    "embed",
    "embed_many",
]
