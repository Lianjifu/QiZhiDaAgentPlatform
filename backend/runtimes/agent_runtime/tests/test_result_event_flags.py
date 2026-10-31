"""Gateway：**结果事件的降级标记** ✓（C-22 ✓ —— Gateway 方案 §9.0 ✓）。

⚠️ **内部协议与对外 chunk 用同一个词汇** ✓（``recall_degraded`` /
``compaction_degraded`` / ``interactive_degraded`` ✓）—— 两套词汇 = 前端要写
两套判断 ✗✗。
"""

from __future__ import annotations

from typing import Any

from qzdap_agent_runtime.outbox import to_result_event
from qzdap_agent_runtime.result import DEGRADATION_FLAGS, DegradationFlag


class _OutboxEvent:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.event_type = "message"
        self.payload = payload
        self.turn_id = "turn-1"
        self.seq = 3


def test_the_flag_vocabulary_is_exactly_three() -> None:
    """**词汇只有三个** ✓（Gateway 方案 §9.0 ✓ —— 前端按固定词汇判断 ✓）。"""
    assert set(DegradationFlag.__args__) == {
        "recall_degraded",
        "compaction_degraded",
        "interactive_degraded",
    }


def test_the_outbox_passes_the_flags_through() -> None:
    """**出站队列里的标记透传** ✓（能投递 ✓）。"""
    event = to_result_event(
        _OutboxEvent({"content": "你好", "flags": ["recall_degraded", "compaction_degraded"]})
    )
    assert event.flags == ["recall_degraded", "compaction_degraded"]


def test_an_unknown_flag_is_dropped() -> None:
    """**认不出来的标记丢掉** ✓（前端不认 ✗✗ —— 塞进去只会误导 ✓）。"""
    event = to_result_event(
        _OutboxEvent({"content": "你好", "flags": ["recall_degraded", "bogus"]})
    )
    assert event.flags == ["recall_degraded"]


def test_the_flag_vocabulary_is_shared_with_the_factory() -> None:
    """**标记的词汇只有一份** ✓（契约层一份 ✓ —— 出站只放行这三个 ✓）。"""
    assert set(DegradationFlag.__args__) == DEGRADATION_FLAGS
