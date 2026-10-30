"""``QZDAPChatModel`` —— 平台的 LLM **包成 LangChain 的 ``BaseChatModel``** ✓。

依据：Agent 方案 §2.2（**为什么必须写这个适配器** ✓）、§5.2.2（调用模型完成
生成 ✓）、§8.1（``execution/chat_model.py`` ✓）。

⚠️ **适配器是「薄」的** ✓（§2.2 ✓）—— 它只做**类型翻译** ✓：不碰供应商 ✓、
不碰路由 ✓、不碰成本 ✓。所有业务语义仍在平台侧 ✓。

⚠️ **模型是「按 agent 配置构造出来的实例」** ✓（§5.2.1 ✓）—— **查表，不是
决策** ✓（决策 #4 ✓）—— 所以这个类**不做任何模型选择** ✗✗。

⚠️ **本 Stage 只支持 mock 供应商** ✓（A-02 骨架 ✓）—— 真实供应商的解析与
失败转移链归 **Stage 1** ✓（§5.2.1 的六条取值链 ✓）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import ConfigDict
from qzdap_llm.client import ChatMessage, ChatRequest


class QZDAPChatModel(BaseChatModel):
    """把 ``qzdap_llm.LLMClient`` 包成 ``BaseChatModel`` ✓。

    ⚠️ **只做类型翻译** ✓：

    | 平台的形状 | LangChain 的形状 |
    |---|---|
    | ``ChatRequest`` | ``list[BaseMessage]`` ✓ |
    | ``LLMChunk.delta``（文本增量 ✓） | ``AIMessageChunk.content`` ✓ |
    | ``LLMChunk.tool_calls``（工具调用 delta ✓） | ``AIMessageChunk.tool_call_chunks`` ✓ |
    | ``LLMChunk.usage`` | ``AIMessageChunk.usage_metadata`` ✓ |
    """

    #: pydantic 字段要放**非 pydantic 类型**（``LLMClient`` 是普通类 ✓）→
    #: 必须放开 `arbitrary_types_allowed` ✓。
    model_config = ConfigDict(arbitrary_types_allowed=True)

    #: 平台的 LLM 客户端 ✓（**由调用方注入** ✓ —— 契约层不自己造 ✓）。
    client: Any
    #: 平台侧的模型名 ✓（``agent.model`` 那串 ✓ —— §5.2.1 的第 4 条 ✓）。
    model_name: str = "default"

    @property
    def _llm_type(self) -> str:
        return "qzdap"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        """LangChain 的身份参数 ✓ —— 缓存键要靠它 ✓。"""
        return {"model_name": self.model_name}

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
        """
        _ = (stop, run_manager)
        request = ChatRequest(
            model=self.model_name,
            messages=[_to_chat_message(message) for message in messages],
        )
        async for chunk in self.client.stream(request):
            message = AIMessageChunk(content=chunk.delta or "")
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
        raise NotImplementedError(
            "QZDAPChatModel 只支持异步流式（平台的 LLM 客户端是异步的）"
        )

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
        async for chunk in self._astream(
            messages, stop=stop, run_manager=run_manager, **kwargs
        ):
            message = chunk.message
            if isinstance(message.content, str):
                parts.append(message.content)
            if message.usage_metadata:
                usage = dict(message.usage_metadata)
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(content="".join(parts), usage_metadata=usage)
                )
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
        raise NotImplementedError(
            "QZDAPChatModel 只支持异步调用（平台的 LLM 客户端是异步的）"
        )


def _to_chat_message(message: BaseMessage) -> ChatMessage:
    """LangChain 消息 → 平台的 ``ChatMessage`` ✓（**只取能翻译的字段** ✓）。"""
    role = getattr(message, "type", None) or "user"
    content = getattr(message, "content", "") or ""
    if not isinstance(content, str):
        # 多模态内容块 —— 本平台只吃字符串 ✓（取文本部分 ✓）。
        parts = [
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict)
        ]
        content = "".join(parts)
    return ChatMessage(role=role, content=content)  # type: ignore[arg-type]


__all__ = ["QZDAPChatModel"]
