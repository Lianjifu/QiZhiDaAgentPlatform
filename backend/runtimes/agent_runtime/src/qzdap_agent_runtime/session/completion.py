"""一轮的**结果汇总** —— chunk 流 → 「最终回复 + 用量」。

⚠️ **为什么收敛到这一个函数**：旧的第二套 turn 实现
（``use_cases/run_turn_to_completion.py``）自带一份 drain 逻辑 —— 同一件事的
**第二份实现** ✗。IM 渠道、子代理、评估三条链路都要「跑一轮，拿到最终回复」
→ 全部走这里 ✓（Session 方案 §6「唯一 turn 实现」）。

**这一层是契约层** —— 不引框架、不引模块 ✓；只认 ``qzdap_schema`` 的 chunk
形状 ✓。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from qzdap_schema.dtos.turn import (
    ApprovalRequiredChunk,
    DoneChunk,
    ErrorChunk,
    MessageChunk,
    TurnChunk,
    UsageChunk,
)


class TurnFailedError(RuntimeError):
    """一轮以错误收尾 —— **带错误码** ✓。

    ⚠️ 契约层**不抛框架异常**（``AppError`` 是模块侧的形状）—— 调用方
    （IM 驱动 / 子代理 / 评估）各自投影成自己的错误 ✓。
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class TurnCompletion:
    """一轮跑完的结果 ✓。

    ⚠️ ``waiting_approval`` 非空 = 这一轮**挂在审批上**（没有终态 chunk）
    —— 调用方据此决定「回一句说明」还是「继续等」✓。
    """

    final_message: str
    turn_id: UUID
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    waiting_approval: ApprovalRequiredChunk | None = None


async def drain_to_completion(chunks: AsyncIterator[TurnChunk]) -> TurnCompletion:
    """把一轮的 chunk 流收敛成**一个结果** ✓。

    规则（与旧实现同口径 ✓）：

    - ``done`` → 最终回复 + 轮次号；
    - ``usage`` → 用量（最后一个为准）；
    - ``error`` → **抛错**（带错误码）—— 失败不能被当成「空回复」✗；
    - ``approval_required`` → 记进 ``waiting_approval``（这一轮挂起了）✓；
    - 一个终态 chunk 都没有 → **抛错**（空流 = 会话可能已关 ✗）。
    """
    final_message: str | None = None
    turn_id: UUID | None = None
    input_tokens = 0
    output_tokens = 0
    cache_read_tokens = 0
    cache_write_tokens = 0
    parts: list[str] = []
    approval: ApprovalRequiredChunk | None = None

    async for chunk in chunks:
        if isinstance(chunk, DoneChunk):
            final_message = chunk.final_message
            turn_id = chunk.turn_id
        elif isinstance(chunk, UsageChunk):
            input_tokens = chunk.input_tokens
            output_tokens = chunk.output_tokens
            cache_read_tokens = chunk.cache_read_tokens
            cache_write_tokens = chunk.cache_write_tokens
            if turn_id is None:
                turn_id = chunk.turn_id
        elif isinstance(chunk, MessageChunk):
            parts.append(chunk.content)
        elif isinstance(chunk, ApprovalRequiredChunk):
            approval = chunk
            if turn_id is None:
                turn_id = chunk.turn_id
        elif isinstance(chunk, ErrorChunk):
            raise TurnFailedError(chunk.code, chunk.message)

    if turn_id is None:
        raise TurnFailedError(
            "TURN_EMPTY_STREAM",
            "turn produced no terminal chunk; session may be closed",
        )

    if final_message is None:
        # 没有 ``done`` 但有正文 → 说明这一轮挂在审批上；正文仍然要给用户看 ✓。
        final_message = "".join(parts)

    return TurnCompletion(
        final_message=final_message,
        turn_id=turn_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        waiting_approval=approval,
    )


__all__ = ["TurnCompletion", "TurnFailedError", "drain_to_completion"]
