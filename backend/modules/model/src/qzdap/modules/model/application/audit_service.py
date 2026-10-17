"""Phase 8: LLM audit recorder.

每次 ModelService.stream 调用结束, 写一条 audit_log 行 (governance 表):
  - event_type: 'llm.invoke' (成功) 或 'llm.invoke.failed' (失败)
  - payload: {model_id, provider_id, provider_name, latency_ms,
             tokens_in, tokens_out, error_class, error_message, route_id?}

跨模块 ORM 读 + 写: 复用 model 自己的 session (audit_log 表在 governance schema,
但都在同一个 DB). 这样不引入跨模块 import.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

_log = logging.getLogger(__name__)


class LLMAuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def record(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        model_id: UUID,
        provider_id: UUID | None = None,
        provider_name: str = "",
        latency_ms: int = 0,
        tokens_in: int = 0,
        tokens_out: int = 0,
        ok: bool = True,
        error_class: str | None = None,
        error_message: str | None = None,
        route_id: UUID | None = None,
    ) -> None:
        """写一条 audit_log 行. 显式 commit (防止 outer rollback)."""
        import json

        event_type = "llm.invoke" if ok else "llm.invoke.failed"
        payload: dict[str, Any] = {
            "model_id": str(model_id),
            "provider_id": str(provider_id) if provider_id else None,
            "provider_name": provider_name,
            "latency_ms": latency_ms,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }
        if route_id is not None:
            payload["route_id"] = str(route_id)
        if not ok:
            payload["error_class"] = error_class
            payload["error_message"] = error_message or ""
        try:
            # 跨模块写 governance 表 (audit_log). 用 raw SQL + JSONB cast 避免
            # 跨模块 import governance.audit_log ORM.
            from sqlalchemy import text

            await self._s.execute(
                text(
                    "INSERT INTO audit_log (id, tenant_id, actor_id, event_type, payload, "
                    "created_at, updated_at) VALUES (:id, :tenant_id, :actor_id, "
                    ":event_type, CAST(:payload AS jsonb), now(), now())"
                ),
                {
                    "id": str(uuid4()),
                    "tenant_id": str(tenant_id),
                    "actor_id": str(actor_id),
                    "event_type": event_type,
                    "payload": json.dumps(payload, default=str),
                },
            )
            # 显式 commit (防止 outer facade rollback 抹掉, 和 QuotaService/Health 同样的修复)
            await self._s.commit()
        except (RuntimeError, OSError, ValueError) as exc:  # defensive
            _log.warning("audit_record_failed: %s", exc)


# 单独函数构造 table 对象, 避免 module-load 时 import governance 整套 ORM
def _audit_log_table():

    # 反射 audit_log 表. 用 keep_existing 模式只创建引用不加载 schema.
    # 简单粗暴: 用 raw SQL 写入 (跨模块 ORM 风险). 改用 SQLAlchemy 1.x compatible core.
    from sqlalchemy import text

    class _TableProxy:
        """Lazy proxy — provides .insert() compatible with SQLAlchemy 2.x.

        实现: 用 text() 直接构造 INSERT. 比 ORM reflection 更稳.
        """

        async def insert(self, _session, **values):  # type: ignore[no-untyped-def]
            stmt = text(
                "INSERT INTO audit_log (id, tenant_id, actor_id, event_type, payload, "
                "created_at, updated_at) VALUES (:id, :tenant_id, :actor_id, "
                ":event_type, CAST(:payload AS jsonb), now(), now())"
            )
            import json

            payload = values.get("payload", {})
            return await _session.execute(
                stmt,
                {
                    "id": values["id"],
                    "tenant_id": values["tenant_id"],
                    "actor_id": values["actor_id"],
                    "event_type": values["event_type"],
                    "payload": json.dumps(payload),
                },
            )

    return _TableProxy()


_audit_log_table = _audit_log_table()


__all__ = ["LLMAuditService"]
