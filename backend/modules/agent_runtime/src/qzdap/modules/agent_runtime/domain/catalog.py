"""Admin agent catalog aggregate — fields match frontend `features/agents/schema.ts`."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Literal, Self
from uuid import UUID

AgentStatus = Literal["draft", "pending", "graying", "published", "retired"]
Tone = Literal["brand", "info", "success", "warn", "danger", "purple"]
MemoryScope = Literal["session", "user", "tenant"]
VisibleScope = Literal["公开", "部门", "个人"]

AGENT_STATUSES = frozenset({"draft", "pending", "graying", "published", "retired"})
TONES = frozenset({"brand", "info", "success", "warn", "danger", "purple"})
MEMORY_SCOPES = frozenset({"session", "user", "tenant"})
VISIBLE_SCOPES = frozenset({"公开", "部门", "个人"})


def _utcnow() -> datetime:
    return datetime.now(UTC)


def format_last_update(moment: datetime) -> str:
    now = _utcnow()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    seconds = max(0, (now - moment.astimezone(UTC)).total_seconds())
    if seconds < 120:
        return "刚刚"
    if seconds < 3600:
        return f"{int(seconds // 60)} 分钟前"
    if seconds < 86400:
        return f"{int(seconds // 3600)} 小时前"
    return moment.astimezone(UTC).strftime("%Y-%m-%d")


def _empty_prompts() -> dict[str, str]:
    return {"prompt": "", "soul": "", "agents": "", "user": "", "tools": ""}


def _default_memory() -> dict[str, Any]:
    return {"enabled": True, "retentionDays": 30, "scope": "user", "autoSummarize": True}


@dataclass(slots=True)
class CatalogAgent:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    name: str
    description: str
    category: str
    owner: str
    status: AgentStatus
    version: str
    updated_at: datetime
    created_at: datetime
    tags: list[str] = field(default_factory=list)
    tone: Tone = "brand"
    calls: int = 0
    success_rate: float = 0.0
    error_rate: float = 0.0
    avg_latency_ms: int = 0
    rating: float = 0.0
    starred: bool = False
    visible_scope: list[VisibleScope] = field(default_factory=lambda: ["部门"])
    data_access: str = ""
    model: str = ""
    max_steps: int = 8
    tools: list[dict[str, Any]] = field(default_factory=list)
    versions: list[dict[str, Any]] = field(default_factory=list)
    evaluation_pass_rate: float = 0.0
    evaluation_runs: int = 0
    evaluation_failed_cases: int = 0
    trend: list[int] = field(default_factory=lambda: [0] * 12)
    prompts: dict[str, str] = field(default_factory=_empty_prompts)
    custom_prompts: list[dict[str, Any]] = field(default_factory=list)
    knowledge_refs: list[dict[str, Any]] = field(default_factory=list)
    memory_policy: dict[str, Any] = field(default_factory=_default_memory)
    flow_refs: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        name: str,
        category: str,
        owner: str,
        description: str = "",
        model: str = "",
    ) -> Self:
        now = _utcnow()
        return cls(
            id=id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name.strip() or "未命名智能体",
            description=description,
            category=category or "企业通用",
            owner=owner or "管理员",
            status="draft",
            version="draft",
            updated_at=now,
            created_at=now,
            model=model,
        )

    def apply_patch(self, patch: dict[str, Any]) -> Self:
        data: dict[str, Any] = {}
        mapping = {
            "name": "name",
            "description": "description",
            "category": "category",
            "owner": "owner",
            "version": "version",
            "dataAccess": "data_access",
            "model": "model",
        }
        for src, dest in mapping.items():
            if src in patch and patch[src] is not None:
                data[dest] = str(patch[src])
        if "status" in patch and patch["status"] in AGENT_STATUSES:
            data["status"] = patch["status"]
        if "tone" in patch and patch["tone"] in TONES:
            data["tone"] = patch["tone"]
        if "starred" in patch:
            data["starred"] = bool(patch["starred"])
        if "maxSteps" in patch:
            data["max_steps"] = max(1, min(int(patch["maxSteps"]), 16))
        if "tags" in patch and isinstance(patch["tags"], list):
            data["tags"] = [str(item) for item in patch["tags"]]
        if "visibleScope" in patch and isinstance(patch["visibleScope"], list):
            data["visible_scope"] = [
                item for item in patch["visibleScope"] if item in VISIBLE_SCOPES
            ] or ["部门"]
        if "tools" in patch and isinstance(patch["tools"], list):
            data["tools"] = [item for item in patch["tools"] if isinstance(item, dict)]
        if "prompts" in patch and isinstance(patch["prompts"], dict):
            data["prompts"] = {**_empty_prompts(), **{k: str(v) for k, v in patch["prompts"].items()}}
        if "customPrompts" in patch and isinstance(patch["customPrompts"], list):
            data["custom_prompts"] = [item for item in patch["customPrompts"] if isinstance(item, dict)]
        if "knowledgeRefs" in patch and isinstance(patch["knowledgeRefs"], list):
            data["knowledge_refs"] = [item for item in patch["knowledgeRefs"] if isinstance(item, dict)]
        if "memoryPolicy" in patch and isinstance(patch["memoryPolicy"], dict):
            policy = {**_default_memory(), **patch["memoryPolicy"]}
            if policy.get("scope") not in MEMORY_SCOPES:
                policy["scope"] = "user"
            data["memory_policy"] = policy
        if "flowRefs" in patch and isinstance(patch["flowRefs"], list):
            data["flow_refs"] = [item for item in patch["flowRefs"] if isinstance(item, dict)]
        data["updated_at"] = _utcnow()
        next_agent = replace(self, **data)
        if next_agent.status == "published" and self.status != "published":
            return next_agent.publish()
        return next_agent

    def publish(self) -> Self:
        stamp = _utcnow().strftime("%Y-%m-%d")
        versions = [{**item, "current": False} for item in self.versions]
        next_version = f"v{len(self.versions) + 1}"
        versions.insert(
            0,
            {"version": next_version, "publisher": self.owner, "releasedAt": stamp, "current": True},
        )
        return replace(
            self,
            status="published",
            version=next_version,
            versions=versions,
            updated_at=_utcnow(),
        )

    def to_admin_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "owner": self.owner,
            "tags": list(self.tags),
            "tone": self.tone,
            "status": self.status,
            "version": self.version,
            "lastUpdate": format_last_update(self.updated_at),
            "createdAt": self.created_at.astimezone(UTC).strftime("%Y-%m-%d"),
            "calls": self.calls,
            "successRate": self.success_rate,
            "errorRate": self.error_rate,
            "avgLatencyMs": self.avg_latency_ms,
            "rating": self.rating,
            "tools": list(self.tools),
            "starred": self.starred,
            "visibleScope": list(self.visible_scope),
            "dataAccess": self.data_access,
            "model": self.model,
            "maxSteps": self.max_steps,
            "versions": list(self.versions),
            "evaluationPassRate": self.evaluation_pass_rate,
            "evaluationRuns": self.evaluation_runs,
            "evaluationFailedCases": self.evaluation_failed_cases,
            "trend": list(self.trend),
            "prompts": dict(self.prompts),
            "customPrompts": list(self.custom_prompts),
            "knowledgeRefs": list(self.knowledge_refs),
            "memoryPolicy": dict(self.memory_policy),
            "flowRefs": list(self.flow_refs),
        }

    def to_catalog_dict(self) -> dict[str, Any]:
        category = self.category
        if "销售" in category:
            mapped = "销售支持"
        elif "客服" in category:
            mapped = "客服应答"
        elif "数据" in category:
            mapped = "数据分析"
        elif "文案" in category or "写作" in category:
            mapped = "文案创作"
        else:
            mapped = "企业通用"
        example = next(
            (
                line.strip("- ").strip()
                for line in (self.prompts.get("user") or "").splitlines()
                if line.strip().startswith("-")
            ),
            f"请用「{self.name}」帮我完成一项与{mapped}相关的工作。",
        )
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "category": mapped,
            "owner": self.owner,
            "useCase": "、".join(self.tags[:2]) or f"{mapped}相关工作",
            "input": f"与「{self.data_access}」相关的上下文" if self.data_access else "任务目标与必要背景",
            "output": "结构化结论与可执行建议",
            "example": example,
            "tone": self.tone,
        }


def is_workspace_visible(scopes: list[str]) -> bool:
    return any(scope in {"公开", "部门"} for scope in scopes)


__all__ = ["CatalogAgent", "format_last_update", "is_workspace_visible"]
