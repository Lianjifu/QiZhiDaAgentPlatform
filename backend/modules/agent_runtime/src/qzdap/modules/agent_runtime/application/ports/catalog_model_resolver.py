"""CatalogModelResolver: 把 agent 的 upstream model 名称(str)解析成 admin_models.id (UUID).

P6 model 模块已经建好 admin_models / admin_model_providers 表 (DB 持久化).
之前 agent_versions.model_id 存的是上游模型名字符串(如 'gpt-4o'),但
ModelService.stream() 只接 ModelId (UUID). 这个 resolver 把二者桥起来:

  agent.model ('gpt-4o') + workspace_id
    → SELECT admin_models.id WHERE workspace_id=? AND upstream_model=? AND status='active'
    → ModelId (UUID) 喂给 LLMPortAdapter.stream(req, model_id=...)

失败时返回 None — 由调用方决定是回退到 env 默认 LLM 还是 raise AGENT_MODEL_UNRESOLVED.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from qzdap_schema.ids import ModelId


class CatalogModelResolver(ABC):
    """把 upstream model 名称解析成 admin_models.id.

    Port — 由 adapter 层 (SqlCatalogModelResolver) 实现, 通过
    SessionFactory 短开会话查询, 避免污染任何长事务.
    """

    @abstractmethod
    async def resolve(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        upstream_model: str,
    ) -> ModelId | None:
        """返回 active model 的 UUID; 没找到返回 None."""
        ...


__all__ = ["CatalogModelResolver"]
