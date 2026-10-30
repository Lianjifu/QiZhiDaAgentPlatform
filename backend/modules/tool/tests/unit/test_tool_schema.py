"""工具的**参数契约** → JSON Schema ✓（Agent 方案 Stage 2 的空 schema 修复 ✓）。

⚠️ **admin 注册的 OpenAPI / MCP 工具必须有真实 schema** ✓ —— 空
``properties`` 会让模型瞎猜 ✗✗。
"""

from __future__ import annotations

from uuid import uuid4

from qzdap_schema.ids import TenantId, ToolId, WorkspaceId

from qzdap.modules.tool.application.tool_schema import (
    tool_description,
    tool_needs_confirm,
    tool_parameters,
    tool_risk,
)
from qzdap.modules.tool.domain import Tool, ToolProtocol

_TENANT = TenantId(uuid4())
_WORKSPACE = WorkspaceId(uuid4())


def _tool(protocol: ToolProtocol, spec: dict, description: str = "") -> Tool:
    return Tool.create(
        id=ToolId(uuid4()),
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        name=f"t-{uuid4().hex[:8]}",
        description=description,
        protocol=protocol,
        spec=spec,
    )


class TestOpenApi:
    def test_the_operations_become_the_argument_contract(self) -> None:
        tool = _tool(
            ToolProtocol.OPENAPI,
            {
                "paths": {
                    "/pets/{petId}": {
                        "get": {
                            "operationId": "getPetById",
                            "parameters": [
                                {
                                    "name": "petId",
                                    "in": "path",
                                    "schema": {"type": "string"},
                                },
                                {
                                    "name": "verbose",
                                    "in": "query",
                                    "schema": {"type": "boolean"},
                                },
                            ],
                        },
                        "post": {
                            "operationId": "createPet",
                            "requestBody": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "properties": {
                                                "name": {"type": "string"},
                                            }
                                        }
                                    }
                                }
                            },
                        },
                    }
                }
            },
        )
        parameters = tool_parameters(tool)
        properties = parameters["properties"]
        assert properties["__operation_id"]["enum"] == ["getPetById", "createPet"]
        assert properties["path"]["properties"]["petId"] == {"type": "string"}
        assert properties["query"]["properties"]["verbose"] == {"type": "boolean"}
        assert properties["body"]["properties"]["name"] == {"type": "string"}
        assert parameters["required"] == ["__operation_id"]

    def test_an_openapi_document_without_paths_is_empty(self) -> None:
        assert tool_parameters(_tool(ToolProtocol.OPENAPI, {})) == {
            "type": "object",
            "properties": {},
        }


class TestDeclaredSchemas:
    def test_the_declared_parameters_are_used_as_is(self) -> None:
        declared = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }
        tool = _tool(ToolProtocol.CUSTOM, {"parameters": declared})
        assert tool_parameters(tool) == declared

    def test_the_mcp_input_schema_is_used(self) -> None:
        declared = {"type": "object", "properties": {"text": {"type": "string"}}}
        tool = _tool(
            ToolProtocol.MCP,
            {"server_url": "https://mcp.example", "input_schema": declared},
        )
        assert tool_parameters(tool) == declared

    def test_the_mcp_tool_without_a_schema_is_empty(self) -> None:
        tool = _tool(
            ToolProtocol.MCP, {"server_url": "https://mcp.example", "mcp_tool_name": "x"}
        )
        assert tool_parameters(tool) == {"type": "object", "properties": {}}


class TestMetadata:
    def test_the_risk_and_the_confirmation_come_from_the_spec(self) -> None:
        tool = _tool(ToolProtocol.CUSTOM, {"risk": "high", "needConfirm": True})
        assert tool_risk(tool) == "high"
        assert tool_needs_confirm(tool) is True

    def test_the_high_risk_tools_need_confirmation_by_default(self) -> None:
        tool = _tool(ToolProtocol.CUSTOM, {"risk": "high"})
        assert tool_needs_confirm(tool) is True

    def test_the_description_prefers_the_spec(self) -> None:
        tool = _tool(ToolProtocol.CUSTOM, {"description": "spec 里的描述"}, "行上的描述")
        assert tool_description(tool) == "spec 里的描述"

    def test_the_description_falls_back_to_the_row(self) -> None:
        tool = _tool(ToolProtocol.CUSTOM, {}, "行上的描述")
        assert tool_description(tool) == "行上的描述"
