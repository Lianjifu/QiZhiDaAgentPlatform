"""演示数据的形状与隔离.

两条线:
* 演示智能体的清单本身是合法的 (工具名真实存在、开场示例能取到).
* 开发那套**绝不**会种演示智能体 —— 判断写在函数里, 不靠调用方自觉.
"""

from __future__ import annotations

import pytest

from qzdap.composition.seeds import (
    DEMO_AGENT_MODEL,
    DEMO_AGENT_SPECS,
    DEMO_KB_SPECS,
    DEMO_MEMORY_SPECS,
    DEMO_SKILL_SPECS,
    DEMO_WORKFLOW_SPECS,
    demo_profile,
    dev_profile,
    seed_demo_agents,
    seed_demo_content,
    seed_demo_memory,
    seed_demo_ops_docs,
)
from qzdap.composition.settings import Settings
from qzdap.modules.tool.application.tool_catalog import BUILTIN_TOOL_SPECS


@pytest.fixture()
def settings() -> Settings:
    return Settings(env="demo", embedding_provider="noop")


def test_demo_agents_are_skipped_for_the_dev_profile(settings: Settings) -> None:
    """dev profile 调用时直接返回空 —— 不碰 session, 更不落库.

    传 ``session=None`` 是故意的: 万一实现哪天先去碰 session 再判断,
    这里会直接炸, 而不是悄悄写进开发库.
    """
    dev = dev_profile(settings)
    assert dev.label == "dev"
    assert dev.accounts[0][0].endswith("@dev.qzdap.dev")

    import asyncio

    created = asyncio.run(seed_demo_agents(None, dev, tenant_id=dev.tenant_id, workspace_id=None))
    assert created == []


def test_demo_and_dev_profiles_do_not_share_accounts(settings: Settings) -> None:
    """两套账号/租户完全不重叠."""
    demo = demo_profile(settings)
    dev = dev_profile(settings)
    demo_emails = {email for email, _name, _role in demo.accounts}
    dev_emails = {email for email, _name, _role in dev.accounts}
    assert demo_emails and dev_emails
    assert not demo_emails & dev_emails
    assert demo.password != dev.password
    assert demo.tenant_slug != dev.tenant_slug


def test_demo_agent_tools_all_exist_in_the_catalog() -> None:
    """智能体引用的工具名必须是真实注册过的 —— 否则模型一调就报"工具不存在"."""
    for spec in DEMO_AGENT_SPECS:
        for name in spec.get("tools", []):
            assert name in BUILTIN_TOOL_SPECS, f"{spec['name']} 引用了不存在的工具 {name}"


def test_demo_agent_specs_are_chat_ready() -> None:
    """每个演示智能体都要有: 分类、开场示例、可用工具、公开可见."""
    for spec in DEMO_AGENT_SPECS:
        assert spec["name"] and spec["description"] and spec["category"]
        prompts = spec["prompts"]
        assert prompts["soul"] and prompts["prompt"]
        # prompts.user 里以 "- " 开头的行会被 to_catalog_dict 取成开场示例.
        starters = [line for line in prompts["user"].splitlines() if line.strip().startswith("-")]
        assert starters, f"{spec['name']} 没有开场示例"
        assert spec["tools"], f"{spec['name']} 没有可用工具"


def test_demo_agents_cover_several_catalog_categories() -> None:
    """分类要散开 —— 否则演示库里看着像"只有一个智能体"."""
    categories = {spec["category"] for spec in DEMO_AGENT_SPECS}
    assert len(categories) >= 4
    assert len(DEMO_AGENT_SPECS) >= 4


def test_demo_agent_model_id_is_not_empty() -> None:
    """model 字段留空的话, 运营配好供应商后这些智能体仍然连不上模型."""
    assert DEMO_AGENT_MODEL


def test_dev_profile_seeds_no_demo_content(settings: Settings) -> None:
    """dev 那套连碰都不能碰演示内容 —— 传 ``session=None``, 碰了就会炸."""
    dev = dev_profile(settings)
    import asyncio

    result = asyncio.run(seed_demo_content(None, dev, tenant_id=dev.tenant_id, workspace_id=None))
    assert result == {
        "agents": [],
        "skills": [],
        "workflows": [],
        "knowledge": [],
        "conversations": [],
        "memory": {},
        "ops": {},
    }


def test_demo_content_specs_are_complete() -> None:
    """技能/工作流/知识库的清单都得有能演示的内容."""
    assert len(DEMO_SKILL_SPECS) >= 3
    for spec in DEMO_SKILL_SPECS:
        assert spec["name"] and spec["description"]
        assert spec["inputSchema"], f"{spec['name']} 没有输入契约"
        assert spec["outputSchema"], f"{spec['name']} 没有输出契约"

    assert len(DEMO_WORKFLOW_SPECS) >= 3
    for spec in DEMO_WORKFLOW_SPECS:
        assert spec["name"] and spec["description"] and spec["scene"]
        assert spec["trigger"] in {"消息触发", "定时触发", "事件触发", "手动触发"}
        assert spec["boundAgentNames"], f"{spec['name']} 没绑智能体"

    assert len(DEMO_KB_SPECS) >= 2
    for spec in DEMO_KB_SPECS:
        assert spec["name"] and spec["description"]
        assert spec["docs"], f"{spec['name']} 里没有文档"
        for doc in spec["docs"]:
            assert doc["name"] and doc["content"]


def test_demo_workflows_only_bind_known_agents() -> None:
    """工作流绑的智能体名必须是演示智能体清单里的 —— 否则绑出来是悬空 id."""
    known = {spec["name"] for spec in DEMO_AGENT_SPECS}
    for spec in DEMO_WORKFLOW_SPECS:
        for name in spec["boundAgentNames"]:
            assert name in known, f"{spec['name']} 绑了不存在的智能体 {name}"


def test_demo_memory_is_skipped_for_the_dev_profile(settings: Settings) -> None:
    """记忆也是演示内容 —— dev 那套连碰都不能碰."""
    dev = dev_profile(settings)
    import asyncio

    counts = asyncio.run(seed_demo_memory(None, dev, tenant_id=dev.tenant_id, workspace_id=None))
    assert counts == {}


def test_demo_memory_specs_cover_l2_only() -> None:
    """**记忆只剩 L2** ✓ —— L1 / L3 都退役了 ✓。

    ⚠️ **不再有 L1** ✓（表退役了 ✓ —— 决策 #5 ✓ —— M-46 ✓）——
    管理端看的「L1」现在是**会话缓冲** ✓（演示环境不配模型 ✓ → 本来就空 ✓）。

    ⚠️ **不再有 L3** ✓（决策 #1 ✓ —— L3 退役 ✓ —— 台账 **X15** ✓）——
    团队知识归 **knowledge** ✓（见 `test_demo_kb_specs_carry_team_knowledge` ✓）。
    """
    assert "l1" not in DEMO_MEMORY_SPECS
    assert "l3" not in DEMO_MEMORY_SPECS
    assert len(DEMO_MEMORY_SPECS["l2"]) >= 3
    for spec in DEMO_MEMORY_SPECS["l2"]:
        assert spec["key"] and spec["value"]
        assert spec["category"] in {"preference", "fact", "style", "context"}
        assert spec["status"] in {"pending", "confirmed", "retired"}


def test_demo_kb_specs_carry_team_knowledge() -> None:
    """**团队知识在 knowledge 里** ✓ —— 一个团队一个库 ✓（M-47 ✓）。

    ⚠️ **类别 / 发布态 / 贡献者都要带着** ✓ —— 它们是 L3 迁过来时的字段 ✓
    （丢了就等于**没迁** ✗✗）。
    """
    team_docs = [doc for kb in DEMO_KB_SPECS for doc in kb.get("docs", []) if doc.get("category")]
    assert len(team_docs) >= 2
    for doc in team_docs:
        assert doc["name"] and doc["content"]
        assert doc["publishState"] in {"draft", "published", "retired"}
        assert doc["contributor"]
    # 演示要能看到"发布 / 下线"两种状态, 按钮才有东西可点
    states = {doc["publishState"] for doc in team_docs}
    assert "published" in states
    assert states & {"draft", "retired"}


def test_demo_ops_docs_are_skipped_for_the_dev_profile(settings: Settings) -> None:
    """⚠️ **管理台文档也是演示数据** ✓ —— 开发库不种 ✓（通道分离 ✓）。

    传 ``session=None`` 是故意的 —— 万一实现先去碰 session 再判断, 这里
    会直接炸, 而不是悄悄写进开发库.
    """
    import asyncio

    dev = dev_profile(settings)
    assert dev.label == "dev"
    seeded = asyncio.run(seed_demo_ops_docs(None, dev, tenant_id=dev.tenant_id, workspace_id=None))
    assert seeded == {}


def test_the_ops_seed_covers_every_admin_console_collection() -> None:
    """⚠️ **管理台八个页面都有数据** ✓ —— 少一个集合那一页就是空的 ✗✗。"""
    from qzdap.modules.platform.fixtures.ops_seed import SEED

    expected = {
        "quotas.budgets",
        "quotas.alerts",
        "notifications.channels",
        "notifications.webhooks",
        "notifications.groups",
        "evaluations.suites",
        "regressions.tracks",
        "feedback.list",
        "operations.sessions",
        "operations.incidents",
        "audit.entries",
        "metrics.dashboards",
    }
    assert expected <= set(SEED)
    for collection, items in SEED.items():
        assert items, f"{collection} 是空的 —— 那一页会是空的"
        for item in items:
            # ⚠️ **没有 id 的由仓储补** ✓（``seed_if_empty`` ✓）—— 不强制 ✓。
            assert isinstance(item, dict) and item
