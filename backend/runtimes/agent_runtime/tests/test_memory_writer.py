"""Memory Stage 3：写入的五步流水线 ✓。

依据：Memory 方案 §4（写入 ✓）、§4.3（闸门 ✓）、§4.4（幂等与去重 ✓）、
§4.5（置信度 ✓）、§4.6（**不能从召回结果反推** ✓）。

验收三条 ✓：**重复内容不产生第二条** ✓ / **手机号类内容被拒绝写入并记审计** ✓ /
**每条记忆可追溯到来源轮次** ✓。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from qzdap_agent_runtime.memory.extraction import RuleFactExtractor
from qzdap_agent_runtime.memory.redaction import RuleRedactor
from qzdap_agent_runtime.memory.writer import (
    WriterPipeline,
    content_hash,
    normalize_content,
)


class _Store:
    """落库口替身 ✓ —— 记住写进去的东西 ✓。"""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.touched: list[str] = []

    async def find_by_hash(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        content_hash: str,
    ) -> dict[str, Any] | None:
        for row in self.rows:
            if row["content_hash"] == content_hash:
                return row
        return None

    async def save(self, **kwargs: Any) -> dict[str, Any]:
        row = {"id": str(uuid4()), **kwargs}
        self.rows.append(row)
        return row

    async def touch(self, *, item_id: str) -> None:
        self.touched.append(item_id)


def _pipeline(store: _Store) -> WriterPipeline:
    return WriterPipeline(
        extractor=RuleFactExtractor(),
        redactor=RuleRedactor(),
        store=store,
    )


class TestExtraction:
    @pytest.mark.asyncio
    async def test_an_explicit_request_is_captured(self) -> None:
        store = _Store()
        outcome = await _pipeline(store).write_turn(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=uuid4(),
            session_id=uuid4(),
            user_input="记住：我的报销额度是五千元",
        )
        assert len(outcome.written) == 1
        assert outcome.written[0]["confidence"] == 0.95
        assert outcome.written[0]["confidence_source"] == "explicit"

    @pytest.mark.asyncio
    async def test_a_statement_is_captured_with_lower_confidence(self) -> None:
        store = _Store()
        outcome = await _pipeline(store).write_turn(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=uuid4(),
            session_id=uuid4(),
            user_input="我的答复偏好是三行以内",
        )
        assert len(outcome.written) == 1
        assert outcome.written[0]["confidence"] < 0.9

    @pytest.mark.asyncio
    async def test_smalltalk_is_not_captured(self) -> None:
        """闲聊**不记** ✓ —— 「宁可少记」✓。"""
        store = _Store()
        outcome = await _pipeline(store).write_turn(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=uuid4(),
            session_id=uuid4(),
            user_input="你好，今天天气不错",
        )
        assert outcome.written == []


class TestRedaction:
    @pytest.mark.asyncio
    async def test_a_phone_number_is_rejected_and_recorded(self) -> None:
        """手机号**拒绝写入** ✓，且**留在审计里** ✓（验收 ✓）。"""
        store = _Store()
        outcome = await _pipeline(store).write_turn(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=uuid4(),
            session_id=uuid4(),
            user_input="记住：我的手机号是13812345678",
        )
        assert outcome.written == []
        assert len(outcome.rejected) == 1
        assert "phone" in outcome.rejected[0]["kinds"]

    @pytest.mark.asyncio
    async def test_a_rejected_item_never_reaches_the_store(self) -> None:
        store = _Store()
        await _pipeline(store).write_turn(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=uuid4(),
            session_id=uuid4(),
            user_input="记住：我的密码是 hunter2",
        )
        assert store.rows == []


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_the_same_content_is_written_once(self) -> None:
        """重复内容**不产生第二条** ✓（验收 ✓）。"""
        store = _Store()
        pipeline = _pipeline(store)
        kwargs = {
            "tenant_id": uuid4(),
            "workspace_id": uuid4(),
            "user_id": uuid4(),
            "session_id": uuid4(),
            "user_input": "记住：我的报销额度是五千元",
        }
        first = await pipeline.write_turn(**kwargs)
        second = await pipeline.write_turn(**kwargs)
        assert len(first.written) == 1
        assert second.written == []
        assert len(second.deduplicated) == 1
        assert len(store.rows) == 1
        # 命中重复 → 只**更新用量** ✓
        assert store.touched == [first.written[0]["id"]]

    def test_the_hash_ignores_formatting(self) -> None:
        """同一内容不同写法 → **同一个 hash** ✓（规范化 ✓ —— §4.4 ✓）。"""
        assert normalize_content("  Ｐｙｔｈｏｎ  3.12  ") == "python 3.12"
        assert content_hash("  Ｐｙｔｈｏｎ  3.12  ") == content_hash("python 3.12")
        assert content_hash("A") != content_hash("B")


class TestProvenance:
    @pytest.mark.asyncio
    async def test_each_memory_carries_its_source_turn(self) -> None:
        """每条记忆**可追溯到来源轮次** ✓（验收 ✓）。"""
        store = _Store()
        turn_id = uuid4()
        outcome = await _pipeline(store).write_turn(
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            user_id=uuid4(),
            session_id=uuid4(),
            turn_id=turn_id,
            user_input="记住：我的工位在 A 座 3 层",
        )
        assert outcome.written[0]["turn_id"] == turn_id
        assert outcome.written[0]["user_id"] is not None
        assert outcome.written[0]["content_hash"]
