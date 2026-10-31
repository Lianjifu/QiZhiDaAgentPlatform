"""④ Idempotency Guard 的 PostgreSQL 实现 —— 表 ``session_inbox``。

表归 Session 层（Gateway 方案 §8），但**实现**放在 Session 侧模块里：
Gateway 只持端口，DB 访问不越层。

⚠️ **两条 INSERT 路径必须分开**（决策 #5）：

- **strong** —— ``ON CONFLICT (...) WHERE key_strength = 'strong' DO NOTHING``，
  原子 claim。**arbiter 必须带同样的谓词**，否则推断不出这个部分唯一索引。
- **weak** —— 普通 INSERT，**不带 arbiter**。weak 行不落进唯一索引的冲突面，
  因此**永不判重、永远放行**。若两条路径合成一条，weak 就会互相抑制，
  「用户连发两条『好的』」会被误杀。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from qzdap_agent_runtime.gateway.idempotency import (
    InboxScope,
)
from qzdap_agent_runtime.gateway.types import (
    IdempotencyDecision,
    IdempotencyKey,
)

_log = logging.getLogger(__name__)

# 崩溃接管阈值 —— 沿用旧路径 try_claim 的经验（30 分钟僵尸接管）。
CLAIM_STALE_MINUTES = 30

# 过期行清理的单批上限 —— 避免长事务。
SWEEP_BATCH_LIMIT = 1000

_CLAIM_SQL = text(
    """
    INSERT INTO session_inbox
        (id, tenant_id, workspace_id, channel_id, idempotency_key, key_source, key_strength,
         external_message_id, payload_hash, status, claimed_at, expires_at, turn_id, trace_id,
         received_at)
    VALUES
        (:id, :tenant_id, :workspace_id, :channel_id, :idempotency_key, :key_source, 'strong',
         :external_message_id, :payload_hash, 'claimed', now(), :expires_at, NULL, :trace_id, now())
    ON CONFLICT (tenant_id, workspace_id, channel_id, idempotency_key)
        WHERE key_strength = 'strong'
    DO NOTHING
    RETURNING id, status, turn_id, expires_at
    """
)

_WEAK_SQL = text(
    """
    INSERT INTO session_inbox
        (id, tenant_id, workspace_id, channel_id, idempotency_key, key_source, key_strength,
         external_message_id, payload_hash, status, claimed_at, expires_at, turn_id, trace_id,
         received_at)
    VALUES
        (:id, :tenant_id, :workspace_id, :channel_id, :idempotency_key, :key_source, 'weak',
         NULL, :payload_hash, 'received', NULL, :expires_at, NULL, :trace_id, now())
    RETURNING id, status, turn_id, expires_at
    """
)

_SELECT_SQL = text(
    """
    SELECT id, status, turn_id, expires_at, claimed_at,
           (expires_at <= now()) AS expired,
           (claimed_at IS NOT NULL
            AND claimed_at < now() - make_interval(mins => :stale_minutes)) AS stale
      FROM session_inbox
     WHERE tenant_id = :tenant_id
       AND workspace_id = :workspace_id
       AND channel_id = :channel_id
       AND idempotency_key = :idempotency_key
       AND key_strength = 'strong'
    """
)

_TAKEOVER_SQL = text(
    """
    UPDATE session_inbox
       SET status = 'claimed', claimed_at = now(), expires_at = :expires_at
     WHERE id = :id
    """
)

_DELETE_SQL = text("DELETE FROM session_inbox WHERE id = :id")

_COMPLETE_SQL = text(
    """
    UPDATE session_inbox
       SET status = 'completed', turn_id = COALESCE(:turn_id, turn_id)
     WHERE id = :id
    """
)

_SWEEP_SQL = text(
    """
    DELETE FROM session_inbox
     WHERE id IN (
        SELECT id FROM session_inbox
         WHERE expires_at <= now()
         ORDER BY expires_at
         LIMIT :limit
     )
    """
)


class PostgresIdempotencyStore:
    """``session_inbox`` 上的 strong claim / weak 记录。

    **每次操作独立开事务并立即提交** —— claim 必须在本轮开始之前落库，
    否则并发的第二个请求看不到它，两轮都会起。
    """

    def __init__(self, session_factory: Any) -> None:
        self._sf = session_factory

    async def claim(
        self,
        scope: InboxScope,
        key: IdempotencyKey,
        *,
        payload_hash: str = "",
        external_message_id: str | None = None,
        trace_id: str = "",
    ) -> IdempotencyDecision:
        """strong 键的原子 claim。

        返回 ``new`` → 本轮由我方接管；``duplicate`` / ``in_progress`` →
        已有同一键的行，**不得**再跑一轮；``taken_over`` → 命中的行已过期
        或原处理方已死，接管后继续往下走。
        """
        params = self._params(
            scope,
            key,
            payload_hash=payload_hash,
            external_message_id=external_message_id,
            trace_id=trace_id,
        )
        # 过期接管要在**同一个事务**里 DELETE 旧行 + INSERT 新行；
        # 并发下旧行可能刚被别人删掉 → 重试一次。
        for _attempt in range(3):
            async with self._sf.session() as session, session.begin():
                inserted = (await session.execute(_CLAIM_SQL, params)).first()
                if inserted is not None:
                    return _decision("new", inserted, key)

                existing = (await session.execute(_SELECT_SQL, params)).first()
                if existing is None:
                    # 冲突的行在两次语句之间消失了（别人接管并删了）→ 重试。
                    continue

                if existing.expired:
                    # 「过期不误杀」的第二道保险：当作不存在 —— 删旧行、插新行。
                    await session.execute(_DELETE_SQL, {"id": existing.id})
                    inserted = (await session.execute(_CLAIM_SQL, params)).first()
                    if inserted is not None:
                        return _decision("taken_over", inserted, key)
                    continue

                status = str(existing.status)
                if status == "completed":
                    return _decision("duplicate", existing, key)
                if status == "claimed" and not existing.stale:
                    return _decision("in_progress", existing, key)
                # status ∈ {received, abandoned} 或 claimed 但已超时 → 接管。
                await session.execute(
                    _TAKEOVER_SQL, {"id": existing.id, "expires_at": key.expires_at}
                )
                return IdempotencyDecision(
                    outcome="taken_over",
                    key_strength=key.strength,
                    row_id=existing.id,
                    status="claimed",
                    turn_id=existing.turn_id,
                    expires_at=key.expires_at,
                )
        raise RuntimeError("idempotency claim failed to converge")

    async def record_weak(
        self,
        scope: InboxScope,
        key: IdempotencyKey,
        *,
        payload_hash: str = "",
        trace_id: str = "",
    ) -> IdempotencyDecision:
        """weak 键的落表记录 —— **永不判重**（决策 #5）。

        不带 ``ON CONFLICT``：weak 行不在 ``uq_session_inbox_idem_strong`` 的
        谓词范围内，插入永不冲突。
        """
        params = self._params(
            scope,
            key,
            payload_hash=payload_hash,
            external_message_id=None,
            trace_id=trace_id,
        )
        async with self._sf.session() as session, session.begin():
            inserted = (await session.execute(_WEAK_SQL, params)).first()
            if inserted is None:  # pragma: no cover - RETURNING 必然有一行
                raise RuntimeError("weak idempotency insert returned no row")
            return IdempotencyDecision(
                outcome="new",
                key_strength="weak",
                row_id=inserted.id,
                status=inserted.status,
                turn_id=inserted.turn_id,
                expires_at=inserted.expires_at,
            )

    async def mark_completed(self, row_id: UUID, *, turn_id: UUID | None = None) -> None:
        async with self._sf.session() as session, session.begin():
            await session.execute(_COMPLETE_SQL, {"id": row_id, "turn_id": turn_id})

    async def release(self, row_id: UUID) -> None:
        """删掉这一行 —— 键没被消费，调用方还要能用同一个键重试。"""
        async with self._sf.session() as session, session.begin():
            await session.execute(_DELETE_SQL, {"id": row_id})

    async def sweep_expired(self, *, limit: int = SWEEP_BATCH_LIMIT) -> int:
        """删掉过期的行 —— **Session 的 sweeper 调用**（§4.3.1）。

        唯一约束不含 ``expires_at``：过期行留在表里，同一个键重发时仍会命中冲突。
        claim 里的过期分支是第二道保险；**只有这一条也能正确工作，但本方法不做，
        表会无限膨胀**。
        """
        async with self._sf.session() as session, session.begin():
            result = await session.execute(_SWEEP_SQL, {"limit": limit})
            return int(result.rowcount or 0)

    @staticmethod
    def _params(
        scope: InboxScope,
        key: IdempotencyKey,
        *,
        payload_hash: str,
        external_message_id: str | None,
        trace_id: str,
    ) -> dict[str, Any]:
        return {
            "id": uuid4(),
            "tenant_id": scope.tenant_id,
            "workspace_id": scope.workspace_id,
            "channel_id": scope.channel_id,
            "idempotency_key": key.value,
            "key_source": str(key.source),
            "key_strength": key.strength,
            "external_message_id": external_message_id,
            "payload_hash": payload_hash,
            "expires_at": key.expires_at,
            "trace_id": trace_id[:64] if trace_id else None,
            "stale_minutes": CLAIM_STALE_MINUTES,
        }


def _decision(
    outcome: str,
    row: Any,
    key: IdempotencyKey,
) -> IdempotencyDecision:
    return IdempotencyDecision(
        outcome=outcome,  # type: ignore[arg-type]
        key_strength=key.strength,
        row_id=row.id,
        status=row.status,
        turn_id=row.turn_id,
        expires_at=row.expires_at or key.expires_at,
    )


__all__ = ["CLAIM_STALE_MINUTES", "SWEEP_BATCH_LIMIT", "PostgresIdempotencyStore"]
