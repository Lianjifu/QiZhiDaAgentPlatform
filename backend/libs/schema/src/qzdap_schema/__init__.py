"""Cross-module DTOs (wire contracts).

⚠️ **品牌 ID 不在这里** ✓ —— 它们住在 :mod:`qzdap_kernel.ids` ✓（2026-10-31，
P-13 ✓）—— 品牌 ID 是**最底层的值对象** ✓ → 住进零依赖的 base 层 ✓，
**每一层**（libs / modules / composition / 契约层 ✓）都共用同一套品牌词汇 ✓。
本包只留**线上的 DTO** ✓（chunk / 错误 / 分页 ✓）。
"""

from __future__ import annotations

from qzdap_schema.dtos import (
    ChunkEnvelope,
    DoneChunk,
    ErrorChunk,
    MemoryEntryDTO,
    MessageChunk,
    PageRequest,
    PageResponse,
    SkillInvocationChunk,
    ToolCallChunk,
    ToolResultChunk,
    TurnChunk,
    UsageChunk,
)

__all__ = [
    "ChunkEnvelope",
    "DoneChunk",
    "ErrorChunk",
    "MemoryEntryDTO",
    "MessageChunk",
    "PageRequest",
    "PageResponse",
    "SkillInvocationChunk",
    "ToolCallChunk",
    "ToolResultChunk",
    "TurnChunk",
    "UsageChunk",
]
