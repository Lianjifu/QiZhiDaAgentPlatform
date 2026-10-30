"""agent 的**记忆策略绑定** ✓ —— C6。

依据：Memory 方案 §7（C6 策略绑定 ✓）、§10.1（A3 ``policy.py`` ✓）。

⚠️ **这一层是契约层** —— 纯解析 ✓（无 IO ✓）。

⚠️ **运行时必须真的消费这六个字段** ✓（§1.7 的问题 ✓）——
``enabled`` / ``scope`` / ``policyLabel`` / ``l3EntryIds`` /
``knowledge_refs`` / ``retentionDays`` —— 否则「管理端能看、运行时读不到」✗✗。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from .scope import MemoryScope


#: 保留策略的**契约视图** ✓（模块侧实体不外泄 ✓ —— 契约层不引模块 ✓）。
@dataclass(frozen=True, slots=True)
class RetentionPolicyView:
    """一条保留策略的**只读视图** ✓（TTL / 上限 / 淘汰方式 ✓）。"""

    label: str
    layer: str = "l2"
    ttl_minutes: int = 0
    max_items: int = 0
    storage_mb: int = 0
    eviction: str = "lru"

    @property
    def has_limits(self) -> bool:
        """这条策略**有没有真正的约束** ✓（全是 0 = 没约束 ✓）。"""
        return bool(self.ttl_minutes or self.max_items or self.storage_mb)


class MemoryRefKind(StrEnum):
    """**被显式引用**的记忆条目的种类 ✓（§7.1 的 ``knowledge_refs`` ✓）。"""

    #: L2 个人记忆 ✓。
    MEMORY = "memory"
    #: L3 团队知识 ✓。
    L3 = "l3"


@dataclass(frozen=True, slots=True)
class MemoryRef:
    """一条**显式引用** ✓（agent 绑定的那条记忆 / 知识 ✓）。

    ⚠️ **显式引用 = 一定被召回** ✓（§7.1 ✓）—— 它绕过阈值 ✓
    （阈值是给「搜出来的」用的 ✓ —— 绑定的不是搜出来的 ✗✗）。
    """

    kind: MemoryRefKind
    ref_id: str

    @property
    def layer(self) -> str:
        return "l3" if self.kind is MemoryRefKind.L3 else "l2"


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    """一个 agent 的记忆策略绑定 ✓（C6 ✓）。"""

    #: 是否允许写记忆 ✓（false → 不写 ✓）。
    enabled: bool = True
    #: 写入与召回的作用域 ✓（不再只是「标签」✗ —— 它决定**存哪层** ✓）。
    scope: MemoryScope = MemoryScope.USER
    #: 保留策略标签 ✓（对应 ``admin_memory_policies.label`` ✓）。
    policy_label: str = ""
    #: 绑定的保留策略 ✓（**运行时解析出来的** ✓ —— 模块侧查 ✓）。
    retention: RetentionPolicyView | None = None
    #: 额外纳入的 L3 条目 ✓（召回时一起带上 ✓）。
    l3_entry_ids: tuple[str, ...] = ()
    #: agent 显式引用的记忆 / 知识 ✓（召回时一起带上 ✓ —— §7.1 ✓）。
    knowledge_refs: tuple[MemoryRef, ...] = ()
    #: 自动沉淀 ✓（**目前无实现** ✗ —— 见 §10.4 ✓）。
    auto_summarize: bool = False
    #: 保留天数 ✓（**目前无实现** ✗ —— 见 §10.4 ✓）。
    retention_days: int | None = None

    @property
    def write_supported(self) -> bool:
        """**这一层能不能写** ✓。

        ⚠️ **工作区级（团队知识）写不了** ✓ —— L3 已定退役 ✓（决策 #1 ✓），
        数据要迁到 ``modules/knowledge`` ✓（M-47 ✓ —— **未接管** ✗）。
        静默降级成「写个人层」是**改语义** ✗✗ → **明确不支持** ✓。
        """
        return self.scope is not MemoryScope.WORKSPACE

    @property
    def pinned_ids(self) -> tuple[str, ...]:
        """**召回时必须额外纳入的条目 id** ✓（``l3EntryIds`` + 引用 ✓）。

        ⚠️ **引用指向 L2 时也要带上** ✓（``knowledge_refs.type == "memory"`` ✓
        —— 那是「引用一条个人记忆」✓ —— 漏了它 = 绑定失效 ✗✗）。
        """
        ids = list(self.l3_entry_ids)
        ids.extend(ref.ref_id for ref in self.knowledge_refs)
        return tuple(dict.fromkeys(ids))

    @property
    def pinned_layer(self) -> str:
        """**被 pin 的条目在哪一层** ✓。

        ⚠️ **同一层** ✓ —— L3 引用与 L2 引用混在一起时**按层分开取** ✓
        （取的时候按 id 逐个判层 ✓ —— 这里只给「默认层」✓）。
        """
        return "l3" if self.l3_entry_ids else "l2"


@dataclass(frozen=True, slots=True)
class PolicyBinding:
    """agent 配置里那段 ``memory_policy`` 的**原始形状** ✓（解析前的形态 ✓）。"""

    raw: dict[str, Any] = field(default_factory=dict)
    #: agent 的 ``knowledge_refs`` ✓（**另一个字段** ✓ —— §1.7 ✓）。
    refs: tuple[Mapping[str, Any], ...] = ()

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
            knowledge_refs=_parse_refs(self.refs),
            auto_summarize=bool(raw.get("autoSummarize") or raw.get("auto_summarize")),
            retention_days=raw.get("retentionDays") or raw.get("retention_days"),
        )


def _parse_refs(refs: Sequence[Mapping[str, Any]]) -> tuple[MemoryRef, ...]:
    """``admin_agents.knowledge_refs`` → **契约层的引用** ✓。

    ⚠️ **只认 ``type ∈ {memory, l3}``** ✓（§1.7 ✓）—— 其它类型（知识库
    之类的）**不是记忆引用** ✓ → 忽略 ✓（否则会把知识库 id 当成记忆 id ✗✗）。
    """
    parsed: list[MemoryRef] = []
    for item in refs:
        kind_raw = str(item.get("type") or "").strip().lower()
        ref_id = str(item.get("id") or item.get("ref_id") or "").strip()
        if not ref_id:
            continue
        try:
            kind = MemoryRefKind(kind_raw)
        except ValueError:
            continue
        parsed.append(MemoryRef(kind=kind, ref_id=ref_id))
    return tuple(parsed)


@runtime_checkable
class RetentionPolicyPort(Protocol):
    """**保留策略的只读端口** ✓（实现在模块侧 ✓ —— 契约层不碰数据库 ✓）。

    ⚠️ **只读** ✓ —— 策略的**写**归平面 B ✓（§2.2 规则 6 ✓）✓。
    """

    async def get_policy(
        self, *, tenant_id: UUID, workspace_id: UUID, label: str
    ) -> RetentionPolicyView | None:
        """按 label 取保留策略 ✓（查不到返回 ``None`` ✓ —— 不猜 ✓）。"""
        ...


__all__ = [
    "MemoryPolicy",
    "MemoryRef",
    "MemoryRefKind",
    "PolicyBinding",
    "RetentionPolicyPort",
    "RetentionPolicyView",
]
