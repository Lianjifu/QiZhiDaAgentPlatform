"""SQL repository for admin console JSON documents."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from qzdap_persistence.tenant_guard import current_tenant_id
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.platform.adapter.persistence.models import AdminOpsDocORM


def _cross_tenant(row: AdminOpsDocORM) -> bool:
    bound = current_tenant_id()
    if bound is None:
        return False
    return row.tenant_id != bound


class SqlAdminOpsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_docs(self, *, workspace_id: UUID, collection: str) -> list[dict[str, Any]]:
        rows = (
            await self._session.scalars(
                select(AdminOpsDocORM).where(
                    AdminOpsDocORM.workspace_id == workspace_id,
                    AdminOpsDocORM.collection == collection,
                )
            )
        ).all()
        items = [dict(row.payload or {}) for row in rows if not _cross_tenant(row)]
        items.sort(key=lambda item: str(item.get("id") or ""))
        return items

    async def get_doc(
        self, *, workspace_id: UUID, collection: str, doc_key: str
    ) -> dict[str, Any] | None:
        row = await self._session.scalar(
            select(AdminOpsDocORM).where(
                AdminOpsDocORM.workspace_id == workspace_id,
                AdminOpsDocORM.collection == collection,
                AdminOpsDocORM.doc_key == doc_key,
            )
        )
        if row is None or _cross_tenant(row):
            return None
        return dict(row.payload or {})

    async def upsert_doc(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        collection: str,
        doc_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        row = await self._session.scalar(
            select(AdminOpsDocORM).where(
                AdminOpsDocORM.workspace_id == workspace_id,
                AdminOpsDocORM.collection == collection,
                AdminOpsDocORM.doc_key == doc_key,
            )
        )
        body = dict(payload)
        body["id"] = doc_key
        if row is None:
            row = AdminOpsDocORM(
                id=uuid4(),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                collection=collection,
                doc_key=doc_key,
                payload=body,
            )
            self._session.add(row)
        else:
            if _cross_tenant(row):
                raise PermissionError("tenant mismatch")
            row.payload = body
        await self._session.flush()
        return dict(row.payload)

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
            saved = await self.upsert_doc(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                collection=collection,
                doc_key=key,
                payload=item,
            )
            out.append(saved)
        return out
