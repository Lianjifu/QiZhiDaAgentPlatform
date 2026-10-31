"""``CatalogAgentRouter`` —— **每一步选专家** ✓（Agent 方案 §4.1 ✓）。

⚠️ **专家 = 一份 agent 配置** ✓（§4.2 ✓）—— 选的是**目录里已发布的专家**
✓（不是会话绑定 agent 的子集 ✓ —— §4.2 规则 5 ✓）。

⚠️ **匹配规则**（**确定性** ✓ —— 同样的输入永远选到同一个专家 ✓）：

| # | 规则 |
|---|---|
| 1 | 分类置信度 **低于阈值** → **不选专家** ✓（落回会话绑定 ✓） |
| 2 | 专家的 ``profile.task_kinds`` **显式声明**了当前任务类型 → 命中 ✓（优先 ✓） |
| 3 | 否则按 **category 关键词**匹配 ✓（研究 / 调研 → 深度研究 ✓ ……） |
| 4 | 命中多个 → 取**最近更新**的那个 ✓（目录的默认排序 ✓） |
| 5 | 都没命中 → **落回会话绑定** ✓（**不报错** ✓ —— §4.1 规则 2 ✓） |

⚠️ **落回时也要带出配置** ✓（模型名 ✓ / 版本 ✓）—— 否则落回的专家**没有模型**
✗✗（那就不是落回 ✓）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from qzdap.modules.agent_runtime.application.catalog import AgentCatalogService
from qzdap.modules.agent_runtime.application.ports import AgentCatalogLister
from qzdap_agent_runtime.agent_router.classifier import TaskKind
from qzdap_agent_runtime.ports import AgentRouterPort, AgentSelection

#: **category 关键词 → 任务类型** ✓（兜底匹配 ✓ —— 显式声明优先 ✓）。
_CATEGORY_KEYWORDS: dict[TaskKind, tuple[str, ...]] = {
    TaskKind.DEEP_RESEARCH: ("研究", "调研", "深度", "综述"),
    TaskKind.MULTI_STEP_CODE: ("代码", "编程", "开发", "工程"),
    TaskKind.DATA_INVESTIGATION: ("数据", "分析", "洞察", "报表"),
    TaskKind.SIMPLE_QA: ("通用", "问答", "客服", "企业通用"),
}


class CatalogAgentRouter(AgentRouterPort):
    """**从目录里选专家** ✓（§4.1 ✓）。"""

    def __init__(
        self,
        *,
        catalog: AgentCatalogLister,
        min_confidence: float = 0.5,
    ) -> None:
        self._catalog = catalog
        self._min_confidence = min_confidence

    async def select(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        session_agent_id: UUID,
        task_kind: TaskKind,
        confidence: float,
        tool_names: tuple[str, ...] = (),
    ) -> AgentSelection:
        """**选一个专家** ✓（没有就落回 ✓）。"""
        _ = (tenant_id, tool_names)
        rows = await self._catalog.list_published(workspace_id=workspace_id)
        if confidence >= self._min_confidence:
            for row in rows:
                if _matches(row, task_kind):
                    return _selection(row, task_kind, confidence, fell_back=False)
        # ⚠️ **落回会话绑定的 agent** ✓（不是报错 ✓ —— §4.1 规则 2 ✓）
        fallback = next((row for row in rows if str(row.get("id")) == str(session_agent_id)), None)
        if fallback is None:
            fallback = await self._safe_get(session_agent_id)
        if fallback is None:
            return AgentSelection(
                agent_id=session_agent_id,
                agent_version="",
                task_kind=task_kind,
                confidence=confidence,
                fell_back=True,
            )
        return _selection(fallback, task_kind, confidence, fell_back=True)

    async def _safe_get(self, agent_id: UUID) -> dict[str, Any] | None:
        try:
            return await self._catalog.get_admin(agent_id)
        except Exception:
            return None


def _matches(row: dict[str, Any], task_kind: TaskKind) -> bool:
    """**这个专家接这类活吗** ✓（显式声明优先 ✓）。"""
    profile = row.get("profile") or {}
    declared = profile.get("task_kinds") if isinstance(profile, dict) else None
    if isinstance(declared, list) and declared:
        return task_kind.value in {str(item) for item in declared}
    category = str(row.get("category") or "")
    return any(keyword in category for keyword in _CATEGORY_KEYWORDS[task_kind])


def _selection(
    row: dict[str, Any],
    task_kind: TaskKind,
    confidence: float,
    *,
    fell_back: bool,
) -> AgentSelection:
    """**目录行 → 选择结果** ✓（含模型名 ✓ 与指令 ✓）。"""
    prompts = row.get("prompts") or {}
    instruction = ""
    if isinstance(prompts, dict):
        instruction = str(prompts.get("prompt") or prompts.get("soul") or "")
    return AgentSelection(
        agent_id=UUID(str(row["id"])),
        agent_version=str(row.get("version") or ""),
        task_kind=task_kind,
        confidence=confidence,
        instruction=instruction or str(row.get("description") or ""),
        fell_back=fell_back,
        # ⚠️ **模型名来自专家配置** ✓（取值链的输入 ✓ —— §5.2.1 ✓）
        model_name=str(row.get("model") or ""),
    )


class CatalogAgentLister(AgentCatalogLister):
    """**`AgentCatalogService` 的窄适配** ✓（只暴露路由要用的两个能力 ✓）。"""

    def __init__(self, catalog: AgentCatalogService) -> None:
        self._catalog = catalog

    async def list_published(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        return await self._catalog.list_admin(workspace_id=workspace_id, tab="published")

    async def get_admin(self, agent_id: UUID) -> dict[str, Any]:
        return await self._catalog.get_admin(agent_id)


__all__ = ["CatalogAgentLister", "CatalogAgentRouter"]
