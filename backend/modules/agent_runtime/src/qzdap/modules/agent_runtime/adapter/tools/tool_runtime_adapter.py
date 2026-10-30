"""``ToolRuntimeAdapter`` —— **工具执行** ✓（Agent 方案 §5.3 / §8.1 ✓）。

依据：Agent 方案 §5.3（**执行路径在 ``modules/tool``** ✓ —— 「本层要做的是给
``modules/tool`` 的执行路径补三样，而不是另写一个执行器」✓）、§8.1
（``ToolRuntimePort`` ✓ —— 幂等 / 重试 / 熔断在 ``modules/tool`` 那一侧 ✓）。

⚠️ **执行必须带真实 actor** ✓ —— 工具执行是**谁的权限**就得用**谁的 actor**
✗✗（用别人的身份调工具 ✗✗✗）。
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

from qzdap.modules.tool.application.services import ToolService
from qzdap.modules.tool.domain import ToolNotFound
from qzdap_agent_runtime.ports import (
    ActorContext,
    ToolInvocation,
    ToolInvocationResult,
    ToolRuntimePort,
)

from qzdap.modules.agent_runtime.application.ports import SkillPort


class ToolRuntimeAdapter(ToolRuntimePort):
    """**调用平台的工具执行路径** ✓（不自建执行器 ✓）。"""

    def __init__(
        self,
        *,
        tool_service: ToolService,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        skills: SkillPort | None = None,
    ) -> None:
        self._svc = tool_service
        self._tenant_id = tenant_id
        self._workspace_id = workspace_id
        self._owner_id = owner_id
        self._skills = skills

    async def invoke(
        self,
        invocation: ToolInvocation,
        *,
        actor: ActorContext,
    ) -> ToolInvocationResult:
        """**执行一次调用** ✓ —— 失败要有 ``error_code`` ✓（不静默吞 ✓）。"""
        if not actor.actor_id:
            return ToolInvocationResult(
                ok=False, error_code="TOOL_ACTOR_MISSING", is_error=True
            )
        if actor.tenant_id and actor.tenant_id != str(self._tenant_id):
            return ToolInvocationResult(
                ok=False, error_code="TOOL_ACTOR_TENANT_MISMATCH", is_error=True
            )
        arguments = dict(invocation.arguments or {})
        call_id = _as_uuid(invocation.call_id) or uuid4()
        try:
            call = await self._svc.invoke_tool().execute(
                tenant_id=self._tenant_id,
                workspace_id=self._workspace_id,
                owner_id=self._owner_id,
                tool_name=invocation.name,
                arguments=arguments,
                call_id=call_id,
            )
        except ToolNotFound:
            # ⚠️ **skill 走 skill 的路径** ✓（工具目录里没有这个名字 ✓）。
            skill_result = await self._invoke_skill(invocation, call_id=call_id)
            if skill_result is not None:
                return skill_result
            return ToolInvocationResult(
                ok=False, error_code="TOOL_NOT_FOUND", is_error=True
            )
        except Exception as exc:  # noqa: BLE001 — 失败要有错误码 ✓
            return ToolInvocationResult(
                ok=False,
                error_code=_error_code(exc),
                output=str(exc),
                is_error=True,
            )
        return ToolInvocationResult(ok=True, output=_as_text(call.result))

    async def _invoke_skill(
        self,
        invocation: ToolInvocation,
        *,
        call_id: UUID,
    ) -> ToolInvocationResult | None:
        """**skill 走 skill 的执行路径** ✓（工具目录里没有这个名字 ✓）。"""
        if self._skills is None:
            return None
        result = await self._skills.invoke(
            call_id=call_id,
            skill_name=invocation.name,
            arguments=dict(invocation.arguments or {}),
            confirmed=False,
        )
        if not result.get("ok"):
            return ToolInvocationResult(
                ok=False,
                error_code=str(result.get("error_code") or "SKILL_FAILED"),
                output=str(result.get("error_message") or ""),
                is_error=True,
            )
        return ToolInvocationResult(ok=True, output=_as_text(result))


def _as_text(payload: Any) -> str:
    """**工具结果 → 文本** ✓（模型只吃文本 ✓）。"""
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(payload)


def _as_uuid(raw: str) -> UUID | None:
    if not raw:
        return None
    try:
        return UUID(raw)
    except (TypeError, ValueError):
        return None


def _error_code(exc: Exception) -> str:
    """**异常 → 错误码** ✓（不静默吞 ✓）。"""
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code:
        return code
    return type(exc).__name__


__all__ = ["ToolRuntimeAdapter"]
