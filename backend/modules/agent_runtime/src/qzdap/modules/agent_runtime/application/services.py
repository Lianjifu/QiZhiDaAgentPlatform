"""Top-level agent runtime service — wires the use cases + ports for the
composition root.

The composition root instantiates this with concrete adapters; routes
instantiate use cases via `svc.run_turn()` etc.
"""

from __future__ import annotations

from dataclasses import dataclass

from qzdap.modules.agent_runtime.application.ports import (
    EventPublisher,
    KnowledgePort,
    LLMPort,
    MemoryPort,
    SandboxPort,
    SessionRepository,
    SkillPort,
    ToolPort,
    TurnRepository,
)
from qzdap.modules.agent_runtime.application.use_cases.close_session import (
    CloseSessionUseCase,
)
from qzdap.modules.agent_runtime.application.use_cases.create_session import (
    CreateSessionUseCase,
)
from qzdap.modules.agent_runtime.application.use_cases.get_session import (
    GetSessionUseCase,
)
from qzdap.modules.agent_runtime.application.use_cases.run_turn import (
    RunTurnUseCase,
)
from qzdap.modules.agent_runtime.application.use_cases.run_turn_to_completion import (
    RunTurnCompletionUseCase,
)


@dataclass(slots=True)
class AgentRuntimeService:
    sessions: SessionRepository
    turns: TurnRepository
    llm: LLMPort
    events: EventPublisher
    tool_port: ToolPort | None = None
    skill_port: SkillPort | None = None
    sandbox_port: SandboxPort | None = None
    memory_port: MemoryPort | None = None
    knowledge_port: KnowledgePort | None = None

    def create_session(self) -> CreateSessionUseCase:
        return CreateSessionUseCase(self.sessions, self.events)

    def close_session(self) -> CloseSessionUseCase:
        return CloseSessionUseCase(self.sessions, self.events)

    def get_session(self) -> GetSessionUseCase:
        return GetSessionUseCase(self.sessions)

    def run_turn(self) -> RunTurnUseCase:
        return RunTurnUseCase(
            self.sessions,
            self.turns,
            self.llm,
            self.events,
            tool_port=self.tool_port,
            skill_port=self.skill_port,
            sandbox_port=self.sandbox_port,
            memory_port=self.memory_port,
            knowledge_port=self.knowledge_port,
        )

    def run_turn_to_completion(self) -> RunTurnCompletionUseCase:
        return RunTurnCompletionUseCase(self.run_turn())
