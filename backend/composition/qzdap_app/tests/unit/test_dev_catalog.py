"""开发目录的一致性测试 —— 三个智能体 + 各自的技能 / 知识 / 工作流。

**纯数据测试** ✓ —— 不碰数据库 ✓（落库那条线由
``tests/integration/test_dev_catalog_seed.py`` 覆盖 ✓）。
"""

from __future__ import annotations

from qzdap.composition.dev_catalog import (
    AGENT_KEYS,
    build_assets,
    catalog_id,
    load_catalog,
)


def _by_kind(kind: str) -> list:
    return [asset for asset in build_assets() if asset.kind == kind]


def test_catalog_has_the_three_agents() -> None:
    agents = _by_kind("agent")
    assert [asset.key for asset in agents] == list(AGENT_KEYS)
    assert [asset.body["name"] for asset in agents] == [
        "办公智能体",
        "招聘智能体",
        "调研智能体",
    ]


def test_ids_are_deterministic_and_unique() -> None:
    first = build_assets()
    second = build_assets()
    assert [asset.id for asset in first] == [asset.id for asset in second]
    ids = [asset.id for asset in first]
    assert len(ids) == len(set(ids)), "资产 id 必须唯一"
    assert catalog_id("skill", "office.calendar") == catalog_id("skill", "office.calendar")
    assert catalog_id("skill", "office.calendar") != catalog_id("kb", "office.calendar")


def test_every_agent_reference_resolves() -> None:
    skill_ids = {asset.id for asset in _by_kind("skill")}
    kb_ids = {asset.id for asset in _by_kind("kb")}
    flow_ids = {asset.id for asset in _by_kind("workflow")}

    for agent in _by_kind("agent"):
        tools = agent.body["tools"]
        refs = agent.body["knowledgeRefs"]
        flows = agent.body["flowRefs"]
        assert tools, f"{agent.key} 没有绑定技能"
        assert refs, f"{agent.key} 没有绑定知识库"
        assert flows, f"{agent.key} 没有绑定工作流"
        assert all(tool["id"] in skill_ids for tool in tools)
        assert all(ref["id"] in kb_ids for ref in refs)
        assert all(flow["id"] in flow_ids for flow in flows)
        assert all(tool["enabled"] for tool in tools)
        assert all(ref["enabled"] for ref in refs)
        assert all(flow["enabled"] for flow in flows)


def test_every_agent_prompt_section_is_filled() -> None:
    for agent in _by_kind("agent"):
        prompts = agent.body["prompts"]
        for section in ("prompt", "soul", "agents", "user", "tools"):
            assert prompts.get(section, "").strip(), f"{agent.key} 缺 {section} 提示词"


def test_workflow_graph_is_consistent() -> None:
    agent_ids = {asset.id for asset in _by_kind("agent")}
    for flow in _by_kind("workflow"):
        nodes = flow.body["initialNodes"]
        edges = flow.body["initialEdges"]
        node_ids = [node["id"] for node in nodes]
        assert len(node_ids) == len(set(node_ids)), f"{flow.key} 节点 id 重复"
        assert nodes, f"{flow.key} 没有节点"
        assert edges, f"{flow.key} 没有连线"
        for edge in edges:
            assert edge["source"] in node_ids
            assert edge["target"] in node_ids
        assert flow.body["boundAgents"], f"{flow.key} 没绑智能体"
        assert all(agent in agent_ids for agent in flow.body["boundAgents"])


def test_docs_belong_to_known_knowledge_bases() -> None:
    kb_ids = {asset.id for asset in _by_kind("kb")}
    docs = _by_kind("doc")
    assert docs
    for doc in docs:
        assert doc.body["kbId"] in kb_ids
        assert doc.body["content"].strip(), f"{doc.key} 正文为空"


def test_eval_suites_target_a_known_agent() -> None:
    agent_ids = {asset.id for asset in _by_kind("agent")}
    suites = _by_kind("evalSuite")
    assert len(suites) == len(AGENT_KEYS)
    for suite in suites:
        assert suite.body["target"] in agent_ids
        assert suite.body["casesList"], f"{suite.key} 没有用例"
        assert suite.body["criteria"].strip(), f"{suite.key} 没有评测口径"
        for case in suite.body["casesList"]:
            assert case.get("input") and case.get("expected")


def test_no_orphan_assets() -> None:
    """技能 / 知识库 / 工作流都被某个智能体用上 ✓ —— 不留孤儿 ✓."""
    used_skills: set[str] = set()
    used_kbs: set[str] = set()
    used_flows: set[str] = set()
    for agent in _by_kind("agent"):
        used_skills.update(tool["id"] for tool in agent.body["tools"])
        used_kbs.update(ref["id"] for ref in agent.body["knowledgeRefs"])
        used_flows.update(flow["id"] for flow in agent.body["flowRefs"])
    assert used_skills == {asset.id for asset in _by_kind("skill")}
    assert used_kbs == {asset.id for asset in _by_kind("kb")}
    assert used_flows == {asset.id for asset in _by_kind("workflow")}


def test_assets_are_ordered_by_dependency() -> None:
    """智能体排在技能 / 知识 / 工作流之后 ✓ —— 落库顺序不能反 ✓."""
    kinds = [asset.kind for asset in build_assets()]
    first_agent = kinds.index("agent")
    assert "skill" in kinds[:first_agent]
    assert "kb" in kinds[:first_agent]
    assert "doc" in kinds[:first_agent]
    assert "workflow" in kinds[:first_agent]
    assert kinds[first_agent:].count("agent") == len(AGENT_KEYS)


def test_raw_catalog_matches_assets() -> None:
    """清单里的 skillKeys / kbKeys / workflowKeys 都要指向存在的条目 ✓."""
    raw = load_catalog()
    skill_keys = {item["key"] for item in raw["skills"]}
    kb_keys = {item["key"] for item in raw["knowledgeBases"]}
    workflow_keys = {item["key"] for item in raw["workflows"]}
    for agent in raw["agents"]:
        assert set(agent["skillKeys"]) <= skill_keys
        assert set(agent["kbKeys"]) <= kb_keys
        assert set(agent["workflowKeys"]) <= workflow_keys
        assert agent["skillKeys"], f"{agent['key']} 没有技能"
        assert agent["kbKeys"], f"{agent['key']} 没有知识库"
        assert agent["workflowKeys"], f"{agent['key']} 没有工作流"
