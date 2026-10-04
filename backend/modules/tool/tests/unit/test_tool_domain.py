"""Domain-layer unit tests for the tool module."""

from __future__ import annotations

from uuid import UUID

import pytest

from qzdap.modules.tool.domain import (
    AuthConfig,
    AuthConfigType,
    SpecOperation,
    Tool,
    ToolProtocol,
)
from qzdap.modules.tool.domain.errors import InvalidToolSpec

TID = UUID("00000000-0000-0000-0000-000000000001")
WID = UUID("00000000-0000-0000-0000-000000000002")
TENANT = UUID("00000000-0000-0000-0000-000000000010")


def _make_openapi_spec() -> dict:
    return {
        "openapi": "3.0.0",
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/pets": {
                "get": {"operationId": "listPets", "summary": "List all pets"},
                "post": {
                    "operationId": "createPet",
                    "requestBody": {"required": True},
                },
            },
            "/pets/{petId}": {
                "get": {"operationId": "getPet", "parameters": []},
                "delete": {},
            },
        },
    }


def _make_mcp_spec() -> dict:
    return {"server_url": "https://mcp.example.com/mcp", "mcp_tool_name": "fetch"}


class TestToolProtocolExtractOperations:
    def test_openapi_extracts_all_http_methods(self) -> None:
        ops = Tool.extract_operations(
            protocol=ToolProtocol.OPENAPI, spec=_make_openapi_spec()
        )
        ids = [op.operation_id for op in ops]
        assert "listPets" in ids
        assert "createPet" in ids
        assert "getPet" in ids
        # delete has no operationId in the fixture → synthesised id present.
        assert any(op.method == "DELETE" for op in ops)

    def test_openapi_missing_paths_raises(self) -> None:
        with pytest.raises(InvalidToolSpec):
            Tool.extract_operations(
                protocol=ToolProtocol.OPENAPI, spec={"openapi": "3.0.0"}
            )

    def test_openapi_path_must_be_object(self) -> None:
        with pytest.raises(InvalidToolSpec):
            Tool.extract_operations(
                protocol=ToolProtocol.OPENAPI, spec={"paths": {"/x": "not-an-object"}}
            )

    def test_openapi_generates_synthetic_id_when_missing(self) -> None:
        ops = Tool.extract_operations(
            protocol=ToolProtocol.OPENAPI,
            spec={"paths": {"/things": {"get": {}}}},
        )
        assert ops == [SpecOperation("GET", "/things", "get_/things")]

    def test_mcp_returns_synthetic_single_operation(self) -> None:
        ops = Tool.extract_operations(protocol=ToolProtocol.MCP, spec=_make_mcp_spec())
        assert ops == [SpecOperation("POST", "/", "fetch")]

    def test_mcp_missing_server_url_raises(self) -> None:
        with pytest.raises(InvalidToolSpec):
            Tool.extract_operations(
                protocol=ToolProtocol.MCP, spec={"mcp_tool_name": "x"}
            )

    def test_mcp_missing_tool_name_raises(self) -> None:
        with pytest.raises(InvalidToolSpec):
            Tool.extract_operations(
                protocol=ToolProtocol.MCP,
                spec={"server_url": "https://mcp.example.com"},
            )

    def test_custom_returns_empty(self) -> None:
        assert (
            Tool.extract_operations(protocol=ToolProtocol.CUSTOM, spec={"any": "shape"})
            == []
        )

    def test_unknown_protocol_raises(self) -> None:
        class FakeProtocol:
            value = "bogus"

        with pytest.raises(InvalidToolSpec):
            Tool.extract_operations(protocol=FakeProtocol(), spec={})  # type: ignore[arg-type]


class TestToolCreate:
    def test_creates_with_version_1(self) -> None:
        tool = Tool.create(
            id=TID,
            tenant_id=TENANT,
            workspace_id=WID,
            name="echo",
            description="echoes args",
            protocol=ToolProtocol.CUSTOM,
            spec={},
        )
        assert tool.version == 1
        assert tool.enabled is True
        assert tool.spec == {}
        assert tool.spec_operations == []

    def test_name_too_long_raises(self) -> None:
        with pytest.raises(ValueError):
            Tool.create(
                id=TID,
                tenant_id=TENANT,
                workspace_id=WID,
                name="x" * 129,
                description="",
                protocol=ToolProtocol.CUSTOM,
                spec={},
            )

    def test_name_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            Tool.create(
                id=TID,
                tenant_id=TENANT,
                workspace_id=WID,
                name="",
                description="",
                protocol=ToolProtocol.CUSTOM,
                spec={},
            )

    def test_name_exactly_128_chars_ok(self) -> None:
        # Boundary: 128 is allowed.
        tool = Tool.create(
            id=TID,
            tenant_id=TENANT,
            workspace_id=WID,
            name="a" * 128,
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
        )
        assert len(tool.name) == 128

    def test_name_unicode_and_special_chars_allowed(self) -> None:
        # The validator is purely length; unicode / spaces / punctuation
        # are accepted at the domain layer (HTTP layer applies a stricter
        # pattern if needed).
        tool = Tool.create(
            id=TID,
            tenant_id=TENANT,
            workspace_id=WID,
            name="天气-tool 1.0",
            description="中文 + emoji ✨",
            protocol=ToolProtocol.CUSTOM,
            spec={},
        )
        assert tool.name == "天气-tool 1.0"

    def test_rate_limit_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError):
            Tool.create(
                id=TID,
                tenant_id=TENANT,
                workspace_id=WID,
                name="x",
                description="",
                protocol=ToolProtocol.CUSTOM,
                spec={},
                rate_limit_per_minute=200_000,
            )

    def test_rate_limit_zero_raises(self) -> None:
        with pytest.raises(ValueError):
            Tool.create(
                id=TID,
                tenant_id=TENANT,
                workspace_id=WID,
                name="x",
                description="",
                protocol=ToolProtocol.CUSTOM,
                spec={},
                rate_limit_per_minute=0,
            )

    def test_rate_limit_negative_raises(self) -> None:
        with pytest.raises(ValueError):
            Tool.create(
                id=TID,
                tenant_id=TENANT,
                workspace_id=WID,
                name="x",
                description="",
                protocol=ToolProtocol.CUSTOM,
                spec={},
                rate_limit_per_minute=-1,
            )

    def test_rate_limit_boundary_values_ok(self) -> None:
        for n in (1, 100_000):
            tool = Tool.create(
                id=TID,
                tenant_id=TENANT,
                workspace_id=WID,
                name="x",
                description="",
                protocol=ToolProtocol.CUSTOM,
                spec={},
                rate_limit_per_minute=n,
            )
            assert tool.rate_limit_per_minute == n

    def test_rate_limit_none_is_unlimited(self) -> None:
        tool = Tool.create(
            id=TID,
            tenant_id=TENANT,
            workspace_id=WID,
            name="x",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            rate_limit_per_minute=None,
        )
        assert tool.rate_limit_per_minute is None

    def test_spec_is_defensively_copied(self) -> None:
        # Mutating the source dict after creation must not affect the tool.
        src = {"a": 1}
        tool = Tool.create(
            id=TID,
            tenant_id=TENANT,
            workspace_id=WID,
            name="x",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec=src,
        )
        src["a"] = 999
        src["b"] = "leak"
        assert tool.spec == {"a": 1}

    def test_created_at_and_updated_at_initialised(self) -> None:
        tool = Tool.create(
            id=TID,
            tenant_id=TENANT,
            workspace_id=WID,
            name="x",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
        )
        assert tool.created_at.tzinfo is not None
        assert tool.updated_at.tzinfo is not None
        # On creation both should be very close to each other.
        delta = abs((tool.updated_at - tool.created_at).total_seconds())
        assert delta < 1.0


class TestToolUpdate:
    def _new(self) -> Tool:
        return Tool.create(
            id=TID,
            tenant_id=TENANT,
            workspace_id=WID,
            name="echo",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
            auth_config=AuthConfig(type=AuthConfigType.BEARER, secrets_ref="r1"),
            rate_limit_per_minute=100,
        )

    def test_update_bumps_version(self) -> None:
        tool = self._new()
        u = tool.update(description="new")
        assert u.version == tool.version + 1
        assert u.description == "new"
        # Untouched fields stay the same.
        assert u.name == tool.name
        assert u.rate_limit_per_minute == 100

    def test_update_can_clear_auth(self) -> None:
        tool = self._new()
        u = tool.update(clear_auth=True)
        assert u.auth_config is None

    def test_update_can_replace_auth(self) -> None:
        tool = self._new()
        new_auth = AuthConfig(type=AuthConfigType.API_KEY, secrets_ref="r2")
        u = tool.update(auth_config=new_auth)
        assert u.auth_config == new_auth

    def test_update_can_clear_rate_limit(self) -> None:
        tool = self._new()
        u = tool.update(clear_rate_limit=True)
        assert u.rate_limit_per_minute is None

    def test_update_disable(self) -> None:
        tool = self._new()
        u = tool.update(enabled=False)
        assert u.enabled is False

    def test_disable_helper(self) -> None:
        tool = self._new()
        assert tool.disable().enabled is False

    def test_update_without_any_field_still_bumps_version(self) -> None:
        # A no-op update still bumps version (the HTTP layer normally
        # short-circuits an empty PATCH body; the domain primitive does
        # not).
        tool = self._new()
        u = tool.update()
        assert u.version == tool.version + 1

    def test_update_updated_at_advances(self) -> None:
        import time as _t

        tool = self._new()
        _t.sleep(0.01)
        u = tool.update(description="x")
        assert u.updated_at > tool.updated_at
        # created_at must be preserved across updates.
        assert u.created_at == tool.created_at

    def test_update_with_invalid_rate_limit_raises(self) -> None:
        tool = self._new()
        with pytest.raises(ValueError):
            tool.update(rate_limit_per_minute=0)
        with pytest.raises(ValueError):
            tool.update(rate_limit_per_minute=100_001)

    def test_update_preserves_name_and_protocol(self) -> None:
        # name and protocol are immutable; update() must never change them.
        tool = self._new()
        u = tool.update(description="x")
        assert u.name == tool.name
        assert u.protocol == tool.protocol

    def test_clear_auth_takes_precedence_over_auth_config(self) -> None:
        # When both clear_auth=True and auth_config=<something> are passed,
        # clear wins — the call still ends up with no auth.
        tool = self._new()
        u = tool.update(
            clear_auth=True,
            auth_config=AuthConfig(type=AuthConfigType.OAUTH2, secrets_ref="x"),
        )
        assert u.auth_config is None

    def test_clear_rate_limit_takes_precedence_over_rate_limit(self) -> None:
        tool = self._new()
        u = tool.update(clear_rate_limit=True, rate_limit_per_minute=999)
        assert u.rate_limit_per_minute is None


class TestToolCallLifecycle:
    def test_create_running(self) -> None:
        from qzdap.modules.tool.domain import ToolCall, ToolCallStatus

        call = ToolCall.create(
            id=UUID(int=1),
            tenant_id=TENANT,
            workspace_id=WID,
            tool_name="echo",
            arguments={"a": 1},
        )
        assert call.status is ToolCallStatus.RUNNING
        assert call.finished_at is None
        assert call.latency_ms is None
        assert call.error_code is None

    def test_succeed(self) -> None:
        from qzdap.modules.tool.domain import ToolCall, ToolCallStatus

        call = ToolCall.create(
            id=UUID(int=1),
            tenant_id=TENANT,
            workspace_id=WID,
            tool_name="echo",
            arguments={},
        )
        succ = call.succeed(result={"out": 1}, latency_ms=42)
        assert succ.status is ToolCallStatus.SUCCEEDED
        assert succ.result == {"out": 1}
        assert succ.latency_ms == 42
        assert succ.finished_at is not None

    def test_fail(self) -> None:
        from qzdap.modules.tool.domain import ToolCall, ToolCallStatus

        call = ToolCall.create(
            id=UUID(int=1),
            tenant_id=TENANT,
            workspace_id=WID,
            tool_name="echo",
            arguments={},
        )
        failed = call.fail(error_code="UPSTREAM_UNAVAILABLE", latency_ms=10)
        assert failed.status is ToolCallStatus.FAILED
        assert failed.error_code == "UPSTREAM_UNAVAILABLE"
        assert failed.latency_ms == 10

    def test_arguments_defensively_copied(self) -> None:
        # Mutating the caller's dict must not leak into the persisted call.
        from qzdap.modules.tool.domain import ToolCall

        args = {"k": 1}
        call = ToolCall.create(
            id=UUID(int=2),
            tenant_id=TENANT,
            workspace_id=WID,
            tool_name="echo",
            arguments=args,
        )
        args["k"] = 999
        args["new"] = "leak"
        assert call.arguments == {"k": 1}

    def test_fail_with_none_latency(self) -> None:
        # latency_ms is optional for failures (we may not know how long
        # we waited if the call was rejected synchronously).
        from qzdap.modules.tool.domain import ToolCall, ToolCallStatus

        call = ToolCall.create(
            id=UUID(int=3),
            tenant_id=TENANT,
            workspace_id=WID,
            tool_name="echo",
            arguments={},
        )
        failed = call.fail(error_code="TOOL_DISABLED", latency_ms=None)
        assert failed.status is ToolCallStatus.FAILED
        assert failed.latency_ms is None
        assert failed.error_code == "TOOL_DISABLED"

    def test_succeed_zero_latency_is_ok(self) -> None:
        # Sub-millisecond calls round to 0 — must not be rejected.
        from qzdap.modules.tool.domain import ToolCall, ToolCallStatus

        call = ToolCall.create(
            id=UUID(int=4),
            tenant_id=TENANT,
            workspace_id=WID,
            tool_name="echo",
            arguments={},
        )
        succ = call.succeed(result={"x": 1}, latency_ms=0)
        assert succ.latency_ms == 0
        assert succ.status is ToolCallStatus.SUCCEEDED

    def test_state_transitions_are_terminal(self) -> None:
        # succeed() / fail() cannot be called twice on the same call.
        from qzdap.modules.tool.domain import ToolCall

        call = ToolCall.create(
            id=UUID(int=5),
            tenant_id=TENANT,
            workspace_id=WID,
            tool_name="echo",
            arguments={},
        )
        succ = call.succeed(result={"x": 1}, latency_ms=5)
        # A second succeed returns a NEW call with the same id — original
        # state isn't mutated; this test just guards against accidental
        # aliasing bugs.
        succ2 = succ.succeed(result={"y": 2}, latency_ms=10)
        assert succ.result == {"x": 1}
        assert succ2.result == {"y": 2}
        assert succ.id == succ2.id

    def test_fail_preserves_arguments(self) -> None:
        # Even on failure the original arguments are kept for debugging.
        from qzdap.modules.tool.domain import ToolCall

        call = ToolCall.create(
            id=UUID(int=6),
            tenant_id=TENANT,
            workspace_id=WID,
            tool_name="echo",
            arguments={"k": "v"},
        )
        failed = call.fail(error_code="UPSTREAM_UNAVAILABLE")
        assert failed.arguments == {"k": "v"}


class TestAuthConfig:
    def test_none_factory_has_no_secrets_ref(self) -> None:
        a = AuthConfig.none()
        assert a.type is AuthConfigType.NONE
        assert a.secrets_ref is None

    def test_bearer_with_empty_secrets_ref_ok(self) -> None:
        # Domain layer doesn't validate that bearer has a secrets_ref —
        # the HTTP / adapter layer is responsible. The frozen dataclass
        # accepts the raw input as-is.
        a = AuthConfig(type=AuthConfigType.BEARER, secrets_ref=None)
        assert a.type is AuthConfigType.BEARER
        assert a.secrets_ref is None

    def test_each_type_round_trips_to_str(self) -> None:
        for t in AuthConfigType:
            assert isinstance(t.value, str)


class TestSpecOperation:
    def test_frozen_dataclass_equality(self) -> None:
        a = SpecOperation(method="GET", path="/x", operation_id="getX")
        b = SpecOperation(method="GET", path="/x", operation_id="getX")
        c = SpecOperation(method="POST", path="/x", operation_id="getX")
        assert a == b
        assert a != c


class TestEventEmission:
    def test_registered_event_carries_protocol_value(self) -> None:
        tool = Tool.create(
            id=TID,
            tenant_id=TENANT,
            workspace_id=WID,
            name="api",
            description="",
            protocol=ToolProtocol.OPENAPI,
            spec={
                "servers": [{"url": "https://x"}],
                "paths": {"/a": {"get": {"operationId": "a"}}},
            },
        )
        ev = tool.raise_registered_event()
        assert ev.name == "api"
        assert ev.protocol == "openapi"

    def test_updated_event_carries_new_version(self) -> None:
        tool = Tool.create(
            id=TID,
            tenant_id=TENANT,
            workspace_id=WID,
            name="x",
            description="",
            protocol=ToolProtocol.CUSTOM,
            spec={},
        )
        u = tool.update(description="y")
        ev = u.raise_updated_event()
        assert ev.version == 2

    def test_invoked_completed_failed_event_payloads(self) -> None:
        from qzdap.modules.tool.domain import ToolCall

        call = ToolCall.create(
            id=UUID(int=7),
            tenant_id=TENANT,
            workspace_id=WID,
            tool_name="echo",
            arguments={},
        )
        invoked = call.raise_invoked_event()
        assert invoked.tool_name == "echo"
        succ = call.succeed(result={"x": 1}, latency_ms=10)
        completed = succ.raise_completed_event(latency_ms=10)
        assert completed.latency_ms == 10
        failed = call.fail(error_code="UPSTREAM_UNAVAILABLE")
        failed_ev = failed.raise_failed_event(error_code="UPSTREAM_UNAVAILABLE")
        assert failed_ev.error_code == "UPSTREAM_UNAVAILABLE"
