"""**任务清单（todo）** ✓ —— 「先规划再执行」的那一半 ✓。

⚠️ **为什么要有** ✓ —— agent 的规划能力**不是**「模型自己想一遍」✓，
而是**一份显式的清单** ✓ —— 模型能改 ✓ / 用户能看 ✓ / 收尾能核对 ✓。

⚠️ **载体 = 工具输出里的结构化前缀** ✓ —— 不用 ``artifact`` ✓
（产物是给用户下载的东西 ✓ —— todo 不是 ✓）。

| 位置 | 内容 |
|---|---|
| ``TODO_PREFIX`` 之后 | JSON 数组 ✓（每项 ``{content, status}`` ✓） |

⚠️ **为什么用前缀而不是新字段** ✓ —— 工具执行链路的形状是
``{text, artifact}`` ✓（``ToolCallOutput`` ✓）—— 加第三格要动**契约** ✓
（会影响所有工具适配器 ✗）→ 用前缀**不动契约** ✓。

⚠️ **解析失败就当没有** ✓ —— 工具输出**永远不能打断对话** ✓
（与「计价失败返回 0」✓ / 「治理故障放行」✓ 同一条纪律 ✓）。
"""

from __future__ import annotations

import json
from typing import Any

from qzdap_kernel.todo_protocol import TODO_PREFIX, TODO_STATUSES


def parse_todos(text: str) -> list[dict[str, Any]] | None:
    """**从工具输出里解析出 todo 清单** ✓。

    ⚠️ **不是 todo 更新就返回 ``None``** ✓（不是空列表 ✓ ——
    空列表与「没有」要分得开 ✓）。
    ⚠️ **解析失败返回 ``None``** ✓ —— 不打断对话 ✓。
    """
    if not text or TODO_PREFIX not in text:
        return None
    raw = text.split(TODO_PREFIX, 1)[1].strip()
    # ⚠️ **只取第一行** ✓ —— 后面可能还有模型看到的说明文字 ✓。
    raw = raw.splitlines()[0].strip() if raw else ""
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, list):
        return None
    # ⚠️ **全是垃圾项 = 不是清单** ✓ —— 返回 ``None`` ✓（不是空清单 ✓）。
    # ⚠️ **「空数组」才是「清空清单」** ✓ —— 两者语义不同 ✓。
    if payload and not any(isinstance(item, dict) for item in payload):
        return None
    out: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        status = str(item.get("status") or "pending").strip()
        if status not in TODO_STATUSES:
            status = "pending"
        out.append({"content": content, "status": status})
    return out


def render_todos(todos: list[dict[str, Any]]) -> str:
    """**清单 → 给模型看的一段文字** ✓（回灌时用 ✓）。

    ⚠️ **只列未完成的** ✓ —— 已完成的项不用反复占模型注意力 ✓
    （但**保留在清单里** ✓ —— 收尾要核对 ✓）。
    """
    if not todos:
        return ""
    lines = ["当前任务清单："]
    for item in todos:
        content = str(item.get("content") or "").strip()
        status = str(item.get("status") or "pending").strip()
        if status == "completed":
            continue
        mark = "→" if status == "in_progress" else "·"
        lines.append(f"{mark} {content}")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def summarize_progress(todos: list[dict[str, Any]]) -> str:
    """**收尾时的一句进度** ✓（给最终回答与日志看 ✓）。"""
    if not todos:
        return ""
    total = len(todos)
    done = sum(1 for item in todos if item.get("status") == "completed")
    return f"任务清单：{done}/{total} 已完成"


__all__ = [
    "TODO_PREFIX",
    "TODO_STATUSES",
    "parse_todos",
    "render_todos",
    "summarize_progress",
]
