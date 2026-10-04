from __future__ import annotations

from typing import Any, TypedDict


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
    total = 0
    for item in messages:
        total += max(1, len(str(item.get("content") or "")) // 4)
        for call in item.get("tool_calls") or []:
            total += max(1, len(str(call)) // 4)
    return total


__all__ = ["LoopState", "estimate_tokens", "tool_signature"]
