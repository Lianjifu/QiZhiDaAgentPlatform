"""Tests for ports protocols (§13.3 / §13.4 / §5.7 / §5.8)。

Protocol 不强制运行时验证，但 @runtime_checkable 允许 isinstance。
这里验证 duck-typing 边界 + ToolMeta dataclass 字段完整性。
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pytest
from pydantic import BaseModel

from qzdap_agent_runtime.ports import (
    ActorContext,
    ApprovalDecision,
    LayeredMemory,
    PolicyGuard,
    RecallHit,
    Risk,
    ToolExecutor,
    ToolMeta,
    ToolRegistry,
)


# ---------------------------------------------------------------------------
# ToolMeta
# ---------------------------------------------------------------------------


class _Args(BaseModel):
    query: str


def test_tool_meta_required_fields() -> None:
    meta = ToolMeta(
        name="search_kb",
        description="search knowledge base",
        args_schema=_Args,
        risk="low",
        requires_approval=False,
        timeout_ms=5000,
        max_retries=3,
        backoff_ms=500,
        idempotent=True,
        side_effect=False,
    )
    d = asdict(meta)
    assert d["name"] == "search_kb"
    assert d["args_schema"] is _Args
    assert d["risk"] in ("low", "medium", "high")


def test_tool_meta_with_policy_and_cost() -> None:
    meta = ToolMeta(
        name="send_email",
        description="send outbound email",
        args_schema=_Args,
        risk="high",
        requires_approval=True,
        timeout_ms=10_000,
        max_retries=1,
        backoff_ms=1000,
        idempotent=False,
        side_effect=True,
        policy_id="pol-pii-outbound",
        max_cost_usd=0.10,
    )
    assert meta.policy_id == "pol-pii-outbound"
    assert meta.max_cost_usd == 0.10


def test_tool_meta_is_frozen() -> None:
    """ToolMeta 必须不可变。"""
    meta = ToolMeta(
        name="x",
        description="x",
        args_schema=_Args,
        risk="low",
        requires_approval=False,
        timeout_ms=1000,
        max_retries=1,
        backoff_ms=100,
        idempotent=True,
        side_effect=False,
    )
    try:
        meta.name = "y"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("ToolMeta should be frozen")


# ---------------------------------------------------------------------------
# RecallHit
# ---------------------------------------------------------------------------


def test_recall_hit_construction() -> None:
    h = RecallHit(
        layer="l3",
        content="chunk text",
        score=0.92,
        source_id="k-1",
        citation="doc://k-1#chunk-2",
        metadata={"asset_id": "asset-1", "chunk_id": "chunk-2"},
    )
    assert h.layer == "l3"
    assert h.score == 0.92


# ---------------------------------------------------------------------------
# ActorContext
# ---------------------------------------------------------------------------


def test_actor_context_default_roles() -> None:
    a = ActorContext(actor_id="u-1", tenant_id="t-1", workspace_id="w-1")
    assert a.roles == ()


def test_actor_context_with_roles() -> None:
    a = ActorContext(
        actor_id="u-1", tenant_id="t-1", workspace_id="w-1",
        roles=("admin", "developer"),
    )
    assert "admin" in a.roles


# ---------------------------------------------------------------------------
# Protocol duck-typing 验证（runtime_checkable）
# ---------------------------------------------------------------------------


class _FakeToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolMeta, Any]] = {}

    def register(self, meta: ToolMeta, tool: Any) -> None:
        self._tools[meta.name] = (meta, tool)

    def get(self, name: str) -> tuple[ToolMeta, Any]:
        return self._tools[name]

    def schemas_for(self, actor: ActorContext) -> list[dict[str, Any]]:
        return []

    def list_by_risk(self, risk: Risk) -> list[str]:
        return [n for n, (m, _) in self._tools.items() if m.risk == risk]


def test_tool_registry_protocol_duck_typing() -> None:
    reg = _FakeToolRegistry()
    meta = ToolMeta(
        name="x", description="x", args_schema=_Args,
        risk="low", requires_approval=False,
        timeout_ms=1000, max_retries=1, backoff_ms=100,
        idempotent=True, side_effect=False,
    )
    reg.register(meta, lambda: None)
    assert isinstance(reg, ToolRegistry)
    assert "x" in reg.list_by_risk("low")


class _FakePolicyGuard:
    async def decide(
        self,
        *,
        actor: ActorContext,
        tool_call_id: str,
        tool_meta: ToolMeta,
        arguments: dict[str, Any],
    ) -> tuple[ApprovalDecision, str | None]:
        if tool_meta.requires_approval:
            return ("approve_required", "apr-1")
        return ("allow", None)


def test_policy_guard_protocol_duck_typing() -> None:
    import asyncio
    guard = _FakePolicyGuard()
    assert isinstance(guard, PolicyGuard)
    meta = ToolMeta(
        name="send_email", description="x", args_schema=_Args,
        risk="high", requires_approval=True,
        timeout_ms=1000, max_retries=1, backoff_ms=100,
        idempotent=False, side_effect=True,
    )
    actor = ActorContext(actor_id="u", tenant_id="t", workspace_id="w")
    decision, approval_id = asyncio.run(
        guard.decide(actor=actor, tool_call_id="tc-1", tool_meta=meta, arguments={})
    )
    assert decision == "approve_required"
    assert approval_id == "apr-1"


class _FakeLayeredMemory:
    async def recall_memory(self, **kwargs: Any) -> list[RecallHit]:
        return []

    async def recall_knowledge(self, **kwargs: Any) -> list[RecallHit]:
        return []

    async def write_l1(self, event: dict[str, Any]) -> None:
        return None

    async def write_l2(self, fact: dict[str, Any]) -> None:
        return None


def test_layered_memory_protocol_duck_typing() -> None:
    mem = _FakeLayeredMemory()
    assert isinstance(mem, LayeredMemory)


class _FakeToolExecutor:
    async def execute(
        self,
        *,
        tool_call_id: str,
        tool: Any,
        arguments: dict[str, Any],
        meta: ToolMeta,
        turn_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return {"ok": True}


def test_tool_executor_protocol_duck_typing() -> None:
    exe = _FakeToolExecutor()
    assert isinstance(exe, ToolExecutor)


# ---------------------------------------------------------------------------
# 缺失方法必须破坏 duck-typing
# ---------------------------------------------------------------------------


class _BrokenRegistry:
    def register(self, meta: ToolMeta, tool: Any) -> None:
        pass

    # 缺少 get / schemas_for / list_by_risk


def test_broken_registry_not_instanceof_protocol() -> None:
    """缺方法的实现不能通过 isinstance(Protocol) 验证。"""
    assert not isinstance(_BrokenRegistry(), ToolRegistry)