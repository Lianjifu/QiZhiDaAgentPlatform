"""会话 key 派生 —— Router 层的职责之一（Router 方案 §4.1 / §7.1）。

**哈希版**取代旧的**冒号拼接版**（台账 **R4**）。

⚠️ **为什么不能是冒号拼接**（旧实现的两难）：

- 不清洗分隔符 → ``"a:b" + "c"`` 与 ``"a" + "b:c"`` **撞车**（两个不同的
  外部会话映射到同一个会话）；
- 清洗（把冒号换成下划线）→ ``"a:b" → "a_b"``，与真的叫 ``"a_b"`` 的
  **又撞上了** —— 清洗只是把一种歧义换成另一种。

**长度前缀**才是无歧义编码：``{长度}:{内容}`` 逐段拼接，任何输入组合都唯一。

⚠️ **为什么是 6 维**（比旧实现多一维 ``channel_type``）：同一个 ``channel_id``
在不同渠道类型下不是一回事 —— 飞书的群 ID 与钉钉的群 ID 可以撞 ✓。

⚠️ **不可逆**：key 由外部身份（租户 / 群 / 用户）派生 → 它会出现在日志、
审计与数据库里。哈希版**不泄漏原文**（§12.2 的观测约束：「会话 key 与用户
身份在日志 / span 中一律哈希或脱敏」✓）。
"""

from __future__ import annotations

import hashlib

from qzdap_observability.metrics import record_router_session_key_hash

#: 参与派生的维度（顺序固定 —— 变了就是另一个 key）。
SESSION_KEY_DIMS: tuple[str, ...] = (
    "tenant_id",
    "workspace_id",
    "channel_type",
    "channel_id",
    "external_chat_id",
    "external_user_id",
)


def derive_session_key(
    *,
    tenant_id: str,
    workspace_id: str,
    channel_type: str,
    channel_id: str,
    external_chat_id: str,
    external_user_id: str,
) -> str:
    """由外部身份派生**稳定**的会话 key（跨 worker 可复算 ✓）。

    返回 sha256 十六进制串（定长 64 ✓ —— `agent_sessions.channel_session_key`
    是 String(512)，哈希定长且不含分隔符歧义 ✓）。

    ⚠️ **同名不同参 = 不同 key** —— `channel_type` 参与派生 ✓（旧实现漏了它 ✗）。
    """
    parts = (
        tenant_id,
        workspace_id,
        channel_type,
        channel_id,
        external_chat_id,
        external_user_id,
    )
    # 长度前缀 —— 逐段自描述，拼接后**无歧义**。
    canonical = "".join(f"{len(part)}:{part}" for part in parts)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    # ⚠️ **只计数，不记录 key** ✓（Router 方案 §12.2 ✓ —— key 会进日志 /
    # 审计 / 数据库 ✓ —— 原文一律不出现 ✓）。
    record_router_session_key_hash()
    return digest


__all__ = ["SESSION_KEY_DIMS", "derive_session_key"]
