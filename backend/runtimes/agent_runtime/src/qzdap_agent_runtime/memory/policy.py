"""agent 的**记忆策略绑定** ✓ —— C6。

依据：Memory 方案 §7（C6 策略绑定 ✓）、§10.1（A3 ``policy.py`` ✓）。

⚠️ **这一层是契约层** —— 纯解析 ✓（无 IO ✓）。

⚠️ **现在的配置语义是「假的」** ✗✗（§10.4 ✓）：``memory_policy.enabled`` /
``autoSummarize`` / ``retentionDays`` / ``scope`` **都没有实现** ✗ —— 这里
先把**契约**定下来 ✓（Stage 4 接线时才有执行者 ✓）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .scope import MemoryScope


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    """一个 agent 的记忆策略绑定 ✓（C6 ✓）。"""

    #: 是否允许写记忆 ✓（false → 不写 ✓）。
    enabled: bool = True
    #: 写入与召回的作用域 ✓（不再只是「标签」✗ —— 它决定**存哪层** ✓）。
    scope: MemoryScope = MemoryScope.USER
    #: 保留策略标签 ✓（对应 ``admin_memory_policies.label`` ✓）。
    policy_label: str = ""
    #: 额外纳入的 L3 条目 ✓（召回时一起带上 ✓）。
    l3_entry_ids: tuple[str, ...] = ()
    #: 自动沉淀 ✓（**目前无实现** ✗ —— 见 §10.4 ✓）。
    auto_summarize: bool = False
    #: 保留天数 ✓（**目前无实现** ✗ —— 见 §10.4 ✓）。
    retention_days: int | None = None


@dataclass(frozen=True, slots=True)
class PolicyBinding:
    """agent 配置里那段 ``memory_policy`` 的**原始形状** ✓（解析前的形态 ✓）。"""

    raw: dict[str, Any] = field(default_factory=dict)

    def to_policy(self) -> MemoryPolicy:
        """解析成 ``MemoryPolicy`` ✓。

        ⚠️ **未知取值按最保守的来** ✓：`enabled` 缺失 → True ✓（默认允许 ✓
        —— 与旧路径一致 ✓）；``scope`` 认不出来 → **用户级** ✓（最窄 ✓）。
        """
        raw = self.raw or {}
        scope_raw = str(raw.get("scope") or "").strip().lower()
        try:
            scope = MemoryScope(scope_raw) if scope_raw else MemoryScope.USER
        except ValueError:
            scope = MemoryScope.USER
        l3_ids = raw.get("l3EntryIds") or raw.get("l3_entry_ids") or []
        return MemoryPolicy(
            enabled=bool(raw.get("enabled", True)),
            scope=scope,
            policy_label=str(raw.get("policyLabel") or raw.get("policy_label") or ""),
            l3_entry_ids=tuple(str(item) for item in l3_ids),
            auto_summarize=bool(raw.get("autoSummarize") or raw.get("auto_summarize")),
            retention_days=raw.get("retentionDays") or raw.get("retention_days"),
        )


__all__ = ["MemoryPolicy", "PolicyBinding"]
