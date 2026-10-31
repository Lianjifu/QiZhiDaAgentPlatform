"""Gateway：**降级标记有可投递的通道** ✓（C-22 ✓ —— Gateway 方案 §9.0 ✓）。

⚠️ **之前 Context 侧已经产出 ``recall_degraded``** ✓ —— 但**没有通道**
✗✗（前端收不到 ✓ → 「降级不可见」✗✗）→ 现在**挂在信封上** ✓
（``ChunkEnvelope.flags`` ✓ + 内部协议的 ``ResultEvent.flags`` ✓）。

验收 ✓：

- **召回失败** → 这一轮的每一块都带 ``recall_degraded`` ✓；
- **没降级** → 不带标记 ✓（不带 ≠ 空列表噪音 ✓）；
- **标记的词汇只有三个** ✓（Gateway 方案 §9.0 ✓ —— 认不出来的丢掉 ✓）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner
from qzdap.modules.agent_runtime.application.ports import LLMPort
from qzdap_llm.client import ChatRequest, LLMChunk, Usage

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
OWNER = UUID("00000000-0000-0000-0000-000000000010")


class _FakeLLM(LLMPort):
    async def stream(self, req: ChatRequest, **kwargs: object):
        _ = kwargs
        yield LLMChunk(model=req.model, delta="好的。")
        yield LLMChunk(
            model=req.model,
            delta="",
            finish_reason="stop",
            usage=Usage(input_tokens=4, output_tokens=2),
        )

    async def synthetic_chunks(self, user_input: str, *, turn_id=None) -> list[dict]:
        _ = (user_input, turn_id)
        return []


class _FailingMemory:
    """**召回必失败** ✓ —— 模拟记忆服务挂了 ✓。"""

    async def recall(self, **kwargs: Any) -> list[dict]:
        _ = kwargs
        raise RuntimeError("memory service is down")

    async def write_turn(self, **kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        return {"written": 0}


class _WorkingMemory:
    async def recall(self, **kwargs: Any) -> list[dict]:
        _ = kwargs
        return []

    async def write_turn(self, **kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        return {"written": 0}


async def _run(runner: SessionGraphRunner) -> list[Any]:
    return [
        chunk
        async for chunk in runner.run_turn(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            owner_id=OWNER,
            turn_id=uuid4(),
            session_id=uuid4(),
            user_input="你好",
            history=[],
            agent=None,
            model="demo",
        )
    ]


@pytest.mark.asyncio
async def test_a_recall_failure_is_visible_on_every_chunk() -> None:
    """**召回失败 → 每一块都带标记** ✓（降级可见 ✓）。"""
    runner = SessionGraphRunner(llm=_FakeLLM(), memory_port=_FailingMemory())  # type: ignore[arg-type]
    chunks = await _run(runner)
    assert chunks, "这一轮应该产出块"
    assert all("recall_degraded" in chunk.flags for chunk in chunks)


@pytest.mark.asyncio
async def test_a_healthy_turn_carries_no_flag() -> None:
    """**没降级就不带标记** ✓（不带 ≠ 塞一堆空标记 ✓）。"""
    runner = SessionGraphRunner(llm=_FakeLLM(), memory_port=_WorkingMemory())  # type: ignore[arg-type]
    chunks = await _run(runner)
    assert chunks
    assert all(not chunk.flags for chunk in chunks)
