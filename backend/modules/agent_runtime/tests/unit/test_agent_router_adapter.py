"""Agent Stage 4（模块侧）：**专家路由** ✓（Agent 方案 §4.1 ✓）。

验收三条 ✓：**显式声明优先** ✓ / **低置信度不选专家** ✓ / **没有专家就落回会话绑定** ✓。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from qzdap_agent_runtime.agent_router.classifier import TaskKind
from qzdap.modules.agent_runtime.adapter.tools.agent_router_adapter import (
    CatalogAgentRouter,
)

TENANT = uuid4()
WORKSPACE = uuid4()
SESSION_AGENT = uuid4()


def _row(
    agent_id: UUID,
    *,
    name: str = "专家",
    category: str = "企业通用",
    version: str = "v1",
    model: str = "deepseek-chat",
    profile: dict[str, Any] | None = None,
    status: str = "published",
) -> dict[str, Any]:
    return {
        "id": str(agent_id),
        "name": name,
        "category": category,
        "version": version,
        "model": model,
        "profile": profile or {},
        "prompts": {"prompt": f"{name}的指令"},
        "description": "",
        "status": status,
    }


class _Catalog:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    async def list_published(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        return list(self._rows)

    async def get_admin(self, agent_id: UUID) -> dict[str, Any]:
        for row in self._rows:
            if row["id"] == str(agent_id):
                return row
        raise KeyError(str(agent_id))


class TestCatalogAgentRouter:
    @pytest.mark.asyncio
    async def test_the_explicit_task_kind_wins(self) -> None:
        """**`profile.task_kinds` 显式声明** ✓（优先于关键词 ✓）。"""
        expert = uuid4()
        router = CatalogAgentRouter(
            catalog=_Catalog(  # type: ignore[arg-type]
                [
                    _row(expert, name="研究员", profile={"task_kinds": ["DEEP_RESEARCH"]}),
                    _row(uuid4(), name="码农", category="代码工程"),
                ]
            )
        )
        selection = await router.select(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            session_agent_id=SESSION_AGENT,
            task_kind=TaskKind.DEEP_RESEARCH,
            confidence=0.9,
        )
        assert selection.agent_id == expert
        assert selection.fell_back is False
        assert selection.model_name == "deepseek-chat"
        assert selection.instruction == "研究员的指令"

    @pytest.mark.asyncio
    async def test_the_category_keyword_matches(self) -> None:
        """**category 关键词兜底** ✓。"""
        expert = uuid4()
        router = CatalogAgentRouter(
            catalog=_Catalog(  # type: ignore[arg-type]
                [_row(expert, name="码农", category="代码工程")]
            )
        )
        selection = await router.select(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            session_agent_id=SESSION_AGENT,
            task_kind=TaskKind.MULTI_STEP_CODE,
            confidence=0.9,
        )
        assert selection.agent_id == expert

    @pytest.mark.asyncio
    async def test_the_low_confidence_falls_back_to_the_session_agent(self) -> None:
        """**置信度不够就不选专家** ✓（落回 ✓ 不硬选 ✓）。"""
        expert = uuid4()
        router = CatalogAgentRouter(
            catalog=_Catalog(  # type: ignore[arg-type]
                [
                    _row(expert, name="研究员", profile={"task_kinds": ["DEEP_RESEARCH"]}),
                    _row(SESSION_AGENT, name="会话绑定", category="企业通用"),
                ]
            )
        )
        selection = await router.select(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            session_agent_id=SESSION_AGENT,
            task_kind=TaskKind.DEEP_RESEARCH,
            confidence=0.3,
        )
        assert selection.agent_id == SESSION_AGENT
        assert selection.fell_back is True

    @pytest.mark.asyncio
    async def test_no_expert_falls_back_to_the_session_agent(self) -> None:
        """**没有匹配的专家 → 落回** ✓（不报错 ✓）。"""
        router = CatalogAgentRouter(
            catalog=_Catalog(  # type: ignore[arg-type]
                [_row(SESSION_AGENT, name="会话绑定", category="企业通用")]
            )
        )
        selection = await router.select(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            session_agent_id=SESSION_AGENT,
            task_kind=TaskKind.DEEP_RESEARCH,
            confidence=0.9,
        )
        assert selection.agent_id == SESSION_AGENT
        assert selection.fell_back is True

    @pytest.mark.asyncio
    async def test_an_unknown_session_agent_still_falls_back(self) -> None:
        """**会话绑定的 agent 不在目录里** ✓ → 落回空配置 ✓（不崩 ✓）。"""
        router = CatalogAgentRouter(catalog=_Catalog([]))  # type: ignore[arg-type]
        selection = await router.select(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            session_agent_id=SESSION_AGENT,
            task_kind=TaskKind.SIMPLE_QA,
            confidence=0.9,
        )
        assert selection.agent_id == SESSION_AGENT
        assert selection.fell_back is True
        assert selection.model_name == ""
