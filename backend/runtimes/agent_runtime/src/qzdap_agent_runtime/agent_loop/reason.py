"""``Reasoner`` —— **推理一步** ✓（上下文 + 工具 schema → 流式文本 + 工具调用 ✓）。

依据：Agent 方案 §3.1（Reason / Plan ✓）、§5.2.2（调用模型完成生成 ✓）、
§8.1（``agent_loop/reason.py`` ✓）、§8.2（**迁入** ``ToolCallAccumulator`` ✓）。

⚠️ **工具调用必须先装配再执行** ✓（§3.1 第 1 条 ✓）—— 流式协议会把一次
tool call 拆成多个 delta（名字分片 ✓、参数分片 ✓）→ **逐 delta 直接执行是
经典 bug** ✗✗（拿半截参数去调工具 ✗）。

⚠️ **文本与工具调用分离投递** ✓（§3.1 第 2 条 ✓）—— 文本增量**立即**推给
前端 ✓；工具调用**等装配完整**才交出去 ✓。

⚠️ **delta 用 ``AIMessageChunk`` 承载** ✓（§3.1 第 3 条 ✓）—— LangChain 的
标准类型 ✓（``ToolNode`` / Deep Agents 都能直接消费 ✓）。

⚠️ **本模块不做上下文裁剪** ✓（§3.1 第 5 条 ✓）—— 那是 Context 层的事 ✓。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessageChunk, BaseMessage

from ..execution.chat_model import QZDAPChatModel


class ToolCallAccumulator:
    """**合并分片的工具调用** ✓（**最容易写错的逻辑** ✓ —— §8.2 ✓）。

    ⚠️ **从旧路径迁入** ✓（``modules/.../adapter/graph/chat_model.py`` ✓）——
    行为保持一致 ✓：按 ``index`` 归并 ✓、字符串参数与 dict 参数**不容混用**
    ✓（混了就抛 ✗ —— 半截参数去调工具比报错更糟 ✗✗）、``thought_signature``
    透传 ✓。

    ⚠️ **旧的那份还留着** ✓（旧循环还在服役 ✓）—— **删除归 Agent Stage 7** ✓
    （A-09 ✓ —— 只迁入不删 ✓）。
    """

    def __init__(self) -> None:
        self._calls: dict[object, dict[str, Any]] = {}
        self._ids: dict[str, object] = {}

    def add(self, chunks: Sequence[Mapping[str, Any]]) -> None:
        """收一批分片 ✓（LangChain 的 ``tool_call_chunks`` 形状 ✓）。"""
        for position, chunk in enumerate(chunks):
            call_id = chunk.get("id")
            key = chunk.get("index")
            if key is None:
                key = self._ids.get(str(call_id), str(call_id)) if call_id else position
            target = self._calls.setdefault(key, {"id": None, "name": "", "args": ""})
            if call_id:
                target["id"] = call_id
                self._ids[str(call_id)] = key
            if chunk.get("thought_signature"):
                target["thought_signature"] = chunk["thought_signature"]
            name = chunk.get("name")
            if name:
                target["name"] += str(name)
            args = chunk.get("args")
            if isinstance(args, str):
                if not isinstance(target["args"], str):
                    raise TypeError("mixed tool argument representations")
                target["args"] += args
            elif isinstance(args, dict):
                if not target["args"]:
                    target["args"] = {}
                if not isinstance(target["args"], dict):
                    raise TypeError("mixed tool argument representations")
                target["args"].update(args)

    def finish(self) -> list[dict[str, Any]]:
        """**装配完成的工具调用** ✓（LangChain 的 ``tool_calls`` 形状 ✓）。

        ⚠️ **参数在这里就解析成 dict** ✓ —— LangChain 的 ``ToolCall.args`` 是
        dict ✓（旧路径留到执行前才解析 ✓ —— 那边是同一套口径 ✓）。
        """
        return [
            {
                "id": call["id"] or str(uuid4()),
                "type": "tool_call",
                "name": call["name"],
                "args": _parse_arguments(call["args"]),
                **(
                    {"thought_signature": call["thought_signature"]}
                    if "thought_signature" in call
                    else {}
                ),
            }
            for call in self._calls.values()
        ]


def _parse_arguments(raw: Any) -> dict[str, Any]:
    """工具参数 → dict ✓（**解析失败不抛** ✓ —— 包成 ``{"input": raw}`` ✓）。

    ⚠️ **口径与旧路径一致** ✓（``adapter/graph/tools.py::parse_arguments`` ✓）
    —— 同一份行为 ✓，别在这里另发明一套 ✗✗。
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"input": raw}
        return parsed if isinstance(parsed, dict) else {"input": parsed}
    return {}


class Reasoner:
    """**跑一步推理** ✓（§3.1 ✓）。

    ⚠️ **模型是构造时给的** ✓（``QZDAPChatModel`` 实例 ✓ —— 「从 agent 配置
    解析出来」的那个 ✓ —— 决策 #4 ✓）—— 本类**不选模型** ✗✗。
    """

    def __init__(self, model: QZDAPChatModel) -> None:
        self._model = model

    async def reason(
        self,
        *,
        messages: list[BaseMessage],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[AIMessageChunk]:
        """**产出文本增量** ✓；**装配好的工具调用**在最后一条上 ✓。

        ⚠️ **文本立即推** ✓（§3.1 第 2 条 ✓）—— 工具调用**最后才给** ✓。
        """
        accumulator = ToolCallAccumulator()
        pending_tool_chunk = False
        # ⚠️ **`astream` 给的是 `AIMessageChunk`** ✓（LangChain 把
        # `ChatGenerationChunk` 拆开了 ✓）—— 字段直接在上面 ✓。
        async for chunk in self._model.astream(messages, tools=tools):
            if chunk.tool_call_chunks:
                accumulator.add(list(chunk.tool_call_chunks))
                pending_tool_chunk = True
                # ⚠️ **工具调用的分片不单独推** ✓ —— 只推文本 ✓（§3.1 第 2 条 ✓）
                if not chunk.content:
                    continue
            if chunk.content or chunk.usage_metadata:
                # ⚠️ **用量要跟着走** ✓（§3.1 第 4 条 ✓）—— 新建 chunk 时
                # 别把它丢了 ✗✗。
                # ⚠️ **用量那一段没有正文** ✓（只有 usage ✓）—— **照样要递出去**
                # ✓（否则这一轮的 token 数永远是 0 ✗✗）。
                yield AIMessageChunk(
                    content=chunk.content, usage_metadata=chunk.usage_metadata
                )
        assembled = accumulator.finish()
        if assembled:
            # ⚠️ **最后一条带装配好的调用** ✓ —— 调用方读它 ✓（而不是读分片 ✗）。
            yield AIMessageChunk(content="", tool_calls=assembled)
        elif pending_tool_chunk:
            yield AIMessageChunk(content="")


__all__ = ["Reasoner", "ToolCallAccumulator"]
