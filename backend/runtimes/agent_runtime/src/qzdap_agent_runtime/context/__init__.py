"""Context 协议层：token 估算 + 契约类型 + 压缩 + 装配。

⚠️ **token 估算只有一份** ✓ —— `tokens.py` ✓（按语种 ✓）；旧路径
（`modules/.../adapter/graph/state.py`）也调它 ✓（口径统一 ✓ ——
Context 方案决策 #2 ✓）。
"""

from __future__ import annotations

from .budget import (
    CompactionResult,
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
    "KNOWLEDGE_TOP_K",
    "MEMORY_TOP_K",
    "AssembledContext",
    "CompactionResult",
    "Compactor",
    "ContextAssembler",
    "ContextBuilder",
    "ContextManifest",
    "InMemorySummaryModel",
    "KnowledgeSearchPort",
    "ManifestEntry",
    "MemoryRecallPort",
    "SummaryError",
    "SummaryModel",
    "estimate_message_tokens",
    "estimate_tokens",
    "render_agent_prompts",
    "render_knowledge_hits",
    "render_memory_hits",
]
