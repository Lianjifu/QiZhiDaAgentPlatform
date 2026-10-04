"""HTTP adapter for frontend admin console pages.

  额度管理    /api/admin/quotas/*
  渠道配置    /api/admin/notifications/*
  评测中心    /api/admin/evaluations/*
  回归追踪    /api/admin/regressions/*
  用户反馈    /api/admin/feedback/*
  调用链路    /api/admin/operations/*
  工具审计    /api/admin/audit/*
  运行指标    /api/admin/metrics/*
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from qzdap.modules.platform.application.ops_service import AdminOpsService


async def ops_dependency(request: Request) -> AdminOpsService:
    factory = getattr(request.app.state, "admin_ops_factory", None)
    container = getattr(request.app.state, "container", None)
    if factory is None or container is None:
        raise HTTPException(status_code=503, detail="admin ops factory not wired")
    sf = container.session_factory()
    async with sf.session() as session:
        svc = factory.for_session(session)
        try:
            yield svc
        except Exception:
            await session.rollback()
            raise
        await session.commit()


def _patch_body(body: dict[str, Any]) -> dict[str, Any]:
    patch = body.get("patch")
    if isinstance(patch, dict):
        return patch
    return {key: value for key, value in body.items() if key != "id"}


def build_ops_router() -> APIRouter:
    router = APIRouter(tags=["admin-ops"])

    @router.get("/api/admin/overview/summary")
    async def overview_summary(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.overview_summary(tenant_id=x_tenant_id, workspace_id=x_workspace_id)

    @router.get("/api/admin/overview/alerts")
    async def overview_alerts(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.overview_alerts(tenant_id=x_tenant_id, workspace_id=x_workspace_id)

    @router.get("/api/admin/overview/trend/{range_key}")
    async def overview_trend(
        range_key: str,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.overview_trend(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, range_key=range_key
        )

    @router.put("/api/admin/overview/trend/{range_key}")
    async def put_overview_trend(
        range_key: str,
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.upsert_overview_trend(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, range_key=range_key, body=body
        )

    @router.post("/api/admin/overview/alerts", status_code=201)
    async def create_overview_alert(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.create_overview_alert(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body
        )

    @router.post("/api/admin/overview/services", status_code=201)
    async def create_overview_service(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.upsert_overview_service(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body
        )

    @router.post("/api/admin/overview/top-agents", status_code=201)
    async def create_overview_top_agent(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.upsert_overview_top_agent(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body
        )

    @router.get("/api/admin/quotas/budgets")
    async def list_budgets(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="quotas.budgets"
        )

    @router.post("/api/admin/quotas/budgets", status_code=201)
    async def create_budget(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.create_budget(tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body)

    @router.patch("/api/admin/quotas/budgets/{doc_id}")
    async def patch_budget(
        doc_id: str,
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        try:
            return await svc.patch(
                tenant_id=x_tenant_id,
                workspace_id=x_workspace_id,
                collection="quotas.budgets",
                doc_key=doc_id,
                patch=_patch_body(body),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="budget not found") from exc

    @router.get("/api/admin/quotas/departments")
    async def list_departments(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="quotas.departments"
        )

    @router.get("/api/admin/quotas/usage")
    async def list_usage(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="quotas.usage"
        )

    @router.get("/api/admin/quotas/alerts")
    async def list_quota_alerts(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="quotas.alerts"
        )

    @router.post("/api/admin/quotas/alerts", status_code=201)
    async def create_quota_alert(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.create_alert(tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body)

    @router.post("/api/admin/quotas/alerts/{doc_id}/toggle")
    async def toggle_quota_alert(
        doc_id: str,
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        try:
            current = await svc.get(
                tenant_id=x_tenant_id,
                workspace_id=x_workspace_id,
                collection="quotas.alerts",
                doc_key=doc_id,
            )
            return await svc.patch(
                tenant_id=x_tenant_id,
                workspace_id=x_workspace_id,
                collection="quotas.alerts",
                doc_key=doc_id,
                patch={"enabled": not bool(current.get("enabled"))},
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="alert not found") from exc

    @router.get("/api/admin/notifications/channels")
    async def list_channels(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="notifications.channels"
        )

    @router.post("/api/admin/notifications/channels", status_code=201)
    async def create_channel(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.create_channel(tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body)

    @router.post("/api/admin/notifications/channels/__batch__")
    async def batch_channels(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, int]:
        ids = [str(item) for item in (body.get("ids") or [])]
        return await svc.batch_channel_status(
            tenant_id=x_tenant_id,
            workspace_id=x_workspace_id,
            ids=ids,
            status=str(body.get("status") or "paused"),
        )

    @router.patch("/api/admin/notifications/channels/{doc_id}")
    async def patch_channel(
        doc_id: str,
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        try:
            return await svc.patch(
                tenant_id=x_tenant_id,
                workspace_id=x_workspace_id,
                collection="notifications.channels",
                doc_key=doc_id,
                patch={**_patch_body(body), "lastUsed": "刚刚"},
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="channel not found") from exc

    @router.get("/api/admin/notifications/webhooks")
    async def list_webhooks(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="notifications.webhooks"
        )

    @router.get("/api/admin/notifications/groups")
    async def list_groups(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="notifications.groups"
        )

    @router.post("/api/admin/notifications/groups", status_code=201)
    async def create_group(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.create_group(tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body)

    @router.get("/api/admin/notifications/events")
    async def list_events(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="notifications.events"
        )

    @router.get("/api/admin/evaluations/suites")
    async def list_eval_suites(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="evaluations.suites"
        )

    @router.post("/api/admin/evaluations/suites", status_code=201)
    async def create_eval_suite(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.create_eval_suite(tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body)

    @router.get("/api/admin/evaluations/results")
    async def list_eval_results(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="evaluations.results"
        )

    @router.get("/api/admin/regressions/tracks")
    async def list_regression_tracks(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="regressions.tracks"
        )

    @router.post("/api/admin/regressions/tracks", status_code=201)
    async def create_regression_track(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.create_regression_track(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body
        )

    @router.get("/api/admin/regressions/alerts")
    async def list_regression_alerts(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="regressions.alerts"
        )

    @router.get("/api/admin/regressions/timeline")
    async def list_regression_timeline(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="regressions.timeline"
        )

    @router.get("/api/admin/feedback/list")
    async def list_feedback(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="feedback.list"
        )

    @router.get("/api/admin/feedback/tickets")
    async def list_feedback_tickets(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="feedback.tickets"
        )

    @router.post("/api/admin/feedback/tickets", status_code=201)
    async def create_feedback_ticket(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.create_feedback_ticket(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body
        )

    @router.get("/api/admin/feedback/topics")
    async def list_feedback_topics(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="feedback.topics"
        )

    @router.post("/api/admin/feedback/rules", status_code=201)
    async def create_feedback_rule(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.create_feedback_rule(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body
        )

    @router.get("/api/admin/feedback/rules")
    async def list_feedback_rules(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="feedback.rules"
        )

    @router.get("/api/admin/operations/summary")
    async def operations_summary(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.operations_summary(tenant_id=x_tenant_id, workspace_id=x_workspace_id)

    @router.get("/api/admin/operations/sessions")
    async def list_sessions(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="operations.sessions"
        )

    @router.get("/api/admin/operations/spans")
    async def list_spans(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="operations.spans"
        )

    @router.get("/api/admin/operations/incidents")
    async def list_incidents(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="operations.incidents"
        )

    @router.get("/api/admin/operations/kind-stats")
    async def list_kind_stats(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="operations.kind-stats"
        )

    @router.get("/api/admin/audit/entries")
    async def list_audit_entries(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="audit.entries"
        )

    @router.get("/api/admin/audit/risks")
    async def list_audit_risks(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="audit.risks"
        )

    @router.post("/api/admin/audit/rules", status_code=201)
    async def create_audit_rule(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.create_audit_rule(tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body)

    @router.get("/api/admin/audit/rules")
    async def list_audit_rules(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="audit.rules"
        )

    @router.get("/api/admin/audit/scopes")
    async def list_audit_scopes(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="audit.scopes"
        )

    @router.get("/api/admin/metrics/models")
    async def list_metric_models(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="metrics.models"
        )

    @router.get("/api/admin/metrics/latency")
    async def list_metric_latency(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="metrics.latency"
        )

    @router.get("/api/admin/metrics/cost-breakdown")
    async def list_metric_cost(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="metrics.cost-breakdown"
        )

    @router.post("/api/admin/metrics/dashboards", status_code=201)
    async def create_metric_dashboard(
        body: dict[str, Any],
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> dict[str, Any]:
        return await svc.create_dashboard(tenant_id=x_tenant_id, workspace_id=x_workspace_id, body=body)

    @router.get("/api/admin/metrics/dashboards")
    async def list_metric_dashboards(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="metrics.dashboards"
        )

    @router.get("/api/admin/metrics/thresholds")
    async def list_metric_thresholds(
        x_tenant_id: UUID = Header(..., alias="X-Tenant-Id"),  # noqa: B008
        x_workspace_id: UUID = Header(..., alias="X-Workspace-Id"),  # noqa: B008
        svc: AdminOpsService = Depends(ops_dependency),  # noqa: B008
    ) -> list[dict[str, Any]]:
        return await svc.list_collection(
            tenant_id=x_tenant_id, workspace_id=x_workspace_id, collection="metrics.thresholds"
        )

    return router


__all__ = ["build_ops_router", "ops_dependency"]
