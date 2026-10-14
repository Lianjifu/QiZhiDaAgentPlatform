"""PolicyGuard 进程内实现 (§5.7)。

Stage 4 PR C 范围：
- InMemoryPolicyGuard: PolicyGuard Protocol 进程内实现
  - 风险等级 + actor.roles + 工具白名单 + 预算 (简化版)
  - 返回 ApprovalDecision: allow / approve_required / deny
- 默认策略: low = allow, medium = allow, high = approve_required
- 角色限制: actor.roles 必须含 'admin' 才能 allow high
"""

from __future__ import annotations

from typing import Any

from ..ports import (
    ActorContext,
    ApprovalDecision,
    PolicyGuard,
    ToolMeta,
)


class InMemoryPolicyGuard:
    """§5.7 PolicyGuard 进程内实现（单测 + 本地 dev）。

    默认策略：
    - low 风险: allow（无审批）
    - medium 风险: allow（无审批）— 简化生产可改为 approve_required
    - high 风险 + 副作用: approve_required
    - high 风险 + actor.roles 含 admin: allow
    - low 风险 + side_effect + actor 无 admin/developer: approve_required
    """

    async def decide(
        self,
        *,
        actor: ActorContext,
        tool_call_id: str,
        tool_meta: ToolMeta,
        arguments: dict[str, Any],
    ) -> tuple[ApprovalDecision, str | None]:
        # 高风险副作用工具: admin allow, 其他 approve_required
        if tool_meta.risk == "high":
            if any(r in actor.roles for r in ("admin", "developer")):
                return ("allow", None)
            return ("approve_required", f"apr-{tool_call_id}")

        # 中风险: 默认 allow（生产可改 approve_required）
        if tool_meta.risk == "medium":
            if tool_meta.requires_approval:
                return ("approve_required", f"apr-{tool_call_id}")
            return ("allow", None)

        # 低风险: 默认 allow
        if tool_meta.requires_approval:
            return ("approve_required", f"apr-{tool_call_id}")
        return ("allow", None)


__all__ = ["InMemoryPolicyGuard"]