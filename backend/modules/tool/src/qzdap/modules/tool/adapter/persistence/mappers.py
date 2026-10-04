"""ORM ↔ domain mappers for tool + tool_call."""

from __future__ import annotations

from datetime import UTC, datetime

from qzdap_schema.ids import TenantId, ToolCallId, ToolId, WorkspaceId

from qzdap.modules.tool.adapter.persistence.models import ToolCallORM, ToolORM
from qzdap.modules.tool.domain import (
    AuthConfig,
    AuthConfigType,
    SpecOperation,
    Tool,
    ToolCall,
    ToolCallStatus,
    ToolProtocol,
)


def _to_auth_config(raw: dict | None) -> AuthConfig | None:
    if raw is None:
        return None
    type_str = raw.get("type", "none")
    try:
        type_ = AuthConfigType(type_str)
    except ValueError:
        type_ = AuthConfigType.NONE
    return AuthConfig(
        type=type_,
        secrets_ref=raw.get("secrets_ref"),
    )


def _auth_config_to_dict(auth: AuthConfig | None) -> dict | None:
    if auth is None:
        return None
    return {"type": auth.type.value, "secrets_ref": auth.secrets_ref}


def _to_spec_operations(raw: list | None) -> list[SpecOperation]:
    out: list[SpecOperation] = []
    for row in raw or []:
        if not isinstance(row, dict):
            continue
        method = str(row.get("method", ""))
        path = str(row.get("path", ""))
        op_id = str(row.get("operation_id", ""))
        if not (method and path and op_id):
            continue
        out.append(SpecOperation(method=method, path=path, operation_id=op_id))
    return out


def _spec_operations_to_list(ops: list[SpecOperation]) -> list[dict]:
    return [
        {"method": o.method, "path": o.path, "operation_id": o.operation_id}
        for o in ops
    ]


def tool_orm_to_domain(o: ToolORM) -> Tool:
    return Tool(
        id=ToolId(o.id),
        tenant_id=TenantId(o.tenant_id),
        workspace_id=WorkspaceId(o.workspace_id),
        name=o.name,
        description=o.description,
        protocol=ToolProtocol(o.protocol),
        spec=dict(o.spec or {}),
        spec_operations=_to_spec_operations(o.spec_operations),
        auth_config=_to_auth_config(o.auth_config),
        rate_limit_per_minute=o.rate_limit_per_minute,
        enabled=o.enabled,
        version=o.version,
        created_at=o.created_at,
        updated_at=o.updated_at,
    )


def tool_domain_to_orm(t: Tool) -> ToolORM:
    return ToolORM(
        id=t.id,
        tenant_id=t.tenant_id,
        workspace_id=t.workspace_id,
        name=t.name,
        description=t.description,
        protocol=t.protocol.value,
        spec=dict(t.spec),
        spec_operations=_spec_operations_to_list(t.spec_operations),
        auth_config=_auth_config_to_dict(t.auth_config),
        rate_limit_per_minute=t.rate_limit_per_minute,
        enabled=t.enabled,
        version=t.version,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


def tool_call_orm_to_domain(o: ToolCallORM) -> ToolCall:
    finished = o.finished_at
    return ToolCall(
        id=ToolCallId(o.id),
        tenant_id=TenantId(o.tenant_id),
        workspace_id=WorkspaceId(o.workspace_id),
        tool_name=o.tool_name,
        arguments=dict(o.arguments or {}),
        result=dict(o.result) if o.result is not None else None,
        error_code=o.error_code,
        status=ToolCallStatus(o.status),
        started_at=o.started_at,
        finished_at=finished,
        latency_ms=o.latency_ms,
    )


def tool_call_domain_to_orm(c: ToolCall) -> ToolCallORM:
    return ToolCallORM(
        id=c.id,
        tenant_id=c.tenant_id,
        workspace_id=c.workspace_id,
        tool_name=c.tool_name,
        arguments=dict(c.arguments),
        result=dict(c.result) if c.result is not None else None,
        error_code=c.error_code,
        status=c.status.value,
        started_at=c.started_at,
        finished_at=c.finished_at,
        latency_ms=c.latency_ms,
    )


__all__ = [
    "tool_call_domain_to_orm",
    "tool_call_orm_to_domain",
    "tool_domain_to_orm",
    "tool_orm_to_domain",
]


def _ensure_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    # Postgres TIMESTAMPTZ returns aware datetimes already; this is defensive.
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt
