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
