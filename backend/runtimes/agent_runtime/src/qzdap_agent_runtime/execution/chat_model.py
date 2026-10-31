"""``QZDAPChatModel`` —— 平台的 LLM **包成 LangChain 的 ``BaseChatModel``** ✓。

依据：Agent 方案 §2.2（**为什么必须写这个适配器** ✓）、§5.2.2（调用模型完成
生成 ✓）、§8.1（``execution/chat_model.py`` ✓）。

⚠️ **适配器是「薄」的** ✓（§2.2 ✓）—— 它只做**类型翻译** ✓：不碰供应商 ✓、
不碰路由 ✓、不碰成本 ✓。所有业务语义仍在平台侧 ✓。

⚠️ **模型是「按 agent 配置构造出来的实例」** ✓（§5.2.1 ✓）—— **查表，不是
决策** ✓（决策 #4 ✓）—— 所以这个类**不做任何模型选择** ✗✗。

⚠️ **内部持的是端口** ✓（``LLMPort`` ✓）—— 不是平台客户端 ✓（那样 runtime
就绑死了供应商实现 ✗✗ —— 模块侧的适配器负责那一层 ✓）。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator, Mapping
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.messages.tool import ToolCallChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import ConfigDict

from qzdap_llm.client import ChatMessage, ChatRequest
from qzdap_schema.ids import ModelId

from ..ports import ActorContext, LLMPort


class QZDAPChatModel(BaseChatModel):
    """把平台的 ``LLMPort`` 包成 ``BaseChatModel`` ✓。

    ⚠️ **只做类型翻译** ✓：

    | 平台的形状 | LangChain 的形状 |
    |---|---|
    | ``ChatRequest`` | ``list[BaseMessage]`` ✓ |
    | ``LLMChunk.delta``（文本增量 ✓） | ``AIMessageChunk.content`` ✓ |
    | ``LLMChunk.tool_calls``（工具调用 delta ✓） | ``AIMessageChunk.tool_call_chunks`` ✓ |
    | ``LLMChunk.usage`` | ``AIMessageChunk.usage_metadata`` ✓ |
    """

    #: pydantic 字段要放**非 pydantic 类型**（端口是 Protocol ✓）→
    #: 必须放开 `arbitrary_types_allowed` ✓。
    model_config = ConfigDict(arbitrary_types_allowed=True)

    #: **模型的调用口** ✓（由模块侧注入 ✓ —— runtime 不自己造客户端 ✓）。
    llm: LLMPort
    #: 平台侧的模型名 ✓（``agent.model`` 那串 ✓ —— §5.2.1 的第 4 条 ✓）。
    model_name: str = "default"
    #: **解析出来的**模型 id ✓（查表得到 ✓ —— §5.2.1 ✓）；查不到就是 ``None``
    #: （= 走环境默认模型 ✓）。
    model_id: ModelId | None = None
    #: **策略路由 id** ✓（**优先于** ``model_id`` ✓ —— §5.2.1 第 3 条 ✓）。
    route_id: ModelId | None = None
    #: **失败转移链** ✓（primary + fallback ✓ —— §5.2.1 第 5 条 ✓）。
    fallback_model_ids: tuple[ModelId, ...] = ()
    #: 调用者身份 ✓（**真实用户** ✓ —— Stage 2 的治理要用 ✓）。
    actor: ActorContext | None = None

    @property
    def _llm_type(self) -> str:
        return "qzdap"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        """LangChain 的身份参数 ✓ —— 缓存键要靠它 ✓。"""
        return {
            "model_name": self.model_name,
            "model_id": str(self.model_id) if self.model_id else None,
            "route_id": str(self.route_id) if self.route_id else None,
        }

    # ── 流式 ────────────────────────────────────────────────────────────

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """**异步流式** ✓ —— 平台的客户端本来就是异步的 ✓。

        ⚠️ **文本增量边到边推** ✓（§5.2.2 第 3 条 ✓）—— 前端的低延迟就靠它 ✓。
        ⚠️ **工具调用以 delta 分片到达** ✓ —— 这里**只翻译** ✓（**装配**归
        Reasoner ✓ —— §3.1 第 1 条 ✓）。
        """
        _ = (stop, run_manager)
        request = ChatRequest(
            model=self.model_name,
            messages=[_to_chat_message(message) for message in messages],
            tools=kwargs.get("tools") or None,
        )
        stream = self.llm.stream(
            request,
            model_id=self.model_id,
            route_id=self.route_id,
            fallback_model_ids=list(self.fallback_model_ids) or None,
            actor=self.actor,
        )
        async for chunk in stream:
            message: AIMessageChunk = AIMessageChunk(content=chunk.delta or "")
            if chunk.tool_calls:
                message.tool_call_chunks = [_to_tool_call_chunk(raw) for raw in chunk.tool_calls]
            if chunk.usage is not None:
                message.usage_metadata = {
                    "input_tokens": chunk.usage.input_tokens,
                    "output_tokens": chunk.usage.output_tokens,
                    "total_tokens": chunk.usage.input_tokens + chunk.usage.output_tokens,
                }
            yield ChatGenerationChunk(message=message)

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """**同步流式** ✓ —— 本平台没有同步客户端 ✗（契约层不该造一个 ✗）。

        ⚠️ **明确报错** ✓（而不是悄悄返回空 ✗✗ —— 那样调用方会以为「模型没
        说话」✓）。
        """
        _ = (messages, stop, run_manager, kwargs)
        raise NotImplementedError("QZDAPChatModel 只支持异步流式（平台的 LLM 客户端是异步的）")

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """**异步一次性生成** ✓ —— 由流式**聚合**而来 ✓（不另写一套逻辑 ✓）。

        ⚠️ 基类的默认实现是「把**同步** `_generate` 丢进线程池」✓ —— 那个
        路径本平台没有 ✗（客户端只有异步 ✓）→ **必须覆盖** ✓。
        """
        parts: list[str] = []
        usage: dict[str, Any] | None = None
        async for chunk in self._astream(messages, stop=stop, run_manager=run_manager, **kwargs):
            message = chunk.message
            if isinstance(message.content, str):
                parts.append(message.content)
            # ⚠️ **用量只在 `AIMessageChunk` 上有** ✓（基类的类型是
            # `BaseMessageChunk` ✗ —— 运行时拿到的就是 `AIMessageChunk` ✓）。
            chunk_usage = getattr(message, "usage_metadata", None)
            if chunk_usage:
                usage = dict(chunk_usage)
        return ChatResult(
            generations=[
                ChatGeneration(message=AIMessage(content="".join(parts), usage_metadata=usage))
            ],
            llm_output={"model_name": self.model_name},
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """**同步一次性生成** ✓ —— 同上 ✗（平台只有异步客户端 ✓）。

        ⚠️ **必须实现** ✓（``BaseChatModel`` 的抽象方法 ✓）—— 但它**明确
        报错** ✓（不是空实现 ✗✗ —— 那样会「调用成功但没有回答」✗）。
        """
        _ = (messages, stop, run_manager, kwargs)
        raise NotImplementedError("QZDAPChatModel 只支持异步调用（平台的 LLM 客户端是异步的）")


def _to_chat_message(message: BaseMessage) -> ChatMessage:
    """LangChain 消息 → 平台的 ``ChatMessage`` ✓（**只取能翻译的字段** ✓）。"""
    role = getattr(message, "type", None) or "user"
    content = getattr(message, "content", "") or ""
    if not isinstance(content, str):
        # 多模态内容块 —— 本平台只吃字符串 ✓（取文本部分 ✓）。
        parts = [str(part.get("text") or "") for part in content if isinstance(part, dict)]
        content = "".join(parts)
    return ChatMessage(role=role, content=content)  # type: ignore[arg-type]


def _to_tool_call_chunk(raw: dict[str, Any]) -> ToolCallChunk:
    """平台的工具调用 delta → LangChain 的 ``tool_call_chunks`` 条目 ✓。

    ⚠️ **形状几乎一样** ✓（``name`` / ``args`` / ``id`` / ``index`` ✓）——
    只把 ``arguments`` 改名成 ``args`` ✓（LangChain 的叫法 ✓），
    ``thought_signature`` 之类的**额外字段原样带走** ✓（Gemini 那种 ✓）。

    ⚠️ **参数可能是 dict** ✓（平台的客户端两种都发 ✓）—— **dict 就原样带走**
    ✓（转成字符串就毁了 ✗✗ —— 单引号的 repr 解析不回来 ✗）。
    """
    raw_arguments = raw.get("arguments")
    if isinstance(raw_arguments, Mapping):
        # ⚠️ **dict 参数要转成 JSON 字符串** ✓（LangChain 的
        # ``tool_call_chunks`` 只收字符串 ✓）—— **不能用 repr** ✗✗
        # （单引号 + Python 字面量 ✗ —— 解析不回来 ✗）。
        args = json.dumps(dict(raw_arguments), ensure_ascii=False)
    else:
        args = str(raw_arguments or "")
    chunk = ToolCallChunk(
        name=str(raw.get("name") or ""),
        args=args,
        id=str(raw.get("id") or ""),
        index=int(raw.get("index") or 0),
        type="tool_call_chunk",
    )
    for key, value in raw.items():
        if key not in {"name", "arguments", "id", "index", "type"}:
            # ⚠️ **额外字段原样带走** ✓（Gemini 的 ``thought_signature`` ✓ ——
            # 它要原样回传给模型 ✗ —— 丢了就断链 ✗✗）。
            # `ToolCallChunk` 是 TypedDict ✗（静态上不允许额外键 ✗）→ 运行期
            # 是普通 dict ✓（带得走 ✓）。
            chunk[key] = value  # type: ignore[literal-required]
    return chunk


__all__ = ["QZDAPChatModel"]
