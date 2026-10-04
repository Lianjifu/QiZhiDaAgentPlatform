"""domain ↔ DTO mappers for the tool module HTTP layer."""

from __future__ import annotations

from qzdap.modules.tool.adapter.http.dto import (
    AuthConfigDTO,
    SpecOperationDTO,
    ToolResponse,
)
from qzdap.modules.tool.domain import AuthConfig, AuthConfigType, Tool


def auth_config_to_dto(auth: AuthConfig | None) -> AuthConfigDTO | None:
    if auth is None:
        return None
    return AuthConfigDTO(type=auth.type.value, secrets_ref=auth.secrets_ref)


def auth_config_from_dto(dto: AuthConfigDTO | None) -> AuthConfig | None:
    if dto is None:
        return None
    return AuthConfig(type=AuthConfigType(dto.type), secrets_ref=dto.secrets_ref)


def tool_to_dto(tool: Tool) -> ToolResponse:
    return ToolResponse(
        id=str(tool.id),
        tenant_id=str(tool.tenant_id),
        workspace_id=str(tool.workspace_id),
        name=tool.name,
        description=tool.description,
        protocol=tool.protocol.value,
        spec=dict(tool.spec),
        spec_operations=[
            SpecOperationDTO(
                method=op.method,  # type: ignore[arg-type]
                path=op.path,
                operation_id=op.operation_id,
            )
            for op in tool.spec_operations
        ],
        auth_config=auth_config_to_dto(tool.auth_config),
        rate_limit_per_minute=tool.rate_limit_per_minute,
        enabled=tool.enabled,
        version=tool.version,
        created_at=tool.created_at.isoformat(),
        updated_at=tool.updated_at.isoformat(),
    )


__all__ = [
    "auth_config_from_dto",
    "auth_config_to_dto",
    "tool_to_dto",
]
