"""SQL implementation of CatalogModelResolver.

每 resolve 一次开一个短会话 (SessionFactory.session() async cm), 查
admin_models 表 (跨模块 ORM 读取), 取 workspace + upstream_model + active 的
第一个匹配, 返回 ModelId (UUID).

设计要点:
  - 短事务: 每次 resolve 完就关闭, 不污染 copilot 的长 turn 会话
  - 跨模块 ORM 读: admin_models 由 model 模块建表, 这里只读不写
  - tenant 守卫: tenant_id 是复合过滤的一部分, 防止越权跨租户解析
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from qzdap.modules.agent_runtime.application.ports.catalog_model_resolver import (
    CatalogModelResolver,
)

# 跨模块 ORM 读: admin_models 由 model 模块建表
from qzdap.modules.model.adapter.persistence.models import CatalogModelORM
from qzdap_kernel.ids import ModelId
from qzdap_persistence.session_factory import SessionFactory

_log = logging.getLogger(__name__)


class SqlCatalogModelResolver(CatalogModelResolver):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._sf = session_factory

    async def resolve(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        upstream_model: str,
    ) -> ModelId | None:
        upstream = (upstream_model or "").strip()
        if not upstream:
            return None
        try:
            async with self._sf.session() as session:
                result = await session.execute(
                    select(CatalogModelORM)
                    .where(
                        CatalogModelORM.tenant_id == tenant_id,
                        CatalogModelORM.workspace_id == workspace_id,
                        CatalogModelORM.upstream_model == upstream,
                        CatalogModelORM.status == "active",
                    )
                    .order_by(CatalogModelORM.created_at.desc())
                    .limit(1)
                )
                row = result.scalar_one_or_none()
                if row is None:
                    _log.warning(
                        "catalog_resolve_no_match",
                        extra={
                            "tenant_id": str(tenant_id),
                            "workspace_id": str(workspace_id),
                            "upstream_model": upstream,
                        },
                    )
                    return None
                return ModelId(row.id)
        except (SQLAlchemyError, RuntimeError, OSError) as exc:  # defensive
            # DB 抖动不应让 chat 整个挂掉 — 回退到 env 默认 LLM
            _log.warning(
                "catalog_model_resolve_failed",
                extra={
                    "tenant_id": str(tenant_id),
                    "workspace_id": str(workspace_id),
                    "upstream_model": upstream,
                    "error": str(exc),
                },
            )
            return None

    async def price_of(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        model_id: ModelId,
    ) -> tuple[float, float] | None:
        """单价的 (price_in, price_out), 每 1K token."""
        try:
            async with self._sf.session() as session:
                row = (
                    await session.execute(
                        select(
                            CatalogModelORM.price_in,
                            CatalogModelORM.price_out,
                        ).where(
                            CatalogModelORM.id == UUID(str(model_id)),
                            CatalogModelORM.tenant_id == tenant_id,
                            CatalogModelORM.workspace_id == workspace_id,
                        )
                    )
                ).one_or_none()
                if row is None:
                    return None
                return float(row[0] or 0.0), float(row[1] or 0.0)
        except (SQLAlchemyError, RuntimeError, OSError) as exc:  # defensive
            _log.warning(
                "catalog_price_lookup_failed",
                extra={"model_id": str(model_id), "error": str(exc)},
            )
            return None


__all__ = ["SqlCatalogModelResolver"]
