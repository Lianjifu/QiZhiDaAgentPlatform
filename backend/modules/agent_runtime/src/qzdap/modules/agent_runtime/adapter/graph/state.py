from __future__ import annotations

from typing import Any, TypedDict

from qzdap_agent_runtime.context.tokens import estimate_message_tokens


class LoopState(TypedDict, total=False):
    messages: list[dict[str, Any]]
    step: int
    max_steps: int
    todos: list[str]
    pending_approval: dict[str, Any] | None
    last_tool_sig: str
    stall_count: int
    final: str
    compacted: bool
    tokens_est: int


def tool_signature(name: str, arguments: dict[str, Any]) -> str:
    keys = ",".join(f"{k}={arguments[k]!r}" for k in sorted(arguments))
    return f"{name}({keys})"


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """一批消息的 token 估算 ✓ —— **口径与 Context 层共用一份** ✓。

    ⚠️ **旧实现按 ``len // 4`` 一刀切** ✗✗ —— 对**中文低估约 4 倍** ✗
    （「超没超预算」这条判断在中文场景下失真 ✗）。现在改调契约层的
    **按语种** 估算（Context 方案决策 #2 ✓）—— 中文按 1 字 1 token ✓。

    ⚠️ 空内容现在记 **0** ✓（旧实现记 1 ✗ —— 白占预算 ✗）。
    """
    return estimate_message_tokens(messages)


__all__ = ["LoopState", "estimate_tokens", "tool_signature"]
