"""平面 B · 记忆**管理面**的服务 —— 目录 CRUD / 策略配置 / 审核 / 趋势 ✓。

依据：Memory 方案 §10.1（B2 管理服务）、§2.2 规则 6（平面分离 ✓）。

⚠️ **从 ``MemoryService`` 拆出** ✓（台账 **X16** ✓）—— 运行时
（``recall`` / ``write``）在平面 A ✓，管理查询在这里 ✓。

⚠️ **拆分是纯重构，行为不变** ✓ —— 但**管理端的直写路径绕过写入侧的脱敏与
去重** ✗✗（X16 的后半段 ✓）→ 那个归 **M-42** ✓（Stage 6b ✓）✓。
"""

from __future__ import annotations

from datetime import UTC, datetime
from logging import getLogger
from typing import Any
from uuid import UUID, uuid4

from qzdap_kernel.errors import ValidationError
from qzdap_observability.metrics import record_legacy_call

from qzdap.modules.memory.application.embedding import embed_item
from qzdap.modules.memory.application.ports import (
    EmbeddingPort,
    MemoryCatalogRepository,
    VectorSearchPort,
)
from qzdap.modules.memory.domain.entities import (
    L2_STATUSES,
    L3_STATUSES,
    L2Fact,
    L3Entry,
    PromotionEvent,
    RetentionPolicy,
)
from qzdap.modules.memory.domain.errors import MemoryNotFound

_log = getLogger(__name__)


class MemoryAdminService:
    """管理面 —— **目录 / 策略 / 审核 / 趋势** ✓（不含运行时召回与写入 ✓）。"""

    def __init__(
        self,
        catalog: MemoryCatalogRepository,
        *,
        embedding: EmbeddingPort | None = None,
        vectors: VectorSearchPort | None = None,
    ) -> None:
        self._catalog = catalog
        self._embedding = embedding
        self._vectors = vectors

    async def list_l1(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._catalog.list_l1(workspace_id)
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_admin_dict() for item in items]

    async def get_l1(self, item_id: UUID) -> dict[str, Any]:
        item = await self._catalog.get_l1(item_id)
        if item is None:
            raise MemoryNotFound(f"l1 session {item_id} not found")
        return item.to_admin_dict()

    async def list_l2(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._catalog.list_l2(workspace_id)
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_admin_dict() for item in items]

    async def get_l2(self, item_id: UUID) -> dict[str, Any]:
        item = await self._catalog.get_l2(item_id)
        if item is None:
            raise MemoryNotFound(f"l2 fact {item_id} not found")
        return item.to_admin_dict()

    async def list_l3(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._catalog.list_l3(workspace_id)
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_admin_dict() for item in items]

    async def get_l3(self, item_id: UUID) -> dict[str, Any]:
        item = await self._catalog.get_l3(item_id)
        if item is None:
            raise MemoryNotFound(f"l3 entry {item_id} not found")
        return item.to_admin_dict()

    async def flush_l1(self, item_id: UUID, *, workspace_id: UUID) -> dict[str, Any]:
        """冲掉一条 L1 会话缓冲 —— 内容落盘后丢弃上下文窗口。"""
        item = await self._catalog.get_l1(item_id)
        if item is None or item.workspace_id != workspace_id:
            raise MemoryNotFound(f"l1 session {item_id} not found")
        now = datetime.now(UTC)
        item.status = "expired"
        item.buffer_text = ""
        item.buffer_size = 0
        item.ttl_remain_min = 0
        item.updated_at = now
        await self._catalog.update_l1(item)
        return item.to_admin_dict()

    async def flush_all_l1(self, *, workspace_id: UUID) -> dict[str, int]:
        """冲掉工作区下所有未过期的 L1 会话。"""
        now = datetime.now(UTC)
        flushed = 0
        for item in await self._catalog.list_l1(workspace_id):
            if item.status == "expired":
                continue
            item.status = "expired"
            item.buffer_text = ""
            item.buffer_size = 0
            item.ttl_remain_min = 0
            item.updated_at = now
            await self._catalog.update_l1(item)
            flushed += 1
        return {"flushed": flushed}

    async def update_l2(
        self, item_id: UUID, *, workspace_id: UUID, patch: dict[str, Any]
    ) -> dict[str, Any]:
        """确认 / 退休一条 L2 事实。"""
        item = await self._catalog.get_l2(item_id)
        if item is None or item.workspace_id != workspace_id:
            raise MemoryNotFound(f"l2 fact {item_id} not found")
        status = patch.get("status")
        if status is not None:
            value = str(status)
            if value not in L2_STATUSES:
                raise ValidationError(f"unknown l2 status {value}")
            item.status = value  # type: ignore[assignment]
        if "value" in patch and patch["value"] is not None:
            item.value = str(patch["value"])
        if patch.get("confidence") is not None:
            item.confidence = float(patch["confidence"])
        item.updated_at = datetime.now(UTC)
        await self._catalog.update_l2(item)
        return item.to_admin_dict()

    async def promote_l2(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        ids: list[UUID],
        team: str,
        title: str,
        summary: str,
        operator: str = "管理员",
        category: str = "knowledge",
    ) -> dict[str, Any]:
        """把选中的 L2 事实晋升为一条 L3 团队知识。"""
        facts: list[L2Fact] = []
        for item_id in ids:
            fact = await self._catalog.get_l2(item_id)
            if fact is None or fact.workspace_id != workspace_id:
                raise MemoryNotFound(f"l2 fact {item_id} not found")
            facts.append(fact)
        if not facts:
            raise ValidationError("没有可晋升的长期记忆")
        now = datetime.now(UTC)
        for fact in facts:
            fact.promoted_to_l3 = True
            fact.updated_at = now
            await self._catalog.update_l2(fact)
        entry = L3Entry.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            team=team,
            title=title,
            summary=summary,
            category=category,
            contributor=operator,
            status="draft",
            promoted_from_l2_ids=[str(fact.id) for fact in facts],
        )
        # ⚠️ **L3 表在用** ✓（台账 X15 —— 决策 #1：L3 退役 ✓）→ 打点 ✓
        record_legacy_call("X15")
        await self._catalog.add_l3(entry)
        await self._catalog.add_promotion(
            PromotionEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                layer="l2→l3",
                label=f"{team} · {title}: {summary[:24]}",
                operator=operator,
                target_id=str(entry.id),
                created_at=now,
            )
        )
        await self._embed_item(
            entry.id, "l3", entry.recall_text(), tenant_id, workspace_id
        )
        return entry.to_admin_dict()

    async def create_l3(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        team: str,
        title: str,
        summary: str,
        category: str = "knowledge",
        contributor: str = "管理员",
        status: str = "published",
    ) -> dict[str, Any]:
        """手工新建一条 L3 团队知识。"""
        if status not in L3_STATUSES:
            raise ValidationError(f"unknown l3 status {status}")
        entry = L3Entry.create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            team=team,
            title=title,
            summary=summary,
            category=category,
            contributor=contributor,
            status=status,  # type: ignore[arg-type]
        )
        # ⚠️ **L3 表在用** ✓（台账 X15 —— 决策 #1：L3 退役 ✓）→ 打点 ✓
        record_legacy_call("X15")
        await self._catalog.add_l3(entry)
        await self._embed_item(
            entry.id, "l3", entry.recall_text(), tenant_id, workspace_id
        )
        return entry.to_admin_dict()

    async def update_l3(
        self, item_id: UUID, *, workspace_id: UUID, patch: dict[str, Any]
    ) -> dict[str, Any]:
        """发布 / 下线一条 L3 知识。"""
        item = await self._catalog.get_l3(item_id)
        if item is None or item.workspace_id != workspace_id:
            raise MemoryNotFound(f"l3 entry {item_id} not found")
        status = patch.get("status")
        if status is not None:
            value = str(status)
            if value not in L3_STATUSES:
                raise ValidationError(f"unknown l3 status {value}")
            item.status = value  # type: ignore[assignment]
        for field in ("title", "summary", "team", "category"):
            if patch.get(field) is not None:
                setattr(item, field, str(patch[field]))
        item.updated_at = datetime.now(UTC)
        await self._catalog.update_l3(item)
        return item.to_admin_dict()

    async def list_promotions(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._catalog.list_promotions(workspace_id)
        items.sort(key=lambda item: item.created_at, reverse=True)
        return [item.to_admin_dict() for item in items]

    async def list_policies(
        self, *, tenant_id: UUID, workspace_id: UUID
    ) -> list[dict[str, Any]]:
        items = await self._ensure_policies(
            tenant_id=tenant_id, workspace_id=workspace_id
        )
        return [item.to_admin_dict() for item in items]

    async def get_policy(self, *, workspace_id: UUID, label: str) -> dict[str, Any]:
        item = await self._catalog.get_policy_by_label(workspace_id, label)
        if item is None:
            raise MemoryNotFound(f"policy {label} not found")
        return item.to_admin_dict()

    async def trend(
        self, *, workspace_id: UUID, range: str = "7d"
    ) -> dict[str, list[int]]:
        _ = range
        l1 = await self._catalog.list_l1(workspace_id)
        l2 = await self._catalog.list_l2(workspace_id)
        l3 = await self._catalog.list_l3(workspace_id)
        l1_n = sum(1 for item in l1 if item.status != "expired")
        l2_n = sum(1 for item in l2 if item.status != "retired")
        l3_hits = sum(item.hits for item in l3 if item.status == "published")
        return {
            "l1Active": _series(l1_n),
            "l2Hits": _series(max(l2_n * 12, l2_n)),
            "l3Hits": _series(l3_hits or l1_n),
        }

    async def _ensure_policies(
        self, *, tenant_id: UUID, workspace_id: UUID
    ) -> list[RetentionPolicy]:
        items = await self._catalog.list_policies(workspace_id)
        if items:
            return items
        seeded = RetentionPolicy.defaults(
            tenant_id=tenant_id, workspace_id=workspace_id
        )
        for item in seeded:
            await self._catalog.add_policy(item)
        return seeded

    async def _embed_item(
        self,
        item_id: UUID,
        layer: str,
        content: str,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID | None = None,
    ) -> None:
        await embed_item(
            self._embedding,
            self._vectors,
            item_id=item_id,
            layer=layer,
            content=content,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )


def _series(end: int) -> list[int]:
    end = max(0, int(end))
    step = max(1, end // 7) if end else 0
    values = [max(0, end - (7 - i) * step) for i in range(8)]
    values[-1] = end
    return values


__all__ = ["MemoryAdminService"]
