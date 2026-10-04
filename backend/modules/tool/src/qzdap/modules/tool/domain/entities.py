"""Tool and ToolCall aggregates.

`Tool` is tenant-scoped, mutable-on-method-call (frozen dataclass + factory
+ state-transition methods). Persistence is the adapter's responsibility —
domain stays framework-free.

Three protocols (CUSTOM / OPENAPI / MCP) are unified on a single row; the
spec JSONB and a pre-computed `spec_operations` index carry whatever shape
the protocol needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from qzdap_schema.ids import TenantId, ToolCallId, ToolId, WorkspaceId

if TYPE_CHECKING:
    from qzdap.modules.tool.domain.events import (
        ToolCompleted,
        ToolDeleted,
        ToolFailed,
        ToolInvoked,
        ToolRegistered,
        ToolUpdated,
    )


class ToolProtocol(StrEnum):
    CUSTOM = "custom"
    OPENAPI = "openapi"
    MCP = "mcp"


class AuthConfigType(StrEnum):
    NONE = "none"
    BEARER = "bearer"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"


@dataclass(slots=True, frozen=True)
class AuthConfig:
    type: AuthConfigType
    secrets_ref: str | None = (
        None  # P5 secrets table reference; raw secrets never stored here
    )

    @classmethod
    def none(cls) -> AuthConfig:
        return cls(type=AuthConfigType.NONE, secrets_ref=None)


@dataclass(slots=True, frozen=True)
class SpecOperation:
    """One (method, path, operation_id) row from an OpenAPI spec.

    Pre-extracted at registration time so invocation is O(1)."""

    method: str  # GET / POST / PUT / DELETE / PATCH
    path: str  # /pets/{petId}
    operation_id: str  # getPetById


@dataclass(slots=True, frozen=True)
class Tool:
    id: ToolId
    tenant_id: TenantId
    workspace_id: WorkspaceId
    name: str
    description: str
    protocol: ToolProtocol
    spec: dict
    spec_operations: list[SpecOperation]
    auth_config: AuthConfig | None
    rate_limit_per_minute: int | None
    enabled: bool
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        id: ToolId,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        name: str,
        description: str,
        protocol: ToolProtocol,
        spec: dict,
        spec_operations: list[SpecOperation] | None = None,
        auth_config: AuthConfig | None = None,
        rate_limit_per_minute: int | None = None,
        enabled: bool = True,
    ) -> Tool:
        if not name or len(name) > 128:
            raise ValueError(f"invalid name: {name!r} (must be non-empty, <=128 chars)")
        if (
            rate_limit_per_minute is not None
            and not 1 <= rate_limit_per_minute <= 100_000
        ):
            raise ValueError("rate_limit_per_minute must be between 1 and 100000")
        return cls(
            id=id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name,
            description=description,
            protocol=protocol,
            spec=dict(spec),
            spec_operations=list(spec_operations or []),
            auth_config=auth_config,
            rate_limit_per_minute=rate_limit_per_minute,
            enabled=enabled,
            version=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    def update(
        self,
        *,
        description: str | None = None,
        spec: dict | None = None,
        spec_operations: list[SpecOperation] | None = None,
        auth_config: AuthConfig | None = None,
        clear_auth: bool = False,
        rate_limit_per_minute: int | None = None,
        clear_rate_limit: bool = False,
        enabled: bool | None = None,
    ) -> Tool:
        """Return a new Tool with selected fields replaced. Version bumps +1."""
        if (
            rate_limit_per_minute is not None
            and not 1 <= rate_limit_per_minute <= 100_000
        ):
            raise ValueError("rate_limit_per_minute must be between 1 and 100000")
        new_spec = dict(self.spec) if spec is None else dict(spec)
        new_ops = (
            self.spec_operations if spec_operations is None else list(spec_operations)
        )
        if clear_auth:
            new_auth: AuthConfig | None = None
        elif auth_config is not None:
            new_auth = auth_config
        else:
            new_auth = self.auth_config
        if clear_rate_limit:
            new_rl: int | None = None
        elif rate_limit_per_minute is not None:
            new_rl = rate_limit_per_minute
        else:
            new_rl = self.rate_limit_per_minute
        return type(self)(
            id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            name=self.name,
            description=self.description if description is None else description,
            protocol=self.protocol,
            spec=new_spec,
            spec_operations=new_ops,
            auth_config=new_auth,
            rate_limit_per_minute=new_rl,
            enabled=self.enabled if enabled is None else enabled,
            version=self.version + 1,
            created_at=self.created_at,
            updated_at=datetime.now(UTC),
        )

    def disable(self) -> Tool:
        return self.update(enabled=False)

    @staticmethod
    def extract_operations(
        *, protocol: ToolProtocol, spec: dict
    ) -> list[SpecOperation]:
        """Pre-extract operation tables from a registration spec.

        Raises `InvalidToolSpec` on malformed input so the use case can map
        to 422."""
        from qzdap.modules.tool.domain.errors import InvalidToolSpec

        if protocol is ToolProtocol.OPENAPI:
            paths = spec.get("paths")
            if not isinstance(paths, dict):
                raise InvalidToolSpec(
                    "openapi spec must contain a 'paths' object",
                    code="INVALID_TOOL_SPEC",
                )
            ops: list[SpecOperation] = []
            http_methods = {"get", "post", "put", "delete", "patch"}
            for path, methods in paths.items():
                if not isinstance(methods, dict):
                    raise InvalidToolSpec(
                        f"openapi paths[{path!r}] must be an object",
                        code="INVALID_TOOL_SPEC",
                    )
                for method, op in methods.items():
                    if method.lower() not in http_methods:
                        continue
                    if not isinstance(op, dict):
                        continue
                    op_id = op.get("operationId") or f"{method.lower()}_{path}"
                    ops.append(
                        SpecOperation(
                            method=method.upper(),
                            path=str(path),
                            operation_id=str(op_id),
                        )
                    )
            return ops
        if protocol is ToolProtocol.MCP:
            server_url = spec.get("server_url")
            if not isinstance(server_url, str) or not server_url:
                raise InvalidToolSpec(
                    "mcp spec must contain a non-empty 'server_url'",
                    code="INVALID_TOOL_SPEC",
                )
            mcp_tool_name = spec.get("mcp_tool_name")
            if not isinstance(mcp_tool_name, str) or not mcp_tool_name:
                raise InvalidToolSpec(
                    "mcp spec must contain a non-empty 'mcp_tool_name'",
                    code="INVALID_TOOL_SPEC",
                )
            # MCP exposes a single tool per registration row.
            return [
                SpecOperation(
                    method="POST",
                    path="/",
                    operation_id=mcp_tool_name,
                )
            ]
        if protocol is ToolProtocol.CUSTOM:
            return []
        raise InvalidToolSpec(
            f"unsupported protocol {protocol!r}",
            code="INVALID_TOOL_SPEC",
        )

    def raise_registered_event(self) -> ToolRegistered:
        from qzdap.modules.tool.domain.events import ToolRegistered

        return ToolRegistered(
            tool_id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            name=self.name,
            protocol=self.protocol.value,
        )

    def raise_updated_event(self) -> ToolUpdated:
        from qzdap.modules.tool.domain.events import ToolUpdated

        return ToolUpdated(
            tool_id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            name=self.name,
            version=self.version,
        )

    def raise_deleted_event(self) -> ToolDeleted:
        from qzdap.modules.tool.domain.events import ToolDeleted

        return ToolDeleted(
            tool_id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            name=self.name,
        )


class ToolCallStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(slots=True, frozen=True)
class ToolCall:
    id: ToolCallId
    tenant_id: TenantId
    workspace_id: WorkspaceId
    tool_name: str
    arguments: dict
    result: dict | None
    error_code: str | None
    status: ToolCallStatus
    started_at: datetime
    finished_at: datetime | None
    latency_ms: int | None

    @classmethod
    def create(
        cls,
        *,
        id: ToolCallId,
        tenant_id: TenantId,
        workspace_id: WorkspaceId,
        tool_name: str,
        arguments: dict,
    ) -> ToolCall:
        return cls(
            id=id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            tool_name=tool_name,
            arguments=dict(arguments),
            result=None,
            error_code=None,
            status=ToolCallStatus.RUNNING,
            started_at=datetime.now(UTC),
            finished_at=None,
            latency_ms=None,
        )

    def succeed(self, *, result: dict, latency_ms: int) -> ToolCall:
        return type(self)(
            id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            tool_name=self.tool_name,
            arguments=self.arguments,
            result=dict(result),
            error_code=None,
            status=ToolCallStatus.SUCCEEDED,
            started_at=self.started_at,
            finished_at=datetime.now(UTC),
            latency_ms=latency_ms,
        )

    def fail(self, *, error_code: str, latency_ms: int | None = None) -> ToolCall:
        return type(self)(
            id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            tool_name=self.tool_name,
            arguments=self.arguments,
            result=None,
            error_code=error_code,
            status=ToolCallStatus.FAILED,
            started_at=self.started_at,
            finished_at=datetime.now(UTC),
            latency_ms=latency_ms,
        )

    def raise_invoked_event(self) -> ToolInvoked:
        from qzdap.modules.tool.domain.events import ToolInvoked

        return ToolInvoked(
            call_id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            tool_name=self.tool_name,
        )

    def raise_completed_event(self, *, latency_ms: int) -> ToolCompleted:
        from qzdap.modules.tool.domain.events import ToolCompleted

        return ToolCompleted(
            call_id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            tool_name=self.tool_name,
            latency_ms=latency_ms,
        )

    def raise_failed_event(self, *, error_code: str) -> ToolFailed:
        from qzdap.modules.tool.domain.events import ToolFailed

        return ToolFailed(
            call_id=self.id,
            tenant_id=self.tenant_id,
            workspace_id=self.workspace_id,
            tool_name=self.tool_name,
            error_code=error_code,
        )
