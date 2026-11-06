"""开发目录 —— 三个业务智能体及其技能 / 知识 / 工作流 / 评测套件。

⚠️ **不是种子** ✓ —— 目录页开箱是空态 ✓；这是一份**显式一次性脚本**用的
清单 ✓（``backend/dev/seed_dev_catalog.py`` ✓）—— 开发环境不种任何内容
数据 ✓，需要时手动跑一次脚本 ✓。

设计:

* **单一来源** ✓ —— ``catalog.json`` 是唯一的内容出处 ✓，后端装载器与
  前端测试读同一份 ✓（前端走 JSON import ✓）。
* **确定性 id** ✓ —— id 由 ``uuid5(namespace, "kind/key")`` 派生 ✓，
  所以脚本可以重复跑 ✓（幂等 ✓），测试也可以断言 id 不漂移 ✓。
* **引用先解析后落库** ✓ —— 智能体的技能 / 知识库 / 工作流引用在装载
  阶段就换成真实 id ✓（``skillKeys`` / ``kbKeys`` / ``workflowKeys`` ✓），
  落库时不再带 key ✓。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

__all__ = [
    "AGENT_KEYS",
    "Asset",
    "build_assets",
    "catalog_id",
    "catalog_namespace",
    "load_catalog",
]

_CATALOG_FILE = Path(__file__).with_name("catalog.json")

#: 三个智能体的 key ✓ —— 测试与脚本都按这个认人 ✓。
AGENT_KEYS: tuple[str, ...] = ("office", "hr", "research")

_PATHS: dict[str, str] = {
    "skill": "/api/admin/skills",
    "kb": "/api/admin/knowledge/kbs",
    "doc": "/api/admin/knowledge/docs",
    "workflow": "/api/admin/workflows",
    "agent": "/api/admin/agents",
    "evalSuite": "/api/admin/evaluations/suites",
}


@dataclass(frozen=True, slots=True)
class Asset:
    """一条待落库的目录资产 —— **id 已解析好** ✓."""

    kind: str
    key: str
    id: str
    path: str
    body: dict[str, Any]

    @property
    def payload(self) -> dict[str, Any]:
        """落库请求体 ✓ —— 带 id ✓."""
        return {**self.body, "id": self.id}


def load_catalog() -> dict[str, Any]:
    """读原始清单 ✓."""
    return json.loads(_CATALOG_FILE.read_text(encoding="utf-8"))


def catalog_namespace() -> UUID:
    """清单的 id 命名空间 ✓ —— 由清单里的 ``namespace`` 派生 ✓."""
    return uuid5(NAMESPACE_URL, str(load_catalog().get("namespace") or "qzdap.dev"))


def catalog_id(kind: str, key: str) -> str:
    """**确定性 id** ✓ —— 同 kind + key 永远同一个 UUID ✓."""
    return str(uuid5(catalog_namespace(), f"{kind}/{key}"))


def _skill_body(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": raw["name"],
        "description": raw.get("description", ""),
        "type": raw.get("type", "Skill"),
        "owner": raw.get("owner", "管理员"),
        "risk": raw.get("risk", "low"),
        "needConfirm": bool(raw.get("needConfirm", False)),
        "inputSchema": list(raw.get("inputSchema") or []),
        "outputSchema": list(raw.get("outputSchema") or []),
        "runtime": dict(raw.get("runtime") or {}),
        "tags": list(raw.get("tags") or []),
        "visibleScope": list(raw.get("visibleScope") or ["部门"]),
    }


def _kb_body(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": raw["name"],
        "description": raw.get("description", ""),
        "scope": raw.get("scope", "部门"),
        "retrieval": raw.get("retrieval", "hybrid"),
        "boundSources": list(raw.get("boundSources") or []),
        "topK": int(raw.get("topK") or 8),
    }


def _workflow_body(raw: dict[str, Any], *, agent_ids: dict[str, str]) -> dict[str, Any]:
    nodes = [
        {
            "id": node["id"],
            "type": "flowNode",
            "position": dict(node.get("position") or {"x": 0, "y": 0}),
            "data": {
                "label": node.get("label", ""),
                "subtitle": node.get("subtitle", ""),
                "kind": node.get("kind", "tool"),
                "config": dict(node.get("config") or {}),
                **({"inputs": list(node["inputs"])} if node.get("inputs") else {}),
                **({"outputs": list(node["outputs"])} if node.get("outputs") else {}),
            },
        }
        for node in (raw.get("nodes") or [])
    ]
    edges = [
        {"id": edge["id"], "source": edge["source"], "target": edge["target"]}
        for edge in (raw.get("edges") or [])
    ]
    return {
        "name": raw["name"],
        "description": raw.get("description", ""),
        "owner": raw.get("owner", "当前管理员"),
        "scene": raw.get("scene", "团队协作"),
        "trigger": raw.get("trigger", "消息触发"),
        "status": raw.get("status", "draft"),
        "initialNodes": nodes,
        "initialEdges": edges,
        "boundAgents": [agent_ids[key] for key in (raw.get("agentKeys") or [])],
        "callCount": int(raw.get("callCount") or 0),
    }


def _agent_body(
    raw: dict[str, Any],
    *,
    skills: dict[str, dict[str, Any]],
    kbs: dict[str, dict[str, Any]],
    workflows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    tools = [
        {
            "id": catalog_id("skill", key),
            "name": skills[key]["name"],
            "type": skills[key].get("type", "Skill"),
            "enabled": True,
        }
        for key in (raw.get("skillKeys") or [])
    ]
    knowledge_refs = [
        {
            "id": catalog_id("kb", key),
            "name": kbs[key]["name"],
            "scope": kbs[key].get("scope", "部门"),
            "enabled": True,
        }
        for key in (raw.get("kbKeys") or [])
    ]
    flow_refs = [
        {
            "id": catalog_id("workflow", key),
            "name": workflows[key]["name"],
            "trigger": workflows[key].get("trigger", "消息触发"),
            "enabled": True,
        }
        for key in (raw.get("workflowKeys") or [])
    ]
    return {
        "name": raw["name"],
        "description": raw.get("description", ""),
        "category": raw.get("category", "企业通用"),
        "owner": raw.get("owner", "管理员"),
        "model": raw.get("model", ""),
        "status": raw.get("status", "draft"),
        "tone": raw.get("tone", "brand"),
        "tags": list(raw.get("tags") or []),
        "visibleScope": list(raw.get("visibleScope") or ["部门"]),
        "dataAccess": raw.get("dataAccess", ""),
        "maxSteps": int(raw.get("maxSteps") or 8),
        "tools": tools,
        "prompts": dict(raw.get("prompts") or {}),
        "memoryPolicy": dict(raw.get("memoryPolicy") or {}),
        "knowledgeRefs": knowledge_refs,
        "flowRefs": flow_refs,
    }


def build_assets() -> list[Asset]:
    """把清单变成**按依赖顺序排好**的落库资产 ✓.

    * id 全部确定性 ✓（``uuid5`` ✓）。
    * 智能体的技能 / 知识 / 工作流引用在**这里**就换成真实 id ✓。
    """
    raw = load_catalog()

    skills = {item["key"]: _skill_body(item) for item in raw.get("skills") or []}
    kbs = {item["key"]: _kb_body(item) for item in raw.get("knowledgeBases") or []}
    agents = {item["key"]: item for item in raw.get("agents") or []}
    agent_ids = {key: catalog_id("agent", key) for key in agents}
    workflows = {
        item["key"]: _workflow_body(item, agent_ids=agent_ids)
        for item in raw.get("workflows") or []
    }

    assets: list[Asset] = []

    for key, body in skills.items():
        assets.append(
            Asset(
                kind="skill", key=key, id=catalog_id("skill", key), path=_PATHS["skill"], body=body
            )
        )

    for key, body in kbs.items():
        assets.append(
            Asset(kind="kb", key=key, id=catalog_id("kb", key), path=_PATHS["kb"], body=body)
        )

    for kb_raw in raw.get("knowledgeBases") or []:
        kb_id = catalog_id("kb", kb_raw["key"])
        for doc in kb_raw.get("docs") or []:
            assets.append(
                Asset(
                    kind="doc",
                    key=doc["key"],
                    id=catalog_id("doc", doc["key"]),
                    path=_PATHS["doc"],
                    body={
                        "kbId": kb_id,
                        "name": doc["name"],
                        "content": doc.get("content", ""),
                        "type": "manual",
                    },
                )
            )

    for key, body in workflows.items():
        assets.append(
            Asset(
                kind="workflow",
                key=key,
                id=catalog_id("workflow", key),
                path=_PATHS["workflow"],
                body=body,
            )
        )

    for key, item in agents.items():
        assets.append(
            Asset(
                kind="agent",
                key=key,
                id=catalog_id("agent", key),
                path=_PATHS["agent"],
                body=_agent_body(item, skills=skills, kbs=kbs, workflows=workflows),
            )
        )

    for suite in raw.get("evalSuites") or []:
        assets.append(
            Asset(
                kind="evalSuite",
                key=suite["key"],
                id=catalog_id("evalSuite", suite["key"]),
                path=_PATHS["evalSuite"],
                body={
                    "name": suite["name"],
                    "description": suite.get("description", ""),
                    "type": suite.get("type", "capability"),
                    "owner": suite.get("owner", "评测团队"),
                    "schedule": suite.get("schedule", "手动"),
                    "target": agent_ids.get(suite.get("agentKey", ""), ""),
                    "casesList": list(suite.get("casesList") or []),
                    "criteria": suite.get("criteria", ""),
                },
            )
        )

    return assets
