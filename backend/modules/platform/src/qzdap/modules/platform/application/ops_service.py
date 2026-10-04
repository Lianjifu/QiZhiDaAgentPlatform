"""Admin console service — JSON documents matching frontend `/api/admin/*` schemas."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID, uuid4

from qzdap.modules.platform.adapter.persistence.ops_repositories import SqlAdminOpsRepository

CHANNEL_TEMPLATES = {
    "feishu": "你好，我是企业助手，可在飞书里查询知识与办理事项。",
    "wecom": "你好，我是企业微信客服助手。",
    "dingtalk": "你好，我是钉钉协作助手。",
    "web": "你好，我是企业智能助手。请直接在对话框里提问。",
}


class AdminOpsService:
    def __init__(self, repo: SqlAdminOpsRepository) -> None:
        self._repo = repo

    async def list_collection(
        self, *, tenant_id: UUID, workspace_id: UUID, collection: str
    ) -> list[dict[str, Any]]:
        _ = tenant_id
        return await self._repo.list_docs(workspace_id=workspace_id, collection=collection)

    async def get(
        self, *, tenant_id: UUID, workspace_id: UUID, collection: str, doc_key: str
    ) -> dict[str, Any]:
        _ = tenant_id
        row = await self._repo.get_doc(
            workspace_id=workspace_id, collection=collection, doc_key=doc_key
        )
        if row is None:
            raise KeyError(doc_key)
        return row

    async def create(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        collection: str,
        body: dict[str, Any],
        prefix: str,
    ) -> dict[str, Any]:
        await self.list_collection(tenant_id=tenant_id, workspace_id=workspace_id, collection=collection)
        key = str(body.get("id") or f"{prefix}-{uuid4().hex[:8]}")
        payload = {**body, "id": key}
        return await self._repo.upsert_doc(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            collection=collection,
            doc_key=key,
            payload=payload,
        )

    async def patch(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        collection: str,
        doc_key: str,
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        current = await self.get(
            tenant_id=tenant_id, workspace_id=workspace_id, collection=collection, doc_key=doc_key
        )
        merged = {**current, **patch, "id": doc_key}
        return await self._repo.upsert_doc(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            collection=collection,
            doc_key=doc_key,
            payload=merged,
        )

    async def create_budget(self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]) -> dict[str, Any]:
        return await self.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            collection="quotas.budgets",
            prefix="bg",
            body={
                "name": str(body.get("name") or "未命名预算"),
                "period": body.get("period") or "monthly",
                "totalCap": int(body.get("totalCap") or 0),
                "used": 0,
                "forecast": 0,
                "rollover": bool(body.get("rollover")),
                "alertThreshold": int(body.get("alertThreshold") or 80),
                "status": "healthy",
                "effectiveDate": str(body.get("effectiveDate") or date.today().isoformat()),
                "owner": str(body.get("owner") or "未指定"),
                "description": "由管理员手动创建",
            },
        )

    async def create_alert(self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]) -> dict[str, Any]:
        notify = body.get("notify")
        if isinstance(notify, str):
            notify_list = [item.strip() for item in notify.split(",") if item.strip()]
        elif isinstance(notify, list):
            notify_list = [str(item) for item in notify]
        else:
            notify_list = []
        return await self.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            collection="quotas.alerts",
            prefix="al",
            body={
                "name": str(body.get("name") or "未命名告警"),
                "scope": body.get("scope") or "enterprise",
                "severity": body.get("severity") or "info",
                "metric": str(body.get("metric") or ""),
                "threshold": float(body.get("threshold") or 0),
                "enabled": True,
                "cooldown": str(body.get("cooldown") or "24h"),
                "notify": notify_list,
                "lastTriggered": "—",
                "description": "由管理员手动创建",
            },
        )

    async def create_channel(self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]) -> dict[str, Any]:
        kind = str(body.get("kind") or "web")
        return await self.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            collection="notifications.channels",
            prefix="ch",
            body={
                "name": str(body.get("name") or "未命名渠道"),
                "kind": kind,
                "status": "draft",
                "target": str(body.get("target") or ""),
                "description": str(body.get("description") or "由管理员手动创建"),
                "lastUsed": "从未",
                "successRate": 0,
                "sentToday": 0,
                "config": dict(body.get("config") or {}),
                "starred": False,
                "scope": [],
                "template": CHANNEL_TEMPLATES.get(kind, CHANNEL_TEMPLATES["web"]),
            },
        )

    async def create_group(self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]) -> dict[str, Any]:
        return await self.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            collection="notifications.groups",
            prefix="gp",
            body={
                "name": str(body.get("name") or "未命名分组"),
                "description": str(body.get("description") or "由管理员手动创建"),
                "members": list(body.get("members") or []),
                "rules": 0,
            },
        )

    async def batch_channel_status(
        self, *, tenant_id: UUID, workspace_id: UUID, ids: list[str], status: str
    ) -> dict[str, int]:
        updated = 0
        for doc_id in ids:
            await self.patch(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                collection="notifications.channels",
                doc_key=doc_id,
                patch={"status": status, "lastUsed": "刚刚"},
            )
            updated += 1
        return {"updated": updated}

    async def create_eval_suite(self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]) -> dict[str, Any]:
        criteria = body.get("criteria")
        if isinstance(criteria, str):
            criteria_list = [line.strip() for line in criteria.splitlines() if line.strip()]
        elif isinstance(criteria, list):
            criteria_list = [str(item) for item in criteria]
        else:
            criteria_list = []
        return await self.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            collection="evaluations.suites",
            prefix="suite",
            body={
                "name": str(body.get("name") or "未命名套件"),
                "description": str(body.get("description") or "新创建的评测套件"),
                "type": body.get("type") or "capability",
                "owner": str(body.get("owner") or "评测团队"),
                "status": "queued",
                "cases": 0,
                "passRate": 0,
                "avgScore": 0,
                "lastRunAt": "未运行",
                "schedule": str(body.get("schedule") or "手动"),
                "target": str(body.get("target") or ""),
                "starred": False,
                "tags": [],
                "trend": [0] * 12,
                "casesList": [],
                "criteria": criteria_list,
                "history": [],
            },
        )

    async def operations_summary(
        self, *, tenant_id: UUID, workspace_id: UUID
    ) -> dict[str, Any]:
        sessions = await self.list_collection(
            tenant_id=tenant_id, workspace_id=workspace_id, collection="operations.sessions"
        )
        spans = await self.list_collection(
            tenant_id=tenant_id, workspace_id=workspace_id, collection="operations.spans"
        )
        incidents = await self.list_collection(
            tenant_id=tenant_id, workspace_id=workspace_id, collection="operations.incidents"
        )
        kind_stats = await self.list_collection(
            tenant_id=tenant_id, workspace_id=workspace_id, collection="operations.kind-stats"
        )
        return {
            "sessions": sessions,
            "spans": spans,
            "incidents": incidents,
            "kindStats": kind_stats,
        }

    async def create_regression_track(
        self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]
    ) -> dict[str, Any]:
        zeros = [0] * 12
        return await self.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            collection="regressions.tracks",
            prefix="track",
            body={
                "name": str(body.get("name") or "未命名追踪"),
                "agent": str(body.get("agent") or ""),
                "owner": str(body.get("owner") or "评测团队"),
                "status": "stable",
                "risk": "low",
                "baselineVersion": str(body.get("baselineVersion") or "v1.0"),
                "currentVersion": str(body.get("currentVersion") or "v1.1"),
                "passRateDelta": 0,
                "latencyDelta": 0,
                "costDelta": 0,
                "scoreDelta": 0,
                "baseline": {"passRate": 95, "avgScore": 4.4, "latencyMs": 1200, "cost": 10},
                "current": {"passRate": 95, "avgScore": 4.4, "latencyMs": 1200, "cost": 10},
                "passRateTrend": zeros,
                "latencyTrend": zeros,
                "costTrend": zeros,
                "lastCheckedAt": "未运行",
                "cases": 0,
                "starred": False,
                "schedule": str(body.get("schedule") or "每次发布后"),
                "tags": [],
                "notes": str(body.get("notes") or "新创建的回归追踪"),
                "history": [],
                "casesList": [],
            },
        )

    async def create_feedback_ticket(
        self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]
    ) -> dict[str, Any]:
        feedback_ids = body.get("feedbackIds") or []
        if not isinstance(feedback_ids, list):
            feedback_ids = []
        return await self.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            collection="feedback.tickets",
            prefix="tk",
            body={
                "title": str(body.get("title") or "未命名工单"),
                "feedbackIds": [str(item) for item in feedback_ids],
                "owner": str(body.get("owner") or "产品组"),
                "priority": body.get("priority") or "medium",
                "status": "triaged",
                "topic": str(body.get("topic") or "其他"),
                "description": str(body.get("description") or "由管理员手动创建"),
                "createdAt": "刚刚",
                "dueAt": str(body.get("dueAt") or "本周内"),
            },
        )

    async def create_feedback_rule(
        self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]
    ) -> dict[str, Any]:
        return await self.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            collection="feedback.rules",
            prefix="rl",
            body={
                "name": str(body.get("name") or "未命名规则"),
                "matchTopic": str(body.get("matchTopic") or body.get("topic") or ""),
                "matchSentiment": body.get("matchSentiment") or "all",
                "action": body.get("action") or "create-ticket",
                "target": str(body.get("target") or "产品组"),
                "enabled": True,
                "description": str(body.get("description") or "由管理员手动创建"),
            },
        )

    async def create_dashboard(
        self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]
    ) -> dict[str, Any]:
        return await self.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            collection="metrics.dashboards",
            prefix="db",
            body={
                "name": str(body.get("name") or "未命名看板"),
                "range": body.get("range") or "24h",
                "panels": int(body.get("panels") or 4),
                "owner": str(body.get("owner") or "管理员"),
                "starred": False,
                "description": str(body.get("description") or body.get("desc") or ""),
            },
        )

    async def create_audit_rule(
        self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]
    ) -> dict[str, Any]:
        return await self.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            collection="audit.rules",
            prefix="rl",
            body={
                "name": str(body.get("name") or "未命名规则"),
                "category": body.get("category") or "tool",
                "condition": str(body.get("condition") or ""),
                "action": body.get("action") or "log",
                "severity": body.get("severity") or "medium",
                "enabled": True,
                "hitCount": 0,
                "description": str(body.get("description") or "由管理员手动创建"),
            },
        )

    _TREND_LABELS = {
        "1h": ["-60", "-50", "-40", "-30", "-20", "-10", "00"],
        "6h": ["-6h", "-5h", "-4h", "-3h", "-2h", "-1h", "00"],
        "24h": ["00", "02", "04", "06", "08", "10", "12", "14", "16", "18", "20", "22"],
        "7d": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
    }

    async def create_overview_alert(
        self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]
    ) -> dict[str, Any]:
        severity = str(body.get("severity") or "info")
        if severity not in {"high", "medium", "low", "info"}:
            severity = "info"
        return await self.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            collection="overview.alerts",
            prefix="oa",
            body={
                "severity": severity,
                "title": str(body.get("title") or "未命名告警"),
                "time": str(body.get("time") or "刚刚"),
                "affected": str(body.get("affected") or "工作空间"),
                "suggestion": str(body.get("suggestion") or ""),
            },
        )

    async def upsert_overview_service(
        self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]
    ) -> dict[str, Any]:
        name = str(body.get("name") or "未命名服务")
        status = str(body.get("status") or "ok")
        if status not in {"ok", "degraded", "down"}:
            status = "ok"
        return await self.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            collection="overview.services",
            prefix="sv",
            body={
                "id": str(body.get("id") or name),
                "name": name,
                "status": status,
                "latency": str(body.get("latency") or "—"),
                "detail": str(body.get("detail") or ""),
            },
        )

    async def upsert_overview_top_agent(
        self, *, tenant_id: UUID, workspace_id: UUID, body: dict[str, Any]
    ) -> dict[str, Any]:
        tone = str(body.get("tone") or "brand")
        if tone not in {"brand", "success", "info", "purple", "warn"}:
            tone = "brand"
        name = str(body.get("name") or "未命名智能体")
        return await self.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            collection="overview.top-agents",
            prefix="ta",
            body={
                "id": str(body.get("id") or name),
                "name": name,
                "calls": str(body.get("calls") or "0"),
                "share": float(body.get("share") or 0),
                "tone": tone,
            },
        )

    async def upsert_overview_trend(
        self, *, tenant_id: UUID, workspace_id: UUID, range_key: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        key = range_key if range_key in self._TREND_LABELS else "24h"
        points = body.get("points")
        if not isinstance(points, list) or not points:
            points = [
                {"label": label, "calls": 0, "success": 100, "errors": 0}
                for label in self._TREND_LABELS[key]
            ]
        normalized = []
        for item in points:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "label": str(item.get("label") or ""),
                    "calls": int(item.get("calls") or 0),
                    "success": float(item.get("success") or 100),
                    "errors": float(item.get("errors") or 0),
                }
            )
        return await self._repo.upsert_doc(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            collection="overview.trends",
            doc_key=key,
            payload={"id": key, "range": key, "points": normalized},
        )

    async def overview_trend(
        self, *, tenant_id: UUID, workspace_id: UUID, range_key: str
    ) -> dict[str, Any]:
        key = range_key if range_key in self._TREND_LABELS else "24h"
        stored = await self._repo.get_doc(
            workspace_id=workspace_id, collection="overview.trends", doc_key=key
        )
        if stored and isinstance(stored.get("points"), list) and stored["points"]:
            return {"range": key, "points": list(stored["points"])}
        return {
            "range": key,
            "points": [
                {"label": label, "calls": 0, "success": 100, "errors": 0}
                for label in self._TREND_LABELS[key]
            ],
        }

    async def overview_alerts(
        self, *, tenant_id: UUID, workspace_id: UUID
    ) -> list[dict[str, Any]]:
        stored = await self.list_collection(
            tenant_id=tenant_id, workspace_id=workspace_id, collection="overview.alerts"
        )
        if stored:
            return stored
        incidents = await self.list_collection(
            tenant_id=tenant_id, workspace_id=workspace_id, collection="operations.incidents"
        )
        quota_alerts = await self.list_collection(
            tenant_id=tenant_id, workspace_id=workspace_id, collection="quotas.alerts"
        )
        out: list[dict[str, Any]] = []
        for item in quota_alerts:
            if not item.get("enabled"):
                continue
            severity = str(item.get("severity") or "info")
            if severity == "critical":
                severity = "high"
            if severity not in {"high", "medium", "low", "info"}:
                severity = "info"
            out.append(
                {
                    "id": str(item.get("id") or ""),
                    "severity": severity,
                    "title": str(item.get("name") or "告警"),
                    "time": str(item.get("lastTriggered") or "—"),
                    "affected": str(item.get("scope") or "工作空间"),
                    "suggestion": str(item.get("description") or ""),
                }
            )
        for item in incidents:
            if item.get("resolved"):
                continue
            severity = str(item.get("severity") or "medium")
            if severity not in {"high", "medium", "low", "info"}:
                severity = "medium"
            out.append(
                {
                    "id": str(item.get("id") or ""),
                    "severity": severity,
                    "title": str(item.get("title") or "调用异常"),
                    "time": str(item.get("occurredAt") or "—"),
                    "affected": str(item.get("affectedUser") or "会话"),
                    "suggestion": str(item.get("message") or ""),
                }
            )
        return out[:12]

    async def overview_summary(
        self, *, tenant_id: UUID, workspace_id: UUID
    ) -> dict[str, Any]:
        sessions = await self.list_collection(
            tenant_id=tenant_id, workspace_id=workspace_id, collection="operations.sessions"
        )
        incidents = await self.list_collection(
            tenant_id=tenant_id, workspace_id=workspace_id, collection="operations.incidents"
        )
        models = await self.list_collection(
            tenant_id=tenant_id, workspace_id=workspace_id, collection="metrics.models"
        )
        suites = await self.list_collection(
            tenant_id=tenant_id, workspace_id=workspace_id, collection="evaluations.suites"
        )
        audit_entries = await self.list_collection(
            tenant_id=tenant_id, workspace_id=workspace_id, collection="audit.entries"
        )
        channels = await self.list_collection(
            tenant_id=tenant_id, workspace_id=workspace_id, collection="notifications.channels"
        )
        alerts = await self.overview_alerts(tenant_id=tenant_id, workspace_id=workspace_id)
        trend = await self.overview_trend(
            tenant_id=tenant_id, workspace_id=workspace_id, range_key="24h"
        )
        spark = [int(point.get("calls") or 0) for point in (trend.get("points") or [])][:12]
        if len(spark) < 12:
            spark = spark + [0] * (12 - len(spark))
        calls = sum(int(item.get("calls") or 0) for item in models)
        if not calls:
            calls = sum(int(point.get("calls") or 0) for point in (trend.get("points") or []))
        error_rate = (
            sum(float(item.get("errorRate") or 0) for item in models) / len(models) if models else 0.0
        )
        avail = (
            sum(float(item.get("availability") or 0) for item in models) / len(models) if models else 100.0
        )
        p95 = int(sum(int(item.get("p95") or 0) for item in models) / max(len(models), 1))
        open_incidents = [item for item in incidents if not item.get("resolved")]
        high_alerts = [item for item in alerts if item.get("severity") == "high"]
        active_agents = {str(item.get("target") or "") for item in suites if item.get("target")}
        kpis = [
            {
                "label": "今日调用",
                "value": f"{calls:,}",
                "delta": f"{len(sessions)} 个会话",
                "deltaTone": "up" if calls else "flat",
                "tone": "brand",
                "href": "/admin/metrics",
                "sparkline": spark,
                "iconName": "Activity",
            },
            {
                "label": "可用率",
                "value": f"{avail:.2f}%",
                "delta": f"{len(models)} 个模型",
                "deltaTone": "flat",
                "tone": "success",
                "href": "/admin/metrics",
                "sparkline": [avail] * 12,
                "iconName": "ShieldCheck",
            },
            {
                "label": "P95 延迟",
                "value": f"{p95} ms",
                "delta": "运行指标均值",
                "deltaTone": "down" if p95 else "flat",
                "tone": "info",
                "href": "/admin/metrics",
                "sparkline": [p95] * 12,
                "iconName": "Timer",
            },
            {
                "label": "错误率",
                "value": f"{error_rate:.2f}%",
                "delta": f"{len(open_incidents)} 条未解决异常",
                "deltaTone": "up" if open_incidents else "flat",
                "tone": "danger" if open_incidents or error_rate else "success",
                "href": "/admin/operations",
                "sparkline": [error_rate] * 12,
                "iconName": "AlertTriangle",
            },
            {
                "label": "活跃智能体",
                "value": str(len(active_agents) or len(sessions)),
                "delta": f"{len(suites)} 个评测对象",
                "deltaTone": "up" if active_agents else "flat",
                "tone": "purple",
                "href": "/admin/agents",
                "sparkline": spark,
                "iconName": "Brain",
            },
            {
                "label": "告警事件",
                "value": f"{len(alerts)} 待处理",
                "delta": f"{len(high_alerts)} 高优",
                "deltaTone": "up" if high_alerts else "flat",
                "tone": "warn",
                "href": "/admin/overview",
                "sparkline": [len(alerts)] * 12,
                "iconName": "BellRing",
            },
        ]
        stored_services = await self.list_collection(
            tenant_id=tenant_id, workspace_id=workspace_id, collection="overview.services"
        )
        if stored_services:
            services = stored_services
        else:
            degraded_models = [
                item for item in models if float(item.get("availability") or 100) < 99
            ]
            services = [
                {
                    "name": "模型服务",
                    "status": "ok" if models else "degraded",
                    "latency": f"{p95} ms" if models else "—",
                    "detail": f"{len(models)} 个模型 · 平均可用率 {avail:.2f}%",
                },
                {
                    "name": "知识检索",
                    "status": "ok",
                    "latency": "—",
                    "detail": "接入知识管理索引",
                },
                {
                    "name": "工具网关",
                    "status": "ok" if channels else "degraded",
                    "latency": "—",
                    "detail": f"{len(channels)} 个渠道 · {len(audit_entries)} 条审计",
                },
                {
                    "name": "模型降级池",
                    "status": "degraded" if degraded_models else "ok",
                    "latency": "—",
                    "detail": (
                        f"{len(degraded_models)} 个模型触发降级"
                        if degraded_models
                        else "未触发降级"
                    ),
                },
                {
                    "name": "审计服务",
                    "status": "ok",
                    "latency": "—",
                    "detail": f"实时落库 · {len(audit_entries)} 条记录",
                },
            ]
        stored_agents = await self.list_collection(
            tenant_id=tenant_id, workspace_id=workspace_id, collection="overview.top-agents"
        )
        if stored_agents:
            top_agents = stored_agents
        else:
            tones = ["brand", "success", "info", "purple", "warn"]
            ranked = sorted(models, key=lambda row: int(row.get("calls") or 0), reverse=True)[:5]
            total = sum(int(item.get("calls") or 0) for item in ranked) or 1
            top_agents = [
                {
                    "name": str(item.get("model") or "模型"),
                    "calls": f"{int(item.get('calls') or 0):,}",
                    "share": round(int(item.get("calls") or 0) / total, 2),
                    "tone": tones[index % len(tones)],
                }
                for index, item in enumerate(ranked)
            ]
        return {
            "kpis": kpis,
            "alerts": alerts,
            "services": services,
            "topAgents": top_agents,
        }

