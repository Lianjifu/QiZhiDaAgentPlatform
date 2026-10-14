"""Tests for Stage 4 PR C: PolicyGuard + governance/execute/route 节点接入。"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from qzdap_agent_runtime.execution import InMemoryToolExecutor
from qzdap_agent_runtime.governance import InMemoryPolicyGuard
from qzdap_agent_runtime.graph import nodes
from qzdap_agent_runtime.ports import ActorContext, ToolMeta
from qzdap_agent_runtime.tools import InMemoryToolRegistry, from_langchain_tool
from langchain_core.tools import tool


@pytest.fixture(autouse=True)
def _reset_deps():
    yield
    nodes.reset_default_dependencies()


# ---------------------------------------------------------------------------
# InMemoryPolicyGuard
# ---------------------------------------------------------------------------


def _meta(name: str, risk: str, requires_approval: bool = False, idempotent: bool = True) -> ToolMeta:
    class _Args(BaseModel):
        query: str = "x"

    return ToolMeta(
        name=name, description=name, args_schema=_Args,
        risk=risk, requires_approval=requires_approval,
        timeout_ms=1000, max_retries=1, backoff_ms=100,
        idempotent=idempotent, side_effect=False,
    )


class TestInMemoryPolicyGuard:
    async def test_low_risk_allows(self) -> None:
        guard = InMemoryPolicyGuard()
        meta = _meta("t", "low")
        decision, _ = await guard.decide(
            actor=ActorContext("u-1", "t-1", "w-1", roles=()),
            tool_call_id="tc-1", tool_meta=meta, arguments={},
        )
        assert decision == "allow"

    async def test_high_risk_requires_approval_for_normal_user(self) -> None:
        guard = InMemoryPolicyGuard()
        meta = _meta("send_email", "high")
        decision, approval_id = await guard.decide(
            actor=ActorContext("u-1", "t-1", "w-1", roles=()),
            tool_call_id="tc-1", tool_meta=meta, arguments={},
        )
        assert decision == "approve_required"
        assert approval_id == "apr-tc-1"

    async def test_high_risk_allows_admin(self) -> None:
        guard = InMemoryPolicyGuard()
        meta = _meta("send_email", "high")
        decision, _ = await guard.decide(
            actor=ActorContext("u-1", "t-1", "w-1", roles=("admin",)),
            tool_call_id="tc-1", tool_meta=meta, arguments={},
        )
        assert decision == "allow"

    async def test_low_risk_with_requires_approval(self) -> None:
        guard = InMemoryPolicyGuard()
        meta = _meta("t", "low", requires_approval=True)
        decision, _ = await guard.decide(
            actor=ActorContext("u-1", "t-1", "w-1", roles=()),
            tool_call_id="tc-1", tool_meta=meta, arguments={},
        )
        assert decision == "approve_required"

    async def test_developer_role_can_high_risk(self) -> None:
        guard = InMemoryPolicyGuard()
        meta = _meta("send_email", "high")
        decision, _ = await guard.decide(
            actor=ActorContext("u-1", "t-1", "w-1", roles=("developer",)),
            tool_call_id="tc-1", tool_meta=meta, arguments={},
        )
        assert decision == "allow"


# ---------------------------------------------------------------------------
# route 节点
# ---------------------------------------------------------------------------


class TestRouteNode:
    def test_passthrough_when_no_config(self) -> None:
        """未注入 agent_config + registry 时, 用默认 fake 配置 → SIMPLE_QA。"""
        out = nodes.route({
            "agent_id": "agt-1",
            "messages": [{"role": "user", "content": "hello"}],
        })
        assert out["route"]["task_kind"] == "SIMPLE_QA"
        assert out["route"]["deep_task"] is False

    def test_uses_heuristic_for_deep_research_keyword(self) -> None:
        """关键词 '研究' 触发 DEEP_RESEARCH → deep_task=True。"""
        nodes.set_default_agent_config(
            nodes.AgentRouteConfig(agent_id="agt-1", deep_research=False)
        )
        out = nodes.route({
            "agent_id": "agt-1",
            "messages": [{"role": "user", "content": "帮我研究 RAG"}],
        })
        assert out["route"]["task_kind"] == "DEEP_RESEARCH"
        assert out["route"]["deep_task"] is True

    def test_deep_research_flag_overrides_keyword(self) -> None:
        """agent.deep_research=true 必须覆盖关键词 (rule 1)。"""
        nodes.set_default_agent_config(
            nodes.AgentRouteConfig(agent_id="agt-1", deep_research=True)
        )
        out = nodes.route({
            "agent_id": "agt-1",
            "messages": [{"role": "user", "content": "hello world"}],
        })
        assert out["route"]["task_kind"] == "DEEP_RESEARCH"
        assert out["route"]["deep_task"] is True

    def test_simple_qa_for_short_messages(self) -> None:
        out = nodes.route({
            "agent_id": "agt-1",
            "messages": [{"role": "user", "content": "今天天气"}],
        })
        assert out["route"]["task_kind"] == "SIMPLE_QA"
        assert out["route"]["deep_task"] is False


# ---------------------------------------------------------------------------
# governance 节点
# ---------------------------------------------------------------------------


class TestGovernanceNode:
    def test_passthrough_when_no_policy(self) -> None:
        out = nodes.governance({
            "tool_calls": [{"tool_name": "x", "status": "pending"}],
        })
        assert out == {}

    def test_approve_required_writes_pending_approval(self) -> None:
        policy = InMemoryPolicyGuard()
        registry = InMemoryToolRegistry()
        meta = _meta("send_email", "high")
        def _send_email(query: str = "x") -> str:
            """send email"""
            return "sent"
        registry.register(meta, tool("send_email", args_schema=meta.args_schema)(_send_email))
        nodes.set_default_policy(policy)
        nodes.set_default_tool_registry(registry)
        out = nodes.governance({
            "tenant_id": "t-1", "workspace_id": "w-1",
            "tool_calls": [
                {"tool_call_id": "tc-1", "tool_name": "send_email", "status": "pending", "arguments": {}},
            ],
        })
        assert "pending_approval" in out
        pa = out["pending_approval"]
        assert pa["tool_call_id"] == "tc-1"
        assert pa["approval_id"] == "apr-tc-1"

    def test_low_risk_no_pending_approval(self) -> None:
        policy = InMemoryPolicyGuard()
        registry = InMemoryToolRegistry()
        meta = _meta("search_kb", "low")
        def _search_kb(query: str = "x") -> str:
            """search kb"""
            return "ok"
        registry.register(meta, tool("search_kb", args_schema=meta.args_schema)(_search_kb))
        nodes.set_default_policy(policy)
        nodes.set_default_tool_registry(registry)
        out = nodes.governance({
            "tool_calls": [
                {"tool_call_id": "tc-1", "tool_name": "search_kb", "status": "pending", "arguments": {}},
            ],
        })
        assert "pending_approval" not in out


# ---------------------------------------------------------------------------
# execute 节点
# ---------------------------------------------------------------------------


class TestExecuteNode:
    def test_passthrough_when_no_executor(self) -> None:
        out = nodes.execute({"tool_calls": [{"tool_name": "x", "status": "pending"}]})
        assert out == {}

    def test_runs_pending_tool_call(self) -> None:
        executor = InMemoryToolExecutor()
        registry = InMemoryToolRegistry()
        meta = _meta("search_kb", "low")
        def _search_kb(query: str = "x") -> str:
            """search kb"""
            return f"result:{query}"
        registry.register(meta, tool("search_kb", args_schema=meta.args_schema)(_search_kb))
        nodes.set_default_executor(executor)
        nodes.set_default_tool_registry(registry)
        out = nodes.execute({
            "turn_id": "t-1",
            "tool_calls": [
                {
                    "tool_call_id": "tc-1",
                    "tool_name": "search_kb",
                    "status": "pending",
                    "arguments": {"query": "hi"},
                },
            ],
        })
        results = out["tool_results"]
        assert len(results) == 1
        assert results[0]["content"] == "result:hi"
        assert results[0]["is_error"] is False

    def test_tool_failure_writes_error(self) -> None:
        executor = InMemoryToolExecutor()
        registry = InMemoryToolRegistry()
        meta = _meta("search_kb", "low", idempotent=False)
        def _search_kb(query: str = "x") -> str:
            """search kb"""
            raise RuntimeError("boom")
        registry.register(meta, tool("search_kb", args_schema=meta.args_schema)(_search_kb))
        nodes.set_default_executor(executor)
        nodes.set_default_tool_registry(registry)
        out = nodes.execute({
            "turn_id": "t-1",
            "tool_calls": [
                {
                    "tool_call_id": "tc-1",
                    "tool_name": "search_kb",
                    "status": "pending",
                    "arguments": {"query": "hi"},
                },
            ],
        })
        results = out["tool_results"]
        assert results[0]["is_error"] is True
        # errors 必须包含 TOOL_TIMEOUT (兜底错误码)
        assert any(e["error_code"] == "TOOL_TIMEOUT" for e in out.get("errors", []))

    def test_skips_non_pending_tool_calls(self) -> None:
        executor = InMemoryToolExecutor()
        registry = InMemoryToolRegistry()
        meta = _meta("search_kb", "low")
        def _search_kb(query: str = "x") -> str:
            """search kb"""
            return "ok"
        registry.register(meta, tool("search_kb", args_schema=meta.args_schema)(_search_kb))
        nodes.set_default_executor(executor)
        nodes.set_default_tool_registry(registry)
        out = nodes.execute({
            "turn_id": "t-1",
            "tool_calls": [
                {
                    "tool_call_id": "tc-1",
                    "tool_name": "search_kb",
                    "status": "succeeded",  # 跳过
                    "arguments": {"query": "hi"},
                },
            ],
        })
        assert out["tool_results"] == []