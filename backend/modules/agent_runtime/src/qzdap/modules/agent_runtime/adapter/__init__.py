"""Adapter package marker.

`import qzdap.modules.agent_runtime.adapter` lets the composition root
discover concrete adapters (persistence / llm / events / http) without
listing each file.
"""

from qzdap.modules.agent_runtime.adapter.events import AgentRuntimeEventPublisher
from qzdap.modules.agent_runtime.adapter.llm import LLMPortAdapter
from qzdap.modules.agent_runtime.adapter.persistence import (
    SqlSessionRepository,
    SqlTurnRepository,
)

__all__ = [
    "AgentRuntimeEventPublisher",
    "LLMPortAdapter",
    "SqlSessionRepository",
    "SqlTurnRepository",
]
