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


__all__ = ["QuotaService"]
