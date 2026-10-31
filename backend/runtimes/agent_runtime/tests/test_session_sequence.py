"""会话内序列的**契约**（Session 方案 §5.1 / §5.2）。

⚠️ 这里只测**契约本身** —— 原子性靠真库集成测试
（``modules/agent_runtime/tests/integration/test_session_messages.py``）✓。
"""

from __future__ import annotations

from qzdap_agent_runtime.session.sequence import SessionSequencePort


def test_the_sequence_port_declares_both_sequences() -> None:
    """端口必须同时有**轮次序**与**消息序** ✓（少一个就少一段序列）。"""
    assert hasattr(SessionSequencePort, "next_ingress_seq")
    assert hasattr(SessionSequencePort, "next_message_seq")


def test_the_sequence_port_is_runtime_checkable() -> None:
    """实现类要能被 ``isinstance`` 认出来（装配层的自检 ✓）。"""
    assert getattr(SessionSequencePort, "_is_runtime_protocol", False) is True
