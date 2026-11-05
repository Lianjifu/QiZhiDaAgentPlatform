"""**任务清单（todo）** ✓ —— 「先规划再执行」✓。

⚠️ **这组测试守的是「清单真的进了状态」** ✓ —— 不是「函数写对了」✓。
"""

from __future__ import annotations

import json
from uuid import UUID

from qzdap_agent_runtime.agent_loop.state import LoopState
from qzdap_agent_runtime.agent_loop.todos import (
    TODO_PREFIX,
    parse_todos,
    render_todos,
    summarize_progress,
)
from qzdap_kernel.todo_protocol import TODO_PREFIX as KERNEL_PREFIX

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
OWNER = UUID("00000000-0000-0000-0000-000000000010")


def test_the_prefix_has_one_source_of_truth() -> None:
    """**前缀只有一份** ✓ —— tool 模块与 runtime 共享 ✓（分层约束 ✓）。"""
    assert TODO_PREFIX == KERNEL_PREFIX


def test_the_todo_payload_is_parsed() -> None:
    """**带前缀的输出能解析出清单** ✓。"""
    payload = json.dumps(
        [
            {"content": "查数据", "status": "completed"},
            {"content": "写报告", "status": "in_progress"},
        ],
        ensure_ascii=False,
    )
    parsed = parse_todos(f"{TODO_PREFIX}{payload}")
    assert parsed == [
        {"content": "查数据", "status": "completed"},
        {"content": "写报告", "status": "in_progress"},
    ]


def test_a_normal_tool_output_is_not_a_todo_update() -> None:
    """**普通工具输出不是 todo 更新** ✓ —— 返回 ``None`` ✓。"""
    assert parse_todos("查到了 42 条记录") is None
    assert parse_todos("") is None


def test_a_broken_todo_payload_does_not_raise() -> None:
    """**解析失败不抛** ✓ —— 工具输出永远不能打断对话 ✓。"""
    assert parse_todos(f"{TODO_PREFIX}这不是 JSON") is None
    assert parse_todos(f"{TODO_PREFIX}{{}}") is None
    assert parse_todos(f"{TODO_PREFIX}[1, 2, 3]") is None


def test_the_status_is_normalized() -> None:
    """**非法状态归一** ✓ —— 不让模型写出第四种状态 ✓。"""
    payload = json.dumps([{"content": "x", "status": "乱写的"}])
    parsed = parse_todos(f"{TODO_PREFIX}{payload}")
    assert parsed == [{"content": "x", "status": "pending"}]


def test_the_plan_is_rendered_for_the_model() -> None:
    """**清单回灌给模型** ✓ —— 只列未完成的 ✓。"""
    text = render_todos(
        [
            {"content": "已完成的事", "status": "completed"},
            {"content": "正在做的事", "status": "in_progress"},
            {"content": "还没做的事", "status": "pending"},
        ]
    )
    assert "正在做的事" in text
    assert "还没做的事" in text
    assert "已完成的事" not in text


def test_an_empty_plan_renders_to_nothing() -> None:
    """**空清单不塞空段** ✓。"""
    assert render_todos([]) == ""
    assert render_todos([{"content": "x", "status": "completed"}]) == ""


def test_the_progress_summary_counts_completed() -> None:
    """**收尾时能报进度** ✓。"""
    text = summarize_progress(
        [
            {"content": "a", "status": "completed"},
            {"content": "b", "status": "pending"},
        ]
    )
    assert "1/2" in text


def test_the_loop_absorbs_the_todo_update_into_the_state() -> None:
    """**循环把清单写进状态** ✓ —— 这是「规划能力真的存在」的判据 ✓。

    ⚠️ **直接打 ``_absorb_todos``** ✓ —— 它是静态方法 ✓（不依赖运行中的
    循环 ✓）—— 断言的是「状态被写了」✓ 而不是「跑了一整轮」✓。
    """
    from qzdap_agent_runtime.agent_loop.observe import ToolOutcome
    from qzdap_agent_runtime.agent_loop.runner import AgentLoopRunner

    payload = json.dumps([{"content": "先做这个", "status": "in_progress"}])
    outcome = ToolOutcome(
        tool_call_id="call-1",
        name="todo_write",
        output=f"{TODO_PREFIX}{payload}",
    )
    state = LoopState()
    AgentLoopRunner._absorb_todos(state, [outcome])
    assert state.todos == [{"content": "先做这个", "status": "in_progress"}]


def test_a_later_update_replaces_the_earlier_one() -> None:
    """**后一次覆盖前一次** ✓ —— 不是增量合并 ✓
    （合并会让「删掉一项」永远做不到 ✗✗）。
    """
    from qzdap_agent_runtime.agent_loop.observe import ToolOutcome
    from qzdap_agent_runtime.agent_loop.runner import AgentLoopRunner

    first = ToolOutcome(
        tool_call_id="c1",
        name="todo_write",
        output=f"{TODO_PREFIX}{json.dumps([{'content': 'a', 'status': 'pending'}])}",
    )
    second = ToolOutcome(
        tool_call_id="c2",
        name="todo_write",
        output=f"{TODO_PREFIX}{json.dumps([{'content': 'b', 'status': 'pending'}])}",
    )
    state = LoopState()
    AgentLoopRunner._absorb_todos(state, [first, second])
    assert state.todos == [{"content": "b", "status": "pending"}]


def test_the_tool_emits_the_payload_the_loop_reads() -> None:
    """**工具真的发出循环能读的那一行** ✓ —— 两端对得上 ✓。

    ⚠️ **这是最关键的一条** ✓ —— 前缀写错 / 字段名写错 ✓ →
    工具发了 ✓ 但循环读不到 ✓ → 「规划」又是假的 ✗✗。
    """
    import asyncio

    from qzdap.modules.tool.adapter.adapters.builtin_extra_tools import (
        built_in_invoke_todo_write,
    )

    result = asyncio.run(
        built_in_invoke_todo_write(
            {"todos": [{"content": "写方案", "status": "in_progress"}]},
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            call_id=UUID("00000000-0000-0000-0000-0000000000cc"),
            actor_id=OWNER,
        )
    )
    parsed = parse_todos(str(result.get("output") or ""))
    assert parsed == [{"content": "写方案", "status": "in_progress"}]
