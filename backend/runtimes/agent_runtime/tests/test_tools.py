"""Tests for tools/registry.py (§13.3 / §5.8)."""

from __future__ import annotations

import pytest
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from qzdap_agent_runtime.ports import ActorContext, ToolMeta, ToolRegistry
from qzdap_agent_runtime.tools import InMemoryToolRegistry, from_langchain_tool


# ---------------------------------------------------------------------------
# Fixtures: LangChain @tool 定义
# ---------------------------------------------------------------------------


class _SearchArgs(BaseModel):
    query: str = Field(description="search query")
    top_k: int = Field(default=5, description="top k results")


@tool("search_kb", args_schema=_SearchArgs)
def _search_kb(query: str, top_k: int = 5) -> str:
    """search knowledge base for query."""
    return f"results for {query} (top {top_k})"


@tool("send_email", args_schema=_SearchArgs)
def _send_email(query: str, top_k: int = 5) -> str:
    """send email (write side effect)."""
    return f"sent: {query}"


# ---------------------------------------------------------------------------
# InMemoryToolRegistry
# ---------------------------------------------------------------------------


def test_registry_satisfies_protocol() -> None:
    assert isinstance(InMemoryToolRegistry(), ToolRegistry)


class TestInMemoryToolRegistry:
    def test_register_and_get(self) -> None:
        reg = InMemoryToolRegistry()
        meta = ToolMeta(
            name="x", description="x", args_schema=_SearchArgs,
            risk="low", requires_approval=False,
            timeout_ms=1000, max_retries=1, backoff_ms=100,
            idempotent=True, side_effect=False,
        )
        reg.register(meta, lambda: None)
        got_meta, got_tool = reg.get("x")
        assert got_meta.name == "x"

    def test_get_unknown_raises_keyerror(self) -> None:
        reg = InMemoryToolRegistry()
        with pytest.raises(KeyError):
            reg.get("missing")

    def test_register_must_be_toolmeta(self) -> None:
        reg = InMemoryToolRegistry()
        with pytest.raises(TypeError):
            reg.register({"name": "x"}, lambda: None)  # type: ignore[arg-type]

    def test_register_none_tool_raises(self) -> None:
        reg = InMemoryToolRegistry()
        meta = ToolMeta(
            name="x", description="x", args_schema=_SearchArgs,
            risk="low", requires_approval=False,
            timeout_ms=1000, max_retries=1, backoff_ms=100,
            idempotent=True, side_effect=False,
        )
        with pytest.raises(ValueError):
            reg.register(meta, None)

    def test_schemas_for_low_risk_visible_to_all(self) -> None:
        """low risk 工具所有 actor 可见。"""
        reg = InMemoryToolRegistry()
        reg.register(_to_meta(_search_kb, risk="low"), _search_kb)
        schemas = reg.schemas_for(ActorContext("u-1", "t-1", "w-1", roles=()))
        names = [s["name"] for s in schemas]
        assert "search_kb" in names

    def test_schemas_for_high_risk_requires_admin(self) -> None:
        """high risk 工具必须 actor.roles 含 admin/developer。"""
        reg = InMemoryToolRegistry()
        reg.register(_to_meta(_send_email, risk="high", requires_approval=True), _send_email)
        # 普通用户看不到
        user_schemas = reg.schemas_for(ActorContext("u-1", "t-1", "w-1", roles=()))
        assert "send_email" not in [s["name"] for s in user_schemas]
        # admin 看到
        admin_schemas = reg.schemas_for(ActorContext("u-1", "t-1", "w-1", roles=("admin",)))
        assert "send_email" in [s["name"] for s in admin_schemas]

    def test_list_by_risk(self) -> None:
        reg = InMemoryToolRegistry()
        reg.register(_to_meta(_search_kb, risk="low"), _search_kb)
        reg.register(_to_meta(_send_email, risk="high"), _send_email)
        assert "search_kb" in reg.list_by_risk("low")
        assert "send_email" in reg.list_by_risk("high")
        assert "search_kb" not in reg.list_by_risk("high")


# ---------------------------------------------------------------------------
# from_langchain_tool: ToolMeta 字段映射
# ---------------------------------------------------------------------------


class TestFromLangChainTool:
    def test_extracts_name_description(self) -> None:
        meta = from_langchain_tool(_search_kb)
        assert meta.name == "search_kb"
        assert "search knowledge base" in meta.description.lower()

    def test_args_schema_is_pydantic_class(self) -> None:
        meta = from_langchain_tool(_search_kb)
        assert meta.args_schema is _SearchArgs

    def test_default_risk_is_low(self) -> None:
        meta = from_langchain_tool(_search_kb)
        assert meta.risk == "low"

    def test_explicit_risk_override(self) -> None:
        meta = from_langchain_tool(_send_email, risk="high")
        assert meta.risk == "high"

    def test_requires_approval_default_false(self) -> None:
        meta = from_langchain_tool(_search_kb)
        assert meta.requires_approval is False

    def test_requires_approval_can_be_set(self) -> None:
        meta = from_langchain_tool(_send_email, requires_approval=True)
        assert meta.requires_approval is True

    def test_invalid_risk_string_falls_back_to_medium(self) -> None:
        meta = from_langchain_tool(_search_kb, risk="bogus")  # type: ignore[arg-type]
        assert meta.risk == "medium"

    def test_max_cost_usd_default_none(self) -> None:
        meta = from_langchain_tool(_search_kb)
        assert meta.max_cost_usd is None

    def test_max_cost_usd_set(self) -> None:
        meta = from_langchain_tool(_search_kb, max_cost_usd=0.05)
        assert meta.max_cost_usd == 0.05

    def test_policy_id_default_none(self) -> None:
        meta = from_langchain_tool(_search_kb)
        assert meta.policy_id is None

    def test_policy_id_set(self) -> None:
        meta = from_langchain_tool(_send_email, policy_id="pol-pii-outbound")
        assert meta.policy_id == "pol-pii-outbound"

    def test_tool_without_name_raises(self) -> None:
        class _NoName:
            description = "no name"
        with pytest.raises(ValueError):
            from_langchain_tool(_NoName())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 集成：registry 接受 from_langchain_tool 的产物
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_register_langchain_tool_full_flow(self) -> None:
        """§13.3：@tool → from_langchain_tool → InMemoryToolRegistry 完整链路。"""
        reg = InMemoryToolRegistry()
        meta = from_langchain_tool(
            _search_kb,
            risk="low",
            timeout_ms=2000,
            max_retries=3,
            idempotent=True,
        )
        reg.register(meta, _search_kb)
        got_meta, got_tool = reg.get("search_kb")
        assert got_meta.timeout_ms == 2000
        assert got_meta.max_retries == 3
        assert got_meta.idempotent is True
        # 真实调用验证 schema 对齐
        result = got_tool.invoke({"query": "LangGraph", "top_k": 3})  # type: ignore[attr-defined]
        assert "LangGraph" in result

    def test_existing_v0_tool_migration(self) -> None:
        """§15 旧实现到新实现的迁移：v0 tool_service_adapter 中的工具可迁移。"""
        reg = InMemoryToolRegistry()
        # 模拟 §15 旧工具的迁移
        for lc_tool, risk, approval in [
            (_search_kb, "low", False),
            (_send_email, "high", True),
        ]:
            meta = from_langchain_tool(
                lc_tool, risk=risk, requires_approval=approval,
                timeout_ms=10_000, max_retries=3, side_effect=(risk == "high"),
            )
            reg.register(meta, lc_tool)

        assert "search_kb" in reg.list_by_risk("low")
        assert "send_email" in reg.list_by_risk("high")
        # admin 看到全部
        all_schemas = reg.schemas_for(ActorContext("u", "t", "w", roles=("admin",)))
        names = {s["name"] for s in all_schemas}
        assert names == {"search_kb", "send_email"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _to_meta(lc_tool, *, risk: str = "low", requires_approval: bool = False) -> ToolMeta:
    return from_langchain_tool(lc_tool, risk=risk, requires_approval=requires_approval)