"""Memory Stage 4：**C6 策略绑定** ✓（Memory 方案 §7.1 ✓）。

验收覆盖 ✓：

- **解析** ✓ —— ``enabled`` / ``scope`` / ``policyLabel`` / ``l3EntryIds`` /
  ``knowledge_refs`` ✓（六个字段**运行时真的读** ✓）；
- **作用域真的生效** ✓ —— 会话级 → 只召回本会话 ✓；
- **显式绑定的条目一定被召回** ✓（绕过阈值 ✓）；
- **关掉记忆就一条不写** ✓（``enabled=False`` ✓）；
- **不支持的作用域明确拒绝** ✓（不静默降级 ✓）。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from qzdap_agent_runtime.memory.policy import (
    MemoryPolicy,
    MemoryRef,
    MemoryRefKind,
    PolicyBinding,
)
from qzdap_agent_runtime.memory.retrieval import Candidate, RetrievalPipeline
from qzdap_agent_runtime.memory.scope import MemoryScope
from qzdap_agent_runtime.memory.writer import WriterPipeline


class _Lexical:
    def __init__(self, candidates: list[Candidate] | None = None) -> None:
        self.candidates = candidates or []
        self.calls: list[dict] = []

    async def search(self, **kwargs) -> list[Candidate]:  # type: ignore[no-untyped-def]
        self.calls.append(kwargs)
        return list(self.candidates)


class _Pinned:
    """**显式绑定**的取法替身 ✓。"""

    def __init__(self, candidates: list[Candidate] | None = None) -> None:
        self.candidates = candidates or []
        self.calls: list[dict] = []

    async def get_by_ids(self, **kwargs) -> list[Candidate]:  # type: ignore[no-untyped-def]
        self.calls.append(kwargs)
        return list(self.candidates)


def _candidate(ref_id: str, score: float, **kwargs) -> Candidate:  # type: ignore[no-untyped-def]
    return Candidate(
        ref_id=ref_id,
        layer=kwargs.pop("layer", "l2"),
        content=kwargs.pop("content", f"内容 {ref_id}"),
        score=score,
        **kwargs,
    )


class TestTheBindingIsParsed:
    def test_all_six_fields_are_read(self) -> None:
        """**六个字段都读** ✓（§1.7 的问题 ✓）。"""
        policy = PolicyBinding(
            raw={
                "enabled": False,
                "scope": "session",
                "policyLabel": "keep-forever",
                "l3EntryIds": ["l3-1", "l3-2"],
            },
            refs=(
                {"type": "memory", "id": "l2-9"},
                {"type": "l3", "id": "l3-3"},
                {"type": "knowledge", "id": "kb-1"},
            ),
        ).to_policy()
        assert policy.enabled is False
        assert policy.scope is MemoryScope.SESSION
        assert policy.policy_label == "keep-forever"
        assert policy.l3_entry_ids == ("l3-1", "l3-2")
        # ⚠️ **只有 memory / l3 是记忆引用** ✓ —— 知识库不是 ✓。
        assert policy.knowledge_refs == (
            MemoryRef(kind=MemoryRefKind.MEMORY, ref_id="l2-9"),
            MemoryRef(kind=MemoryRefKind.L3, ref_id="l3-3"),
        )
        # ⚠️ **被 pin 的 id 合并去重** ✓（L3 条目 + 引用 ✓）。
        assert set(policy.pinned_ids) == {"l3-1", "l3-2", "l2-9", "l3-3"}

    def test_the_defaults_stay_conservative(self) -> None:
        """**缺省按最保守的来** ✓（与旧路径一致 ✓）。"""
        policy = PolicyBinding().to_policy()
        assert policy.enabled is True
        assert policy.scope is MemoryScope.USER
        assert policy.pinned_ids == ()

    def test_an_unknown_scope_falls_back_to_the_user_scope(self) -> None:
        """**认不出来的作用域 → 用户级** ✓（最窄 ✓）。"""
        policy = PolicyBinding(raw={"scope": "galaxy"}).to_policy()
        assert policy.scope is MemoryScope.USER

    def test_the_workspace_scope_cannot_write(self) -> None:
        """**工作区级写不了** ✓（L3 已定退役 ✓ —— 决策 #1 ✓）。"""
        assert PolicyBinding(raw={"scope": "workspace"}).to_policy().write_supported is False
        assert PolicyBinding(raw={"scope": "user"}).to_policy().write_supported is True


class TestTheScopeTakesEffect:
    @pytest.mark.asyncio
    async def test_the_session_scope_is_pushed_down(self) -> None:
        """**会话作用域下推到存储层** ✓（不是 Python 侧逐行过滤 ✗✗）。"""
        lexical = _Lexical()
        pipeline = RetrievalPipeline(lexical=lexical)
        session_id = uuid4()
        await pipeline.recall(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=uuid4(),
            query="报销",
            session_id=session_id,
        )
        assert lexical.calls[0]["session_id"] == session_id

    @pytest.mark.asyncio
    async def test_the_pinned_entries_bypass_the_threshold(self) -> None:
        """**绑定的条目一定被召回** ✓（低于阈值也要 ✓）。"""
        lexical = _Lexical([_candidate("l1", 0.9)])
        pinned = _Pinned([_candidate("p1", 0.01)])
        pipeline = RetrievalPipeline(lexical=lexical, pinned=pinned)
        outcome = await pipeline.recall(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=uuid4(),
            query="报销",
            extra_l3_entry_ids=("p1",),
        )
        assert "p1" in [hit["ref_id"] for hit in outcome.hits]
        # ⚠️ **绑定的排前面** ✓（管理端指定的东西优先 ✓）。
        assert outcome.hits[0]["ref_id"] == "p1"


class _Store:
    def __init__(self) -> None:
        self.saved: list[dict] = []

    async def find_by_hash(self, **kwargs) -> dict | None:  # type: ignore[no-untyped-def]
        return None

    async def save(self, **kwargs) -> dict:  # type: ignore[no-untyped-def]
        self.saved.append(kwargs)
        return {"id": str(uuid4())}

    async def touch(self, *, item_id: str) -> None: ...


class _Extractor:
    async def extract(self, **kwargs) -> list:  # type: ignore[no-untyped-def]
        from qzdap_agent_runtime.memory.extraction import FactCandidate

        return [
            FactCandidate(
                content="记住：我在上海办公",
                confidence=0.95,
                source="explicit",
                category="fact",
            )
        ]


class _Redactor:
    def redact(self, content: str):  # type: ignore[no-untyped-def]
        from qzdap_agent_runtime.memory.redaction import RedactionResult

        return RedactionResult(blocked=False, kinds=(), reason="")


class TestTheWriteIsGated:
    async def _pipeline(self) -> tuple[WriterPipeline, _Store]:
        store = _Store()
        return (
            WriterPipeline(extractor=_Extractor(), redactor=_Redactor(), store=store),
            store,
        )

    @pytest.mark.asyncio
    async def test_a_disabled_policy_writes_nothing(self) -> None:
        """**关掉记忆 → 一条不写** ✓（可见行为 ✓）。"""
        pipeline, store = await self._pipeline()
        outcome = await pipeline.write_turn(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=uuid4(),
            session_id=uuid4(),
            user_input="记住：我在上海办公",
            policy=MemoryPolicy(enabled=False),
        )
        assert outcome.written == []
        assert outcome.skipped == "policy_disabled"
        assert store.saved == []

    @pytest.mark.asyncio
    async def test_an_unsupported_scope_is_refused_explicitly(self) -> None:
        """**不支持的作用域 → 明确跳过** ✓（不静默降级 ✓）。"""
        pipeline, store = await self._pipeline()
        outcome = await pipeline.write_turn(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=uuid4(),
            session_id=uuid4(),
            user_input="记住：我在上海办公",
            policy=MemoryPolicy(scope=MemoryScope.WORKSPACE),
        )
        assert outcome.written == []
        assert outcome.skipped == "scope_unsupported"
        assert store.saved == []

    @pytest.mark.asyncio
    async def test_the_default_policy_writes(self) -> None:
        """**默认策略照常写** ✓（旧行为不变 ✓）。"""
        pipeline, store = await self._pipeline()
        outcome = await pipeline.write_turn(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=uuid4(),
            session_id=uuid4(),
            user_input="记住：我在上海办公",
        )
        assert outcome.written
        assert outcome.skipped == ""
        assert store.saved
