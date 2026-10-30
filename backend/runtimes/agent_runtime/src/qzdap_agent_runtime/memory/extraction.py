"""``FactExtractor`` —— 从**本轮对话**里抽「值得记的事实」✓。

依据：Memory 方案 §4.2（抽取 ✓，决策 #3：**规则起步 + 预留 LLM 接口** ✓）。

⚠️ **这一层是契约层** —— 纯规则 / 纯协议 ✓（A3 策略层无 IO ✓）。

⚠️ **输入只能是本轮的对话内容** ✓ —— ⚠️ **不能是召回结果** ✗✗
（从召回结果反推事实会造成**记忆的自我强化循环** ✗✗ —— 召回到的写回去 →
下次更容易召回 → 再写回去 ✗；方案 §4.6 ✓）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class FactCandidate:
    """一条候选事实 ✓（还没入库 ✓ —— 要先过闸门与去重 ✓）。"""

    #: 规范化后的内容 ✓（去重按它算 hash ✓ —— §4.4 ✓）。
    content: str
    #: 抽取来源 ✓（`explicit` = 用户明说「记住这个」✓ / `rule` ✓ / `llm` ✓）。
    source: str
    #: 置信度 ✓（§4.5 ✓：显式 0.95 / 规则 0.6–0.8 / LLM 0.5–0.9 ✓）。
    confidence: float
    #: 分类 ✓（对应 L2 的 ``category`` ✓）。
    category: str = "fact"
    #: 命中的原文片段 ✓（可回溯 ✓）。
    source_text: str = ""


@runtime_checkable
class FactExtractor(Protocol):
    """事实抽取器 ✓（规则起步 ✓，预留 LLM 实现 ✓ —— §4.2 ✓）。"""

    async def extract(
        self,
        *,
        user_input: str,
        assistant_reply: str = "",
    ) -> list[FactCandidate]:
        """从**本轮**对话里抽候选事实 ✓（**不含召回结果** ✓ —— §4.6 ✓）。"""
        ...


__all__ = ["FactCandidate", "FactExtractor"]


# ---------------------------------------------------------------------------
# 规则抽取（决策 #3：(a) 规则起步 ✓，预留 (b) LLM 接口 ✓）
# ---------------------------------------------------------------------------

#: **显式**要求记住的模式 ✓（置信度 0.95 ✓ —— §4.5 ✓）。
EXPLICIT_PATTERNS: tuple[str, ...] = ("记住", "记一下", "请记住", "备忘")

#: 陈述句模式 ✓（置信度 0.7 ✓ —— §4.5 ✓：规则从陈述句抽取 0.6–0.8 ✓）。
STATEMENT_PATTERNS: tuple[str, ...] = ("我是", "我叫", "我的", "我喜欢", "我不喜欢", "我需要")


class RuleFactExtractor:
    """规则抽取器 ✓（零成本、确定性强 ✓ —— §4.2 (a) ✓）。

    ⚠️ **召回率低是有意的** ✓ —— 先保「不乱记」✓（宁可少记，不要记错 ✗✗）。
    """

    async def extract(
        self,
        *,
        user_input: str,
        assistant_reply: str = "",
    ) -> list[FactCandidate]:
        text = (user_input or "").strip()
        if not text:
            return []
        candidates: list[FactCandidate] = []
        for line in (part.strip() for part in text.splitlines()):
            if not line:
                continue
            if any(pattern in line for pattern in EXPLICIT_PATTERNS):
                candidates.append(
                    FactCandidate(
                        content=line,
                        source="explicit",
                        confidence=0.95,
                        source_text=line,
                    )
                )
                continue
            if any(line.startswith(pattern) for pattern in STATEMENT_PATTERNS):
                candidates.append(
                    FactCandidate(
                        content=line,
                        source="rule",
                        confidence=0.7,
                        source_text=line,
                    )
                )
        return candidates


__all__ = [
    "EXPLICIT_PATTERNS",
    "STATEMENT_PATTERNS",
    "FactCandidate",
    "FactExtractor",
    "RuleFactExtractor",
]
