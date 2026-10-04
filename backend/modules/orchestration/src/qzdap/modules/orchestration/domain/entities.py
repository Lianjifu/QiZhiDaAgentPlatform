"""Admin workflow aggregate — fields match frontend `features/workflows/schema.ts`."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Literal, Self
from uuid import UUID

FlowStatus = Literal["draft", "published", "retired"]
TriggerType = Literal["消息触发", "定时触发", "事件触发", "手动触发"]

FLOW_STATUSES = frozenset({"draft", "published", "retired"})
TRIGGER_TYPES = frozenset({"消息触发", "定时触发", "事件触发", "手动触发"})

_DEFAULT_NODES: list[dict[str, Any]] = [
    {
        "id": "n-trigger",
        "type": "flowNode",
        "position": {"x": 40, "y": 120},
        "data": {
            "label": "手动触发",
            "subtitle": "开始",
            "kind": "trigger",
            "config": {"trigger": "手动触发"},
            "outputs": [{"name": "started_at", "type": "string"}],
        },
    },
    {
        "id": "n-end",
        "type": "flowNode",
        "position": {"x": 360, "y": 120},
        "data": {
            "label": "结束",
            "subtitle": "完成",
            "kind": "end",
            "config": {"action": "done"},
        },
    },
]
_DEFAULT_EDGES: list[dict[str, Any]] = [
    {"id": "e1", "source": "n-trigger", "target": "n-end"},
]


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


def count_ports(nodes: list[dict[str, Any]]) -> tuple[int, int]:
    inputs = 0
    outputs = 0
    for node in nodes:
        data = node.get("data") if isinstance(node, dict) else None
        if not isinstance(data, dict):
            continue
        inputs += len(data.get("inputs") or [])
        outputs += len(data.get("outputs") or [])
    return inputs, outputs


def cadence_from_trigger(trigger: str) -> str:
    if "定时" in trigger:
        return "按计划自动运行"
    if "消息" in trigger:
        return "消息触发"
    if "事件" in trigger:
        return "事件触发"
    return "手动启动"


def step_labels(nodes: list[dict[str, Any]]) -> list[str]:
    labels: list[str] = []
    for node in nodes:
        data = node.get("data") if isinstance(node, dict) else None
        if not isinstance(data, dict):
            continue
        label = data.get("label")
        if label:
            labels.append(str(label))
    return labels or ["确认输入", "执行步骤", "查看结果"]


@dataclass(slots=True)
class FlowVersion:
    v: str
    at: str
    operator: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {"v": self.v, "at": self.at, "operator": self.operator, "note": self.note}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Self:
        return cls(
            v=str(raw.get("v") or ""),
            at=str(raw.get("at") or ""),
            operator=str(raw.get("operator") or ""),
            note=str(raw.get("note") or ""),
        )


@dataclass(slots=True)
class FlowRun:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    user_id: UUID
    workflow_id: UUID
    name: str
    time: str
    result: str
    created_at: datetime = field(default_factory=_utcnow)

    def to_catalog_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "time": self.time,
            "result": self.result,
        }


@dataclass(slots=True)
class Workflow:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    name: str
    description: str
    owner: str
    scene: str
    trigger: TriggerType
    status: FlowStatus
    call_count: int
    inputs: int
    outputs: int
    created_at: datetime
    updated_at: datetime
    bound_agents: list[str] = field(default_factory=list)
    versions: list[FlowVersion] = field(default_factory=list)
    initial_nodes: list[dict[str, Any]] = field(default_factory=list)
    initial_edges: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        tenant_id: UUID,
        workspace_id: UUID,
        name: str,
        description: str,
        owner: str,
        scene: str,
        trigger: TriggerType,
        initial_nodes: list[dict[str, Any]] | None = None,
        initial_edges: list[dict[str, Any]] | None = None,
        bound_agents: list[str] | None = None,
        status: FlowStatus = "draft",
        call_count: int = 0,
    ) -> Self:
        now = _utcnow()
        nodes = list(initial_nodes) if initial_nodes else list(_DEFAULT_NODES)
        edges = list(initial_edges) if initial_edges else list(_DEFAULT_EDGES)
        ins, outs = count_ports(nodes)
        return cls(
            id=id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name.strip() or "未命名工作流",
            description=description or "尚未填写描述",
            owner=owner or "当前管理员",
            scene=scene or "团队协作",
            trigger=trigger,
            status=status if status in FLOW_STATUSES else "draft",
            call_count=call_count,
            inputs=ins or 1,
            outputs=outs or 1,
            created_at=now,
            updated_at=now,
            bound_agents=list(bound_agents or []),
            versions=[
                FlowVersion(
                    v="v0.1-草稿",
                    at="刚刚",
                    operator=owner or "当前管理员",
                    note="新建工作流",
                )
            ],
            initial_nodes=nodes,
            initial_edges=edges,
        )

    def apply_patch(self, patch: dict[str, Any], *, actor: str) -> Self:
        data: dict[str, Any] = {}
        if patch.get("name"):
            data["name"] = str(patch["name"]).strip()
        if "description" in patch:
            data["description"] = str(patch["description"])
        if patch.get("owner"):
            data["owner"] = str(patch["owner"])
        if patch.get("scene"):
            data["scene"] = str(patch["scene"])
        if patch.get("trigger") in TRIGGER_TYPES:
            data["trigger"] = patch["trigger"]
        if "boundAgents" in patch and isinstance(patch["boundAgents"], list):
            data["bound_agents"] = [str(item) for item in patch["boundAgents"]]
        if "initialNodes" in patch and isinstance(patch["initialNodes"], list):
            nodes = [item for item in patch["initialNodes"] if isinstance(item, dict)]
            data["initial_nodes"] = nodes
            ins, outs = count_ports(nodes)
            data["inputs"] = ins or 1
            data["outputs"] = outs or 1
        if "initialEdges" in patch and isinstance(patch["initialEdges"], list):
            data["initial_edges"] = [
                item for item in patch["initialEdges"] if isinstance(item, dict)
            ]
        if "versions" in patch and isinstance(patch["versions"], list):
            data["versions"] = [
                FlowVersion.from_dict(item) for item in patch["versions"] if isinstance(item, dict)
            ]
        data["updated_at"] = _utcnow()
        next_flow = replace(self, **data)
        if patch.get("status") in FLOW_STATUSES and patch["status"] != self.status:
            if patch["status"] == "published":
                return next_flow.publish(actor=actor)
            if patch["status"] == "retired":
                return next_flow.retire(actor=actor)
            return replace(next_flow, status="draft")
        return next_flow

    def publish(self, *, actor: str) -> Self:
        versions = list(self.versions)
        next_version = f"v{len(self.versions) + 1}.0"
        versions.insert(
            0,
            FlowVersion(v=next_version, at="刚刚", operator=actor, note="发布工作流"),
        )
        return replace(
            self,
            status="published",
            versions=versions[:20],
            updated_at=_utcnow(),
        )

    def retire(self, *, actor: str) -> Self:
        _ = actor
        return replace(self, status="retired", updated_at=_utcnow())

    def bump_call(self) -> Self:
        return replace(self, call_count=self.call_count + 1, updated_at=_utcnow())

    def to_admin_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "owner": self.owner,
            "scene": self.scene,
            "trigger": self.trigger,
            "status": self.status,
            "callCount": self.call_count,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "createdAt": self.created_at.astimezone(UTC).strftime("%Y-%m-%d"),
            "updatedAt": format_last_update(self.updated_at),
            "boundAgents": list(self.bound_agents),
            "versions": [item.to_dict() for item in self.versions],
            "initialNodes": list(self.initial_nodes),
            "initialEdges": list(self.initial_edges),
        }

    def to_catalog_dict(self) -> dict[str, Any]:
        available = self.status == "published"
        return {
            "id": str(self.id),
            "name": self.name,
            "scene": self.scene,
            "description": self.description,
            "owner": self.owner,
            "cadence": cadence_from_trigger(self.trigger),
            "availability": "available" if available else "unavailable",
            "steps": step_labels(self.initial_nodes),
            "lastRun": format_last_update(self.updated_at),
            "usage": self.call_count,
        }


__all__ = [
    "FLOW_STATUSES",
    "TRIGGER_TYPES",
    "FlowRun",
    "FlowStatus",
    "FlowVersion",
    "TriggerType",
    "Workflow",
    "cadence_from_trigger",
    "count_ports",
    "format_last_update",
    "step_labels",
]
