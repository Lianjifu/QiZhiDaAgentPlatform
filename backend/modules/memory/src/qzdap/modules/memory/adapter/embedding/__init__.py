"""Embedding adapter implementations (openai, embedding_runtime HTTP, noop)."""

from qzdap.modules.memory.adapter.embedding.http_adapter import HttpEmbeddingAdapter
from qzdap.modules.memory.adapter.embedding.noop_adapter import (
    NoOpEmbedding,
    NoOpEmbeddingAdapter,
)
from qzdap.modules.memory.adapter.embedding.openai_adapter import OpenAIEmbeddingAdapter

__all__ = [
    "HttpEmbeddingAdapter",
    "NoOpEmbedding",
    "NoOpEmbeddingAdapter",
    "OpenAIEmbeddingAdapter",
]
