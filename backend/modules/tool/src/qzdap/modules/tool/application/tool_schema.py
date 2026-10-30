"""工具的**参数契约** → JSON Schema ✓（模型看到的那个形状 ✓）。

单一真相 ✓：

| 工具来源 | 参数契约来自 |
|---|---|
| **内置工具** | ``tool_catalog.BUILTIN_TOOL_SPECS`` ✓（种子里 ``spec`` 是空的 ✓） |
| **admin 注册的工具** | ``tools.spec`` ✓（OpenAPI 文档 ✓ / MCP 描述 ✓ / 自定义参数声明 ✓） |

⚠️ **旧路径给 admin 工具的是空 schema** ✗✗ —— ``{"type":"object","properties":{}}``
✗（模型只能瞎猜参数 ✗✗）。这里把**真实 schema** 从 spec 里长出来 ✓。

⚠️ **本模块只产出 schema** ✓ —— 不做治理 ✓（风险 / 审批是别的事 ✓）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from qzdap.modules.tool.domain import Tool, ToolProtocol

#: **空 schema** ✓ —— 只有真的什么都没有时才给这个 ✓（不是默认兜底 ✓）。
EMPTY_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}

_HTTP_METHODS = frozenset({"get", "post", "put", "delete", "patch"})

#: spec 里可能出现的**参数 schema 键** ✓（不同来源叫法不同 ✓）。
_SCHEMA_KEYS = ("parameters", "input_schema", "inputSchema", "args_schema", "schema")


def schema_from_spec(spec: Mapping[str, Any], *, protocol: ToolProtocol) -> dict[str, Any]:
    """**spec → 参数 schema** ✓。

    ⚠️ **按协议分派** ✓ —— OpenAPI 的 spec 是一份文档 ✓（要抽出操作 ✓），
    MCP / 自定义工具的 spec 里直接就带着参数声明 ✓。
    """
    if protocol is ToolProtocol.OPENAPI:
        return _openapi_schema(spec)
    declared = _declared_schema(spec)
    if declared is not None:
        return declared
    return dict(EMPTY_SCHEMA)


def tool_parameters(tool: Tool) -> dict[str, Any]:
    """**工具实体 → 参数 schema** ✓（模型看到的 ✓）。"""
    return schema_from_spec(tool.spec or {}, protocol=tool.protocol)


def tool_description(tool: Tool) -> str:
    """**工具实体 → 描述** ✓（spec 里的优先 ✓）。"""
    spec = tool.spec or {}
    description = spec.get("description")
    if isinstance(description, str) and description.strip():
        return description.strip()
    return tool.description or tool.name


def tool_risk(tool: Tool) -> str:
    """**工具实体 → 风险等级** ✓（spec 里没写就是 medium ✓）。"""
    risk = (tool.spec or {}).get("risk")
    if isinstance(risk, str) and risk in {"low", "medium", "high"}:
        return risk
    return "medium"


def tool_needs_confirm(tool: Tool) -> bool:
    """**工具实体 → 是否需要人工确认** ✓（高风险默认要确认 ✓）。"""
    spec = tool.spec or {}
    for key in ("needConfirm", "need_confirm", "requires_approval"):
        if key in spec:
            return bool(spec[key])
    return tool_risk(tool) == "high"


def _declared_schema(spec: Mapping[str, Any]) -> dict[str, Any] | None:
    """**spec 里直接声明的参数 schema** ✓（找不到就是 ``None`` ✓）。"""
    for key in _SCHEMA_KEYS:
        candidate = spec.get(key)
        if isinstance(candidate, Mapping) and candidate:
            return dict(candidate)
    return None


def _openapi_schema(spec: Mapping[str, Any]) -> dict[str, Any]:
    """**OpenAPI 文档 → 参数 schema** ✓。

    ⚠️ **形状与 ``openapi_runtime`` 的参数路由一致** ✓ —— 那是执行时的真相 ✓：
    ``arguments["path"]`` / ``arguments["query"]`` / ``arguments["body"]`` ✓ +
    ``arguments["__operation_id"]`` ✓（选哪个操作 ✓）。

    ⚠️ **一个注册行 = 一份文档（多个操作）** ✓ —— 所以 operation 是**枚举** ✓
    （不是选一个 ✓ —— 那是运行时的事 ✓）。
    """
    paths = spec.get("paths")
    if not isinstance(paths, Mapping):
        return dict(EMPTY_SCHEMA)

    operation_ids: list[str] = []
    path_params: dict[str, Any] = {}
    query_params: dict[str, Any] = {}
    body_properties: dict[str, Any] = {}

    for path, methods in paths.items():
        if not isinstance(methods, Mapping):
            continue
        for method, operation in methods.items():
            if str(method).lower() not in _HTTP_METHODS or not isinstance(
                operation, Mapping
            ):
                continue
            operation_ids.append(
                str(operation.get("operationId") or f"{str(method).lower()}_{path}")
            )
            for parameter in operation.get("parameters") or []:
                if not isinstance(parameter, Mapping):
                    continue
                name = parameter.get("name")
                if not isinstance(name, str) or not name:
                    continue
                schema = parameter.get("schema")
                field = dict(schema) if isinstance(schema, Mapping) else {"type": "string"}
                if parameter.get("in") == "path":
                    path_params[name] = field
                elif parameter.get("in") == "query":
                    query_params[name] = field
            request_body = operation.get("requestBody")
            if isinstance(request_body, Mapping):
                content = request_body.get("content")
                if isinstance(content, Mapping):
                    json_body = content.get("application/json")
                    if isinstance(json_body, Mapping):
                        body_schema = json_body.get("schema")
                        if isinstance(body_schema, Mapping):
                            body_props = body_schema.get("properties")
                            if isinstance(body_props, Mapping):
                                body_properties.update(dict(body_props))

    properties: dict[str, Any] = {
        "__operation_id": {
            "type": "string",
            "description": "要调用的操作 id。",
            **({"enum": operation_ids} if operation_ids else {}),
        }
    }
    required = ["__operation_id"]
    if path_params:
        properties["path"] = {"type": "object", "properties": path_params}
    if query_params:
        properties["query"] = {"type": "object", "properties": query_params}
    if body_properties:
        properties["body"] = {"type": "object", "properties": body_properties}
    return {"type": "object", "properties": properties, "required": required}


__all__ = [
    "EMPTY_SCHEMA",
    "schema_from_spec",
    "tool_description",
    "tool_needs_confirm",
    "tool_parameters",
    "tool_risk",
]
