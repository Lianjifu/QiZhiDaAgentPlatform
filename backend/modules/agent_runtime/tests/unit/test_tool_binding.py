"""Agent Stage 2（模块侧）：绑定集读取 ✓ / 真实 schema ✓ / 真实 actor ✓。

依据：Agent 方案 §5.3.1（绑定集读取与治理过滤 ✓）、§9 Stage 2（修
``list_tools`` 的空 schema ✓ —— 真实 schema 从 ``tools`` 表的 spec 长出来 ✓）。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from qzdap.modules.tool.domain import Tool, ToolProtocol
from qzdap_agent_runtime.ports import ActorContext, ToolInvocation
from qzdap_schema.ids import TenantId, ToolId, UserId, WorkspaceId

from qzdap.modules.agent_runtime.adapter.tools import (
    ToolBindingAdapter,
    ToolServiceAdapter,
)

_TENANT = TenantId(uuid4())
_WORKSPACE = WorkspaceId(uuid4())
_OWNER = UserId(uuid4())

_ACTOR = ActorContext(
    actor_id=str(_OWNER),
    tenant_id=str(_TENANT),
    workspace_id=str(_WORKSPACE),
)


def _tool(
    name: str,
    *,
    protocol: ToolProtocol = ToolProtocol.CUSTOM,
    spec: dict[str, Any] | None = None,
    description: str = "",
) -> Tool:
    return Tool.create(
        id=ToolId(uuid4()),
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        name=name,
        description=description,
        protocol=protocol,
        spec=spec or {},
    )


class _FakeUseCase:
    def __init__(self, rows: list[Tool]) -> None:
        self._rows = rows

    async def execute(self, **_kwargs: Any) -> list[Tool]:
        return self._rows


class _FakeToolService:
    """只实现了 ``list_tools`` 的工具服务替身 ✓。"""

    def __init__(self, rows: list[Tool]) -> None:
        self._rows = rows

    def list_tools(self) -> _FakeUseCase:
        return _FakeUseCase(self._rows)


class _FakeToolPort:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    async def list_tools(self) -> list[dict[str, Any]]:
        return self._rows

    async def invoke(self, **_kwargs: Any) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError


class _FakeSkillPort:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    async def list_executable(self) -> list[dict[str, Any]]:
        return self._rows

    async def invoke(self, **_kwargs: Any) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError


class _FakeAgentReader:
    def __init__(self, names: tuple[str, ...]) -> None:
        self._names = names

    async def declared(self, **_kwargs: Any) -> tuple[str, ...]:
        return self._names


class TestListToolsSchema:
    """Stage 2 的验收之一 —— **admin 工具有真实 schema** ✓。"""

    @pytest.mark.asyncio
    async def test_the_admin_tool_gets_its_real_schema(self) -> None:
        adapter = ToolServiceAdapter(
            tool_service=_FakeToolService(
                [
                    _tool(
                        "pet_api",
                        protocol=ToolProtocol.OPENAPI,
                        spec={
                            "paths": {
                                "/pets": {
                                    "get": {
                                        "operationId": "listPets",
                                        "parameters": [
                                            {
                                                "name": "limit",
                                                "in": "query",
                                                "schema": {"type": "integer"},
                                            }
                                        ],
                                    }
                                }
                            }
                        },
                    )
                ]
            ),
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            owner_id=_OWNER,
        )
        rows = await adapter.list_tools()
        assert len(rows) == 1
        parameters = rows[0]["parameters"]
        assert parameters["properties"]["query"]["properties"]["limit"] == {
            "type": "integer"
        }
        assert rows[0]["protocol"] == "openapi"

    @pytest.mark.asyncio
    async def test_the_builtin_tools_keep_their_catalog(self) -> None:
        adapter = ToolServiceAdapter(
            tool_service=_FakeToolService([_tool("echo")]),
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            owner_id=_OWNER,
        )
        rows = await adapter.list_tools()
        assert rows[0]["parameters"]["properties"] == {"text": {"type": "string"}}
        assert rows[0]["risk"] == "low"


class TestBindingAdapter:
    """§5.3.1 —— **只取不选** ✓。"""

    @pytest.mark.asyncio
    async def test_the_declared_tools_become_bindings(self) -> None:
        adapter = ToolBindingAdapter(
            tools=_FakeToolPort(
                [
                    {
                        "name": "echo",
                        "description": "回显",
                        "parameters": {
                            "type": "object",
                            "properties": {"text": {"type": "string"}},
                        },
                        "risk": "low",
                        "needConfirm": False,
                    }
                ]
            ),
            agents=_FakeAgentReader(("echo",)),
        )
        bindings = await adapter.bindings(
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            agent_id=uuid4(),
            agent_version="v1",
        )
        assert [binding.name for binding in bindings] == ["echo"]
        binding = bindings[0]
        assert binding.kind == "tool"
        assert binding.side_effect is False
        assert binding.spec["parameters"]["properties"] == {"text": {"type": "string"}}

    @pytest.mark.asyncio
    async def test_an_empty_binding_set_is_not_an_error(self) -> None:
        adapter = ToolBindingAdapter(
            tools=_FakeToolPort([]),
            agents=_FakeAgentReader(()),
        )
        assert (
            await adapter.bindings(
                tenant_id=_TENANT,
                workspace_id=_WORKSPACE,
                agent_id=uuid4(),
                agent_version="v1",
            )
            == []
        )

    @pytest.mark.asyncio
    async def test_the_unregistered_tools_are_not_exposed(self) -> None:
        adapter = ToolBindingAdapter(
            tools=_FakeToolPort([]),
            agents=_FakeAgentReader(("ghost",)),
        )
        assert (
            await adapter.bindings(
                tenant_id=_TENANT,
                workspace_id=_WORKSPACE,
                agent_id=uuid4(),
                agent_version="v1",
            )
            == []
        )

    @pytest.mark.asyncio
    async def test_the_mcp_tools_are_marked(self) -> None:
        adapter = ToolBindingAdapter(
            tools=_FakeToolPort(
                [{"name": "remote", "protocol": "mcp", "risk": "medium"}]
            ),
            agents=_FakeAgentReader(("remote",)),
        )
        bindings = await adapter.bindings(
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            agent_id=uuid4(),
            agent_version="v1",
        )
        assert bindings[0].kind == "mcp"

    @pytest.mark.asyncio
    async def test_the_skills_are_unified_into_the_same_shape(self) -> None:
        adapter = ToolBindingAdapter(
            tools=_FakeToolPort([]),
            skills=_FakeSkillPort(
                [
                    {
                        "name": "summarize",
                        "description": "总结",
                        "inputSchema": [
                            {
                                "name": "text",
                                "type": "string",
                                "required": True,
                                "description": "原文",
                            }
                        ],
                        "risk": "medium",
                        "needConfirm": True,
                    }
                ]
            ),
            agents=_FakeAgentReader(("summarize",)),
        )
        bindings = await adapter.bindings(
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            agent_id=uuid4(),
            agent_version="v1",
        )
        binding = bindings[0]
        assert binding.kind == "skill"
        assert binding.requires_approval is True
        assert binding.side_effect is True
        parameters = binding.spec["parameters"]
        assert parameters["properties"]["text"]["type"] == "string"
        assert parameters["required"] == ["text"]

    @pytest.mark.asyncio
    async def test_the_high_risk_tools_are_side_effects(self) -> None:
        adapter = ToolBindingAdapter(
            tools=_FakeToolPort(
                [{"name": "bash", "risk": "high", "needConfirm": False}]
            ),
            agents=_FakeAgentReader(("bash",)),
        )
        bindings = await adapter.bindings(
            tenant_id=_TENANT,
            workspace_id=_WORKSPACE,
            agent_id=uuid4(),
            agent_version="v1",
        )
        assert bindings[0].side_effect is True
        assert bindings[0].risk == "high"


class _FakeCall:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result


class _FakeInvokeUseCase:
    def __init__(self, result: dict[str, Any]) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    async def execute(self, **kwargs: Any) -> _FakeCall:
        self.calls.append(kwargs)
        return _FakeCall(self._result)


class _FakeInvokeService:
    def __init__(self, result: dict[str, Any]) -> None:
        self.use_case = _FakeInvokeUseCase(result)

    def invoke_tool(self) -> _FakeInvokeUseCase:
        return self.use_case


class TestToolRuntimeAdapter:
    """**真实 actor 才能执行工具** ✓。"""

    @staticmethod
    def _runtime(service: object) -> object:
        from qzdap.modules.agent_runtime.adapter.graph.agent_loop import (
            ModuleToolRuntime,
        )
        from qzdap.modules.agent_runtime.adapter.tools.tool_service_adapter import (
            ToolServiceAdapter,
        )

        return ModuleToolRuntime(
            tool_port=ToolServiceAdapter(
                tool_service=service,  # type: ignore[arg-type]
                tenant_id=_TENANT,
                workspace_id=_WORKSPACE,
                owner_id=_OWNER,
            ),
            tenant_id=_TENANT,
        )

    @pytest.mark.asyncio
    async def test_the_call_without_an_actor_is_refused(self) -> None:
        service = _FakeInvokeService({"ok": True})
        runtime = self._runtime(service)
        result = await runtime.invoke(
            ToolInvocation(tool_name="echo", arguments={"text": "hi"}),
            actor=ActorContext(
                actor_id="", tenant_id=str(_TENANT), workspace_id=str(_WORKSPACE)
            ),
        )
        assert result.ok is False
        assert result.error_code == "TOOL_ACTOR_MISSING"
        assert service.use_case.calls == []

    @pytest.mark.asyncio
    async def test_the_actor_of_another_tenant_is_refused(self) -> None:
        service = _FakeInvokeService({"ok": True})
        runtime = self._runtime(service)
        result = await runtime.invoke(
            ToolInvocation(tool_name="echo", arguments={"text": "hi"}),
            actor=ActorContext(
                actor_id="u-1", tenant_id=str(uuid4()), workspace_id=str(_WORKSPACE)
            ),
        )
        assert result.ok is False
        assert result.error_code == "TOOL_ACTOR_TENANT_MISMATCH"
        assert service.use_case.calls == []

    @pytest.mark.asyncio
    async def test_the_result_comes_back_as_text(self) -> None:
        service = _FakeInvokeService({"echo": "hi"})
        runtime = self._runtime(service)
        result = await runtime.invoke(
            ToolInvocation(tool_name="echo", arguments={"text": "hi"}), actor=_ACTOR
        )
        assert result.ok is True
        assert result.output == '{"echo": "hi"}'
        assert service.use_case.calls[0]["owner_id"] == _OWNER
