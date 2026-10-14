"""Tests for ChannelMessage DTO + helpers (§5.1)。"""

from __future__ import annotations

from qzdap_agent_runtime.channels import (
    ChannelMessage,
    build_session_key,
    build_trace_id,
    payload_hash,
)


# ---------------------------------------------------------------------------
# ChannelMessage 构造 + 必填字段
# ---------------------------------------------------------------------------


def test_channel_message_required_fields() -> None:
    m = ChannelMessage(
        tenant_id="tnt-1",
        workspace_id="ws-1",
        channel_id="feishu-bot",
        channel_type="feishu",
        external_chat_id="oc_abc123",
        external_user_id="u_xyz",
        external_message_id="om_def456",
        text="hello",
    )
    assert m.tenant_id == "tnt-1"
    assert m.channel_type == "feishu"
    assert m.text == "hello"
    assert m.trace_id is None  # 未传则 None


def test_channel_message_is_frozen() -> None:
    """ChannelMessage 必须不可变（避免在渠道派发链路上意外修改）。"""
    m = ChannelMessage(
        tenant_id="t", workspace_id="w", channel_id="c",
        channel_type="web", external_chat_id="chat", external_user_id="u",
        external_message_id="m", text="hi",
    )
    try:
        m.text = "modified"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("ChannelMessage should be frozen")


def test_channel_message_extras_forbidden() -> None:
    """不允许传未声明字段（防注入）。"""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ChannelMessage(
            tenant_id="t", workspace_id="w", channel_id="c",
            channel_type="web", external_chat_id="chat", external_user_id="u",
            external_message_id="m", text="hi",
            rogue_field="x",  # type: ignore[call-arg]
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_build_trace_id_is_deterministic() -> None:
    """同一 channel + event 必须产出同一 trace_id（UUIDv5 决定性）。"""
    a = build_trace_id("feishu-bot", "om_abc")
    b = build_trace_id("feishu-bot", "om_abc")
    assert a == b


def test_build_trace_id_different_inputs() -> None:
    """不同 channel / event 必须产出不同 trace_id。"""
    a = build_trace_id("feishu-bot", "om_abc")
    b = build_trace_id("feishu-bot", "om_def")
    c = build_trace_id("wecom-bot", "om_abc")
    assert a != b
    assert a != c


def test_build_trace_id_is_uuid_format() -> None:
    """trace_id 必须是 UUID 字符串（36 字符含连字符）。"""
    tid = build_trace_id("c", "e")
    assert len(tid) == 36
    assert tid.count("-") == 4


def test_build_session_key_includes_all_dims() -> None:
    """Session key 必须包含租户/工作区/渠道/外部会话/外部用户 5 维（§5.1）。"""
    k = build_session_key("tnt-1", "ws-1", "feishu-bot", "oc_abc", "u_xyz")
    parts = k.split(":")
    assert parts == ["tnt-1", "ws-1", "feishu-bot", "oc_abc", "u_xyz"]


def test_build_session_key_sanitizes_colons() -> None:
    """Session key 中各组件含冒号必须替换为下划线（避免分隔符冲突）。"""
    k = build_session_key("tnt:1", "ws:1", "c", "chat", "u")
    # 原始 5 段：tnt:1 / ws:1 / c / chat / u → tnt_1 / ws_1 / c / chat / u
    parts = k.split(":")
    assert parts == ["tnt_1", "ws_1", "c", "chat", "u"]


def test_payload_hash_is_stable() -> None:
    """payload_hash 必须稳定（sha256 + sort_keys）。"""
    p1 = {"a": 1, "b": 2}
    p2 = {"b": 2, "a": 1}  # 不同 key 顺序
    assert payload_hash(p1) == payload_hash(p2)


def test_payload_hash_different_for_different_input() -> None:
    assert payload_hash({"a": 1}) != payload_hash({"a": 2})


def test_payload_hash_format() -> None:
    """sha256 hex 是 64 字符。"""
    h = payload_hash({"x": 1})
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)