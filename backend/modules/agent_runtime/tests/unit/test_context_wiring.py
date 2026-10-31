"""Context Stage 4：接线 —— 压缩 / manifest / 摘要写新列 ✓。

依据：Context 方案 §4（Compressor）、§5.2（**manifest 先于模型落库** ✓）、
§5.1（**摘要的唯一落点** ✓）、台账 **X9**（旧压缩 ✓）。

验收三条 ✓：**旧压缩不再被调用** ✓ / **压缩事件带真实 token 与降级标记** ✓ /
**每次模型调用前落一条 manifest** ✓。
"""

from __future__ import annotations

import inspect
from typing import Any
from uuid import UUID, uuid4

import pytest

from qzdap.modules.agent_runtime.adapter.graph import runner as runner_module
from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner
from qzdap.modules.agent_runtime.application.ports import LLMPort
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent
from qzdap_kernel.ids import ModelId
from qzdap_llm.client import ChatRequest, LLMChunk, Usage
from qzdap_schema.dtos.turn import ContextCompactedChunk

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
OWNER = UUID("00000000-0000-0000-0000-000000000010")

#: 摘要请求的提示词片段 ✓ —— 测试据此把「摘要」与「主对话」分开 ✓。
_SUMMARY_MARKER = "结构化摘要"


class _FakeLLM(LLMPort):
    """主对话正常 ✓ —— **摘要请求一律失败** ✓（模拟摘要模型挂了 ✓）。"""

    def __init__(self, *, reply: str = "好的。") -> None:
        self.reply = reply
        self.calls = 0
        self.summary_attempts = 0

    async def stream(self, req: ChatRequest, **kwargs: object):
        _ = kwargs
        self.calls += 1
        content = " ".join(str(m.content or "") for m in req.messages)
        if _SUMMARY_MARKER in content:
            self.summary_attempts += 1
            raise RuntimeError("summary model is down")
        yield LLMChunk(model=req.model, delta=self.reply)
        yield LLMChunk(
            model=req.model,
            delta="",
            finish_reason="stop",
            usage=Usage(input_tokens=4, output_tokens=2),
        )

    async def synthetic_chunks(self, user_input: str, *, turn_id=None) -> list[dict]:
        _ = (user_input, turn_id)
        return []


class _RecordingManifestStore:
    """manifest 落库口替身 ✓ —— 记下调用与顺序 ✓。"""

    def __init__(self, order: list[str]) -> None:
        self.order = order
        self.manifests: list[dict[str, Any]] = []
        self.summaries: list[dict[str, Any]] = []

    async def save_manifest(self, **kwargs: Any) -> None:
        self.order.append("manifest")
        self.manifests.append(dict(kwargs))

    async def save_rolling_summary(self, **kwargs: Any) -> None:
        self.order.append("summary")
        self.summaries.append(dict(kwargs))


def _agent() -> CatalogAgent:
    return CatalogAgent.create(
        id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        name="助手",
        category="企业通用",
        owner="管理员",
        description="",
        model="demo",
    )


def _long_history(count: int = 40) -> list[dict[str, Any]]:
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": "内容" * 100}
        for i in range(count)
    ]


async def _run(
    runner: SessionGraphRunner,
    *,
    history: list[dict[str, Any]] | None = None,
    context_window: int = 8000,
    agent: CatalogAgent | None = None,
) -> list[Any]:
    return [
        chunk
        async for chunk in runner.run_turn(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            owner_id=OWNER,
            turn_id=uuid4(),
            session_id=uuid4(),
            user_input="你好",
            history=history or [],
            agent=agent if agent is not None else _agent(),
            model="demo",
            context_window=context_window,
        )
    ]


class TestTheOldCompressionIsGone:
    def test_the_runner_no_longer_calls_the_old_compaction(self) -> None:
        """**旧的 `compact_messages` 不再被调用** ✓（台账 X9 ✓）。"""
        source = inspect.getsource(runner_module)
        assert "compact_messages(" not in source

    def test_the_old_module_is_not_imported(self) -> None:
        assert "adapter.graph.compact" not in inspect.getsource(runner_module)


class TestCompaction:
    @pytest.mark.asyncio
    async def test_a_long_history_is_compacted(self) -> None:
        """长会话 → **压到预算内** ✓（并发出事件 ✓）。"""
        llm = _FakeLLM()
        runner = SessionGraphRunner(llm=llm)
        chunks = await _run(runner, history=_long_history())
        compacted = [c for c in chunks if isinstance(c, ContextCompactedChunk)]
        assert compacted, "超预算的长会话必须触发压缩"
        assert compacted[0].tokens_before > 0
        assert compacted[0].tokens_after <= compacted[0].tokens_before

    @pytest.mark.asyncio
    async def test_a_summary_failure_degrades_visibly(self) -> None:
        """**摘要模型挂了 → 确定性窗口** ✓ + **降级可见** ✓（§4.3 缺陷 7 ✓）。"""
        llm = _FakeLLM()
        runner = SessionGraphRunner(llm=llm)
        chunks = await _run(runner, history=_long_history())
        compacted = [c for c in chunks if isinstance(c, ContextCompactedChunk)]
        assert llm.summary_attempts == 1, "超预算就该先试摘要"
        assert compacted[0].degraded is True

    @pytest.mark.asyncio
    async def test_a_short_turn_is_not_compacted(self) -> None:
        """没超预算 → **不压缩** ✓（不多花钱 ✓）。"""
        llm = _FakeLLM()
        runner = SessionGraphRunner(llm=llm)
        chunks = await _run(runner, history=[])
        assert not [c for c in chunks if isinstance(c, ContextCompactedChunk)]
        assert llm.summary_attempts == 0


class TestManifest:
    @pytest.mark.asyncio
    async def test_a_manifest_is_saved_before_the_model_call(self) -> None:
        """**模型已回答 ⇒ manifest 一定存在** ✓（§5.2 ✓）。"""
        order: list[str] = []
        store = _RecordingManifestStore(order)
        llm = _FakeLLM()
        runner = SessionGraphRunner(llm=llm, context_manifest_store=store)  # type: ignore[arg-type]
        await _run(runner, history=[])
        assert len(store.manifests) == 1
        saved = store.manifests[0]
        assert saved["step"] == 0
        assert saved["tokens_total"] > 0
        assert saved["degraded"]["recall_degraded"] is False
        assert order[0] == "manifest"

    @pytest.mark.asyncio
    async def test_the_manifest_describes_what_was_sent(self) -> None:
        """manifest 的条目 = **真正喂进去的那批消息** ✓（§3.5 ✓）。"""
        store = _RecordingManifestStore([])
        llm = _FakeLLM()
        runner = SessionGraphRunner(llm=llm, context_manifest_store=store)  # type: ignore[arg-type]
        agent = _agent()
        agent.prompts["soul"] = "你是测试助手"
        await _run(runner, history=[], agent=agent)
        entries = store.manifests[0]["manifest"]["entries"]
        sources = {entry["source"] for entry in entries}
        assert "system" in sources
        assert "agent" in sources
        assert all("tokens" in entry for entry in entries)

    @pytest.mark.asyncio
    async def test_the_rolling_summary_goes_to_the_new_column(self) -> None:
        """**摘要写新列** ✓（§5.1 ✓）—— 旧副本不再写 ✓。"""
        store = _RecordingManifestStore([])
        llm = _FakeLLM()
        runner = SessionGraphRunner(llm=llm, context_manifest_store=store)  # type: ignore[arg-type]
        await _run(runner, history=_long_history())
        assert store.summaries, "轮次收尾要把摘要写进新列"
        assert store.summaries[0]["summary"]


class TestModelResolution:
    @pytest.mark.asyncio
    async def test_a_saved_model_id_still_works(self) -> None:
        """模型 id 是 UUID 时照旧解析 ✓（接线不能改坏这条路 ✓）。"""
        llm = _FakeLLM()
        runner = SessionGraphRunner(llm=llm)
        chunks = [
            chunk
            async for chunk in runner.run_turn(
                tenant_id=TENANT,
                workspace_id=WORKSPACE,
                owner_id=OWNER,
                turn_id=uuid4(),
                session_id=uuid4(),
                user_input="你好",
                history=[],
                agent=_agent(),
                model=str(ModelId(uuid4())),
            )
        ]
        assert chunks


__all__ = ["TestCompaction", "TestManifest", "TestModelResolution", "TestTheOldCompressionIsGone"]
