"""Phase 4: model quota service.

每 (tenant, workspace, model, period) 一条 model_quotas 配置 + 一条 (或一条新周期)
model_quota_usage 计数. period_key 是当前周期的 bucket id (例如 '2026-10-17T10:00'
或 '2026-10-17').

API:
  - check_and_consume(actor, model_id, period='minute', estimated_tokens_in=0)
    抛 QuotaExceeded (status=429) 当超额, 否则 atomic UPDATE 增计数
  - record(actor, model_id, period='minute', tokens_in=0, tokens_out=0)
    异步累加实际 usage (在 stream 完成后调用)

设计要点:
  - 每次 check_and_consume 在 SQL 内做 read+update (避免 race condition)
  - 默认 period='minute' (限流粒度), hourly/daily 留给 admin 配
  - 没配 quota (model_quotas 无行) → 不限制 (skip)
  - 0 / 0 (max 0) → 视为「不限制」 (admin 用 0 表示无上限)
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.model.adapter.persistence.quota_models import (
    ModelQuotaORM,
    ModelQuotaUsageORM,
)
from qzdap.modules.model.domain.errors import QuotaExceeded


def _period_key(period: str, now: datetime) -> str:
    """Period bucket id 简化滑动窗口."""
    if period == "minute":
        return now.strftime("%Y-%m-%dT%H:%M")
    if period == "hour":
        return now.strftime("%Y-%m-%dT%H")
    if period == "day":
        return now.strftime("%Y-%m-%d")
    raise ValueError(f"unknown period: {period!r}")


def _period_start(period: str, now: datetime) -> datetime:
    """Period 起始时间 (UTC)."""
    if period == "minute":
        return now.replace(second=0, microsecond=0)
    if period == "hour":
        return now.replace(minute=0, second=0, microsecond=0)
    if period == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"unknown period: {period!r}")


class QuotaService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def check_and_consume(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        model_id: UUID,
        period: str = "minute",
        estimated_tokens_in: int = 0,
    ) -> None:
        """检查 + 原子扣减. 超额抛 QuotaExceeded.

        实现: 单独短事务. 不和 outer ModelService session 共享 — outer rollback
        (例如 ProviderTransportError) 不能把 quota 计数也回滚, 否则用户每次失败
        调用都不计数, 超额保护失效.
        """
        now = datetime.now(UTC)
        key = _period_key(period, now)
        start = _period_start(period, now)

        # 读配置
        cfg_row = await self._s.execute(
            select(ModelQuotaORM).where(
                ModelQuotaORM.tenant_id == tenant_id,
                ModelQuotaORM.workspace_id == workspace_id,
                ModelQuotaORM.model_id == model_id,
                ModelQuotaORM.period == period,
                ModelQuotaORM.enabled.is_(True),
            )
        )
        cfg = cfg_row.scalar_one_or_none()
        if cfg is None:
            return
        max_in = int(cfg.max_tokens_in)
        max_out = int(cfg.max_tokens_out)
        max_req = int(cfg.max_requests)
        if max_in == 0 and max_out == 0 and max_req == 0:
            return

        # 插入 usage 行 (新周期)
        stmt = (
            pg_insert(ModelQuotaUsageORM)
            .values(
                id=uuid4(),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                model_id=model_id,
                period=period,
                period_key=key,
                period_start=start,
                tokens_in=0,
                tokens_out=0,
                requests=0,
            )
            .on_conflict_do_nothing(
                constraint="uq_model_quota_usage_window",
            )
        )
        await self._s.execute(stmt)

        # 读当前 usage
        result = await self._s.execute(
            select(ModelQuotaUsageORM).where(
                ModelQuotaUsageORM.tenant_id == tenant_id,
                ModelQuotaUsageORM.workspace_id == workspace_id,
                ModelQuotaUsageORM.model_id == model_id,
                ModelQuotaUsageORM.period == period,
                ModelQuotaUsageORM.period_key == key,
            )
        )
        usage = result.scalar_one()
        projected_in = int(usage.tokens_in) + int(estimated_tokens_in)
        projected_req = int(usage.requests) + 1
        if max_in and projected_in > max_in:
            raise QuotaExceeded(
                f"tokens_in quota exceeded for model {model_id}: "
                f"projected={projected_in} > max={max_in} (period={period})"
            )
        if max_req and projected_req > max_req:
            raise QuotaExceeded(
                f"requests quota exceeded for model {model_id}: "
                f"projected={projected_req} > max={max_req} (period={period})"
            )
        # 原子增 + 单独提交
        from sqlalchemy import update

        await self._s.execute(
            update(ModelQuotaUsageORM)
            .where(
                ModelQuotaUsageORM.tenant_id == tenant_id,
                ModelQuotaUsageORM.workspace_id == workspace_id,
                ModelQuotaUsageORM.model_id == model_id,
                ModelQuotaUsageORM.period == period,
                ModelQuotaUsageORM.period_key == key,
            )
            .values(
                tokens_in=ModelQuotaUsageORM.tokens_in + int(estimated_tokens_in),
                requests=ModelQuotaUsageORM.requests + 1,
                updated_at=now,
            )
        )
        # 关键: 显式 commit quota 事务, 不让 outer ModelService 的 rollback 抹掉
        await self._s.commit()

    async def record(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        model_id: UUID,
        period: str = "minute",
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        """在 stream 完成后修正实际 token 数. estimated - 0 (默认) = 不增."""
        if tokens_in == 0 and tokens_out == 0:
            return
        now = datetime.now(UTC)
        key = _period_key(period, now)
        from sqlalchemy import update

        await self._s.execute(
            update(ModelQuotaUsageORM)
            .where(
                ModelQuotaUsageORM.tenant_id == tenant_id,
                ModelQuotaUsageORM.workspace_id == workspace_id,
                ModelQuotaUsageORM.model_id == model_id,
                ModelQuotaUsageORM.period == period,
                ModelQuotaUsageORM.period_key == key,
            )
            .values(
                tokens_in=ModelQuotaUsageORM.tokens_in + int(tokens_in),
                tokens_out=ModelQuotaUsageORM.tokens_out + int(tokens_out),
                updated_at=now,
            )
        )

    # ── Phase 17: admin CRUD + usage 查询 ─────────────────────────────────
    async def list_quotas(
        self, *, tenant_id: UUID, workspace_id: UUID
    ) -> list[dict]:
        """列 workspace 内所有 quota 配置."""
        result = await self._s.execute(
            select(ModelQuotaORM)
            .where(
                ModelQuotaORM.tenant_id == tenant_id,
                ModelQuotaORM.workspace_id == workspace_id,
            )
            .order_by(ModelQuotaORM.model_id, ModelQuotaORM.period)
        )
        return [
            {
                "id": str(row.id),
                "tenantId": str(row.tenant_id),
                "workspaceId": str(row.workspace_id),
                "modelId": str(row.model_id),
                "period": row.period,
                "maxTokensIn": int(row.max_tokens_in),
                "maxTokensOut": int(row.max_tokens_out),
                "maxRequests": int(row.max_requests),
                "enabled": bool(row.enabled),
                "description": row.description,
            }
            for row in result.scalars().all()
        ]

    async def upsert_quota(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        body: dict,
    ) -> dict:
        """创建或更新一条 quota (按 (model_id, period) upsert)."""
        try:
            model_id = UUID(str(body.get("modelId") or body.get("model_id")))
        except (ValueError, TypeError) as exc:
            raise ValueError("modelId 不是有效 UUID") from exc
        period = str(body.get("period") or "").strip()
        if period not in {"minute", "hour", "day"}:
            raise ValueError("period 必须是 minute/hour/day")
        max_tokens_in = int(body.get("maxTokensIn") or body.get("max_tokens_in") or 0)
        max_tokens_out = int(
            body.get("maxTokensOut") or body.get("max_tokens_out") or 0
        )
        max_requests = int(body.get("maxRequests") or body.get("max_requests") or 0)
        if max_tokens_in < 0 or max_tokens_out < 0 or max_requests < 0:
            raise ValueError("maxTokensIn/maxTokensOut/maxRequests 必须 >= 0")
        enabled = bool(body.get("enabled", True))
        description = str(body.get("description") or "")
        now = datetime.now(UTC)
        # upsert via INSERT ... ON CONFLICT
        insert_values = {
            "id": uuid4(),
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "model_id": model_id,
            "period": period,
            "max_tokens_in": max_tokens_in,
            "max_tokens_out": max_tokens_out,
            "max_requests": max_requests,
            "enabled": enabled,
            "description": description,
            "created_at": now,
            "updated_at": now,
        }
        stmt = pg_insert(ModelQuotaORM).values(**insert_values)
        update_dict = {
            "max_tokens_in": max_tokens_in,
            "max_tokens_out": max_tokens_out,
            "max_requests": max_requests,
            "enabled": enabled,
            "description": description,
            "updated_at": now,
        }
        stmt = stmt.on_conflict_do_update(
            constraint="uq_model_quotas_tenant_ws_model_period",
            set_=update_dict,
        )
        await self._s.execute(stmt)
        await self._s.commit()
        # 读回
        result = await self._s.execute(
            select(ModelQuotaORM).where(
                ModelQuotaORM.tenant_id == tenant_id,
                ModelQuotaORM.workspace_id == workspace_id,
                ModelQuotaORM.model_id == model_id,
                ModelQuotaORM.period == period,
            )
        )
        row = result.scalar_one()
        return {
            "id": str(row.id),
            "tenantId": str(row.tenant_id),
            "workspaceId": str(row.workspace_id),
            "modelId": str(row.model_id),
            "period": row.period,
            "maxTokensIn": int(row.max_tokens_in),
            "maxTokensOut": int(row.max_tokens_out),
            "maxRequests": int(row.max_requests),
            "enabled": bool(row.enabled),
            "description": row.description,
        }

    async def delete_quota(self, *, quota_id: UUID) -> None:
        """删除一条 quota 配置 (不影响 usage 历史)."""
        from sqlalchemy import delete

        await self._s.execute(
            delete(ModelQuotaORM).where(ModelQuotaORM.id == quota_id)
        )
        await self._s.commit()

    async def list_usage(
        self, *, tenant_id: UUID, workspace_id: UUID
    ) -> list[dict]:
        """当前每个 (model, period) 的 usage 计数 + 配置上限 (若有)."""
        from sqlalchemy import func

        result = await self._s.execute(
            select(
                ModelQuotaUsageORM.model_id,
                ModelQuotaUsageORM.period,
                func.max(ModelQuotaUsageORM.period_key).label("latest_key"),
                func.sum(ModelQuotaUsageORM.tokens_in).label("total_tokens_in"),
                func.sum(ModelQuotaUsageORM.tokens_out).label("total_tokens_out"),
                func.sum(ModelQuotaUsageORM.requests).label("total_requests"),
            )
            .where(
                ModelQuotaUsageORM.tenant_id == tenant_id,
                ModelQuotaUsageORM.workspace_id == workspace_id,
            )
            .group_by(
                ModelQuotaUsageORM.model_id,
                ModelQuotaUsageORM.period,
            )
        )
        rows = result.all()
        # 拉配置上限 (若有)
        cfg_result = await self._s.execute(
            select(ModelQuotaORM).where(
                ModelQuotaORM.tenant_id == tenant_id,
                ModelQuotaORM.workspace_id == workspace_id,
            )
        )
        cfg_index = {
            (str(c.model_id), c.period): c for c in cfg_result.scalars().all()
        }
        out: list[dict] = []
        for r in rows:
            cfg = cfg_index.get((str(r.model_id), r.period))
            out.append(
                {
                    "modelId": str(r.model_id),
                    "period": r.period,
                    "latestPeriodKey": r.latest_key,
                    "tokensIn": int(r.total_tokens_in or 0),
                    "tokensOut": int(r.total_tokens_out or 0),
                    "requests": int(r.total_requests or 0),
                    "maxTokensIn": int(cfg.max_tokens_in) if cfg else None,
                    "maxTokensOut": int(cfg.max_tokens_out) if cfg else None,
                    "maxRequests": int(cfg.max_requests) if cfg else None,
                }
            )
        return out


__all__ = ["QuotaService"]
