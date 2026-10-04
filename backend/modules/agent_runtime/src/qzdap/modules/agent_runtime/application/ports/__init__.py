"""Application-layer ports (interfaces) for the agent runtime.

The adapter package implements these; use cases depend ONLY on ports.
Forward-compat `Protocol` stubs (Tool / Skill / Memory / Knowledge) are
declared so P2+ can plug in concrete adapters without touching the turn
runner.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Protocol
from uuid import UUID

from qzdap_kernel.events import DomainEvent
from qzdap_llm.client import ChatRequest, LLMChunk
from qzdap_schema.ids import ModelId

from qzdap.modules.agent_runtime.domain import Session, Turn


class SessionRepository(ABC):
    @abstractmethod
    async def add(self, session: Session) -> None: ...
    @abstractmethod
    async def get(self, session_id: UUID) -> Session | None: ...
    @abstractmethod
    async def update(self, session: Session) -> None: ...
    @abstractmethod
    async def list_for_owner(
        self, owner_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Session]: ...


class TurnRepository(ABC):
    @abstractmethod
    async def add(self, turn: Turn) -> None: ...
    @abstractmethod
    async def get(self, turn_id: UUID) -> Turn | None: ...


class LLMPort(ABC):
    """Async-iterator facade over `qzdap_llm.LLMClient.stream`.

    When ``model_id`` is supplied (P6), the adapter delegates to
    ``ModelService.invoke`` for per-tenant routing, quota tracking, and
    credential decryption. When ``model_id`` is ``None``, the legacy
    default path is used (P0–P5 callers stay unchanged).
    """

    @abstractmethod
    def stream(
        self,
        req: ChatRequest,
        *,
        model_id: ModelId | None = None,
    ) -> AsyncIterator[LLMChunk]: ...


class EventPublisher(ABC):
    """Wraps the messaging bus for application-layer emission.

    The use case passes a `DomainEvent`; the publisher wraps it into an
    `EventEnvelope` with the request's tenant/workspace/trace scope."""

    @abstractmethod
    async def publish(
        self,
        event: DomainEvent,
        *,
        tenant_id: UUID,
        workspace_id: UUID | None,
        trace_id: str | None = None,
    ) -> None: ...


# ── Forward-compat ports (Protocol stubs; concrete adapters land in P2/P3/P4) ──


class ToolPort(Protocol):
    async def invoke(
        self, *, call_id: UUID, tool_name: str, arguments: dict
    ) -> dict: ...


class MemoryPort(Protocol):
    """P4: recall relevant memories before constructing the system prompt.

    Returns a list of dicts with at least `id`, `content`, `score` keys.
    Concrete adapter: ``MemoryServiceAdapter`` wraps ``MemoryService``.
    """

    async def recall(
        self, *, tenant_id: UUID, workspace_id: UUID, query: str, top_k: int
    ) -> list[dict]: ...

    async def write(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        content: str,
        metadata: dict | None = None,
    ) -> dict: ...


class SkillPort(Protocol):
    """Catalog skill invoke — runs published Skill.runtime in sandbox_runtime."""

    async def invoke(
        self,
        *,
        call_id: UUID,
        skill_name: str,
        arguments: dict,
        confirmed: bool = False,
    ) -> dict: ...

    async def list_executable(self) -> list[dict]: ...


class SandboxPort(Protocol):
    """Generic gVisor exec for the agent (`sandbox_exec` tool)."""

    async def exec(
        self,
        *,
        call_id: UUID,
        language: str,
        code: str,
        timeout_ms: int = 30_000,
    ) -> dict: ...


class KnowledgePort(Protocol):
    """P7: recall relevant knowledge chunks before constructing the
    system prompt. Returns a list of dicts with at least ``id``,
    ``asset_id``, ``package_id``, ``package_name``, ``asset_name``,
    ``content``, ``score``, ``ordinal`` keys.

    Concrete adapter: ``KnowledgeServiceAdapter`` wraps ``KnowledgeService``.
    The signature is intentionally tenant/workspace scoped so cross-tenant
    reads are impossible from the use case side.
    """

    async def search(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        query: str,
        top_k: int,
        package_ids: tuple[UUID, ...] = (),
    ) -> list[dict]: ...


class SubAgentPort(Protocol):
    """P7: orchestration-layer reverse-call into agent_runtime.

    The orchestration ``WorkflowExecutor`` invokes a sub-agent via this
    port without importing agent_runtime directly. Adapter:
    ``SubAgentAdapter`` drains ``RunTurnUseCase.execute`` until the
    ``DoneChunk`` and packages ``{final_message, turn_id, input_tokens,
    output_tokens}`` for the executor.
    """

    async def run_turn_to_completion(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        owner_id: UUID,
        agent_id: UUID,
        agent_version: str,
        user_input: str,
        model_override: str | None = None,
        timeout_seconds: int = 60,
    ) -> dict: ...


class PolicyPort(Protocol):
    """Approval + governance gate. P5; declared here so the use case can
    surface `ApprovalRequiredError` for gated actions."""

    async def evaluate_action(
        self, *, tenant_id: UUID, action: str, context: dict
    ) -> bool: ...
