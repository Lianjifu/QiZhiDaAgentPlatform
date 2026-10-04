"""Progressive context compaction against a model context window."""

from __future__ import annotations

from typing import Any

from qzdap.modules.agent_runtime.adapter.graph.state import estimate_tokens

KEEP_RECENT = 6
WINDOW_RATIO = 0.70
DEFAULT_WINDOW = 32_000


def compact_messages(
    messages: list[dict[str, Any]],
    *,
    rolling_summary: str = "",
    context_window: int = DEFAULT_WINDOW,
) -> tuple[list[dict[str, Any]], str, bool]:
    budget = max(1024, int(context_window * WINDOW_RATIO))
    cleaned: list[dict[str, Any]] = []
    for item in messages:
        role = item.get("role")
        content = str(item.get("content") or "")
        if role == "tool" and (
            content.startswith("ERROR") or "SKILL_DENIED" in content or len(content) > 4000
        ):
            item = {**item, "content": content[:1500] + ("…" if len(content) > 1500 else "")}
        cleaned.append(item)
    if estimate_tokens(cleaned) <= budget:
        return cleaned, rolling_summary, False

    system = [m for m in cleaned if m.get("role") == "system"][:1]
    rest = [m for m in cleaned if m.get("role") != "system"]
    keep = rest[-KEEP_RECENT:] if len(rest) > KEEP_RECENT else rest
    folded = rest[:-KEEP_RECENT] if len(rest) > KEEP_RECENT else []
    digest_parts = []
    for item in folded:
        role = item.get("role")
        text = str(item.get("content") or "").replace("\n", " ")[:180]
        if text:
            digest_parts.append(f"{role}: {text}")
    summary = rolling_summary
    if digest_parts:
        summary = (rolling_summary + "\n" if rolling_summary else "") + " | ".join(digest_parts[-20:])
        summary = summary[-4000:]
    compact_sys = list(system)
    if summary:
        compact_sys.append({"role": "system", "content": f"更早轮次摘要：{summary}"})
    return compact_sys + keep, summary, True


__all__ = ["DEFAULT_WINDOW", "WINDOW_RATIO", "compact_messages"]
