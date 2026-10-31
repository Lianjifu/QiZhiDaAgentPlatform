"""``LLMSummaryAdapter`` —— **摘要模型**的模块侧实现 ✓。

依据：Context 方案 §4.2（一级摘要 ✓）、§4.3 缺陷 1（**async** ✓）、
§11 风险表（「摘要模型成为延迟瓶颈」→ **只在超预算时才触发** ✓）。

⚠️ **契约层只定义端口** ✓（``SummaryModelPort`` ✓）—— 这里把平台的
``LLMPort`` 包成它 ✓（契约层不引平台 LLM ✓）。

⚠️ **失败就抛** ✓ —— 由 Compressor 降级成**确定性窗口** ✓（这里吞掉
就没人知道降级了 ✗✗）。
"""

from __future__ import annotations

import logging

from qzdap.modules.agent_runtime.application.ports import LLMPort
from qzdap_agent_runtime.context.compressor import SummaryModelPort
from qzdap_kernel.ids import ModelId
from qzdap_llm.client import ChatMessage, ChatRequest
from qzdap_vault.actor import ActorContext

_log = logging.getLogger(__name__)

#: 摘要的输出上限（token）✓ —— 摘要不该比它概括的内容还长 ✗。
SUMMARY_MAX_TOKENS = 800


class LLMSummaryAdapter(SummaryModelPort):
    """用平台 LLM 生成**结构化摘要** ✓。

    ⚠️ **提示词由契约层给** ✓（``summarize(prompt=…)`` ✓）—— 提示词模板
    是 Context 层的责任 ✓（这里只管调用 ✓）。
    """

    def __init__(
        self,
        llm: LLMPort,
        *,
        model: str,
        actor: ActorContext | None = None,
        model_id: ModelId | None = None,
    ) -> None:
        self._llm = llm
        self._model = model or "default"
        self._actor = actor
        self._model_id = model_id

    async def summarize(self, *, prompt: str) -> str:
        """调一次模型，把增量文本拼成摘要 ✓。"""
        request = ChatRequest(
            model=self._model,
            messages=[ChatMessage(role="user", content=prompt)],
            max_tokens=SUMMARY_MAX_TOKENS,
        )
        if self._model_id is not None:
            stream = self._llm.stream(request, model_id=self._model_id, actor=self._actor)
        else:
            stream = self._llm.stream(request)
        parts: list[str] = []
        # ⚠️ **整条流读完** ✓（不中途退出 ✓）—— 所以不需要 `aclosing` ✓
        # （仓库里那两处 `aclosing` 是 mypy 已知的抱怨 ✗ —— 不再添一处 ✗）。
        async for chunk in stream:
            delta = str(getattr(chunk, "delta", "") or "")
            if delta:
                parts.append(delta)
        return "".join(parts).strip()


__all__ = ["SUMMARY_MAX_TOKENS", "LLMSummaryAdapter"]
