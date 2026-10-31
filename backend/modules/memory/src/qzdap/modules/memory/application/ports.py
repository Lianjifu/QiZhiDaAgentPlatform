from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from qzdap.modules.memory.domain.entities import (
    L2Fact,
    L3Entry,
    PromotionEvent,
    RetentionPolicy,
)


@runtime_checkable
class EmbeddingPort(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(slots=True, frozen=True)
class VectorHit:
    item_id: UUID
    score: float
    layer: str
    content: str


@runtime_checkable
class VectorSearchPort(Protocol):
    async def upsert(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        item_id: UUID,
        layer: str,
        content: str,
        embedding: list[float],
        user_id: UUID | None = None,
    ) -> None: ...

    async def delete(self, ids: list[UUID]) -> None: ...

    async def search(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        query_embedding: list[float],
        top_k: int,
        user_id: UUID | None = None,
    ) -> list[VectorHit]: ...


class MemoryCatalogRepository(ABC):
    @abstractmethod
    async def add_l2(self, item: L2Fact) -> None: ...

    @abstractmethod
    async def get_l2(self, item_id: UUID) -> L2Fact | None: ...

    @abstractmethod
    async def list_l2(self, workspace_id: UUID, *, user_id: UUID | None = None) -> list[L2Fact]: ...

    @abstractmethod
    async def update_l2(self, item: L2Fact) -> None: ...

    @abstractmethod
    async def find_l2_by_hash(
        self,
        workspace_id: UUID,
        *,
        user_id: UUID,
        content_hash: str,
    ) -> L2Fact | None:
        """按内容哈希查已有条目 ✓（**去重的依据** ✓ —— §4.4 ✓）。

        ⚠️ **唯一约束只对有 hash 的行生效** ✓（存量行为 NULL ✓）。
        """
        ...

    @abstractmethod
    async def add_l3(self, item: L3Entry) -> None: ...

    @abstractmethod
    async def get_l3(self, item_id: UUID) -> L3Entry | None: ...

    @abstractmethod
    async def list_l3(self, workspace_id: UUID) -> list[L3Entry]: ...

    @abstractmethod
    async def list_l2_updated_since(self, since: datetime, *, limit: int = 100) -> list[L2Fact]:
        """**最近更新过的 L2** ✓（兜底补写的来源 ✓ —— §5.4 ✓）。"""
        ...

    @abstractmethod
    async def search_l2_by_keyword(
        self,
        workspace_id: UUID,
        *,
        user_id: UUID | None = None,
        keyword: str,
        limit: int,
        session_id: UUID | None = None,
    ) -> list[L2Fact]:
        """**词法候选** ✓ —— 过滤与截断**下推到 SQL** ✓（§3.1 第 2 步 ✓）。

        ⚠️ **不是全量扫描** ✗✗ —— Python 侧逐行过滤是现状的缺陷 ✗
        （1 万条 L2 时召回延迟随 N 线性增长 ✗）。
        """
        ...

    @abstractmethod
    async def search_l3_by_keyword(
        self,
        workspace_id: UUID,
        *,
        keyword: str,
        limit: int,
    ) -> list[L3Entry]:
        """L3 的词法候选 ✓ —— 同样**下推到 SQL** ✓。"""
        ...

    @abstractmethod
    async def update_l3(self, item: L3Entry) -> None: ...

    @abstractmethod
    async def add_promotion(self, item: PromotionEvent) -> None: ...

    @abstractmethod
    async def list_promotions(self, workspace_id: UUID) -> list[PromotionEvent]: ...

    @abstractmethod
    async def list_policy_workspaces(self) -> list[UUID]:
        """**有策略的工作区** ✓（淘汰器按工作区跑 ✓）。"""
        ...

    @abstractmethod
    async def usage_by_day(self, workspace_id: UUID, *, since: datetime) -> list[tuple[date, int]]:
        """**每天被用过的条数** ✓（真实使用趋势 ✓ —— C7 ✓）。"""
        ...

    @abstractmethod
    async def add_policy(self, item: RetentionPolicy) -> None: ...

    @abstractmethod
    async def list_policies(self, workspace_id: UUID) -> list[RetentionPolicy]: ...

    @abstractmethod
    async def get_policy_by_label(
        self, workspace_id: UUID, label: str
    ) -> RetentionPolicy | None: ...


__all__ = [
    "EmbeddingPort",
    "MemoryCatalogRepository",
    "VectorHit",
    "VectorSearchPort",
]
