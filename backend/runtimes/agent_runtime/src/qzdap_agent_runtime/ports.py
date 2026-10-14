"""Port 协议 — runtime 与外部能力域的稳定边界。

§3.1 决议：runtime library 向上只暴露 SessionEngine / ChannelGateway
和端口协议。新 runtime 不得 import FastAPI Request / SQLAlchemy model /
具体 channel adapter；通过 Protocol 与外部能力对接。

本文件聚合下列协议：

- ToolRegistry / ToolMeta（§13.3）
- LayeredMemory / RecallHit（§13.4）
- PolicyGuard / ApprovalDecision（§5.7）
- ActorContext（来自 qzdap_vault 的最小接口）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Tool registry（§13.3）
# ---------------------------------------------------------------------------


Risk = Literal["low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class ToolMeta:
    """Tool 注册表元数据：治理/路由/观测/执行只读此表。"""

    name: str
    description: str
    args_schema: type  # Pydantic BaseModel subclass
    risk: Risk
    requires_approval: bool
    timeout_ms: int
    max_retries: int
    backoff_ms: int
    idempotent: bool
    side_effect: bool
    policy_id: str | None = None
    max_cost_usd: float | None = None


@runtime_checkable
class ToolRegistry(Protocol):
    """§13.3 ToolRegistry Protocol — 注册表元数据 + tools 集合。"""

    def register(self, meta: ToolMeta, tool: Any) -> None: ...

    def get(self, name: str) -> tuple[ToolMeta, Any]: ...

    def schemas_for(self, actor: "ActorContext") -> list[dict[str, Any]]: ...

    def list_by_risk(self, risk: Risk) -> list[str]: ...


# ---------------------------------------------------------------------------
# Memory / Knowledge（§13.4）
# ---------------------------------------------------------------------------


RecallLayer = Literal["l1", "l2", "l3"]


@dataclass(frozen=True, slots=True)
class RecallHit:
    """§13.4 统一召回结果。L3 必须携带 knowledge_asset_id / chunk_id。"""

    layer: RecallLayer
    content: str
    score: float
    source_id: str
    citation: str | None
    metadata: dict[str, Any]


@runtime_checkable
class LayeredMemory(Protocol):
    """§13.4 LayeredMemory — recall_memory + recall_knowledge 拆分。"""

    async def recall_memory(
        self,
        *,
        query: str,
        tenant_id: str,
        workspace_id: str,
        user_id: str,
        session_id: str,
        policy: dict[str, Any],
    ) -> list[RecallHit]: ...

    async def recall_knowledge(
        self,
        *,
        query: str,
        tenant_id: str,
        workspace_id: str,
        package_ids: tuple[str, ...] | None = None,
    ) -> list[RecallHit]: ...

    async def write_l1(self, event: dict[str, Any]) -> None: ...

    async def write_l2(self, fact: dict[str, Any]) -> None: ...


# ---------------------------------------------------------------------------
# Governance / PolicyGuard（§5.7）
# ---------------------------------------------------------------------------


ApprovalDecision = Literal["allow", "approve_required", "deny"]


@dataclass(frozen=True, slots=True)
class ActorContext:
    """调用者身份最小接口（避免 runtime 反向 import qzdap_vault）。"""

    actor_id: str
    tenant_id: str
    workspace_id: str
    roles: tuple[str, ...] = ()


@runtime_checkable
class PolicyGuard(Protocol):
    """§5.7 PolicyGuard — 工具执行前的统一治理端口。"""

    async def decide(
        self,
        *,
        actor: ActorContext,
        tool_call_id: str,
        tool_meta: ToolMeta,
        arguments: dict[str, Any],
    ) -> tuple[ApprovalDecision, str | None]:
        """返回 (decision, approval_id_or_reason)。"""
        ...


# ---------------------------------------------------------------------------
# Execution（§13.3 / §5.8）
# ---------------------------------------------------------------------------


@runtime_checkable
class ToolExecutor(Protocol):
    """§5.8 统一执行器：retry / timeout / idempotency / 熔断 / 降级。"""

    async def execute(
        self,
        *,
        tool_call_id: str,
        tool: Any,
        arguments: dict[str, Any],
        meta: ToolMeta,
        turn_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]: ...


__all__ = [
    "ActorContext",
    "ApprovalDecision",
    "LayeredMemory",
    "PolicyGuard",
    "RecallHit",
    "RecallLayer",
    "Risk",
    "ToolExecutor",
    "ToolMeta",
    "ToolRegistry",
]