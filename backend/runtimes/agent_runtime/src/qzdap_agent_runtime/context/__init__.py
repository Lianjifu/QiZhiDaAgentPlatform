"""Context 协议层：token 估算 + 契约类型 + 压缩 + 装配。

⚠️ **token 估算只有一份** ✓ —— `tokens.py` ✓（按语种 ✓）；旧路径
（`modules/.../adapter/graph/state.py`）也调它 ✓（口径统一 ✓ ——
Context 方案决策 #2 ✓）。
"""

from __future__ import annotations

from .budget import (
    Compactor,
    ContextAssembler,
    InMemorySummaryModel,
    SummaryError,
    SummaryModel,
)
from .builder import (
    KNOWLEDGE_TOP_K,
    MEMORY_TOP_K,
    ContextBuilder,
    KnowledgeSearchPort,
    MemoryRecallPort,
)
from .compressor import (
    DEFAULT_WINDOW,
    KEEP_RECENT,
    WINDOW_RATIO,
    CompactionOutcome,
    ContextCompressor,
    ContextTooLargeError,
    SummaryModelPort,
)
from .prompts import (
    DEFAULT_SYSTEM_PROMPT,
    render_agent_prompts,
    render_knowledge_hits,
    render_memory_hits,
)
from .tokens import estimate_message_tokens, estimate_tokens
from .types import (
    CONTEXT_SOURCES,
    AssembledContext,
    ContextManifest,
    ManifestEntry,
)

__all__ = [
    "CONTEXT_SOURCES",
    "DEFAULT_SYSTEM_PROMPT",
    "DEFAULT_WINDOW",
    "KEEP_RECENT",
    "KNOWLEDGE_TOP_K",
    "MEMORY_TOP_K",
    "WINDOW_RATIO",
    "AssembledContext",
    "CompactionOutcome",
    "Compactor",
    "ContextAssembler",
    "ContextBuilder",
    "ContextCompressor",
    "ContextManifest",
    "ContextTooLargeError",
    "InMemorySummaryModel",
    "KnowledgeSearchPort",
    "ManifestEntry",
    "MemoryRecallPort",
    "SummaryError",
    "SummaryModel",
    "SummaryModelPort",
    "estimate_message_tokens",
    "estimate_tokens",
    "render_agent_prompts",
    "render_knowledge_hits",
    "render_memory_hits",
]
