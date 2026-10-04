from __future__ import annotations

from uuid import UUID

from qzdap_persistence.tenant_guard import current_tenant_id
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.memory.adapter.persistence.models import (
    MemoryL1ORM,
    MemoryL2ORM,
    MemoryL3ORM,
    MemoryPolicyORM,
    MemoryPromotionORM,
)
from qzdap.modules.memory.application.ports import MemoryCatalogRepository
from qzdap.modules.memory.domain.entities import (
    L1Session,
    L2Fact,
    L3Entry,
    PromotionEvent,
    RetentionPolicy,
)


def _cross_tenant(row: object) -> bool:
    bound = current_tenant_id()
    if bound is None:
        return False
    return getattr(row, "tenant_id", None) != bound


def _l1(row: MemoryL1ORM) -> L1Session:
    return L1Session(
        id=row.id,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        user_name=row.user_name,
        agent_name=row.agent_name,
        buffer_size=row.buffer_size,
        tokens_used=row.tokens_used,
        ttl_minutes=row.ttl_minutes,
        ttl_remain_min=row.ttl_remain_min,
        status=row.status,  # type: ignore[arg-type]
        updated_at=row.updated_at,
        created_at=row.created_at,
        buffer_text=row.buffer_text,
    )


def _l2(row: MemoryL2ORM) -> L2Fact:
    return L2Fact(
        id=row.id,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        user_name=row.user_name,
        key=row.key,
        value=row.value,
        category=row.category,  # type: ignore[arg-type]
        source_session=row.source_session,
        confidence=row.confidence,
        status=row.status,  # type: ignore[arg-type]
        promoted_to_l3=bool(row.promoted_to_l3),
        updated_at=row.updated_at,
        created_at=row.created_at,
        usage_history=list(row.usage_history or []),
    )


def _l3(row: MemoryL3ORM) -> L3Entry:
    return L3Entry(
        id=row.id,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        team=row.team,
        title=row.title,
        summary=row.summary,
        category=row.category,
        hits=row.hits,
        contributor=row.contributor,
        status=row.status,  # type: ignore[arg-type]
        updated_at=row.updated_at,
        created_at=row.created_at,
        hits_trend=list(row.hits_trend or []),
        promoted_from_l2_ids=list(row.promoted_from_l2_ids or []),
    )


class SqlMemoryCatalogRepository(MemoryCatalogRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add_l1(self, item: L1Session) -> None:
        self._s.add(
            MemoryL1ORM(
                id=item.id,
                tenant_id=item.tenant_id,
                workspace_id=item.workspace_id,
                user_name=item.user_name,
                agent_name=item.agent_name,
                buffer_size=item.buffer_size,
                tokens_used=item.tokens_used,
                ttl_minutes=item.ttl_minutes,
                ttl_remain_min=item.ttl_remain_min,
                status=item.status,
                buffer_text=item.buffer_text,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
        )

    async def get_l1(self, item_id: UUID) -> L1Session | None:
        row = await self._s.get(MemoryL1ORM, item_id)
        if row is None or _cross_tenant(row):
            return None
        return _l1(row)

    async def list_l1(self, workspace_id: UUID) -> list[L1Session]:
        result = await self._s.execute(
            select(MemoryL1ORM).where(MemoryL1ORM.workspace_id == workspace_id)
        )
        return [_l1(row) for row in result.scalars().all() if not _cross_tenant(row)]

    async def update_l1(self, item: L1Session) -> None:
        row = await self._s.get(MemoryL1ORM, item.id)
        if row is None or _cross_tenant(row):
            return
        row.buffer_size = item.buffer_size
        row.tokens_used = item.tokens_used
        row.ttl_remain_min = item.ttl_remain_min
        row.status = item.status
        row.buffer_text = item.buffer_text
        row.updated_at = item.updated_at

    async def add_l2(self, item: L2Fact) -> None:
        self._s.add(
            MemoryL2ORM(
                id=item.id,
                tenant_id=item.tenant_id,
                workspace_id=item.workspace_id,
                user_name=item.user_name,
                key=item.key,
                value=item.value,
                category=item.category,
                source_session=item.source_session,
                confidence=item.confidence,
                status=item.status,
                promoted_to_l3=item.promoted_to_l3,
                usage_history=list(item.usage_history),
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
        )

    async def get_l2(self, item_id: UUID) -> L2Fact | None:
        row = await self._s.get(MemoryL2ORM, item_id)
        if row is None or _cross_tenant(row):
            return None
        return _l2(row)

    async def list_l2(self, workspace_id: UUID) -> list[L2Fact]:
        result = await self._s.execute(
            select(MemoryL2ORM).where(MemoryL2ORM.workspace_id == workspace_id)
        )
        return [_l2(row) for row in result.scalars().all() if not _cross_tenant(row)]

    async def update_l2(self, item: L2Fact) -> None:
        row = await self._s.get(MemoryL2ORM, item.id)
        if row is None or _cross_tenant(row):
            return
        row.value = item.value
        row.status = item.status
        row.confidence = item.confidence
        row.promoted_to_l3 = item.promoted_to_l3
        row.usage_history = list(item.usage_history)
        row.updated_at = item.updated_at

    async def add_l3(self, item: L3Entry) -> None:
        self._s.add(
            MemoryL3ORM(
                id=item.id,
                tenant_id=item.tenant_id,
                workspace_id=item.workspace_id,
                team=item.team,
                title=item.title,
                summary=item.summary,
                category=item.category,
                hits=item.hits,
                contributor=item.contributor,
                status=item.status,
                hits_trend=list(item.hits_trend),
                promoted_from_l2_ids=list(item.promoted_from_l2_ids),
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
        )

    async def get_l3(self, item_id: UUID) -> L3Entry | None:
        row = await self._s.get(MemoryL3ORM, item_id)
        if row is None or _cross_tenant(row):
            return None
        return _l3(row)

    async def list_l3(self, workspace_id: UUID) -> list[L3Entry]:
        result = await self._s.execute(
            select(MemoryL3ORM).where(MemoryL3ORM.workspace_id == workspace_id)
        )
        return [_l3(row) for row in result.scalars().all() if not _cross_tenant(row)]

    async def add_promotion(self, item: PromotionEvent) -> None:
        self._s.add(
            MemoryPromotionORM(
                id=item.id,
                tenant_id=item.tenant_id,
                workspace_id=item.workspace_id,
                layer=item.layer,
                label=item.label,
                operator=item.operator,
                target_id=item.target_id,
                created_at=item.created_at,
                updated_at=item.created_at,
            )
        )

    async def list_promotions(self, workspace_id: UUID) -> list[PromotionEvent]:
        result = await self._s.execute(
            select(MemoryPromotionORM).where(MemoryPromotionORM.workspace_id == workspace_id)
        )
        return [
            PromotionEvent(
                id=row.id,
                tenant_id=row.tenant_id,
                workspace_id=row.workspace_id,
                layer=row.layer,  # type: ignore[arg-type]
                label=row.label,
                operator=row.operator,
                target_id=row.target_id,
                created_at=row.created_at,
            )
            for row in result.scalars().all()
            if not _cross_tenant(row)
        ]

    async def add_policy(self, item: RetentionPolicy) -> None:
        self._s.add(
            MemoryPolicyORM(
                id=item.id,
                tenant_id=item.tenant_id,
                workspace_id=item.workspace_id,
                layer=item.layer,
                label=item.label,
                description=item.description,
                ttl_minutes=item.ttl_minutes,
                max_items=item.max_items,
                storage_mb=item.storage_mb,
                eviction=item.eviction,
                hit_rate=item.hit_rate,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
        )

    async def list_policies(self, workspace_id: UUID) -> list[RetentionPolicy]:
        result = await self._s.execute(
            select(MemoryPolicyORM).where(MemoryPolicyORM.workspace_id == workspace_id)
        )
        return [_policy(row) for row in result.scalars().all() if not _cross_tenant(row)]

    async def get_policy_by_label(self, workspace_id: UUID, label: str) -> RetentionPolicy | None:
        result = await self._s.execute(
            select(MemoryPolicyORM).where(
                MemoryPolicyORM.workspace_id == workspace_id,
                MemoryPolicyORM.label == label,
            )
        )
        row = result.scalars().first()
        if row is None or _cross_tenant(row):
            return None
        return _policy(row)


def _policy(row: MemoryPolicyORM) -> RetentionPolicy:
    return RetentionPolicy(
        id=row.id,
        tenant_id=row.tenant_id,
        workspace_id=row.workspace_id,
        layer=row.layer,  # type: ignore[arg-type]
        label=row.label,
        description=row.description,
        ttl_minutes=row.ttl_minutes,
        max_items=row.max_items,
        storage_mb=row.storage_mb,
        eviction=row.eviction,  # type: ignore[arg-type]
        hit_rate=row.hit_rate,
        updated_at=row.updated_at,
        created_at=row.created_at,
    )
