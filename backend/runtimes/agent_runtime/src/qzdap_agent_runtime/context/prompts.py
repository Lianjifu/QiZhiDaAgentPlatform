"""**单段式** system prompt 渲染 —— 替代旧路径的四套模板 ✓。

依据：Context 方案 §3.4（四套模板合并）、§3.3（agent prompts 的处理）。

⚠️ **为什么不再有「四套模板」** ✗✗ —— 旧路径有四个函数（无记忆 / 有记忆 /
有知识 / 有记忆+知识）✗ —— 调用方二选一 ✗ —— **分支爆炸的源头** ✓：
新增一种来源（附件摘要？工具结果？）就要再加两个函数 ✗✗。
那四个函数**已随 Session Stage 5b 删除** ✓（台账 **X10** ✓）。

现在：**一个模板 + 可选片段追加** ✓ —— 记忆 / 知识是**可选段落** ✓，
不是模板变体 ✓。

⚠️ **agent 的五段配置（soul / prompt / agents / tools / user）按原顺序拼**
✓ —— 顺序与旧路径**一致** ✓（`runner.py:505-513` ✓）—— 换顺序会改变
模型行为 ✗✗。
"""

from __future__ import annotations

from typing import Any

#: agent 配置里进 system prompt 的五段 ✓（顺序即拼接顺序 ✓）。
AGENT_PROMPT_KEYS: tuple[str, ...] = ("soul", "prompt", "agents", "tools", "user")

#: agent 没有任何 prompt 时的兜底 ✓（旧路径同一句 ✓ —— 改了会改变
#: 「没配 prompt 的 agent」的行为 ✗✗）。
DEFAULT_SYSTEM_PROMPT = "你是企业助手，使用可用工具完成任务，最终给出中文回答。"

#: 召回命中在 system 段里的**每条截断长度** ✓（旧路径 `[:400]` ✓ ——
#: 迁移必须复刻，否则新旧行为漂移 ✗）。
HIT_MAX_CHARS = 400


def render_agent_prompts(agent_prompts: dict[str, Any] | None) -> str:
    """agent 的五段配置 → 一段 system 文本 ✓。

    ⚠️ **空段落跳过** ✓（旧路径 `if part` ✓）—— 拼出两个连续换行 ✗。
    """
    prompts = dict(agent_prompts or {})
    parts = [str(prompts.get(key) or "").strip() for key in AGENT_PROMPT_KEYS]
    return "\n\n".join(part for part in parts if part)


def render_memory_hits(hits: list[dict[str, Any]]) -> str:
    """记忆命中 → system 段落文本 ✓。

    ⚠️ **复刻旧路径的三件事** ✓（Context 方案 §3.2 ✓）：
    ① 按 ``score`` 降序 ✓；② 每条**截 400 字** ✓；
    ③ 分数按 ``%.2f`` 显示 ✓。

    ⚠️ 内容取 ``content``，没有就取 ``value`` ✓（旧路径同 ✓）。
    """
    lines = [
        f"- ({float(item.get('score') or 0):.2f}) "
        f"{item.get('content') or item.get('value') or ''}"[:HIT_MAX_CHARS]
        for item in hits
    ]
    return "\n".join(lines)


def render_knowledge_hits(hits: list[dict[str, Any]]) -> str:
    """知识命中 → system 段落文本 ✓（同样复刻旧路径的三件事 ✓）。"""
    lines = [
        f"- ({float(item.get('score') or 0):.2f}) {item.get('content') or ''}"[
            :HIT_MAX_CHARS
        ]
        for item in hits
    ]
    return "\n".join(lines)


def sort_hits_by_score(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """召回命中按 ``score`` **降序** ✓（旧路径同 ✓ —— 顺序决定截断谁 ✓）。"""
    return sorted(hits, key=lambda row: float(row.get("score") or 0), reverse=True)


__all__ = [
    "AGENT_PROMPT_KEYS",
    "DEFAULT_SYSTEM_PROMPT",
    "HIT_MAX_CHARS",
    "render_agent_prompts",
    "render_knowledge_hits",
    "render_memory_hits",
    "sort_hits_by_score",
]
