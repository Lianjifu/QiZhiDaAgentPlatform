"""会话 key 派生的单测（Router 方案 §4.1）。

⚠️ 这里测的是**旧实现治不了的病** —— 冒号拼接的两个老问题：

1. **分隔符注入** —— ``("a:b", "c")`` 与 ``("a", "b:c")`` 撞车；
2. **清洗歧义** —— 把冒号换成下划线，``"a:b"`` 与真的 ``"a_b"`` 又撞上了。

哈希版用**长度前缀**编码，两者都不可能撞 ✓。
"""

from __future__ import annotations

from qzdap_agent_runtime.router.session_key import (
    SESSION_KEY_DIMS,
    derive_session_key,
)

BASE = {
    "tenant_id": "tnt-1",
    "workspace_id": "ws-1",
    "channel_type": "feishu",
    "channel_id": "bot-1",
    "external_chat_id": "oc_abc",
    "external_user_id": "u_xyz",
}


def _key(**overrides: str) -> str:
    return derive_session_key(**{**BASE, **overrides})


def test_the_key_is_stable() -> None:
    """跨 worker 可复算 —— 同一份外部身份永远得到同一个 key ✓。"""
    assert _key() == _key()


def test_the_key_is_a_fixed_length_sha256_hex() -> None:
    """定长 64 —— `agent_sessions.channel_session_key` 是 String(512) ✓。"""
    key = _key()
    assert len(key) == 64
    assert all(char in "0123456789abcdef" for char in key)


def test_every_dimension_changes_the_key() -> None:
    """6 维**每一维**都参与派生 —— 少一维就少一层隔离 ✗。"""
    for dim in SESSION_KEY_DIMS:
        assert _key(**{dim: "别的值"}) != _key(), f"{dim} 没参与派生"


def test_the_channel_type_separates_two_channels_with_the_same_id() -> None:
    """同一个 channel_id 在不同渠道类型下不是一回事（飞书群 ID vs 钉钉群 ID）。"""
    assert _key(channel_type="feishu") != _key(channel_type="dingtalk")


def test_a_colon_in_a_component_does_not_collide() -> None:
    """**分隔符注入**：旧的冒号拼接会让这两组撞车。"""
    assert _key(external_chat_id="a:b", external_user_id="c") != _key(
        external_chat_id="a", external_user_id="b:c"
    )


def test_sanitising_would_have_been_ambiguous_too() -> None:
    """旧的「冒号换下划线」同样撞车 —— 清洗只是换了一种歧义 ✓。"""
    assert _key(external_chat_id="a:b") != _key(external_chat_id="a_b")


def test_the_key_does_not_leak_the_input() -> None:
    """key 会进日志 / 审计 / 数据库 → **不可逆**（§12.2 的观测约束 ✓）。"""
    key = _key()
    for secret in BASE.values():
        assert secret not in key
