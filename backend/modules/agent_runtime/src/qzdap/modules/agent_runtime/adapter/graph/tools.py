"""Tool gate + execution for the inner ReAct loop."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from qzdap.modules.agent_runtime.application.ports import SandboxPort, SkillPort, ToolPort


def parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"input": raw}
        return parsed if isinstance(parsed, dict) else {"input": parsed}
    return {}


def needs_confirm(name: str, *, tool_meta: dict[str, Any] | None) -> bool:
    if name == "sandbox_exec":
        return True
    meta = tool_meta or {}
    if bool(meta.get("needConfirm")):
        return True
    risk = str(meta.get("risk") or "low").lower()
    return risk not in {"", "low"}


async def execute_tool(
    *,
    name: str,
    arguments: dict[str, Any],
    skill_port: SkillPort | None,
    sandbox_port: SandboxPort | None,
    tool_port: ToolPort | None,
    confirmed: bool = False,
) -> dict[str, Any]:
    call_id = uuid4()
    if name == "sandbox_exec" and sandbox_port is not None:
        return await sandbox_port.exec(
            call_id=call_id,
            language=str(arguments.get("language") or "python"),
            code=str(arguments.get("code") or arguments.get("input") or ""),
            timeout_ms=int(arguments.get("timeout_ms") or 30_000),
        )
    if skill_port is not None:
        result = await skill_port.invoke(
            call_id=call_id,
            skill_name=name,
            arguments=arguments,
            confirmed=confirmed,
        )
        if result.get("error_code") != "SKILL_NOT_FOUND":
            return result
    if tool_port is not None:
        return await tool_port.invoke(call_id=call_id, tool_name=name, arguments=arguments)
    return {
        "ok": False,
        "error_code": "TOOL_NOT_FOUND",
        "error_message": f"tool {name} is not bound",
        "call_id": str(call_id),
    }


def result_text(result: dict[str, Any]) -> str:
    if result.get("ok") is False:
        return f"ERROR {result.get('error_code')}: {result.get('error_message')}"
    output = result.get("output")
    if output is None:
        output = result.get("stdout") or result.get("content") or result
    if isinstance(output, (dict, list)):
        return json.dumps(output, ensure_ascii=False)[:8000]
    return str(output)[:8000]


__all__ = ["execute_tool", "needs_confirm", "parse_arguments", "result_text"]
