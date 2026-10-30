"""会话内序列的**契约**（Session 方案 §5.1 / §5.2）。

⚠️ 这里只测**契约本身** —— 原子性靠真库集成测试
（``modules/agent_runtime/tests/integration/test_session_messages.py``）✓。
"""

from __future__ import annotations

from uuid import uuid4

from qzdap_agent_runtime.session.sequence import (
    SessionSequencePort,
    checkpoint_thread_id,
)


def test_thread_is_the_session() -> None:
    """**thread ≡ session**（§5.1）—— checkpoint 按它隔离 ✓。"""
    session_id = uuid4()
    assert checkpoint_thread_id(session_id) == str(session_id)


def test_two_sessions_get_two_different_threads() -> None:
    """不同会话 → 不同 thread → checkpoint 互不干扰 ✓。"""
    assert checkpoint_thread_id(uuid4()) != checkpoint_thread_id(uuid4())


def test_the_sequence_port_declares_both_sequences() -> None:
    """端口必须同时有**轮次序**与**消息序** ✓（少一个就少一段序列）。"""
    assert hasattr(SessionSequencePort, "next_ingress_seq")
    assert hasattr(SessionSequencePort, "next_message_seq")


def test_the_sequence_port_is_runtime_checkable() -> None:
    """实现类要能被 ``isinstance`` 认出来（装配层的自检 ✓）。"""
    assert getattr(SessionSequencePort, "_is_runtime_protocol", False) is True
