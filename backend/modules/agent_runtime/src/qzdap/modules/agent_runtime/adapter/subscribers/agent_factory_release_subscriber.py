"""Phase 19: agent_factory.version.released → agent_runtime.CatalogAgent 同步.

当 ``ReleaseAgentVersionUseCase`` 写完 release 行后, 会发布
``agent_factory.version.released`` 事件 (envelope 携带 ``template_id``,
``version_id``, ``eval_score``).

本 subscriber 在 catalog 里找 ``admin_agents.id == template_id`` 的行, 找到就:
  - ``status`` → ``'published'``
  - ``version`` → ``'v{tenant_marker}-{version_tag}'`` (前端 to_admin_dict 直接返)
  - ``audit_events`` 追加一条 {action: '工厂发布', detail: '...'}

约定: 在 admin UI 创建 catalog agent 时, 把 ``id`` 设成对应的 ``template_id``
(让两侧用同一个 UUID). 这样 factory release 就能直接命中已存在的 catalog 行.

若 catalog 找不到匹配行, silent skip (产品上允许独立建 catalog agent,
只有"两边都建过"才需要联动).
"""
from __future__ import annotations

import inspect
import logging
from datetime import UTC
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from qzdap.modules.agent_runtime.adapter.persistence.catalog_repositories import (
    SqlCatalogAgentRepository,
)
from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent

_log = logging.getLogger(__name__)

# 事件名: 与 agent_factory.domain.events.AgentReleased.event_name 一致.
EVENT_NAME = "agent_factory.version.released"


def _parse_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _as_agent_released_payload(envelope: Any) -> dict[str, Any] | None:
    """兼容 EventEnvelope 与 raw dict. 返回 {template_id, version_id,
    eval_score, version_tag?} 的 dict 或 None.
    """
    if isinstance(envelope, dict):
        payload = envelope.get("payload") or envelope
    else:
        payload = getattr(envelope, "payload", None) or envelope
    if not isinstance(payload, dict):
        return None
    return payload


def _bump_version_string(current: str, version_tag: str) -> str:
    """CatalogAgent.version 是字符串, 用 tag 拼出 v1.0 / v0.3 之类.

    工厂侧的 version_tag (e.g. 'v1' or '0.3.1') 直接当 version 用最稳.
    """
    if not version_tag:
        return current
    return version_tag


def build_handler(session: AsyncSession):
    """返回一个闭包, 闭包捕获 session, 真正干活的 handler."""
    repo = SqlCatalogAgentRepository(session)

    async def handle(envelope: Any) -> None:
        # 防御: InProcessBus 已经按 event_name 过滤, 但 envelope 来自
        # redis_stream / kafka 时可能无此字段, 这里再校验一次
        event_name = getattr(envelope, "event_name", None)
        if event_name is not None and event_name != EVENT_NAME:
            return
        payload = _as_agent_released_payload(envelope)
        if payload is None:
            _log.debug("agent_factory_release: no payload, skip")
            return
        template_id = _parse_uuid(payload.get("template_id"))
        if template_id is None:
            _log.debug("agent_factory_release: no template_id, skip")
            return
        agent = await repo.get(template_id)
        if agent is None:
            _log.info(
                "agent_factory_release: no catalog row for template_id=%s, skip",
                template_id,
            )
            return
        version_tag = str(payload.get("version_tag") or "")
        new_version = _bump_version_string(agent.version, version_tag)
        eval_score = payload.get("eval_score")
        detail = f"version_tag={version_tag}" + (
            f" eval_score={eval_score}" if eval_score is not None else ""
        )
        # 直接 replace, 不走 apply_patch (apply_patch 会在 status='published' 时
        # 触发 self.publish() 重新算 version = f"v{len(versions)+1}", 覆盖我们
        # 想设的 factory version_tag).
        from dataclasses import replace as _replace
        from datetime import datetime as _dt

        now = _dt.now(UTC)
        audit_event = {
            "id": str(UUID(int=0)),
            "at": now.isoformat(),
            "actor": "agent_factory",
            "action": "工厂发布",
            "detail": detail,
        }
        # 复制 frontend snapshot 进 versions[0] (admin UI 期望 version 有 snapshot)
        snapshot = {
            "name": agent.name,
            "description": agent.description,
            "category": agent.category,
            "owner": agent.owner,
            "tags": list(agent.tags),
            "tone": agent.tone,
            "visibleScope": list(agent.visible_scope),
            "dataAccess": agent.data_access,
            "model": agent.model,
            "maxSteps": agent.max_steps,
            "tools": list(agent.tools),
            "prompts": dict(agent.prompts),
            "customPrompts": list(agent.custom_prompts),
            "knowledgeRefs": list(agent.knowledge_refs),
            "memoryPolicy": dict(agent.memory_policy),
            "flowRefs": list(agent.flow_refs),
            "profile": agent.profile,
        }
        existing = [v for v in agent.versions if not v.get("current")]
        new_version_record = {
            "version": new_version,
            "publisher": "agent_factory",
            "releasedAt": now.strftime("%Y-%m-%d"),
            "current": True,
            "snapshot": snapshot,
            "rollbackOf": None,
        }
        updated: CatalogAgent = _replace(
            agent,
            status="published",
            version=new_version,
            versions=[new_version_record, *existing],
            audit_events=[*agent.audit_events, audit_event],
            updated_at=now,
        )
        await repo.update(updated)
        # 显式 commit: 防止 subscriber session 被外层回收导致 audit 不落库
        try:
            await session.commit()
        except Exception:  # noqa: BLE001
            _log.exception("agent_factory_release: commit failed")

    return handle


async def install(event_bus: Any, session_opener: Any) -> None:
    """安装 subscriber. ``session_opener`` 可以是:

    * 一个 async context manager factory (例如 ``container.session_factory()``,
      调用 ``.session()`` 拿一个 async CM)
    * 一个 async generator (lifespan 里那种 ``async def gen(): ... yield s``)
    * 任何支持 ``async with session_opener() as session`` 的对象
    """
    async def _open_session():  # type: ignore[no-untyped-def]
        if hasattr(session_opener, "session") and callable(
            getattr(session_opener, "session", None)
        ):
            # container.session_factory() 模式: 调 .session() 拿 async CM
            cm = session_opener.session()
        else:
            # 直接是 async generator / async context manager factory
            cm = session_opener()
        async with cm as s:
            yield s

    async def _handler(envelope: Any) -> None:
        try:
            async for session in _open_session():
                handler = build_handler(session)
                await handler(envelope)
                return
        except Exception:  # noqa: BLE001
            _log.exception("agent_factory_release handler failed")

    result = event_bus.subscribe(EVENT_NAME, _handler)
    if inspect.isawaitable(result):
        await result


__all__ = ["EVENT_NAME", "build_handler", "install"]
