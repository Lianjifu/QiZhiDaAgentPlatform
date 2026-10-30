"""Tool module domain types.

Domain code MUST NOT import any framework / ORM / transport. All I/O is
expressed through ports (defined in application/ports/).
"""

from qzdap.modules.tool.domain.entities import (
    AuthConfig,
    AuthConfigType,
    SpecOperation,
    Tool,
    ToolCall,
    ToolCallStatus,
    ToolProtocol,
)
from qzdap.modules.tool.domain.errors import (
    InvalidToolSpec,
    ToolAlreadyExists,
    ToolCallTimeout,
    ToolDisabled,
    ToolError,
    ToolExecutionInProgress,
    ToolIdempotencyConflict,
    ToolNotFound,
    ToolRateLimited,
    ToolVersionMismatch,
    UpstreamUnavailable,
)
from qzdap.modules.tool.domain.events import (
    ToolCompleted,
    ToolDeleted,
    ToolFailed,
    ToolInvoked,
    ToolRegistered,
    ToolUpdated,
)

__all__ = [
    "AuthConfig",
    "AuthConfigType",
    "InvalidToolSpec",
    "SpecOperation",
    "Tool",
    "ToolAlreadyExists",
    "ToolCall",
    "ToolCallStatus",
    "ToolCallTimeout",
    "ToolCompleted",
    "ToolDeleted",
    "ToolDisabled",
    "ToolError",
    "ToolExecutionInProgress",
    "ToolFailed",
    "ToolIdempotencyConflict",
    "ToolInvoked",
    "ToolNotFound",
    "ToolProtocol",
    "ToolRateLimited",
    "ToolRegistered",
    "ToolUpdated",
    "ToolVersionMismatch",
    "UpstreamUnavailable",
]
