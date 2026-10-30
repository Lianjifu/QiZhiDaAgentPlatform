"""``Writer`` —— 记忆写入的**端口** ✓（C1）。

依据：Memory 方案 §4（写入五步 ✓）、§10.1（A2 ``writer.py`` ✓）。

⚠️ **这一层是契约层** —— 端口 + 结果形状 ✓（实现归模块侧 ✓）。

⚠️ **写入流水线**（§4.1 ✓）：抽取候选 → **敏感信息闸门** → 去重
（``content_hash`` ✓）→ 置信度 → 落库（带 provenance ✓）→ 写统计 ✓。

⚠️ **触发点是「一轮结束一次」** ✓（决策 #4 ✓）—— 不是每次 LLM 调用后 ✗。

⚠️ **输入只能是本轮的对话内容** ✓ —— ⚠️ **不能是召回结果** ✗✗（自我强化
循环 ✗ —— §4.6 ✓）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True, slots=True)
class WriteOutcome:
    """一次写入的结果 ✓。"""

    #: 真正落库的几条 ✓。
    written: list[dict] = field(default_factory=list)
    #: 因**闸门**被拒的几条 ✓（要记审计 ✓ —— §4.3 ✓）。
    rejected: list[dict] = field(default_factory=list)
    #: 因**重复**被跳过（改为更新用量）的几条 ✓（§4.4 ✓）。
    deduplicated: list[dict] = field(default_factory=list)


@runtime_checkable
class Writer(Protocol):
    """记忆写入 ✓（C1 ✓）。"""

    async def write_turn(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        session_id: UUID,
        turn_id: UUID | None = None,
        user_input: str,
        assistant_reply: str = "",
        policy: object | None = None,
    ) -> WriteOutcome:
        """把**本轮**对话沉淀成记忆 ✓（**不含召回结果** ✓ —— §4.6 ✓）。"""
        ...


__all__ = ["WriteOutcome", "Writer"]
