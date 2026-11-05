"""上下文的**契约类型** —— ``AssembledContext`` / ``ContextManifest`` / ``ManifestEntry``。

依据：Context 方案 §3.5（manifest 的内容）、§8.1（``types.py``）。

⚠️ **这一层是契约层** —— 不引框架 ✓（纯 dataclass ✓）。

⚠️ **manifest 的关键字段是 ``filtered_reason``** ✓ —— 「**什么没进去**」只有
它能回答 ✓（消融评测与排障都靠它 ✓）。它**早就存在** ✓（``budget.py`` 里 ✓），
本层补的是 **``ref_id`` / ``score`` / ``degraded``** 三个 ✓。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: manifest 的**来源**枚举 ✓（§3.5 ✓）—— 固定值集 ✓，拼错要能看出来 ✗✗。
CONTEXT_SOURCES: frozenset[str] = frozenset(
    {
        "system",
        "agent",
        "expert",
        "tenant",
        "summary",
        "memory",
        "knowledge",
        "recent",
        "tool_result",
        "attachment",
    }
)


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    """一次模型调用里，**一个片段**的来龙去脉 ✓（§3.5 ✓）。

    | 字段 | 含义 |
    |---|---|
    | ``source`` | 来源（``CONTEXT_SOURCES`` 之一 ✓） |
    | ``tokens`` | 该片段的 token 估算 ✓（按语种口径 ✓） |
    | ``version`` | agent 版本 / 记忆批次版本 / 知识包版本 ✓ |
    | ``ref_id`` | 命中项 ID（记忆 id / 知识 chunk id / 消息 id）✓ |
    | ``score`` | 召回得分（记忆 / 知识）✓ |
    | ``filtered_reason`` | **被淘汰的原因** ✓ —— 没有它就不知道「什么没进去」✗✗ |
    | ``degraded`` | 该来源是否降级（召回失败 / 摘要失败）✓ |
    """

    source: str
    tokens: int
    filtered_reason: str | None = None
    version: str | None = None
    ref_id: str | None = None
    score: float | None = None
    degraded: bool = False


@dataclass(slots=True)
class ContextManifest:
    """一次模型调用的**上下文清单** ✓（§3.5 ✓）。"""

    entries: list[ManifestEntry] = field(default_factory=list)

    def add(self, entry: ManifestEntry) -> None:
        self.entries.append(entry)

    @property
    def total_tokens(self) -> int:
        return sum(e.tokens for e in self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "entries": [
                {
                    "source": e.source,
                    "tokens": e.tokens,
                    "filtered_reason": e.filtered_reason,
                    "version": e.version,
                    "ref_id": e.ref_id,
                    "score": e.score,
                    "degraded": e.degraded,
                }
                for e in self.entries
            ],
        }


@dataclass(frozen=True, slots=True)
class AssembledContext:
    """装配好的上下文 ✓ —— ``messages`` **可直接喂 LLM** ✓（§6 边界表 ✓）。

    ⚠️ ``messages`` 的形状是 ``[{role, content}]`` ✓ —— 契约形状 ✓，
    装配细节（片段怎么拼）归 Builder ✓。
    """

    messages: list[Any]
    manifest: ContextManifest
    degraded_flags: dict[str, bool]
    #: 整段上下文的 token 估算 ✓（= manifest 的合计 ✓）。
    tokens_estimated: int = 0
    #: **原始召回结果** ✓（记忆 / 知识 ✓）—— 调用方要单独下发
    #: ``knowledge_search`` 事件时用 ✓（不必再召回一次 ✗✗）。
    recalled: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


__all__ = [
    "CONTEXT_SOURCES",
    "AssembledContext",
    "ContextManifest",
    "ManifestEntry",
]
