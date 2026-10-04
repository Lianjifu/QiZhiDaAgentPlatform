"""Admin ops service tests — empty catalog + quota/channel mutations."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from qzdap.modules.platform.application.ops_service import AdminOpsService

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")


class InMemoryOpsRepo:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], dict[str, Any]] = {}

    async def list_docs(self, *, workspace_id: UUID, collection: str) -> list[dict[str, Any]]:
        _ = workspace_id
        items = [dict(row) for (col, _key), row in self._rows.items() if col == collection]
        items.sort(key=lambda item: str(item.get("id") or ""))
        return items

    async def get_doc(
        self, *, workspace_id: UUID, collection: str, doc_key: str
    ) -> dict[str, Any] | None:
        _ = workspace_id
        row = self._rows.get((collection, doc_key))
        return dict(row) if row else None

    async def upsert_doc(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        collection: str,
        doc_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        _ = (tenant_id, workspace_id)
        body = {**payload, "id": doc_key}
        self._rows[(collection, doc_key)] = body
        return dict(body)

    async def seed_if_empty(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        collection: str,
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        existing = await self.list_docs(workspace_id=workspace_id, collection=collection)
        if existing:
            return existing
        out: list[dict[str, Any]] = []
        for item in items:
            key = str(item.get("id") or uuid4())
            out.append(
                await self.upsert_doc(
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    collection=collection,
                    doc_key=key,
                    payload=item,
                )
            )
        return out


@pytest.fixture
def service() -> AdminOpsService:
    return AdminOpsService(InMemoryOpsRepo())


@pytest.mark.asyncio
async def test_empty_catalog_then_create_budget(service: AdminOpsService) -> None:
    budgets = await service.list_collection(
        tenant_id=TENANT, workspace_id=WORKSPACE, collection="quotas.budgets"
    )
    assert budgets == []
    created = await service.create_budget(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "联调预算", "period": "monthly", "totalCap": 1000, "alertThreshold": 80, "rollover": False, "owner": "测试"},
    )
    assert created["name"] == "联调预算"
    assert created["status"] == "healthy"


@pytest.mark.asyncio
async def test_toggle_alert_and_channel_create(service: AdminOpsService) -> None:
    alert = await service.create_alert(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "联调告警", "metric": "cost", "threshold": 80, "window": "1h"},
    )
    enabled = bool(alert["enabled"])
    patched = await service.patch(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        collection="quotas.alerts",
        doc_key=str(alert["id"]),
        patch={"enabled": not enabled},
    )
    assert patched["enabled"] is (not enabled)
    channel = await service.create_channel(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "飞书联调", "kind": "feishu", "target": "客服助手"},
    )
    assert channel["kind"] == "feishu"
    assert channel["status"] == "draft"


@pytest.mark.asyncio
async def test_operations_summary_empty(service: AdminOpsService) -> None:
    summary = await service.operations_summary(tenant_id=TENANT, workspace_id=WORKSPACE)
    assert summary["sessions"] == []
    assert summary["spans"] == []
    assert "kindStats" in summary


@pytest.mark.asyncio
async def test_overview_and_create_dashboard_rule(service: AdminOpsService) -> None:
    summary = await service.overview_summary(tenant_id=TENANT, workspace_id=WORKSPACE)
    assert len(summary["kpis"]) == 6
    assert summary["alerts"] == []
    dash = await service.create_dashboard(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "联调看板", "range": "24h", "description": "api"},
    )
    assert dash["name"] == "联调看板"
    rule = await service.create_audit_rule(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "循环熔断", "category": "tool", "condition": "repeat > 5", "action": "block", "severity": "high"},
    )
    assert rule["action"] == "block"


@pytest.mark.asyncio
async def test_overview_write_then_read(service: AdminOpsService) -> None:
    alert = await service.create_overview_alert(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={
            "severity": "high",
            "title": "模型错误率突增",
            "time": "刚刚",
            "affected": "客户沟通助手",
            "suggestion": "切换备用模型",
        },
    )
    assert alert["severity"] == "high"
    await service.upsert_overview_service(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "模型服务", "status": "ok", "latency": "42 ms", "detail": "1 个模型"},
    )
    await service.upsert_overview_top_agent(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        body={"name": "客户沟通助手", "calls": "18.2k", "share": 0.42, "tone": "brand"},
    )
    await service.upsert_overview_trend(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        range_key="24h",
        body={"points": [{"label": "00", "calls": 3200, "success": 99.9, "errors": 0.3}]},
    )
    summary = await service.overview_summary(tenant_id=TENANT, workspace_id=WORKSPACE)
    assert any(item["label"] == "活跃智能体" for item in summary["kpis"])
    assert summary["alerts"][0]["title"] == "模型错误率突增"
    assert summary["services"][0]["name"] == "模型服务"
    assert summary["topAgents"][0]["name"] == "客户沟通助手"
    trend = await service.overview_trend(
        tenant_id=TENANT, workspace_id=WORKSPACE, range_key="24h"
    )
    assert trend["points"][0]["calls"] == 3200
