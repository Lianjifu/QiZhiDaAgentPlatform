"""Use-case unit tests for the tool module."""

from __future__ import annotations

from uuid import UUID

import pytest
from _tool_unit_in_memory import (
    CollectingEventPublisher,
    FakeCustomInvoker,
    FakeMCPRuntime,
    FakeOpenAPIRuntime,
    InMemoryToolCallRepository,
    InMemoryToolRepository,
)

from qzdap.modules.tool.application.use_cases import (
    BatchInvokeInput,
    DeleteToolUseCase,
    GetToolUseCase,
    InvokeToolUseCase,
    ListToolsUseCase,
    RegisterToolUseCase,
    UpdateToolUseCase,
)
from qzdap.modules.tool.domain import (
    AuthConfig,
    AuthConfigType,
    SpecOperation,
    Tool,
    ToolCallStatus,
    ToolProtocol,
)
from qzdap.modules.tool.domain.errors import (
    ToolAlreadyExists,
    ToolCallTimeout,
    ToolDisabled,
    ToolNotFound,
    ToolVersionMismatch,
    UpstreamUnavailable,
)

TENANT = UUID("00000000-0000-0000-0000-000000000010")
OTHER_TENANT = UUID("00000000-0000-0000-0000-0000000000ff")
WID = UUID("00000000-0000-0000-0000-000000000002")
OWNER = UUID("00000000-0000-0000-0000-000000000020")


def _custom_invoker_with_echo():
    async def _echo(args):
        return {"echo": dict(args)}

    inv = FakeCustomInvoker()
    inv.register("echo", _echo)
    return inv


def _deps():
    return {
        "tools": InMemoryToolRepository(),
        "calls": InMemoryToolCallRepository(),
        "custom": _custom_invoker_with_echo(),
        "openapi": FakeOpenAPIRuntime(),
        "mcp": FakeMCPRuntime(),
        "events": CollectingEventPublisher(),
    }


def _service(d):
    from qzdap.modules.tool.application.services import ToolService

    return ToolService(
        tools=d["tools"],
        calls=d["calls"],
        custom=d["custom"],
        openapi=d["openapi"],
        mcp=d["mcp"],
        events=d["events"],
    )


def _per_call_factory(d):
    """Yield a fresh `ToolService` over the same in-memory ports.

    Mirrors the production wiring: a fresh service per batch item so
    SQLAlchemy's async-session "concurrent operations not permitted"
    rule is never violated. With in-memory ports there's no actual
    session, but the shape is identical so the use-case code under test
    sees the real factory contract.
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _factory():
        yield _service(d)

    return _factory


# ── RegisterTool ────────────────────────────────────────────────────


class TestRegisterTool:
    @pytest.mark.asyncio
    async def test_registers_custom_tool(self) -> None:
        d = _deps()
        tool = await RegisterToolUseCase(d["tools"], d["events"]).execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="echo",
            description="echo",
            protocol=ToolProtocol.CUSTOM,
            spec={"x": 1},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        assert tool.name == "echo"
        assert tool.protocol is ToolProtocol.CUSTOM
        assert d["events"].published and d["events"].published[0][0].name == "echo"

    @pytest.mark.asyncio
    async def test_registers_openapi_tool_with_operations(self) -> None:
        d = _deps()
        spec = {
            "servers": [{"url": "https://api.example.com"}],
            "paths": {"/x": {"get": {"operationId": "getX"}}},
        }
        tool = await RegisterToolUseCase(d["tools"], d["events"]).execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="api",
            description="",
            protocol=ToolProtocol.OPENAPI,
            spec=spec,
            auth_config=None,
            rate_limit_per_minute=None,
        )
        assert tool.spec_operations == [SpecOperation("GET", "/x", "getX")]

    @pytest.mark.asyncio
    async def test_duplicate_name_raises(self) -> None:
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="dup",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        with pytest.raises(ToolAlreadyExists):
            await reg.execute(
                tenant_id=TENANT,
                workspace_id=WID,
                owner_id=OWNER,
                name="dup",
                description="",
                protocol=ToolProtocol.CUSTOM,
                spec={},
                auth_config=None,
                rate_limit_per_minute=None,
            )

    @pytest.mark.asyncio
    async def test_invalid_openapi_spec_raises(self) -> None:
        from qzdap.modules.tool.domain.errors import InvalidToolSpec

        d = _deps()
        with pytest.raises(InvalidToolSpec):
            await RegisterToolUseCase(d["tools"], d["events"]).execute(
                tenant_id=TENANT,
                workspace_id=WID,
                owner_id=OWNER,
                name="bad",
                description="",
                protocol=ToolProtocol.OPENAPI,
                spec={"no_paths": True},
                auth_config=None,
                rate_limit_per_minute=None,
            )


# ── List / Get / Update / Delete ─────────────────────────────────────


class TestCRUD:
    @pytest.mark.asyncio
    async def test_list_filters_by_enabled(self) -> None:
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        a = await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="a",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        b = await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="b",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        await UpdateToolUseCase(d["tools"], d["events"]).execute(
            tenant_id=TENANT,
            tool_id=b.id,
            expected_version=None,
            description=None,
            spec=None,
            auth_config=None,
            clear_auth=False,
            rate_limit_per_minute=None,
            clear_rate_limit=False,
            enabled=False,
        )
        all_tools = await ListToolsUseCase(d["tools"]).execute(tenant_id=TENANT)
        only_enabled = await ListToolsUseCase(d["tools"]).execute(
            tenant_id=TENANT, enabled=True
        )
        assert {t.id for t in all_tools} == {a.id, b.id}
        assert {t.id for t in only_enabled} == {a.id}

    @pytest.mark.asyncio
    async def test_get_cross_tenant_raises(self) -> None:
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        tool = await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="x",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        with pytest.raises(ToolNotFound):
            await GetToolUseCase(d["tools"]).execute(
                tenant_id=OTHER_TENANT, tool_id=tool.id
            )

    @pytest.mark.asyncio
    async def test_update_version_mismatch_raises(self) -> None:
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        tool = await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="x",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        with pytest.raises(ToolVersionMismatch):
            await UpdateToolUseCase(d["tools"], d["events"]).execute(
                tenant_id=TENANT,
                tool_id=tool.id,
                expected_version=99,
                description="x",
                spec=None,
                auth_config=None,
                clear_auth=False,
                rate_limit_per_minute=None,
                clear_rate_limit=False,
                enabled=None,
            )

    @pytest.mark.asyncio
    async def test_delete_emits_event_and_removes(self) -> None:
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        tool = await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="x",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        await DeleteToolUseCase(d["tools"], d["events"]).execute(
            tenant_id=TENANT, tool_id=tool.id
        )
        with pytest.raises(ToolNotFound):
            await GetToolUseCase(d["tools"]).execute(tenant_id=TENANT, tool_id=tool.id)


# ── InvokeTool ──────────────────────────────────────────────────────


class TestInvokeTool:
    @pytest.mark.asyncio
    async def test_invoke_custom_dispatches_to_registry(self) -> None:
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="echo",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        invoke = InvokeToolUseCase(
            tools=d["tools"],
            calls=d["calls"],
            custom=d["custom"],
            openapi=d["openapi"],
            mcp=d["mcp"],
            events=d["events"],
        )
        call = await invoke.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            tool_name="echo",
            arguments={"hi": "there"},
        )
        assert call.status is ToolCallStatus.SUCCEEDED
        assert call.result == {"echo": {"hi": "there"}}
        assert call.latency_ms is not None and call.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_invoke_unknown_tool_raises(self) -> None:
        d = _deps()
        invoke = InvokeToolUseCase(
            tools=d["tools"],
            calls=d["calls"],
            custom=d["custom"],
            openapi=d["openapi"],
            mcp=d["mcp"],
            events=d["events"],
        )
        with pytest.raises(ToolNotFound):
            await invoke.execute(
                tenant_id=TENANT,
                workspace_id=WID,
                owner_id=OWNER,
                tool_name="ghost",
                arguments={},
            )

    @pytest.mark.asyncio
    async def test_invoke_disabled_tool_raises(self) -> None:
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="echo",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        # Mark disabled via repo directly to skip the version bump.
        tool = await d["tools"].get_by_name(tenant_id=TENANT, name="echo")
        assert tool is not None
        await d["tools"].update(tool.update(enabled=False))

        invoke = InvokeToolUseCase(
            tools=d["tools"],
            calls=d["calls"],
            custom=d["custom"],
            openapi=d["openapi"],
            mcp=d["mcp"],
            events=d["events"],
        )
        with pytest.raises(ToolDisabled):
            await invoke.execute(
                tenant_id=TENANT,
                workspace_id=WID,
                owner_id=OWNER,
                tool_name="echo",
                arguments={},
            )

    @pytest.mark.asyncio
    async def test_invoke_openapi_dispatches_with_operation_id(self) -> None:
        d = _deps()
        spec = {
            "servers": [{"url": "https://api.example.com"}],
            "paths": {"/x": {"get": {"operationId": "getX"}}},
        }
        reg = RegisterToolUseCase(d["tools"], d["events"])
        await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="api",
            description="",
            protocol=ToolProtocol.OPENAPI,
            spec=spec,
            auth_config=AuthConfig(type=AuthConfigType.BEARER, secrets_ref="r"),
            rate_limit_per_minute=None,
        )
        invoke = InvokeToolUseCase(
            tools=d["tools"],
            calls=d["calls"],
            custom=d["custom"],
            openapi=d["openapi"],
            mcp=d["mcp"],
            events=d["events"],
        )
        await invoke.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            tool_name="api",
            arguments={"__operation_id": "getX", "query": {"a": "1"}},
        )
        assert len(d["openapi"].invocations) == 1
        inv = d["openapi"].invocations[0]
        assert inv["operation"].operation_id == "getX"
        assert inv["auth"].type is AuthConfigType.BEARER
        assert "__operation_id" not in inv["arguments"]
        assert inv["arguments"] == {"query": {"a": "1"}}

    @pytest.mark.asyncio
    async def test_invoke_openapi_without_operation_id_422(self) -> None:

        # Tested through the HTTP layer; here we just confirm the use case
        # raises the sentinel.
        d = _deps()
        spec = {
            "servers": [{"url": "https://api.example.com"}],
            "paths": {"/x": {"get": {"operationId": "getX"}}},
        }
        reg = RegisterToolUseCase(d["tools"], d["events"])
        await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="api",
            description="",
            protocol=ToolProtocol.OPENAPI,
            spec=spec,
            auth_config=None,
            rate_limit_per_minute=None,
        )
        invoke = InvokeToolUseCase(
            tools=d["tools"],
            calls=d["calls"],
            custom=d["custom"],
            openapi=d["openapi"],
            mcp=d["mcp"],
            events=d["events"],
        )
        from qzdap.modules.tool.application.use_cases import InvalidToolSpecCallError

        with pytest.raises(InvalidToolSpecCallError):
            await invoke.execute(
                tenant_id=TENANT,
                workspace_id=WID,
                owner_id=OWNER,
                tool_name="api",
                arguments={},
            )

    @pytest.mark.asyncio
    async def test_invoke_mcp_dispatches_call(self) -> None:
        d = _deps()
        spec = {"server_url": "https://mcp.example.com", "mcp_tool_name": "fetch"}
        reg = RegisterToolUseCase(d["tools"], d["events"])
        await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="mcptool",
            description="",
            protocol=ToolProtocol.MCP,
            spec=spec,
            auth_config=None,
            rate_limit_per_minute=None,
        )
        invoke = InvokeToolUseCase(
            tools=d["tools"],
            calls=d["calls"],
            custom=d["custom"],
            openapi=d["openapi"],
            mcp=d["mcp"],
            events=d["events"],
        )
        d["mcp"].call_response = {"content": "ok"}
        call = await invoke.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            tool_name="mcptool",
            arguments={"x": 1},
        )
        assert call.result == {"content": "ok"}
        assert d["mcp"].call_calls and d["mcp"].call_calls[0]["tool_name"] == "fetch"

    @pytest.mark.asyncio
    async def test_invoke_timeout_translates_to_504(self) -> None:
        d = _deps()
        spec = {"server_url": "https://mcp.example.com", "mcp_tool_name": "fetch"}
        reg = RegisterToolUseCase(d["tools"], d["events"])
        await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="slow",
            description="",
            protocol=ToolProtocol.MCP,
            spec=spec,
            auth_config=None,
            rate_limit_per_minute=None,
        )

        class SlowMCP(FakeMCPRuntime):
            async def call_tool(self, **kw):
                import httpx

                raise httpx.ConnectTimeout("upstream too slow")

        d["mcp"] = SlowMCP()
        invoke = InvokeToolUseCase(
            tools=d["tools"],
            calls=d["calls"],
            custom=d["custom"],
            openapi=d["openapi"],
            mcp=d["mcp"],
            events=d["events"],
            timeout_seconds=0.05,
        )
        with pytest.raises(ToolCallTimeout):
            await invoke.execute(
                tenant_id=TENANT,
                workspace_id=WID,
                owner_id=OWNER,
                tool_name="slow",
                arguments={},
            )

    @pytest.mark.asyncio
    async def test_invoke_upstream_http_error_translates_to_502(self) -> None:
        d = _deps()
        spec = {"server_url": "https://mcp.example.com", "mcp_tool_name": "fetch"}
        reg = RegisterToolUseCase(d["tools"], d["events"])
        await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="dead",
            description="",
            protocol=ToolProtocol.MCP,
            spec=spec,
            auth_config=None,
            rate_limit_per_minute=None,
        )

        class BrokenMCP(FakeMCPRuntime):
            async def call_tool(self, **kw):
                import httpx

                raise httpx.ConnectError("connection refused")

        d["mcp"] = BrokenMCP()
        invoke = InvokeToolUseCase(
            tools=d["tools"],
            calls=d["calls"],
            custom=d["custom"],
            openapi=d["openapi"],
            mcp=d["mcp"],
            events=d["events"],
        )
        with pytest.raises(UpstreamUnavailable):
            await invoke.execute(
                tenant_id=TENANT,
                workspace_id=WID,
                owner_id=OWNER,
                tool_name="dead",
                arguments={},
            )


# ── Batch ────────────────────────────────────────────────────────────


class TestBatchInvoke:
    @pytest.mark.asyncio
    async def test_mixed_success_and_error(self) -> None:
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="echo",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        svc = _service(d)
        results = await svc.batch_invoke_tools(_per_call_factory(d)).execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            calls=[
                BatchInvokeInput(tool_name="echo", arguments={"a": 1}),
                BatchInvokeInput(tool_name="ghost", arguments={}),
            ],
        )
        assert results[0].status == 200
        assert results[0].result == {"echo": {"a": 1}}
        assert results[1].status == 404
        assert results[1].error and results[1].error["code"] == "TOOL_NOT_FOUND"


# ── Negative / multi-angle tests ───────────────────────────────────────


class TestRegisterToolNegative:
    @pytest.mark.asyncio
    async def test_register_with_empty_name_rejected(self) -> None:
        # Empty name is rejected by the domain validator.
        d = _deps()
        with pytest.raises(ValueError):
            await RegisterToolUseCase(d["tools"], d["events"]).execute(
                tenant_id=TENANT,
                workspace_id=WID,
                owner_id=OWNER,
                name="",
                description="",
                protocol=ToolProtocol.CUSTOM,
                spec={},
                auth_config=None,
                rate_limit_per_minute=None,
            )

    @pytest.mark.asyncio
    async def test_register_with_oversized_name_rejected(self) -> None:
        d = _deps()
        with pytest.raises(ValueError):
            await RegisterToolUseCase(d["tools"], d["events"]).execute(
                tenant_id=TENANT,
                workspace_id=WID,
                owner_id=OWNER,
                name="x" * 129,
                description="",
                protocol=ToolProtocol.CUSTOM,
                spec={},
                auth_config=None,
                rate_limit_per_minute=None,
            )

    @pytest.mark.asyncio
    async def test_register_with_invalid_rate_limit_rejected(self) -> None:
        d = _deps()
        with pytest.raises(ValueError):
            await RegisterToolUseCase(d["tools"], d["events"]).execute(
                tenant_id=TENANT,
                workspace_id=WID,
                owner_id=OWNER,
                name="x",
                description="",
                protocol=ToolProtocol.CUSTOM,
                spec={},
                auth_config=None,
                rate_limit_per_minute=0,
            )

    @pytest.mark.asyncio
    async def test_register_bearer_without_secrets_ref_allowed_at_domain(self) -> None:
        # The domain doesn't validate that a bearer token must have a
        # secrets_ref — that's an integration-time concern (the adapter
        # will silently skip auth injection if secrets_ref is missing).
        d = _deps()
        tool = await RegisterToolUseCase(d["tools"], d["events"]).execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="authy",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=AuthConfig(type=AuthConfigType.BEARER, secrets_ref=None),
            rate_limit_per_minute=None,
        )
        assert tool.auth_config is not None
        assert tool.auth_config.secrets_ref is None

    @pytest.mark.asyncio
    async def test_register_mcp_missing_server_url_rejected(self) -> None:
        from qzdap.modules.tool.domain.errors import InvalidToolSpec

        d = _deps()
        with pytest.raises(InvalidToolSpec):
            await RegisterToolUseCase(d["tools"], d["events"]).execute(
                tenant_id=TENANT,
                workspace_id=WID,
                owner_id=OWNER,
                name="bad_mcp",
                description="",
                protocol=ToolProtocol.MCP,
                spec={"mcp_tool_name": "fetch"},
                auth_config=None,
                rate_limit_per_minute=None,
            )

    @pytest.mark.asyncio
    async def test_register_mcp_missing_tool_name_rejected(self) -> None:
        from qzdap.modules.tool.domain.errors import InvalidToolSpec

        d = _deps()
        with pytest.raises(InvalidToolSpec):
            await RegisterToolUseCase(d["tools"], d["events"]).execute(
                tenant_id=TENANT,
                workspace_id=WID,
                owner_id=OWNER,
                name="bad_mcp2",
                description="",
                protocol=ToolProtocol.MCP,
                spec={"server_url": "https://x"},
                auth_config=None,
                rate_limit_per_minute=None,
            )

    @pytest.mark.asyncio
    async def test_register_openapi_missing_paths_rejected(self) -> None:
        from qzdap.modules.tool.domain.errors import InvalidToolSpec

        d = _deps()
        with pytest.raises(InvalidToolSpec):
            await RegisterToolUseCase(d["tools"], d["events"]).execute(
                tenant_id=TENANT,
                workspace_id=WID,
                owner_id=OWNER,
                name="bad_api",
                description="",
                protocol=ToolProtocol.OPENAPI,
                spec={"servers": [{"url": "https://x"}]},
                auth_config=None,
                rate_limit_per_minute=None,
            )

    @pytest.mark.asyncio
    async def test_register_custom_is_disabled(self) -> None:
        # Tools can be created already disabled; the use case must not
        # silently override that.
        d = _deps()
        tool = await RegisterToolUseCase(d["tools"], d["events"]).execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="off",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        # Mark disabled directly to confirm the field is honoured.
        await d["tools"].update(tool.update(enabled=False))
        fetched = await d["tools"].get(tool.id)
        assert fetched is not None
        assert fetched.enabled is False


class TestUpdateToolNegative:
    @pytest.mark.asyncio
    async def test_update_without_if_match_succeeds(self) -> None:
        # expected_version=None must skip the version check.
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        tool = await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="x",
            description="v1",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        updated = await UpdateToolUseCase(d["tools"], d["events"]).execute(
            tenant_id=TENANT,
            tool_id=tool.id,
            expected_version=None,
            description="v2",
            spec=None,
            auth_config=None,
            clear_auth=False,
            rate_limit_per_minute=None,
            clear_rate_limit=False,
            enabled=None,
        )
        assert updated.description == "v2"
        assert updated.version == 2

    @pytest.mark.asyncio
    async def test_update_cross_tenant_raises_not_found(self) -> None:
        # Updating another tenant's tool must surface as 404, not 412
        # (we never acknowledge existence across tenants).
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        tool = await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="x",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        with pytest.raises(ToolNotFound):
            await UpdateToolUseCase(d["tools"], d["events"]).execute(
                tenant_id=OTHER_TENANT,
                tool_id=tool.id,
                expected_version=1,
                description="hijack",
                spec=None,
                auth_config=None,
                clear_auth=False,
                rate_limit_per_minute=None,
                clear_rate_limit=False,
                enabled=None,
            )

    @pytest.mark.asyncio
    async def test_update_unknown_id_raises(self) -> None:
        d = _deps()
        with pytest.raises(ToolNotFound):
            await UpdateToolUseCase(d["tools"], d["events"]).execute(
                tenant_id=TENANT,
                tool_id=UUID("00000000-0000-0000-0000-0000000000aa"),
                expected_version=1,
                description="x",
                spec=None,
                auth_config=None,
                clear_auth=False,
                rate_limit_per_minute=None,
                clear_rate_limit=False,
                enabled=None,
            )

    @pytest.mark.asyncio
    async def test_update_with_empty_body_still_bumps_version(self) -> None:
        # The domain primitive doesn't gate on no-op; callers (HTTP
        # layer) usually do. Document the actual behavior here.
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        tool = await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="x",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        updated = await UpdateToolUseCase(d["tools"], d["events"]).execute(
            tenant_id=TENANT,
            tool_id=tool.id,
            expected_version=1,
            description=None,
            spec=None,
            auth_config=None,
            clear_auth=False,
            rate_limit_per_minute=None,
            clear_rate_limit=False,
            enabled=None,
        )
        assert updated.version == 2

    @pytest.mark.asyncio
    async def test_re_enable_disabled_tool(self) -> None:
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        tool = await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="x",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        disabled = await UpdateToolUseCase(d["tools"], d["events"]).execute(
            tenant_id=TENANT,
            tool_id=tool.id,
            expected_version=1,
            description=None,
            spec=None,
            auth_config=None,
            clear_auth=False,
            rate_limit_per_minute=None,
            clear_rate_limit=False,
            enabled=False,
        )
        assert disabled.enabled is False
        re_enabled = await UpdateToolUseCase(d["tools"], d["events"]).execute(
            tenant_id=TENANT,
            tool_id=tool.id,
            expected_version=2,
            description=None,
            spec=None,
            auth_config=None,
            clear_auth=False,
            rate_limit_per_minute=None,
            clear_rate_limit=False,
            enabled=True,
        )
        assert re_enabled.enabled is True
        assert re_enabled.version == 3

    @pytest.mark.asyncio
    async def test_update_invalid_rate_limit_raises(self) -> None:
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        tool = await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="x",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=10,
        )
        with pytest.raises(ValueError):
            await UpdateToolUseCase(d["tools"], d["events"]).execute(
                tenant_id=TENANT,
                tool_id=tool.id,
                expected_version=1,
                description=None,
                spec=None,
                auth_config=None,
                clear_auth=False,
                rate_limit_per_minute=0,
                clear_rate_limit=False,
                enabled=None,
            )

    @pytest.mark.asyncio
    async def test_update_changes_spec_and_extracts_operations(self) -> None:
        # When spec is changed on an OpenAPI tool, spec_operations must
        # be re-extracted.
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        tool = await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="api",
            description="",
            protocol=ToolProtocol.OPENAPI,
            spec={
                "servers": [{"url": "https://x"}],
                "paths": {"/a": {"get": {"operationId": "getA"}}},
            },
            auth_config=None,
            rate_limit_per_minute=None,
        )
        new_spec = {
            "servers": [{"url": "https://x"}],
            "paths": {
                "/a": {"get": {"operationId": "getA"}},
                "/b": {"post": {"operationId": "createB"}},
            },
        }
        updated = await UpdateToolUseCase(d["tools"], d["events"]).execute(
            tenant_id=TENANT,
            tool_id=tool.id,
            expected_version=1,
            description=None,
            spec=new_spec,
            auth_config=None,
            clear_auth=False,
            rate_limit_per_minute=None,
            clear_rate_limit=False,
            enabled=None,
        )
        ids = [op.operation_id for op in updated.spec_operations]
        assert "getA" in ids
        assert "createB" in ids

    @pytest.mark.asyncio
    async def test_update_with_invalid_spec_raises(self) -> None:
        from qzdap.modules.tool.domain.errors import InvalidToolSpec

        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        tool = await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="api",
            description="",
            protocol=ToolProtocol.OPENAPI,
            spec={
                "servers": [{"url": "https://x"}],
                "paths": {"/a": {"get": {"operationId": "getA"}}},
            },
            auth_config=None,
            rate_limit_per_minute=None,
        )
        with pytest.raises(InvalidToolSpec):
            await UpdateToolUseCase(d["tools"], d["events"]).execute(
                tenant_id=TENANT,
                tool_id=tool.id,
                expected_version=1,
                description=None,
                spec={"no_paths": True},  # missing 'paths'
                auth_config=None,
                clear_auth=False,
                rate_limit_per_minute=None,
                clear_rate_limit=False,
                enabled=None,
            )


class TestDeleteToolNegative:
    @pytest.mark.asyncio
    async def test_delete_already_deleted_raises(self) -> None:
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        tool = await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="x",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        await DeleteToolUseCase(d["tools"], d["events"]).execute(
            tenant_id=TENANT, tool_id=tool.id
        )
        with pytest.raises(ToolNotFound):
            await DeleteToolUseCase(d["tools"], d["events"]).execute(
                tenant_id=TENANT, tool_id=tool.id
            )

    @pytest.mark.asyncio
    async def test_delete_unknown_id_raises(self) -> None:
        d = _deps()
        with pytest.raises(ToolNotFound):
            await DeleteToolUseCase(d["tools"], d["events"]).execute(
                tenant_id=TENANT,
                tool_id=UUID("00000000-0000-0000-0000-0000000000aa"),
            )

    @pytest.mark.asyncio
    async def test_delete_cross_tenant_raises(self) -> None:
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        tool = await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="x",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        with pytest.raises(ToolNotFound):
            await DeleteToolUseCase(d["tools"], d["events"]).execute(
                tenant_id=OTHER_TENANT, tool_id=tool.id
            )


class TestGetToolNegative:
    @pytest.mark.asyncio
    async def test_get_cross_tenant_raises(self) -> None:
        # Already in TestCRUD; add the negative-corollary: same tenant
        # different tool id also raises.
        d = _deps()
        with pytest.raises(ToolNotFound):
            await GetToolUseCase(d["tools"]).execute(
                tenant_id=TENANT,
                tool_id=UUID("00000000-0000-0000-0000-0000000000ff"),
            )

    @pytest.mark.asyncio
    async def test_list_empty_tenant_returns_empty(self) -> None:
        d = _deps()
        out = await ListToolsUseCase(d["tools"]).execute(tenant_id=TENANT)
        assert out == []

    @pytest.mark.asyncio
    async def test_list_disabled_filter_excludes_disabled(self) -> None:
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="on",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        tool_off = await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="off",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        await d["tools"].update(tool_off.update(enabled=False))
        out_enabled = await ListToolsUseCase(d["tools"]).execute(
            tenant_id=TENANT, enabled=True
        )
        out_disabled = await ListToolsUseCase(d["tools"]).execute(
            tenant_id=TENANT, enabled=False
        )
        assert {t.name for t in out_enabled} == {"on"}
        assert {t.name for t in out_disabled} == {"off"}


class TestInvokeToolNegative:
    @pytest.mark.asyncio
    async def test_invoke_openapi_with_unknown_operation_id_422(self) -> None:
        from qzdap.modules.tool.application.use_cases import InvalidToolSpecCallError

        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="api",
            description="",
            protocol=ToolProtocol.OPENAPI,
            spec={
                "servers": [{"url": "https://x"}],
                "paths": {"/a": {"get": {"operationId": "getA"}}},
            },
            auth_config=None,
            rate_limit_per_minute=None,
        )
        invoke = InvokeToolUseCase(
            tools=d["tools"],
            calls=d["calls"],
            custom=d["custom"],
            openapi=d["openapi"],
            mcp=d["mcp"],
            events=d["events"],
        )
        with pytest.raises(InvalidToolSpecCallError):
            await invoke.execute(
                tenant_id=TENANT,
                workspace_id=WID,
                owner_id=OWNER,
                tool_name="api",
                arguments={"__operation_id": "ghostOp"},
            )

    @pytest.mark.asyncio
    async def test_invoke_openapi_without_servers_url_422(self) -> None:
        from qzdap.modules.tool.application.use_cases import InvalidToolSpecCallError

        d = _deps()
        # Bypass the registration validator by manually crafting a tool
        # with a spec that has operations but no 'servers' entry.
        tool = Tool.create(  # type: ignore[name-defined]
            id=UUID("00000000-0000-0000-0000-0000000000c0"),
            tenant_id=TENANT,
            workspace_id=WID,
            name="apix",
            description="",
            protocol=ToolProtocol.OPENAPI,
            spec={},  # no servers
            spec_operations=[
                SpecOperation(method="GET", path="/a", operation_id="getA")
            ],
            auth_config=None,
            rate_limit_per_minute=None,
        )
        await d["tools"].add(tool)
        invoke = InvokeToolUseCase(
            tools=d["tools"],
            calls=d["calls"],
            custom=d["custom"],
            openapi=d["openapi"],
            mcp=d["mcp"],
            events=d["events"],
        )
        with pytest.raises(InvalidToolSpecCallError):
            await invoke.execute(
                tenant_id=TENANT,
                workspace_id=WID,
                owner_id=OWNER,
                tool_name="apix",
                arguments={"__operation_id": "getA"},
            )

    @pytest.mark.asyncio
    async def test_invoke_openapi_with_operation_id_non_string(self) -> None:
        # __operation_id must be a non-empty string; a list/int is rejected.
        from qzdap.modules.tool.application.use_cases import InvalidToolSpecCallError

        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="api",
            description="",
            protocol=ToolProtocol.OPENAPI,
            spec={
                "servers": [{"url": "https://x"}],
                "paths": {"/a": {"get": {"operationId": "getA"}}},
            },
            auth_config=None,
            rate_limit_per_minute=None,
        )
        invoke = InvokeToolUseCase(
            tools=d["tools"],
            calls=d["calls"],
            custom=d["custom"],
            openapi=d["openapi"],
            mcp=d["mcp"],
            events=d["events"],
        )
        with pytest.raises(InvalidToolSpecCallError):
            await invoke.execute(
                tenant_id=TENANT,
                workspace_id=WID,
                owner_id=OWNER,
                tool_name="api",
                arguments={"__operation_id": 12345},
            )

    @pytest.mark.asyncio
    async def test_invoke_openapi_strips_internal_keys(self) -> None:
        # All __-prefixed keys must be filtered before reaching the upstream.
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="api",
            description="",
            protocol=ToolProtocol.OPENAPI,
            spec={
                "servers": [{"url": "https://x"}],
                "paths": {"/a": {"get": {"operationId": "getA"}}},
            },
            auth_config=None,
            rate_limit_per_minute=None,
        )
        invoke = InvokeToolUseCase(
            tools=d["tools"],
            calls=d["calls"],
            custom=d["custom"],
            openapi=d["openapi"],
            mcp=d["mcp"],
            events=d["events"],
        )
        await invoke.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            tool_name="api",
            arguments={
                "__operation_id": "getA",
                "__internal": "leak",
                "query": {"a": 1},
            },
        )
        inv = d["openapi"].invocations[-1]
        assert "__operation_id" not in inv["arguments"]
        assert "__internal" not in inv["arguments"]
        assert inv["arguments"] == {"query": {"a": 1}}

    @pytest.mark.asyncio
    async def test_invoke_custom_strips_internal_keys(self) -> None:
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="echo",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        invoke = InvokeToolUseCase(
            tools=d["tools"],
            calls=d["calls"],
            custom=d["custom"],
            openapi=d["openapi"],
            mcp=d["mcp"],
            events=d["events"],
        )
        await invoke.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            tool_name="echo",
            arguments={"__x": 1, "y": 2},
        )
        # echo should have been called with {"y": 2}.
        assert d["custom"].last_args == {"y": 2}


class TestBatchInvokeNegative:
    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self) -> None:
        d = _deps()
        svc = _service(d)
        out = await svc.batch_invoke_tools(_per_call_factory(d)).execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            calls=[],
        )
        assert out == []

    @pytest.mark.asyncio
    async def test_all_disabled_each_item_disabled(self) -> None:
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        tool = await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="echo",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        await d["tools"].update(tool.update(enabled=False))
        svc = _service(d)
        results = await svc.batch_invoke_tools(_per_call_factory(d)).execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            calls=[
                BatchInvokeInput(tool_name="echo", arguments={}),
                BatchInvokeInput(tool_name="echo", arguments={}),
            ],
        )
        assert len(results) == 2
        assert all(r.status == 409 for r in results)
        assert all(r.error and r.error["code"] == "TOOL_DISABLED" for r in results)

    @pytest.mark.asyncio
    async def test_mixed_404_409_200(self) -> None:
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        tool = await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="echo",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )
        await d["tools"].update(tool.update(enabled=False))
        svc = _service(d)
        results = await svc.batch_invoke_tools(_per_call_factory(d)).execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            calls=[
                BatchInvokeInput(tool_name="ghost", arguments={}),
                BatchInvokeInput(tool_name="echo", arguments={}),  # disabled
                BatchInvokeInput(tool_name="ghost", arguments={}),
            ],
        )
        assert results[0].status == 404
        assert results[1].status == 409
        assert results[2].status == 404

    @pytest.mark.asyncio
    async def test_unexpected_exception_becomes_500(self) -> None:
        d = _deps()
        reg = RegisterToolUseCase(d["tools"], d["events"])
        await reg.execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            name="boom",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=None,
            rate_limit_per_minute=None,
        )

        class ExplodingCustom(FakeCustomInvoker):
            async def invoke(self, *, name: str, arguments: dict) -> dict:
                raise RuntimeError("kaboom")

        d["custom"] = ExplodingCustom()
        svc = _service(d)
        results = await svc.batch_invoke_tools(_per_call_factory(d)).execute(
            tenant_id=TENANT,
            workspace_id=WID,
            owner_id=OWNER,
            calls=[BatchInvokeInput(tool_name="boom", arguments={})],
        )
        assert results[0].status == 500
        assert results[0].error and results[0].error["code"] == "INTERNAL_ERROR"
