"""Admin skill aggregate — fields match frontend `features/skills/schema.ts`."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Literal, Self
from uuid import UUID

SkillType = Literal["Skill", "Tool", "MCP"]
SkillStatus = Literal["published", "draft", "graying", "retired"]
RiskLevel = Literal["low", "medium", "high"]
VisibleScope = Literal["公开", "部门", "个人"]

SCHEMA_FIELD_TYPES = frozenset({"string", "number", "boolean", "object", "array"})
SKILL_TYPES = frozenset({"Skill", "Tool", "MCP"})
SKILL_STATUSES = frozenset({"published", "draft", "graying", "retired"})
RISK_LEVELS = frozenset({"low", "medium", "high"})
VISIBLE_SCOPES = frozenset({"公开", "部门", "个人"})


def _utcnow() -> datetime:
    return datetime.now(UTC)


def format_last_update(moment: datetime) -> str:
    now = _utcnow()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    seconds = max(0, (now - moment).total_seconds())
    if seconds < 120:
        return "刚刚"
    if seconds < 3600:
        return f"{int(seconds // 60)} 分钟前"
    if seconds < 86400:
        return f"{int(seconds // 3600)} 小时前"
    if seconds < 86400 * 7:
        return f"{int(seconds // 86400)} 天前"
    return moment.astimezone(UTC).strftime("%Y-%m-%d %H:%M")


@dataclass(slots=True)
class SchemaField:
    name: str
    type: str
    required: bool
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Self:
        field_type = str(raw.get("type") or "string")
        if field_type not in SCHEMA_FIELD_TYPES:
            field_type = "string"
        return cls(
            name=str(raw.get("name") or ""),
            type=field_type,
            required=bool(raw.get("required", False)),
            description=str(raw.get("description") or ""),
        )


@dataclass(slots=True)
class VersionEntry:
    version: str
    publisher: str
    released_at: str
    current: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "publisher": self.publisher,
            "releasedAt": self.released_at,
            "current": self.current,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Self:
        return cls(
            version=str(raw.get("version") or ""),
            publisher=str(raw.get("publisher") or ""),
            released_at=str(raw.get("releasedAt") or raw.get("released_at") or ""),
            current=bool(raw.get("current", False)),
        )


DEFAULT_RUNTIME_IMAGE = "qzdap/sandbox-python:latest"


@dataclass(slots=True)
class SkillRuntime:
    enabled: bool = False
    language: str = "python"
    image: str = DEFAULT_RUNTIME_IMAGE
    entry: str = "main.py"
    source: str = ""
    timeout_ms: int = 30_000
    network: str = "none"
    memory_mb: int = 256

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "language": self.language,
            "image": self.image,
            "entry": self.entry,
            "source": self.source,
            "timeoutMs": self.timeout_ms,
            "network": self.network,
            "memoryMb": self.memory_mb,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> Self:
        data = raw or {}
        language = str(data.get("language") or "python")
        if language not in {"python"}:
            language = "python"
        network = str(data.get("network") or "none")
        if network not in {"none", "bridge"}:
            network = "none"
        entry = str(data.get("entry") or "main.py").replace("\\", "/").split("/")[-1]
        if not entry or entry in {".", ".."}:
            entry = "main.py"
        timeout_ms = int(data.get("timeoutMs") or data.get("timeout_ms") or 30_000)
        memory_mb = int(data.get("memoryMb") or data.get("memory_mb") or 256)
        return cls(
            enabled=bool(data.get("enabled", False)),
            language=language,
            image=str(data.get("image") or DEFAULT_RUNTIME_IMAGE),
            entry=entry,
            source=str(data.get("source") or ""),
            timeout_ms=max(1, min(timeout_ms, 120_000)),
            network=network,
            memory_mb=max(32, min(memory_mb, 4096)),
        )


@dataclass(slots=True)
class AuditEntry:
    time: str
    actor: str
    action: str

    def to_dict(self) -> dict[str, Any]:
        return {"time": self.time, "actor": self.actor, "action": self.action}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Self:
        return cls(
            time=str(raw.get("time") or ""),
            actor=str(raw.get("actor") or ""),
            action=str(raw.get("action") or ""),
        )


@dataclass(slots=True)
class Skill:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    name: str
    description: str
    type: SkillType
    owner: str
    status: SkillStatus
    version: str
    updated_at: datetime
    created_at: datetime
    calls: int = 0
    success_rate: float = 0.0
    error_rate: float = 0.0
    avg_latency_ms: int = 0
    rating: float = 0.0
    risk: RiskLevel = "low"
    need_confirm: bool = False
    visible_scope: list[VisibleScope] = field(default_factory=lambda: ["部门"])
    tags: list[str] = field(default_factory=list)
    starred: bool = False
    input_schema: list[SchemaField] = field(default_factory=list)
    output_schema: list[SchemaField] = field(default_factory=list)
    versions: list[VersionEntry] = field(default_factory=list)
    trend: list[int] = field(default_factory=lambda: [0] * 12)
    used_by_agents: list[str] = field(default_factory=list)
    audit_log: list[AuditEntry] = field(default_factory=list)
    runtime: SkillRuntime = field(default_factory=SkillRuntime)

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        name: str,
        description: str,
        type: SkillType,
        owner: str,
        risk: RiskLevel,
        need_confirm: bool,
        input_schema: list[SchemaField],
        output_schema: list[SchemaField],
    ) -> Self:
        if type not in SKILL_TYPES:
            raise ValueError(f"invalid skill type: {type}")
        if risk not in RISK_LEVELS:
            raise ValueError(f"invalid risk: {risk}")
        now = _utcnow()
        confirm = need_confirm or risk != "low"
        return cls(
            id=id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name.strip(),
            description=description,
            type=type,
            owner=owner,
            status="draft",
            version="draft",
            updated_at=now,
            created_at=now,
            risk=risk,
            need_confirm=confirm,
            input_schema=list(input_schema),
            output_schema=list(output_schema),
            audit_log=[AuditEntry(time="刚刚", actor=owner, action="新建技能")],
        )

    def apply_patch(self, patch: dict[str, Any], *, actor: str) -> Self:
        data: dict[str, Any] = {}
        if patch.get("name"):
            data["name"] = str(patch["name"]).strip()
        if "description" in patch:
            data["description"] = str(patch["description"])
        if patch.get("owner"):
            data["owner"] = str(patch["owner"])
        if patch.get("version"):
            data["version"] = str(patch["version"])
        if "type" in patch and patch["type"] in SKILL_TYPES:
            data["type"] = patch["type"]
        if "status" in patch and patch["status"] in SKILL_STATUSES:
            data["status"] = patch["status"]
        if "risk" in patch and patch["risk"] in RISK_LEVELS:
            data["risk"] = patch["risk"]
        if "needConfirm" in patch:
            data["need_confirm"] = bool(patch["needConfirm"])
        if "visibleScope" in patch and isinstance(patch["visibleScope"], list):
            data["visible_scope"] = [
                item for item in patch["visibleScope"] if item in VISIBLE_SCOPES
            ] or ["部门"]
        if "tags" in patch and isinstance(patch["tags"], list):
            data["tags"] = [str(item) for item in patch["tags"]]
        if "starred" in patch:
            data["starred"] = bool(patch["starred"])
        if "inputSchema" in patch and isinstance(patch["inputSchema"], list):
            data["input_schema"] = [
                SchemaField.from_dict(item) for item in patch["inputSchema"] if isinstance(item, dict)
            ]
        if "outputSchema" in patch and isinstance(patch["outputSchema"], list):
            data["output_schema"] = [
                SchemaField.from_dict(item) for item in patch["outputSchema"] if isinstance(item, dict)
            ]
        if "runtime" in patch and isinstance(patch["runtime"], dict):
            data["runtime"] = SkillRuntime.from_dict(patch["runtime"])
        data["updated_at"] = _utcnow()
        next_skill = replace(self, **data)
        log = list(self.audit_log)
        log.insert(0, AuditEntry(time="刚刚", actor=actor, action="更新技能"))
        next_skill.audit_log = log[:50]
        if next_skill.status == "published" and self.status != "published":
            return next_skill.publish(actor=actor)
        if next_skill.status == "retired" and self.status != "retired":
            return next_skill.retire(actor=actor)
        return next_skill

    def publish(self, *, actor: str) -> Self:
        stamp = _utcnow().strftime("%Y-%m-%d")
        versions = [
            replace(item, current=False) for item in self.versions
        ]
        next_version = f"v{len(self.versions) + 1}"
        versions.insert(
            0,
            VersionEntry(
                version=next_version,
                publisher=actor,
                released_at=stamp,
                current=True,
            ),
        )
        log = list(self.audit_log)
        log.insert(0, AuditEntry(time="刚刚", actor=actor, action="发布技能"))
        return replace(
            self,
            status="published",
            version=next_version,
            versions=versions,
            updated_at=_utcnow(),
            audit_log=log[:50],
        )

    def retire(self, *, actor: str) -> Self:
        log = list(self.audit_log)
        log.insert(0, AuditEntry(time="刚刚", actor=actor, action="下线技能"))
        return replace(
            self,
            status="retired",
            updated_at=_utcnow(),
            audit_log=log[:50],
        )

    def bump_call(self) -> Self:
        trend = list(self.trend or [0] * 12)
        if len(trend) < 12:
            trend = ([0] * (12 - len(trend))) + trend
        trend = trend[1:] + [trend[-1] + 1]
        return replace(
            self,
            calls=self.calls + 1,
            trend=trend[-12:],
            updated_at=_utcnow(),
        )

    def record_outcome(self, *, ok: bool, latency_ms: int) -> Self:
        prev = max(0, self.calls)
        successes = (self.success_rate / 100.0) * prev
        errors = (self.error_rate / 100.0) * prev
        if ok:
            successes += 1
        else:
            errors += 1
        calls = prev + 1
        bumped = self.bump_call()
        return replace(
            bumped,
            success_rate=round(100.0 * successes / calls, 2),
            error_rate=round(100.0 * errors / calls, 2),
            avg_latency_ms=int((self.avg_latency_ms * prev + max(0, latency_ms)) / calls),
        )

    def to_admin_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "owner": self.owner,
            "status": self.status,
            "version": self.version,
            "lastUpdate": format_last_update(self.updated_at),
            "calls": self.calls,
            "successRate": self.success_rate,
            "errorRate": self.error_rate,
            "avgLatencyMs": self.avg_latency_ms,
            "rating": self.rating,
            "risk": self.risk,
            "needConfirm": self.need_confirm,
            "visibleScope": list(self.visible_scope),
            "tags": list(self.tags),
            "starred": self.starred,
            "inputSchema": [item.to_dict() for item in self.input_schema],
            "outputSchema": [item.to_dict() for item in self.output_schema],
            "versions": [item.to_dict() for item in self.versions],
            "trend": list(self.trend),
            "usedByAgents": list(self.used_by_agents),
            "auditLog": [item.to_dict() for item in self.audit_log],
            "runtime": self.runtime.to_dict(),
        }

    def to_catalog_dict(self, *, last_used: str | None = None) -> dict[str, Any]:
        input_desc = "；".join(
            field.description or field.name for field in self.input_schema if field.name or field.description
        )
        output_desc = "；".join(
            field.description or field.name for field in self.output_schema if field.name or field.description
        )
        available = self.status in {"published", "graying"}
        return {
            "id": str(self.id),
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "owner": self.owner,
            "useCase": "、".join(self.tags[:2]) or self.description,
            "input": input_desc or "按能力说明提供输入",
            "output": output_desc or "结构化结果",
            "risk": "needsConfirm" if self.need_confirm or self.risk != "low" else "low",
            "status": "available" if available else "unavailable",
            "tags": list(self.tags),
            "lastUsed": last_used or format_last_update(self.updated_at),
            "relatedAgents": list(self.used_by_agents),
            "runtimeEnabled": self.runtime.enabled,
        }


def is_workspace_visible(scopes: list[str]) -> bool:
    return any(scope in {"公开", "部门"} for scope in scopes)


__all__ = [
    "AuditEntry",
    "RiskLevel",
    "SchemaField",
    "Skill",
    "SkillRuntime",
    "SkillStatus",
    "SkillType",
    "VersionEntry",
    "VisibleScope",
    "format_last_update",
    "is_workspace_visible",
]
