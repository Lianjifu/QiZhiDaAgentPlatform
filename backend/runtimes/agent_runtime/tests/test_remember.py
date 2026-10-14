"""Tests for §8 Stage 3 PR C — remember node + L2 dedup/promotion."""

from __future__ import annotations

import pytest

from qzdap_agent_runtime.graph import nodes
from qzdap_agent_runtime.memory import InMemoryLayeredMemory


@pytest.fixture(autouse=True)
def _reset_deps():
    yield
    nodes.reset_default_dependencies()


# ---------------------------------------------------------------------------
# remember 节点：L2 提取 + 去重 + 提升
# ---------------------------------------------------------------------------


class TestRememberNode:
    def test_passthrough_when_no_memory(self) -> None:
        out = nodes.remember({})  # type: ignore[arg-type]
        assert out == {}

    def test_skips_low_confidence_hits(self) -> None:
        """§11 风险: 低置信度只作为候选, 不进入长期事实。"""
        mem = InMemoryLayeredMemory()
        nodes.set_default_memory(mem)
        out = nodes.remember({
            "tenant_id": "t-1",
            "workspace_id": "w-1",
            "turn_id": "turn-1",
            "memory_hits": [
                {
                    "layer": "l2",
                    "content": "低置信度事实",
                    "source_id": "f-low",
                    "metadata": {"confidence": 0.3},  # < 0.7 门槛
                },
            ],
        })
        # 不应写入
        hits = mem.recall_memory(
            query="低置信度",
            tenant_id="t-1",
            workspace_id="w-1",
            user_id="*",
            session_id="s-1",
            policy={"top_k": 5, "threshold": 0.01},
        )
        assert hits == []

    def test_writes_high_confidence_hits(self) -> None:
        mem = InMemoryLayeredMemory()
        nodes.set_default_memory(mem)
        out = nodes.remember({
            "tenant_id": "t-1",
            "workspace_id": "w-1",
            "turn_id": "turn-1",
            "memory_hits": [
                {
                    "layer": "l2",
                    "content": "用户偏好使用 Rust 编程",
                    "source_id": "f-rust",
                    "metadata": {"confidence": 0.9},
                },
            ],
        })
        hits = mem.recall_memory(
            query="Rust",
            tenant_id="t-1",
            workspace_id="w-1",
            user_id="*",
            session_id="s-1",
            policy={"top_k": 5, "threshold": 0.01},
        )
        assert len(hits) == 1
        assert "Rust" in hits[0].content

    def test_skips_l1_hits_only_writes_l2(self) -> None:
        """L1 hits 必须跳过（只入 L2）。"""
        mem = InMemoryLayeredMemory()
        nodes.set_default_memory(mem)
        out = nodes.remember({
            "tenant_id": "t-1",
            "workspace_id": "w-1",
            "turn_id": "turn-1",
            "memory_hits": [
                {
                    "layer": "l1",  # 不是 l2
                    "content": "session 内消息",
                    "source_id": "msg-1",
                    "metadata": {"confidence": 1.0},
                },
            ],
        })
        hits = mem.recall_memory(
            query="消息",
            tenant_id="t-1",
            workspace_id="w-1",
            user_id="*",
            session_id="s-1",
            policy={"top_k": 5, "threshold": 0.01},
        )
        # L1 不通过 write_l2 路径, L2 应为空
        assert hits == []

    def test_dedup_by_content_hash(self) -> None:
        """§5.4 同 content_hash 写入幂等。"""
        mem = InMemoryLayeredMemory()
        nodes.set_default_memory(mem)
        base = {
            "tenant_id": "t-1",
            "workspace_id": "w-1",
            "turn_id": "turn-1",
            "memory_hits": [
                {
                    "layer": "l2",
                    "content": "用户偏好 Rust",
                    "source_id": "f-1",
                    "metadata": {"confidence": 0.9},
                },
            ],
        }
        # 两次写入
        nodes.remember(base)
        nodes.remember(base)
        # 召回时只有 1 条（content_hash 相同）
        hits = mem.recall_memory(
            query="Rust",
            tenant_id="t-1",
            workspace_id="w-1",
            user_id="*",
            session_id="s-1",
            policy={"top_k": 5, "threshold": 0.01},
        )
        assert len(hits) == 1

    def test_empty_memory_hits_noop(self) -> None:
        mem = InMemoryLayeredMemory()
        nodes.set_default_memory(mem)
        out = nodes.remember({
            "tenant_id": "t-1",
            "workspace_id": "w-1",
            "memory_hits": [],
        })
        assert out == {}

    def test_failure_does_not_raise(self) -> None:
        """§5.4 记忆写失败不回滚答案。"""
        class _FailMemory:
            def write_l2(self, fact):
                raise RuntimeError("vector db down")

            # 鸭子类型, recall 节点会调用
            def recall_memory(self, **kwargs):
                return []

            def recall_knowledge(self, **kwargs):
                return []

        nodes.set_default_memory(_FailMemory())  # type: ignore[arg-type]
        # 不应抛异常
        out = nodes.remember({
            "tenant_id": "t-1",
            "workspace_id": "w-1",
            "memory_hits": [
                {
                    "layer": "l2",
                    "content": "test",
                    "source_id": "f-1",
                    "metadata": {"confidence": 0.9},
                },
            ],
        })
        assert out == {}