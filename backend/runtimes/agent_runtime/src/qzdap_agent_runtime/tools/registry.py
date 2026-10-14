"""Tool registry + LangChain @tool adapter (§13.3 / §5.8)。

Stage 4 PR A 范围：

- `InMemoryToolRegistry`: ToolRegistry Protocol 进程内实现
- `LangChainToolAdapter`: 把 `@tool(args_schema=...)` 装饰的函数转成
  ToolMeta + BaseTool 元组，注入 registry
- `Risk` + ToolMeta 字段映射：risk / requires_approval / timeout_ms /
  max_retries / backoff_ms / idempotent / side_effect
- Pydantic BaseModel → JSON Schema (`schemas_for(actor)`)

注意：本 PR 仅实现 tool 元数据注册与 schema 暴露；执行逻辑（重试/超时/
幂等/熔断）由 ToolExecutor 在 PR B 实现。
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel

from ..ports import ActorContext, Risk, ToolMeta, ToolRegistry


def _risk_from_string(risk: str) -> Risk:
    """normalize risk 字符串 → 字面量联合。"""
    if risk not in ("low", "medium", "high"):
        return "medium"
    return risk  # type: ignore[return-value]


def _pydantic_to_json_schema(model: type[BaseModel] | None) -> dict[str, Any]:
    """Pydantic v2 BaseModel → JSON Schema dict。"""
    if model is None:
        return {"type": "object", "properties": {}}
    try:
        return model.model_json_schema()
    except Exception:
        return {"type": "object", "properties": {}}


# ---------------------------------------------------------------------------
# InMemoryToolRegistry
# ---------------------------------------------------------------------------


class InMemoryToolRegistry:
    """§13.3 ToolRegistry 进程内实现。"""

    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolMeta, BaseTool]] = {}

    def register(self, meta: ToolMeta, tool: Any) -> None:
        if not isinstance(meta, ToolMeta):
            raise TypeError(f"meta must be ToolMeta, got {type(meta).__name__}")
        if tool is None:
            raise ValueError(f"tool for {meta.name!r} is None")
        self._tools[meta.name] = (meta, tool)

    def get(self, name: str) -> tuple[ToolMeta, BaseTool]:
        if name not in self._tools:
            raise KeyError(f"tool {name!r} not registered")
        return self._tools[name]

    def schemas_for(self, actor: ActorContext) -> list[dict[str, Any]]:
        """返回所有 tool 的 JSON Schema 列表（用于喂给 LLM）。

        §5.7 风险过滤：低风险工具对所有 actor 可见；中/高风险需要 actor.roles
        包含对应策略（简化实现：role 包含 'admin' 或 'developer' 才看得到
        medium/high 工具）。
        """
        schemas: list[dict[str, Any]] = []
        for meta, tool in self._tools.values():
            if meta.risk in ("medium", "high"):
                if not any(r in actor.roles for r in ("admin", "developer")):
                    continue
            schemas.append({
                "name": meta.name,
                "description": meta.description,
                "args_schema": _pydantic_to_json_schema(meta.args_schema),
                "risk": meta.risk,
                "requires_approval": meta.requires_approval,
            })
        return schemas

    def list_by_risk(self, risk: Risk) -> list[str]:
        return [n for n, (m, _) in self._tools.items() if m.risk == risk]

    def all_tools(self) -> dict[str, tuple[ToolMeta, BaseTool]]:
        return dict(self._tools)


# ---------------------------------------------------------------------------
# LangChain @tool 适配
# ---------------------------------------------------------------------------


def from_langchain_tool(
    lc_tool: BaseTool,
    *,
    risk: str | Risk = "low",
    requires_approval: bool = False,
    timeout_ms: int = 5000,
    max_retries: int = 3,
    backoff_ms: int = 500,
    idempotent: bool = False,
    side_effect: bool = False,
    policy_id: str | None = None,
    max_cost_usd: float | None = None,
) -> ToolMeta:
    """§5.8 / §13.3 从 LangChain BaseTool 构造 ToolMeta。

    Args:
        lc_tool: `from langchain_core.tools import tool` 装饰得到的对象
        risk: low / medium / high
        requires_approval: 写入/外发/删除/代码执行必须 True
        timeout_ms: 默认 5000
        max_retries: 默认 3
        backoff_ms: 默认 500
        idempotent: 工具可安全重试
        side_effect: 工具会改变外部状态
        policy_id: 关联策略 ID（§5.7）
        max_cost_usd: 单次调用成本上限
    """
    if not hasattr(lc_tool, "name") or not lc_tool.name:
        raise ValueError("LangChain tool must have non-empty name")
    return ToolMeta(
        name=lc_tool.name,
        description=lc_tool.description or "",
        args_schema=getattr(lc_tool, "args_schema", None) or type(None),
        risk=_risk_from_string(risk),  # type: ignore[arg-type]
        requires_approval=bool(requires_approval),
        timeout_ms=int(timeout_ms),
        max_retries=int(max_retries),
        backoff_ms=int(backoff_ms),
        idempotent=bool(idempotent),
        side_effect=bool(side_effect),
        policy_id=policy_id,
        max_cost_usd=max_cost_usd,
    )


__all__ = [
    "InMemoryToolRegistry",
    "from_langchain_tool",
]