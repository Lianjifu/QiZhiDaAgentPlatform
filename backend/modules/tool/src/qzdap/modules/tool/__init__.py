"""Tool module — registration, CRUD, MCP / OpenAPI / custom invocation, batch.

Public surface re-exports the most common domain types so route / service
callers can `from qzdap.modules.tool import Tool, ToolCall, ...`.
"""

from qzdap.modules.tool.application.services import ToolService
from qzdap.modules.tool.domain import (
    AuthConfig,
    AuthConfigType,
    SpecOperation,
    Tool,
    ToolCall,
    ToolProtocol,
)
from qzdap.modules.tool.domain.errors import (
    InvalidToolSpec,
    ToolAlreadyExists,
    ToolCallTimeout,
    ToolDisabled,
    ToolError,
    ToolNotFound,
    ToolVersionMismatch,
    UpstreamUnavailable,
)

__all__ = [
    "AuthConfig",
    "AuthConfigType",
    "InvalidToolSpec",
    "SpecOperation",
    "Tool",
    "ToolAlreadyExists",
    "ToolCall",
    "ToolCallTimeout",
    "ToolDisabled",
    "ToolError",
    "ToolNotFound",
    "ToolProtocol",
    "ToolService",
    "ToolVersionMismatch",
    "UpstreamUnavailable",
]
