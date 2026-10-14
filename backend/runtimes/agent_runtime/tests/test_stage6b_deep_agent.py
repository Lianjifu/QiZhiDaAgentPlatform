"""Tests for Stage 6b: DeepAgentFactory + deep_agent_plan + subagent 节点."""

from __future__ import annotations

import pytest

from qzdap_agent_runtime.graph import (
    DEEP_AGENT_BUDGET_EXCEEDED_ERROR_CODE,
    DEEP_AGENT_FAILED_ERROR_CODE,
    DeepAgent,
    DeepAgentBudgetExceeded,
    DeepAgentConfig,
    DeepAgentFactory,
    InMemoryDeepAgent,
    InMemoryDeepAgentFactory,
    SubAgentSpec,
)
from qzdap_agent_runtime.graph import nodes


@pytest.fixture(autouse=True)
def _reset_deps():
    yield
    nodes.reset_default_dependencies()


# ---------------------------------------------------------------------------
# Protocol duck-typing
# ---------------------------------------------------------------------------


def test_in_memory_deep_agent_factory_satisfies_protocol() -> None:
    assert isinstance(InMemoryDeepAgentFactory(), DeepAgentFactory)


def test_in_memory_deep_agent_satisfies_protocol() -> None:
    async def _test() -> None:
        agent = await InMemoryDeepAgentFactory().create(
            DeepAgentConfig(agent_id="a", max_steps=1, max_cost_usd=0.1)
        )
        assert isinstance(agent, DeepAgent)
    import asyncio
    asyncio.run(_test())


# ---------------------------------------------------------------------------
# DeepAgentConfig + SubAgentSpec
# ---------------------------------------------------------------------------


class TestConfig:
    def test_default_config(self) -> None:
        cfg = DeepAgentConfig(agent_id="a")
        assert cfg.deep_research is False
        assert cfg.max_steps == 20
        assert cfg.max_cost_usd == 1.0
        assert cfg.skills == ()

    def test_subagent_spec_defaults(self) -> None:
        sub = SubAgentSpec(name="research-1", system_prompt="x")
        assert sub.max_steps == 10
        assert sub.max_cost_usd == 0.5


# ---------------------------------------------------------------------------
# InMemoryDeepAgentFactory + budget
# ---------------------------------------------------------------------------


class TestInMemoryDeepAgentFactory:
    def test_invalid_max_steps_raises(self) -> None:
        async def _test() -> None:
            with pytest.raises(DeepAgentBudgetExceeded):
                await InMemoryDeepAgentFactory().create(
                    DeepAgentConfig(agent_id="a", max_steps=0, max_cost_usd=1.0)
                )
        import asyncio
        asyncio.run(_test())

    def test_invalid_max_cost_raises(self) -> None:
        async def _test() -> None:
            with pytest.raises(DeepAgentBudgetExceeded):
                await InMemoryDeepAgentFactory().create(
                    DeepAgentConfig(agent_id="a", max_steps=10, max_cost_usd=0)
                )
        import asyncio
        asyncio.run(_test())

    def test_create_records_factory_history(self) -> None:
        async def _test() -> None:
            f = InMemoryDeepAgentFactory()
            await f.create(DeepAgentConfig(agent_id="a1"))
            await f.create(DeepAgentConfig(agent_id="a2"))
            assert len(f._created) == 2
        import asyncio
        asyncio.run(_test())


# ---------------------------------------------------------------------------
# InMemoryDeepAgent: step + budget
# ---------------------------------------------------------------------------


class TestInMemoryDeepAgentStep:
    def test_emits_plan(self) -> None:
        async def _test() -> None:
            f = InMemoryDeepAgentFactory()
            agent = await f.create(DeepAgentConfig(agent_id="a", max_steps=5, max_cost_usd=1.0))
            agent.emit_plan([{"id": "t1", "status": "pending", "content": "x"}])
            assert len(agent.todos) == 1
        import asyncio
        asyncio.run(_test())

    def test_step_increments_count_and_cost(self) -> None:
        async def _test() -> None:
            f = InMemoryDeepAgentFactory()
            agent = await f.create(DeepAgentConfig(agent_id="a", max_steps=5, max_cost_usd=1.0))
            agent.step(cost=0.1)
            agent.step(cost=0.2)
            assert agent.steps == 2
            assert abs(agent.cost - 0.3) < 1e-6
        import asyncio
        asyncio.run(_test())

    def test_step_exceeds_max_steps_raises(self) -> None:
        async def _test() -> None:
            f = InMemoryDeepAgentFactory()
            agent = await f.create(DeepAgentConfig(agent_id="a", max_steps=2, max_cost_usd=1.0))
            agent.step()
            agent.step()
            with pytest.raises(DeepAgentBudgetExceeded):
                agent.step()  # 第 3 步超
        import asyncio
        asyncio.run(_test())

    def test_step_exceeds_max_cost_raises(self) -> None:
        async def _test() -> None:
            f = InMemoryDeepAgentFactory()
            agent = await f.create(DeepAgentConfig(agent_id="a", max_steps=10, max_cost_usd=0.05))
            agent.step(cost=0.04)
            with pytest.raises(DeepAgentBudgetExceeded):
                agent.step(cost=0.02)  # 0.06 > 0.05
        import asyncio
        asyncio.run(_test())


# ---------------------------------------------------------------------------
# deep_agent_plan 节点
# ---------------------------------------------------------------------------


class TestDeepAgentPlanNode:
    def test_passthrough_when_no_factory(self) -> None:
        out = nodes.deep_agent_plan({})  # type: ignore[arg-type]
        assert out == {}

    def test_emits_todos_via_factory(self) -> None:
        factory = InMemoryDeepAgentFactory()
        nodes.set_default_deep_agent_factory(factory)
        out = nodes.deep_agent_plan({
            "agent_id": "agt-1",
            "messages": [{"role": "user", "content": "研究 RAG"}],
            "route": {"reason": "task_kind=DEEP_RESEARCH"},
        })
        # 必须有 todos
        assert "todos" in out
        assert len(out["todos"]) > 0
        # todos 包含 id/status/content
        for todo in out["todos"]:
            assert "id" in todo
            assert "status" in todo
            assert "content" in todo

    def test_budget_exceeded_writes_error(self) -> None:
        # 注入一个会抛 DeepAgentBudgetExceeded 的 fake factory
        class _FailFactory:
            async def create(self, config, subagents=()):
                raise DeepAgentBudgetExceeded(
                    "max_steps=0 invalid",
                    spent_steps=0,
                )

        nodes.set_default_deep_agent_factory(_FailFactory())
        out = nodes.deep_agent_plan({
            "agent_id": "agt-1",
            "messages": [{"role": "user", "content": "test"}],
        })
        # errors 包含 DEEP_AGENT_BUDGET_EXCEEDED
        assert any(
            e["error_code"] == DEEP_AGENT_BUDGET_EXCEEDED_ERROR_CODE
            for e in out.get("errors", [])
        )

    def test_unexpected_exception_writes_deep_agent_failed(self) -> None:
        class _BoomFactory:
            async def create(self, config, subagents=()):
                raise RuntimeError("boom")

        nodes.set_default_deep_agent_factory(_BoomFactory())
        out = nodes.deep_agent_plan({
            "agent_id": "agt-1",
            "messages": [{"role": "user", "content": "test"}],
        })
        assert any(
            e["error_code"] == DEEP_AGENT_FAILED_ERROR_CODE
            for e in out.get("errors", [])
        )


# ---------------------------------------------------------------------------
# subagent 节点
# ---------------------------------------------------------------------------


class TestSubagentNode:
    def test_passthrough_when_no_factory(self) -> None:
        out = nodes.subagent({})  # type: ignore[arg-type]
        assert out == {}

    def test_runs_subagent_and_marks_todos_done(self) -> None:
        factory = InMemoryDeepAgentFactory()
        nodes.set_default_deep_agent_factory(factory)
        out = nodes.subagent({
            "agent_id": "agt-1",
            "todos": [{"id": "t-1", "status": "in_progress", "content": "x"}],
        })
        # todos 都被标记为 done
        assert all(t["status"] == "done" for t in out["todos"])
        # context_manifest.subagent 记录步骤
        assert out["context_manifest"]["subagent"]["steps"] == 1
        assert out["context_manifest"]["subagent"]["cost_usd"] > 0

    def test_subagent_budget_exceeded_marks_todos_done_and_writes_error(self) -> None:
        # max_steps=1 注入, 第一次 step 后第二次 step 必抛
        class _LimitFactory:
            async def create(self, config, subagents=()):
                from qzdap_agent_runtime.graph.deep_agent import InMemoryDeepAgent
                # 先创建一个会立即超 budget 的 agent
                return InMemoryDeepAgent(name="a", config=config)
            def get_inner(self, config):
                from qzdap_agent_runtime.graph.deep_agent import InMemoryDeepAgent
                return InMemoryDeepAgent(name="a", config=config)
        # 用 InMemoryDeepAgentFactory 即可, max_steps=1 + 强制 2 step
        nodes.set_default_deep_agent_factory(InMemoryDeepAgentFactory())
        # 先建 max_steps=1 agent
        # 通过 deep_agent_plan 间接跑 (但需 pre-set todos)
        # 简化: 直接在 subagent 节点中测
        # 实际 subagent 节点内部调 factory.create → agent.step; 我们测 budget 超限
        # 修改 factory 让 create 返回 max_steps=0 (会抛)
        class _BrokenFactory:
            async def create(self, config, subagents=()):
                raise DeepAgentBudgetExceeded("sub-agent budget exhausted", spent_steps=10)
        nodes.set_default_deep_agent_factory(_BrokenFactory())
        out = nodes.subagent({
            "agent_id": "agt-1",
            "todos": [{"id": "t-1", "status": "in_progress", "content": "x"}],
        })
        # todos 全部 done (即使 budget 超也强制收敛)
        assert all(t["status"] == "done" for t in out["todos"])
        # errors 记录 budget exceeded
        assert any(
            e["error_code"] == DEEP_AGENT_BUDGET_EXCEEDED_ERROR_CODE
            for e in out.get("errors", [])
        )


# ---------------------------------------------------------------------------
# §8 Stage 6b 退出条件: deep_task 触发 deep_agent_plan
# ---------------------------------------------------------------------------


class TestDeepTaskTriggersDeepAgentPlan:
    def test_route_deep_task_then_deep_agent_plan_receives_todos(self) -> None:
        """§8 Stage 6b: route.deep_task=true → deep_agent_plan emit todos。"""
        # 注入 deep_research 触发 deep_task
        nodes.set_default_agent_config(
            nodes.AgentRouteConfig(agent_id="agt-1", deep_research=True)
        )
        # 跑 route 节点
        route_out = nodes.route({
            "agent_id": "agt-1",
            "messages": [{"role": "user", "content": "test"}],
        })
        assert route_out["route"]["deep_task"] is True
        # 注入 deep agent factory 跑 deep_agent_plan 节点
        factory = InMemoryDeepAgentFactory()
        nodes.set_default_deep_agent_factory(factory)
        # 把 route 结果合并到 state 模拟图流
        state = {
            "agent_id": "agt-1",
            "messages": [{"role": "user", "content": "test"}],
            "route": route_out["route"],
        }
        plan_out = nodes.deep_agent_plan(state)
        # 必须 emit todos
        assert "todos" in plan_out
        assert len(plan_out["todos"]) > 0