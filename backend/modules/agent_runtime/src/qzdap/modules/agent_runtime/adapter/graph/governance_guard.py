"""**治理适配器** ✓ —— 把治理域的策略判定接进 agent 循环 ✓。

⚠️ **为什么需要它** ✓ —— 两边的形状不一样 ✓：

| | runtime 的 ``PolicyGuard`` 协议 | governance 的 ``PolicyGuard`` |
|---|---|---|
| 入口 | ``decide(actor, tool_call_id, tool_meta, arguments)`` | ``check(actor, action, resource)`` |
| 返回 | ``(decision, approval_id)`` ✓ —— **三态** ✓ | **抛异常** ✓（DENY / REQUIRE_APPROVAL）✓ |
| 语义 | 循环需要**知道**结果才能继续 ✓ | use case 需要**被拦住** ✓ |

⚠️ **本模块只做翻译** ✓ —— 判定逻辑**不在这里** ✓（在 governance 的
``PolicyEvaluator`` ✓ —— 那里有 30s TTL 的规则缓存 ✓）。

⚠️ **异常 → 决策** ✓ —— governance 抛的两种异常在这里**翻译成决策值** ✓：

- ``ActionDeniedError`` → ``("deny", None)`` ✓
- ``ApprovalRequiredError`` → ``("approve_required", approval_id)`` ✓
- 其他异常 → **放行** ✓（⚠️ 治理服务本身故障**不能挡住对话** ✓
  —— 与「计价失败返回 0」同口径 ✓ —— 记账与治理都不能打断会话 ✓）
"""

from __future__ import annotations

import logging
from typing import Any

from qzdap_kernel.errors import ActionDeniedError, ApprovalRequiredError
from qzdap_vault.actor import ActorContext as VaultActorContext

_log = logging.getLogger(__name__)


class GovernancePolicyGuard:
    """**治理域的策略判定 → runtime 的 ``PolicyGuard`` 协议** ✓。

    ⚠️ **请求作用域** ✓ —— 装配时带上 actor ✓（actor 是**这一轮的人** ✓
    —— 治理按人判 ✓ —— 不能用服务账号判 ✓）。
    """

    def __init__(
        self,
        *,
        guard: Any,
        actor: VaultActorContext,
    ) -> None:
        self._guard = guard
        self._actor = actor

    async def decide(
        self,
        *,
        actor: Any,
        tool_call_id: str,
        tool_meta: Any,
        arguments: dict[str, Any],
    ) -> tuple[str, str | None]:
        """**这个工具要不要审批** ✓（三态 ✓）。

        ⚠️ **actor 用装配时那个** ✓ —— 治理按**真实用户**判 ✓
        （循环传的 actor 是同一个人 ✓ —— 但这里用装配时的 ✓ ——
        那个是**从 JWT 来的** ✓ 更可信 ✓）。

        ⚠️ **「这一轮能不能挂审批」不在这判** ✓ —— 那是**轮次属性** ✓
        （IM 渠道不能挂 ✓）—— 由循环按 ``allow_approval`` 决定 ✓
        （它拿到 ``approve_required`` 且不能挂时会**转成 deny** ✓）。
        """
        _ = (actor, tool_call_id)
        name = str(getattr(tool_meta, "name", "") or "")
        try:
            await self._guard.check(
                actor=self._actor,
                action=f"tool:execute:{name}",
                resource={"tool": name, "arguments": dict(arguments or {})},
            )
        except ApprovalRequiredError as exc:
            return ("approve_required", str(exc.approval_id or "") or None)
        except ActionDeniedError:
            return ("deny", None)
        except Exception as exc:  # defensive
            # ⚠️ **治理服务故障 → 放行** ✓ —— 不能因为治理挂了就把对话也挂
            # 掉 ✓（记日志 ✓ —— 事后能查 ✓）。
            _log.warning("policy guard failed, allowing tool %s: %s", name, exc)
            return ("allow", None)
        return ("allow", None)


__all__ = ["GovernancePolicyGuard"]
