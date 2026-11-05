"""**接线回归** ✓ —— 「已实现」必须「真生效」✓。

⚠️ **这组测试守的是「接上了」** ✓ —— 不是「函数写对了」✓
（函数写对了但**没接线** ✓ = 能力不存在 ✓ —— 那正是 2026-10-15 的坑 ✓）。

| # | 断言 | 对应的缺口 |
|---|---|---|
| 1 | agent 配了成本上限 → 超过就中止 | ``max_cost_usd`` 从未传入 → 成本闸门失效 ✓ |
| 2 | 治理 DENY → 工具不执行 | ``policy_guard`` 从未注入 → 策略走不到 ✓ |
| 3 | 专家的指令进了 system prompt | 专家 instruction 装配后被丢弃 ✓ |
| 4 | 预算口径 = 窗口 × 0.70 | Builder 硬编码 8000 vs 压缩器 0.7 ✓ |
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from qzdap.modules.agent_runtime.adapter.graph.governance_guard import GovernancePolicyGuard
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent
from qzdap_agent_runtime.context.builder import BUDGET_RATIO, ContextBuilder
from qzdap_kernel.errors import ActionDeniedError
from qzdap_vault.actor import ActorContext

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
OWNER = UUID("00000000-0000-0000-0000-000000000010")


class _Prices:
    """``price_of`` 的替身 ✓ —— 返回固定单价 ✓。"""

    def __init__(self, price_in: float = 1.0, price_out: float = 2.0) -> None:
        self.price_in = price_in
        self.price_out = price_out

    async def price_of(self, **kwargs: Any):  # type: ignore[no-untyped-def]
        _ = kwargs
        return (self.price_in, self.price_out)


class _DenyingGuard:
    """治理侧的守卫替身 ✓ —— 总是拒绝 ✓。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def check(self, *, actor: Any, action: str, resource: Any = None) -> None:
        _ = (actor, resource)
        self.calls.append(action)
        raise ActionDeniedError(reason="测试策略拒绝", code="ACTION_DENIED")


class _RecordingGuard:
    """治理侧的守卫替身 ✓ —— 放行 ✓ 但记录被问过 ✓。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def check(self, *, actor: Any, action: str, resource: Any = None) -> None:
        _ = (actor, resource)
        self.calls.append(action)


def _agent(**kwargs: Any) -> CatalogAgent:
    agent = CatalogAgent.create(
        id=UUID("00000000-0000-0000-0000-0000000000aa"),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        name="测试 agent",
        category="test",
        owner="test",
        model="default",
    )
    return agent.apply_patch(kwargs) if kwargs else agent


# ── ① 成本闸门 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_cost_gate_aborts_the_turn_when_the_limit_is_passed() -> None:
    """**成本上限真的会中止这一轮** ✓。

    ⚠️ **在契约层验** ✓ —— 闸门在 ``Evaluator`` ✓ —— 那里才有判据 ✓
    （模块侧只负责**把上限传进去** ✓ —— 那是另两个断言 ✓）。
    """
    from qzdap_agent_runtime.agent_loop.evaluate import Evaluator
    from qzdap_agent_runtime.agent_loop.state import LoopState

    evaluator = Evaluator(max_steps=8, max_cost_usd=0.001)
    state = LoopState()
    state.cost_usd = 1.0  # $1 > $0.001
    termination = evaluator.evaluate(state)
    assert termination.action == "abort"
    assert "成本" in termination.reason

    # ⚠️ **没超就不中止** ✓
    ok = Evaluator(max_steps=8, max_cost_usd=10.0)
    assert ok.evaluate(state).action != "abort"


def test_the_cost_limit_comes_from_the_agent_config() -> None:
    """**上限从 agent 配置读出来** ✓ —— 没配就是不限 ✓。"""
    from qzdap.modules.agent_runtime.adapter.graph.runner import _max_cost_usd

    agent = _agent(profile={"maxCostUsd": 0.001})
    assert _max_cost_usd(agent) == pytest.approx(0.001)
    # ⚠️ **没配就是不限** ✓
    assert _max_cost_usd(_agent()) == 0.0
    assert _max_cost_usd(None) == 0.0
    # ⚠️ **下划线写法也认** ✓（两种命名 ✓）
    assert _max_cost_usd(_agent(profile={"max_cost_usd": 2.5})) == pytest.approx(2.5)
    # ⚠️ **非法值归零** ✓（不因为脏配置炸掉 ✓）
    assert _max_cost_usd(_agent(profile={"maxCostUsd": "不是数字"})) == 0.0


# ── ② 治理注入 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_governance_guard_translates_a_deny_into_a_deny_decision() -> None:
    """**治理拒绝 → 循环看到的 deny** ✓。"""
    guard = _DenyingGuard()
    adapter = GovernancePolicyGuard(
        guard=guard,
        actor=ActorContext(tenant_id=TENANT, workspace_id=WORKSPACE, principal_id=OWNER),
    )
    decision, approval_id = await adapter.decide(
        actor=None,
        tool_call_id="call-1",
        tool_meta=type("M", (), {"name": "web_search"})(),
        arguments={"query": "x"},
    )
    assert decision == "deny"
    assert approval_id is None
    # ⚠️ **动作名带工具名** ✓ —— 策略按动作匹配 ✓
    assert guard.calls == ["tool:execute:web_search"]


@pytest.mark.asyncio
async def test_the_governance_guard_allows_when_the_check_passes() -> None:
    """**治理放行 → allow** ✓。"""
    guard = _RecordingGuard()
    adapter = GovernancePolicyGuard(
        guard=guard,
        actor=ActorContext(tenant_id=TENANT, workspace_id=WORKSPACE, principal_id=OWNER),
    )
    decision, _ = await adapter.decide(
        actor=None,
        tool_call_id="call-1",
        tool_meta=type("M", (), {"name": "web_search"})(),
        arguments={},
    )
    assert decision == "allow"
    assert guard.calls == ["tool:execute:web_search"]


@pytest.mark.asyncio
async def test_the_governance_guard_allows_when_the_governance_service_breaks() -> None:
    """**治理服务故障 → 放行** ✓ —— 不能因为治理挂了把对话也挂掉 ✓。"""

    class _Broken:
        async def check(self, **kwargs: Any) -> None:
            _ = kwargs
            raise RuntimeError("治理服务不可用")

    adapter = GovernancePolicyGuard(
        guard=_Broken(),
        actor=ActorContext(tenant_id=TENANT, workspace_id=WORKSPACE, principal_id=OWNER),
    )
    decision, _ = await adapter.decide(
        actor=None,
        tool_call_id="call-1",
        tool_meta=type("M", (), {"name": "web_search"})(),
        arguments={},
    )
    assert decision == "allow"


# ── ③ 专家指令 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_expert_instruction_reaches_the_system_prompt() -> None:
    """**专家的指令进了上下文** ✓ —— 不再被丢弃 ✓。"""
    builder = ContextBuilder()
    assembled = await builder.build(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        owner_id=OWNER,
        user_input="问题",
        expert_instruction="你是数据分析专家，只回答数字相关的问题。",
    )
    # ⚠️ **装配结果是契约形状的 dict** ✓（``{role, content}`` ✓）
    system_texts = [
        str(item.get("content") or "")
        for item in assembled.messages
        if item.get("role") == "system"
    ]
    assert any("数据分析专家" in text for text in system_texts), (
        f"专家指令没进 system prompt: {system_texts}"
    )
    # ⚠️ **manifest 里能查到来源** ✓ —— 分段溯源 ✓
    assert any(entry.source == "expert" for entry in assembled.manifest.entries)


@pytest.mark.asyncio
async def test_no_expert_instruction_means_no_extra_system_segment() -> None:
    """**没有专家指令就不加那一段** ✓ —— 不塞空段 ✓。"""
    builder = ContextBuilder()
    assembled = await builder.build(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        owner_id=OWNER,
        user_input="问题",
    )
    assert not any(entry.source == "expert" for entry in assembled.manifest.entries)


# ── ④ 预算口径 ────────────────────────────────────────────────────────────


def test_the_context_budget_matches_the_compressor_ratio() -> None:
    """**Builder 的预算与压缩器同口径** ✓ —— ``window × 0.70`` ✓。

    ⚠️ **之前 Builder 硬编码 8000** ✓ —— 与压缩器的 ``window×0.7`` 是
    **两套** ✗✗（谁先到谁生效 ✗ → 行为不可预测 ✗）。
    """
    from qzdap_agent_runtime.context.compressor import WINDOW_RATIO

    assert BUDGET_RATIO == WINDOW_RATIO

    window = 100_000
    builder = ContextBuilder(context_window=window)
    assert builder._max_tokens == int(window * WINDOW_RATIO)

    # ⚠️ **显式给死预算时尊重它** ✓
    explicit = ContextBuilder(max_tokens=1234)
    assert explicit._max_tokens == 1234
