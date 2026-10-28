"""Built-in tool catalog — the argument contract for every shipped tool.

The ``tools`` table stores rows for the built-ins, but their ``spec`` column
is empty: the seed only records "a tool with this name exists". The LLM,
however, needs the *argument contract* to call a tool at all — a function
schema with empty ``properties`` makes the model guess.

This module is the single source of truth for that contract. It lives in the
tool module (not in agent-runtime) because the implementations live here; the
runtime reaches it through ``ToolPort.list_tools()``.
"""

from __future__ import annotations

from typing import Any

_S = {"type": "string"}
_I = {"type": "integer"}
_B = {"type": "boolean"}
_OBJ = {"type": "object"}
_ARR = {"type": "array"}


def _p(**kwargs: Any) -> dict[str, Any]:
    """Build one property entry."""
    return dict(kwargs)


# 每个工具: description / parameters / risk / needConfirm
# risk: low | medium | high —— high 会在执行前触发人工审批 (needs_confirm)
BUILTIN_TOOL_SPECS: dict[str, dict[str, Any]] = {
    "echo": {
        "description": "回显传入的文本，用于连通性自检。",
        "parameters": {"type": "object", "properties": {"text": _S}},
        "risk": "low",
    },
    "reverse": {
        "description": "把传入文本反转。",
        "parameters": {"type": "object", "properties": {"text": _S}},
        "risk": "low",
    },
    "clock": {
        "description": "返回当前服务器时间。",
        "parameters": {"type": "object", "properties": {}},
        "risk": "low",
    },
    "web_search": {
        "description": "联网搜索，返回前 N 条结果的标题、链接与摘要。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": _p(type="string", description="搜索关键词，必填。"),
                "top_k": _p(type="integer", description="返回条数，默认 5，最大 10。"),
            },
            "required": ["query"],
        },
        "risk": "medium",
    },
    "http_fetch": {
        "description": "抓取一个 URL，返回标题与正文纯文本。",
        "parameters": {
            "type": "object",
            "properties": {
                "url": _p(type="string", description="必须是 http(s):// 开头的地址，必填。"),
                "max_chars": _p(type="integer", description="正文最大字符数，默认 8000。"),
            },
            "required": ["url"],
        },
        "risk": "medium",
    },
    "fetch_url_with_auth": {
        "description": "带自定义请求头 / Cookie / Bearer 认证抓取 URL。",
        "parameters": {
            "type": "object",
            "properties": {
                "url": _p(type="string", description="目标地址，必填。"),
                "headers": _p(type="object", description="自定义请求头映射。"),
                "cookies": _p(type="object", description="自定义 Cookie 映射。"),
                "bearer_token": _p(type="string", description="Bearer Token。"),
                "max_chars": _p(type="integer", description="正文最大字符数。"),
            },
            "required": ["url"],
        },
        "risk": "high",
        "needConfirm": True,
    },
    "bash": {
        "description": "在工作区目录里执行一条 shell 命令。",
        "parameters": {
            "type": "object",
            "properties": {
                "command": _p(type="string", description="要执行的 shell 命令，必填。"),
                "cwd": _p(type="string", description="工作目录，相对工作区根。"),
                "timeout_seconds": _p(type="integer", description="超时秒数。"),
            },
            "required": ["command"],
        },
        "risk": "high",
        "needConfirm": True,
    },
    "read_file": {
        "description": "读取工作区内的文本文件。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": _p(type="string", description="相对工作区根的文件路径，必填。"),
                "start_line": _p(type="integer", description="起始行号，从 1 开始。"),
                "end_line": _p(type="integer", description="结束行号。"),
                "max_bytes": _p(type="integer", description="最大读取字节数。"),
            },
            "required": ["path"],
        },
        "risk": "medium",
    },
    "write_file": {
        "description": "把文本写入工作区内的文件（覆盖）。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": _p(type="string", description="相对工作区根的文件路径，必填。"),
                "content": _p(type="string", description="要写入的完整内容。"),
                "create_parents": _p(type="boolean", description="是否自动创建父目录。"),
            },
            "required": ["path"],
        },
        "risk": "high",
        "needConfirm": True,
    },
    "edit_file": {
        "description": "在文件里把 old_text 精确替换成 new_text（只替换一次）。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": _p(type="string", description="相对工作区根的文件路径，必填。"),
                "old_text": _p(type="string", description="要被替换的原文，必须唯一出现。"),
                "new_text": _p(type="string", description="替换后的新文本。"),
            },
            "required": ["path"],
        },
        "risk": "high",
        "needConfirm": True,
    },
    "ls": {
        "description": "列出工作区内的目录内容。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": _p(type="string", description="相对工作区根的目录，默认工作区根。"),
                "recursive": _p(type="boolean", description="是否递归列出。"),
                "max_depth": _p(type="integer", description="递归最大深度。"),
                "include_hidden": _p(type="boolean", description="是否包含隐藏文件。"),
            },
        },
        "risk": "low",
    },
    "glob": {
        "description": "按 glob 模式查找工作区内的文件路径。",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": _p(type="string", description="glob 模式，如 src/**/*.ts，必填。"),
                "cwd": _p(type="string", description="起始目录。"),
                "max_results": _p(type="integer", description="最多返回多少条。"),
            },
            "required": ["pattern"],
        },
        "risk": "low",
    },
    "grep": {
        "description": "在工作区文件内容里用正则搜索。",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": _p(type="string", description="正则表达式。"),
                "cwd": _p(type="string", description="搜索起始目录。"),
                "include": _p(type="string", description="只搜索匹配该 glob 的文件。"),
                "case_insensitive": _p(type="boolean", description="是否忽略大小写。"),
                "max_results": _p(type="integer", description="最多返回多少条。"),
            },
        },
        "risk": "low",
    },
    "apply_patch": {
        "description": "一次性应用一组 {path, old_text, new_text} 补丁。",
        "parameters": {
            "type": "object",
            "properties": {
                "patches": _p(
                    type="array",
                    description="补丁数组，每项 {path, old_text, new_text}，必填。",
                    items=_OBJ,
                ),
            },
            "required": ["patches"],
        },
        "risk": "high",
        "needConfirm": True,
    },
    "diff": {
        "description": "比较两个文件或两段文本，输出统一 diff。",
        "parameters": {
            "type": "object",
            "properties": {
                "a_path": _p(type="string", description="旧版本文件路径。"),
                "b_path": _p(type="string", description="新版本文件路径。"),
                "a_text": _p(type="string", description="旧版本文本（与 b_text 搭配使用）。"),
                "b_text": _p(type="string", description="新版本文本。"),
                "a_label": _p(type="string", description="旧版本的显示名。"),
                "b_label": _p(type="string", description="新版本的显示名。"),
                "context_lines": _p(type="integer", description="上下文行数，默认 3。"),
            },
        },
        "risk": "low",
    },
    "image_view": {
        "description": "读取图片文件，缩放后返回 base64。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": _p(type="string", description="图片路径，必填。"),
                "max_dim": _p(type="integer", description="最长边缩放上限。"),
                "format": _p(type="string", description="输出格式，如 png / jpeg。"),
            },
            "required": ["path"],
        },
        "risk": "low",
    },
    "pdf_read": {
        "description": "提取 PDF 前 N 页的文本。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": _p(type="string", description="PDF 路径，必填。"),
                "max_pages": _p(type="integer", description="最多读取页数。"),
                "max_chars": _p(type="integer", description="返回字符上限。"),
            },
            "required": ["path"],
        },
        "risk": "low",
    },
    "json_query": {
        "description": "对 JSON 数据做简化 JSONPath 查询。",
        "parameters": {
            "type": "object",
            "properties": {
                "data": _p(type="object", description="要查询的 JSON 对象，必填。"),
                "path": _p(type="string", description="JSONPath 表达式，如 $..items[?(@.ok==true)]，必填。"),
            },
            "required": ["data", "path"],
        },
        "risk": "low",
    },
    "csv_query": {
        "description": "用内联 Python 表达式过滤 CSV 行，可选列投影。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": _p(type="string", description="CSV 文件路径，必填。"),
                "where": _p(type="string", description="布尔表达式，如 amount > 100。"),
                "columns": _p(type="array", description="要保留的列名数组。", items=_S),
                "limit": _p(type="integer", description="最多返回行数。"),
            },
            "required": ["path"],
        },
        "risk": "low",
    },
    "git_status": {
        "description": "查看工作区的 git 状态。",
        "parameters": {"type": "object", "properties": {}},
        "risk": "low",
    },
    "git_diff": {
        "description": "查看工作区的 git 差异。",
        "parameters": {
            "type": "object",
            "properties": {
                "staged": _p(type="boolean", description="是否只看暂存区。"),
                "context_lines": _p(type="integer", description="上下文行数。"),
            },
        },
        "risk": "low",
    },
    "git_log": {
        "description": "查看工作区的 git 提交历史。",
        "parameters": {
            "type": "object",
            "properties": {"n": _p(type="integer", description="返回条数，默认 10。")},
        },
        "risk": "low",
    },
    "code_search": {
        "description": "语法感知的代码搜索（优先 ast-grep，回退 grep）。",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": _p(type="string", description="搜索模式，必填。"),
                "lang": _p(type="string", description="限定语言，如 python / ts。"),
                "include": _p(type="string", description="只搜索匹配该 glob 的文件。"),
                "cwd": _p(type="string", description="搜索起始目录。"),
                "max_results": _p(type="integer", description="最多返回多少条。"),
            },
            "required": ["pattern"],
        },
        "risk": "low",
    },
    "convert_format": {
        "description": "在 csv / json / yaml 之间转换。",
        "parameters": {
            "type": "object",
            "properties": {
                "input": _p(type="string", description="内联的源文本。"),
                "path": _p(type="string", description="源文件路径（与 input 二选一）。"),
                "from": _p(type="string", description="源格式 csv / json / yaml。"),
                "to": _p(type="string", description="目标格式 csv / json / yaml。"),
            },
            "required": ["from", "to"],
        },
        "risk": "low",
    },
    "calculator": {
        "description": "受限数学表达式求值器。",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": _p(type="string", description="算术表达式，如 (1+2)*3，必填。"),
            },
            "required": ["expression"],
        },
        "risk": "low",
    },
    "ask_user_question": {
        "description": "向用户提问并等待回答（前端渲染成选择题卡片）。",
        "parameters": {
            "type": "object",
            "properties": {
                "question": _p(type="string", description="单个问题。"),
                "questions": _p(type="array", description="问题数组，每项含 question / options。", items=_OBJ),
                "options": _p(type="array", description="单题的候选项数组。", items=_OBJ),
            },
        },
        "risk": "low",
    },
    "notify_user": {
        "description": "给用户弹一条通知（前端渲染成 toast）。",
        "parameters": {
            "type": "object",
            "properties": {
                "title": _p(type="string", description="通知标题，必填。"),
                "body": _p(type="string", description="通知正文。"),
                "level": _p(type="string", description="级别 info / warn / error / success。"),
            },
            "required": ["title"],
        },
        "risk": "low",
    },
    "plan_submit": {
        "description": "提交一份待批准的执行计划（前端渲染成计划卡）。",
        "parameters": {
            "type": "object",
            "properties": {
                "title": _p(type="string", description="计划标题。"),
                "steps": _p(type="array", description="步骤数组，每项 {id, title, description, kind}。", items=_OBJ),
                "plan_id": _p(type="string", description="计划 ID。"),
                "reason": _p(type="string", description="提交理由。"),
            },
        },
        "risk": "low",
    },
    "todo_write": {
        "description": "更新待办事项列表（前端渲染成待办卡）。",
        "parameters": {
            "type": "object",
            "properties": {
                "todos": _p(type="array", description="待办数组，每项 {id, content, status, active_form}。", items=_OBJ),
                "content": _p(type="string", description="单条待办内容。"),
                "id": _p(type="string", description="待办 ID。"),
                "status": _p(type="string", description="状态 pending / in_progress / completed。"),
                "active_form": _p(type="string", description="进行中的显示文案。"),
            },
        },
        "risk": "low",
    },
    "delegate_to_agent": {
        "description": "把一个子任务委派给另一个智能体，子会话跑完后回传结果。",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": _p(type="string", description="目标智能体 ID，必填。"),
                "task": _p(type="string", description="交给子智能体的任务描述，必填。"),
                "context": _p(type="string", description="补充上下文。"),
            },
            "required": ["agent_id", "task"],
        },
        "risk": "medium",
    },
}


def builtin_spec(name: str) -> dict[str, Any] | None:
    """Return the catalog entry for a built-in tool, if any."""
    return BUILTIN_TOOL_SPECS.get(name)


__all__ = ["BUILTIN_TOOL_SPECS", "builtin_spec"]
