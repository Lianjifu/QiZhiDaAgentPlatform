"""**产物**（模型 / 工具的输出）✓ —— 落库 + 出卡片 ✓。

覆盖三件事：

- 工具结果里的产物**被摘走** ✓（内容不进模型上下文 ✓）；
- ``write_artifact`` 工具**产出**产物 ✓（校验 ✓）；
- 轮次里**落库并发一张卡片** ✓（``artifact_ready`` chunk ✓）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner
from qzdap.modules.agent_runtime.adapter.graph.tools import take_artifact
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent
from qzdap.modules.tool.adapter.adapters.builtin_extra_tools import (
    built_in_invoke_write_artifact,
)
from qzdap_agent_runtime.ports import ActorContext
from qzdap_kernel.ids import ModelId
from qzdap_llm.client import ChatRequest, LLMChunk, Usage
from qzdap_schema.dtos.turn import ArtifactReadyChunk
from qzdap_vault.actor import ActorContext as VaultActorContext

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
OWNER = UUID("00000000-0000-0000-0000-000000000010")

_ARTIFACT = {
    "name": "周报.md",
    "kind": "markdown",
    "mime": "text/markdown",
    "content": "# 本周周报\n\n- 做了三件事\n",
}


# ── 摘产物 ──────────────────────────────────────────────────────────────


def test_take_artifact_pulls_the_payload_out() -> None:
    artifact, rest = take_artifact({"_artifact": dict(_ARTIFACT)})
    assert artifact == _ARTIFACT
    assert "_artifact" not in rest
    assert "已产出产物" in str(rest["output"])


def test_take_artifact_leaves_other_results_alone() -> None:
    artifact, rest = take_artifact({"ok": True, "output": "42"})
    assert artifact is None
    assert rest == {"ok": True, "output": "42"}


def test_take_artifact_ignores_an_empty_payload() -> None:
    artifact, rest = take_artifact({"_artifact": {"name": "", "content": ""}})
    assert artifact is None
    assert "_artifact" in rest


# ── 工具 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_tool_produces_an_artifact() -> None:
    result = await built_in_invoke_write_artifact(
        {"name": "周报.md", "content": "# 周报", "kind": "markdown"},
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        call_id=uuid4(),
        actor_id=OWNER,
    )
    assert result["_artifact"]["name"] == "周报.md"
    assert result["_artifact"]["kind"] == "markdown"
    assert result["_artifact"]["mime"] == "text/markdown"
    assert result["_artifact"]["content"] == "# 周报"


@pytest.mark.asyncio
async def test_the_tool_needs_a_name_and_content() -> None:
    missing_name = await built_in_invoke_write_artifact(
        {"content": "x"},
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        call_id=uuid4(),
        actor_id=OWNER,
    )
    missing_content = await built_in_invoke_write_artifact(
        {"name": "a.md"},
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        call_id=uuid4(),
        actor_id=OWNER,
    )
    assert "error" in missing_name
    assert "error" in missing_content


@pytest.mark.asyncio
async def test_the_tool_refuses_more_than_one_mebibyte() -> None:
    result = await built_in_invoke_write_artifact(
        {"name": "big.md", "content": "x" * (1024 * 1024 + 1)},
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        call_id=uuid4(),
        actor_id=OWNER,
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_an_unknown_kind_falls_back_to_text() -> None:
    result = await built_in_invoke_write_artifact(
        {"name": "a.bin", "content": "x", "kind": "不存在的类别"},
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        call_id=uuid4(),
        actor_id=OWNER,
    )
    assert result["_artifact"]["kind"] == "text"


# ── 轮次 ────────────────────────────────────────────────────────────────


class _ScriptedLLM:
    def __init__(self, steps: list[dict[str, Any]]) -> None:
        self._steps = list(steps)
        self.calls = 0

    async def stream(self, req: ChatRequest, **kwargs: object):
        _ = kwargs
        idx = min(self.calls, len(self._steps) - 1)
        self.calls += 1
        step = self._steps[idx]
        if step.get("tool_calls"):
            yield LLMChunk(model=req.model, delta="", tool_calls=list(step["tool_calls"]))
        if step.get("delta"):
            yield LLMChunk(model=req.model, delta=str(step["delta"]))
        yield LLMChunk(
            model=req.model,
            delta="",
            finish_reason="stop",
            usage=Usage(input_tokens=4, output_tokens=2),
        )

    async def synthetic_chunks(
        self, user_input: str, *, turn_id: UUID | None = None
    ) -> list[dict[str, Any]]:
        _ = (user_input, turn_id)
        return []


class _ArtifactToolPort:
    """工具端口的替身 ✓ —— 每次调用都产出一个产物 ✓。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "write_artifact",
                "description": "产出产物",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["name", "content"],
                },
                "risk": "low",
                "needConfirm": False,
            }
        ]

    async def invoke(
        self,
        *,
        call_id: UUID,
        tool_name: str,
        arguments: dict[str, Any],
        turn_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        _ = (call_id, turn_id, idempotency_key)
        self.calls.append({"tool_name": tool_name, "arguments": arguments})
        return {"_artifact": dict(_ARTIFACT)}


class _RecordingArtifactStore:
    """产物落库口的替身 ✓ —— 记录落了什么 ✓。"""

    def __init__(self) -> None:
        self.saved: list[dict[str, Any]] = []

    async def save(self, **kwargs: Any) -> Any:
        from qzdap.modules.agent_runtime.adapter.persistence.artifact_store import (
            ArtifactRecord,
        )

        self.saved.append(kwargs)
        content = kwargs["content"]
        return ArtifactRecord(
            id=uuid4(),
            name=kwargs["name"],
            kind=kwargs["kind"],
            mime=kwargs["mime"],
            size_bytes=len(content),
            sha256="0" * 64,
            snippet=content.decode()[:800],
            content=content,
        )

    async def get(self, **kwargs: Any) -> Any:
        _ = kwargs
        return None


def _agent() -> CatalogAgent:
    agent = CatalogAgent.create(
        id=uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        name="助手",
        category="企业通用",
        owner="管理员",
        model="demo",
    )
    # ⚠️ **工具要显式绑定** ✓（目录工具的规矩 ✓ —— 不绑就调不到 ✓）。
    agent.tools = [{"name": "write_artifact", "enabled": True}]
    return agent


@pytest.mark.asyncio
async def test_a_tool_artifact_becomes_a_card() -> None:
    llm = _ScriptedLLM(
        [
            {
                "tool_calls": [
                    {
                        "id": str(uuid4()),
                        "name": "write_artifact",
                        "arguments": {"name": "周报.md", "content": "# 周报"},
                    }
                ]
            },
            {"delta": "已生成周报。"},
        ]
    )
    store = _RecordingArtifactStore()
    tool_port = _ArtifactToolPort()
    runner = SessionGraphRunner(
        llm=llm,  # type: ignore[arg-type]
        tool_port=tool_port,  # type: ignore[arg-type]
        artifact_store=store,  # type: ignore[arg-type]
    )
    session_id = uuid4()
    turn_id = uuid4()
    chunks = []
    async for chunk in runner.run_turn(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        owner_id=OWNER,
        turn_id=turn_id,
        user_input="写一份周报",
        history=[],
        agent=_agent(),
        model="demo",
        session_id=session_id,
    ):
        chunks.append(chunk)

    cards = [c for c in chunks if isinstance(c, ArtifactReadyChunk)]
    assert len(cards) == 1, "工具产出一个产物 → 一张卡片"
    card = cards[0]
    assert card.name == "周报.md"
    assert card.kind_ == "markdown"
    assert card.download_path == f"/api/sessions/{session_id}/artifacts/{card.artifact_id}/content"
    assert card.snippet.startswith("# 本周周报")
    assert len(store.saved) == 1
    assert store.saved[0]["session_id"] == session_id
    assert store.saved[0]["turn_id"] == turn_id
    assert store.saved[0]["content"] == _ARTIFACT["content"].encode()


@pytest.mark.asyncio
async def test_without_a_store_no_card_is_emitted() -> None:
    """⚠️ **没有落库口就不发卡片** ✓（测试 / 纯内存场景 ✓）。"""
    llm = _ScriptedLLM(
        [
            {
                "tool_calls": [
                    {
                        "id": str(uuid4()),
                        "name": "write_artifact",
                        "arguments": {"name": "周报.md", "content": "# 周报"},
                    }
                ]
            },
            {"delta": "已生成周报。"},
        ]
    )
    runner = SessionGraphRunner(
        llm=llm,  # type: ignore[arg-type]
        tool_port=_ArtifactToolPort(),  # type: ignore[arg-type]
    )
    chunks = []
    async for chunk in runner.run_turn(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        owner_id=OWNER,
        turn_id=uuid4(),
        user_input="写一份周报",
        history=[],
        agent=_agent(),
        model="demo",
        session_id=uuid4(),
    ):
        chunks.append(chunk)
    assert not [c for c in chunks if isinstance(c, ArtifactReadyChunk)]


_ = (ActorContext, VaultActorContext, ModelId)
