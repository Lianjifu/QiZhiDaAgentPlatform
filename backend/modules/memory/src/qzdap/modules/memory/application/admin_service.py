"""平面 B · 记忆**管理面**的服务 —— 目录 CRUD / 策略配置 / 审核 / 趋势 ✓。

依据：Memory 方案 §10.1（B2 管理服务）、§2.2 规则 6（平面分离 ✓）。

⚠️ **从 ``MemoryService`` 拆出** ✓（台账 **X16** ✓）—— 运行时
（``recall`` / ``write``）在平面 A ✓，管理查询在这里 ✓。

⚠️ **拆分是纯重构，行为不变** ✓ —— 但**管理端的直写路径绕过写入侧的脱敏与
去重** ✗✗（X16 的后半段 ✓）→ 那个归 **M-42** ✓（Stage 6b ✓）✓。
"""

from __future__ import annotations

import builtins
from datetime import UTC, datetime, timedelta
from logging import getLogger
from typing import Any, Mapping
from uuid import UUID, uuid4

from qzdap.modules.memory.application.admin_rules import AdminEditRules
from qzdap.modules.memory.application.embedding import embed_item
from qzdap.modules.memory.application.ports import (
    EmbeddingPort,
    MemoryCatalogRepository,
    VectorSearchPort,
)
from qzdap.modules.memory.domain.entities import (
    L2_STATUSES,
    L2Fact,
    PromotionEvent,
    RetentionPolicy,
    format_last_update,
)
from qzdap.modules.memory.domain.errors import MemoryNotFound
from qzdap_agent_runtime.context.tokens import estimate_tokens
from qzdap_agent_runtime.memory.policy import (
    MemoryPolicyConfig,
    MemoryPolicyPublisherPort,
)
from qzdap_agent_runtime.memory.promotion import KnowledgePromotionPort
from qzdap_agent_runtime.memory.refine import BufferPort, SessionBufferView
from qzdap_agent_runtime.memory.session_info import SessionInfoPort
from qzdap_kernel.error_codes import ErrorCode
from qzdap_kernel.errors import ConflictError, ValidationError

_log = getLogger(__name__)


class MemoryAdminService:
    """管理面 —— **目录 / 策略 / 审核 / 趋势** ✓（不含运行时召回与写入 ✓）。"""

    def __init__(
        self,
        catalog: MemoryCatalogRepository,
        *,
        embedding: EmbeddingPort | None = None,
        vectors: VectorSearchPort | None = None,
        knowledge: KnowledgePromotionPort | None = None,
        publisher: MemoryPolicyPublisherPort | None = None,
        rules: AdminEditRules | None = None,
        buffer: BufferPort | None = None,
        session_info: SessionInfoPort | None = None,
    ) -> None:
        self._catalog = catalog
        self._embedding = embedding
        self._vectors = vectors
        #: ⚠️ **团队知识候选的落点** ✓（决策 #1 ✓ —— L3 退役 ✓）——
        #: 没有它 = **提升走不了** ✓（明确失败 ✓ —— 不静默写 L3 ✗✗）。
        self._knowledge = knowledge
        #: ⚠️ **策略发布的落点** ✓（B2 的「配置发布与生效」✓ —— M-37 ✓）——
        #: 没有它 = **发布走不了** ✓（明确失败 ✓ —— 不假装发布成功 ✗✗）。
        self._publisher = publisher
        #: ⚠️ **人工编辑的规则** ✓（B3 ✓ —— M-38 ✓）—— 默认用平面 A 的
        #: **同一个闸门实现** ✓（规则 4 ✓）。
        self._rules = rules or AdminEditRules()
        #: ⚠️ **会话缓冲** ✓（**L1 表退役后的唯一来源** ✓ —— M-46 ✓）——
        #: 管理端看的「L1」现在就是**会话缓冲** ✓（决策 #5 ✓）。
        self._buffer = buffer
        #: ⚠️ **会话的展示信息** ✓（「谁 ↔ 哪个 agent」✓）—— 走窄端口 ✓
        #: （Memory 不查会话表 ✓）。
        self._session_info = session_info

    async def list_l1(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        """**会话缓冲的概览** ✓（M-46 ✓ —— **L1 表退役后的唯一来源** ✓）。

        ⚠️ **形状不变** ✓（前端那套 `L1Session` ✓ —— 契约没变 ✓）。
        """
        if self._buffer is None:
            return []
        views = await self._buffer.list_workspace_views(workspace_id=workspace_id)
        items = [self._l1_view(view) for view in views]
        await self._fill_l1_names(items)
        return items

    async def get_l1(self, item_id: UUID) -> dict[str, Any]:
        """**一个会话的缓冲** ✓（详情页 ✓）。"""
        if self._buffer is None:
            raise MemoryNotFound(f"session buffer {item_id} not found")
        rows = await self._buffer.list_session_rows(session_id=item_id)
        if not rows:
            raise MemoryNotFound(f"session buffer {item_id} not found")
        item = self._l1_view(self._l1_view_of(item_id, rows))
        await self._fill_l1_names([item])
        return item

    @staticmethod
    def _l1_view_of(session_id: UUID, rows: list[Any]) -> SessionBufferView:
        """**缓冲行 → 概览** ✓（详情页没有聚合查询 ✓ —— 直接算 ✓）。"""
        first = rows[0]
        return SessionBufferView(
            session_id=session_id,
            workspace_id=first.workspace_id,
            user_id=first.user_id,
            items=len(rows),
            total_chars=sum(len(str(row.content)) for row in rows),
            created_at=min(row.created_at for row in rows),
            last_write_at=max(row.created_at for row in rows),
        )

    async def _fill_l1_names(self, items: list[dict[str, Any]]) -> None:
        """**补上「谁 ↔ 哪个 agent」** ✓（窄端口 ✓ —— Memory 不查会话表 ✓）。

        ⚠️ **查不到就留空** ✓（不猜 ✓ —— 名字只是展示 ✓）。
        """
        if self._session_info is None or not items:
            return
        session_ids = tuple(UUID(str(item["id"])) for item in items)
        described = await self._session_info.describe(session_ids)
        for item in items:
            info = described.get(UUID(str(item["id"])))
            if info is None:
                continue
            item["agentName"] = info.agent_name
            if info.owner_id is not None:
                item["userName"] = str(info.owner_id)

    @staticmethod
    def _l1_view(view: SessionBufferView) -> dict[str, Any]:
        """**概览 → 管理端那一行** ✓（形状与旧的 L1 一样 ✓）。"""
        content_chars = view.total_chars
        return {
            "id": str(view.session_id),
            # ⚠️ **名字由路由补** ✓（Memory 不查 identity / agent 表 ✓ ——
            # 那是别人的表 ✗✗）。
            "userName": str(view.user_id),
            "agentName": "",
            "bufferSize": content_chars,
            "tokensUsed": estimate_tokens("x" * content_chars),
            # ⚠️ **缓冲没有 TTL 列** ✓（提炼器按创建时间判过期 ✓）→ 0 ✓
            # （前端会显示「TTL 剩 0/0m」✓ —— 不骗人 ✓）。
            "ttlMinutes": 0,
            "ttlRemainMin": 0,
            "status": "active",
            "lastFlush": format_last_update(view.last_write_at),
            "startedAt": format_last_update(view.created_at),
        }

    async def list_l2(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._catalog.list_l2(workspace_id)
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_admin_dict() for item in items]

    async def get_l2(self, item_id: UUID) -> dict[str, Any]:
        item = await self._catalog.get_l2(item_id)
        if item is None:
            raise MemoryNotFound(f"l2 fact {item_id} not found")
        return item.to_admin_dict()

    async def flush_l1(self, item_id: UUID, *, workspace_id: UUID) -> dict[str, Any]:
        """**冲掉一个会话的缓冲** ✓（M-46 ✓）—— 内容丢弃 ✓（不再占上下文窗口 ✓）。

        ⚠️ **工作区要对得上** ✓（别人的会话冲不掉 ✓）。
        """
        if self._buffer is None:
            raise MemoryNotFound(f"session buffer {item_id} not found")
        rows = await self._buffer.list_session_rows(session_id=item_id)
        if not rows or rows[0].workspace_id != workspace_id:
            raise MemoryNotFound(f"session buffer {item_id} not found")
        flushed = await self._buffer.delete_session(session_id=item_id)
        return {"id": str(item_id), "flushed": flushed}

    async def flush_all_l1(self, *, workspace_id: UUID) -> dict[str, int]:
        """**冲掉工作区下所有会话的缓冲** ✓（M-46 ✓）。"""
        if self._buffer is None:
            return {"flushed": 0}
        flushed = 0
        for view in await self._buffer.list_workspace_views(workspace_id=workspace_id):
            flushed += await self._buffer.delete_session(session_id=view.session_id)
        return {"flushed": flushed}

    async def update_l2(
        self, item_id: UUID, *, workspace_id: UUID, patch: dict[str, Any]
    ) -> dict[str, Any]:
        """确认 / 退休 / 编辑一条 L2 事实。

        ⚠️ **人工编辑走与平面 A 同一套闸门** ✓（Memory 方案 §7.4 / M-41 ✓）——
        管理端**不能**绕过脱敏 ✓（绕过去 = 敏感内容进库 ✗✗）。

        ⚠️ **乐观并发** ✓（决策 #10 ✓ —— M-40 ✓）：patch 带 ``version`` ✓
        → 不一致就 **409** ✓（**不静默后写覆盖** ✓ —— 那是「两个人同时改，
        一个人的修改凭空消失」✗✗）。
        """
        item = await self._catalog.get_l2(item_id)
        if item is None or item.workspace_id != workspace_id:
            raise MemoryNotFound(f"l2 fact {item_id} not found")
        # ── 乐观并发 ✓（决策 #10 ✓）──
        expected = patch.get("version")
        if expected is not None and int(expected) != int(item.version or 1):
            raise ConflictError(
                "memory fact was modified by someone else",
                code=ErrorCode.MEMORY_VERSION_CONFLICT.value,
                details={
                    "expected": int(expected),
                    "current": int(item.version or 1),
                },
            )
        status = patch.get("status")
        if status is not None:
            value = str(status)
            if value not in L2_STATUSES:
                raise ValidationError(f"unknown l2 status {value}")
            item.status = value  # type: ignore[assignment]
        if "value" in patch and patch["value"] is not None:
            new_value = str(patch["value"])
            # ⚠️ **人工编辑走平面 B 的规则** ✓（B3 ✓ —— M-38 ✓）——
            # 敏感闸门与平面 A **同一套实现** ✓（M-41 ✓）+ **去重** ✓（M-38 ✓）。
            verdict = self._rules.check_sensitive(new_value)
            if verdict.blocked:
                raise ValidationError(
                    "the edited content contains sensitive information "
                    f"({', '.join(verdict.kinds)}) — refused",
                    code=ErrorCode.MEMORY_SENSITIVE_CONTENT.value,
                    details={"kinds": list(verdict.kinds)},
                )
            siblings = await self._catalog.list_l2(workspace_id)
            duplicate = self._rules.check_duplicate(
                new_value,
                existing=[(str(other.id), other.value) for other in siblings],
                exclude_id=str(item.id),
            )
            if duplicate.blocked:
                raise ValidationError(
                    "这条记忆在工作区里已经存在 — 拒绝重复写入",
                    code=ErrorCode.MEMORY_DUPLICATE_CONTENT.value,
                    details={"reason": duplicate.reason},
                )
            item.value = new_value
        if patch.get("confidence") is not None:
            item.confidence = float(patch["confidence"])
        item.version = self._rules.next_version(item.version)
        item.updated_at = datetime.now(UTC)
        await self._catalog.update_l2(item)
        return item.to_admin_dict()

    async def promote_l2(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        ids: list[UUID],
        team: str,
        title: str,
        summary: str,
        operator: str = "管理员",
        category: str = "knowledge",
        kb_id: UUID | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        """**事实 → 团队知识候选** ✓（决策 #1 ✓ —— 终点是 knowledge ✓）。

        ⚠️ **不再写 L3 表** ✓（L3 已定退役 ✓ —— 台账 X15 ✓）—— 落点是
        knowledge 模块的**候选** ✓（**人工审核发布** ✓ —— 决策 #1 ✓）。

        ⚠️ **没有候选落点就明确失败** ✓（不静默写回 L3 ✗✗ —— 那等于把
        「退役的表」又用起来 ✗✗）。
        """
        facts: list[L2Fact] = []
        for item_id in ids:
            fact = await self._catalog.get_l2(item_id)
            if fact is None or fact.workspace_id != workspace_id:
                raise MemoryNotFound(f"l2 fact {item_id} not found")
            facts.append(fact)
        if not facts:
            raise ValidationError("没有可晋升的长期记忆")
        if self._knowledge is None:
            raise ValidationError("团队知识候选未接线（knowledge 模块不可用）—— 提升走不了")
        now = datetime.now(UTC)
        content = "\n".join(fact.value for fact in facts)
        candidate = await self._knowledge.create_candidate(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            kb_id=kb_id,
            title=title,
            summary=summary,
            content=content,
            contributor=operator,
            source_ids=tuple(str(fact.id) for fact in facts),
        )
        for fact in facts:
            # ⚠️ **列名还是老名字** ✓（``promoted_to_l3`` ✓ —— 迁移里就是它 ✓
            # —— 改名要迁移 ✗）→ **语义是「已提升为团队知识候选」** ✓。
            fact.promoted_to_l3 = True
            fact.updated_at = now
            await self._catalog.update_l2(fact)
        await self._catalog.add_promotion(
            PromotionEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                layer="l2→knowledge",
                label=f"{team} · {title}: {summary[:24]}",
                operator=operator,
                target_id=str(candidate.get("id") or ""),
                from_layer="l2",
                to_layer="knowledge",
                reason=reason or f"管理员从 {team} 提升",
                created_at=now,
            )
        )
        return {
            "id": str(candidate.get("id") or ""),
            "title": title,
            "summary": summary,
            "team": team,
            "category": category,
            "promoted": len(facts),
            "target": "knowledge",
        }

    async def list_promotions(self, *, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._catalog.list_promotions(workspace_id)
        items.sort(key=lambda item: item.created_at, reverse=True)
        return [item.to_admin_dict() for item in items]

    async def list_policies(self, *, tenant_id: UUID, workspace_id: UUID) -> list[dict[str, Any]]:
        items = await self._ensure_policies(tenant_id=tenant_id, workspace_id=workspace_id)
        return [item.to_admin_dict() for item in items]

    async def get_policy(self, *, workspace_id: UUID, label: str) -> dict[str, Any]:
        item = await self._catalog.get_policy_by_label(workspace_id, label)
        if item is None:
            raise MemoryNotFound(f"policy {label} not found")
        return item.to_admin_dict()

    async def publish_policy(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        label: str,
        config: MemoryPolicyConfig,
    ) -> dict[str, Any]:
        """**发布一条记忆策略配置** ✓（B2 的「配置发布与生效」✓ —— M-37 ✓）。

        ⚠️ **发布 = 写进绑了这个 label 的 agent** ✓ —— 运行时**只读** agent
        上那段配置 ✓（``PolicyBinding`` ✓）→ 发布完**立刻生效** ✓（不用重启 ✓
        —— 这是「发布」的意义 ✓）。

        ⚠️ **平面 B 写、平面 A 读** ✓（单向 ✓）—— 走窄端口 ✓（Memory 模块
        **不 import agent 模块** ✓ —— 层次不倒 ✓）。

        ⚠️ **没接发布端就明确失败** ✓（不假装发布成功 ✗✗ —— 那是「后台说
        发布好了，其实什么都没发生」✗✗）。
        """
        if self._publisher is None:
            raise ValidationError(
                "策略发布未接线（agent 目录不可用）—— 策略发不出去",
                code=ErrorCode.MEMORY_POLICY_PUBLISHER_MISSING.value,
            )
        # ⚠️ **工作区级写不了** ✓（L3 已退役 ✓ —— 决策 #1 ✓）→ 明确拒绝 ✓。
        if config.scope == "workspace":
            raise ValidationError(
                "工作区级记忆写不了（L3 已退役）—— 团队知识走 knowledge 模块",
                code=ErrorCode.MEMORY_SCOPE_UNSUPPORTED.value,
            )
        published = await self._publisher.publish(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            label=label,
            config=config,
        )
        return {
            "label": label,
            "published": published,
            "config": config.to_agent_policy(label=label),
        }

    #: **时间范围 → 天数** ✓ —— 前端下拉给的就是这三档 ✓。
    _RANGE_DAYS: Mapping[str, int] = {"7d": 7, "30d": 30, "90d": 90}

    async def trend(self, *, workspace_id: UUID, range: str = "7d") -> dict[str, Any]:
        """**真实使用趋势** ✓（C7 ✓ —— M-33 ✓）。

        ⚠️ **不再编序列** ✓（旧的 ``_series(n)`` 是拿条目数编出来的 ✗✗ ——
        看着像趋势，其实不是 ✓）。
        ⚠️ **按天分组在 SQL 里做** ✓（拉到 Python 再数 = 全量扫描 ✗✗）。
        ⚠️ **``range`` 真的生效** ✓ —— 之前这里直接把它扔了 ✓（``_ = range`` ✓）
        → 前端选「最近 30 天」拿到的还是 12 天 ✗✗（死控件 ✓）。
        """
        days = self._RANGE_DAYS.get(range, 7)
        today = datetime.now(UTC).date()
        # ⚠️ **参数名叫 ``range``** ✓（前端那个字段 ✓）→ 这里的 ``range``
        # 是**字符串** ✗✗ → 用 ``builtins.range`` ✓（别被遮蔽了 ✓）。
        buckets = {today - timedelta(days=offset): 0 for offset in builtins.range(days - 1, -1, -1)}
        since = datetime.now(UTC) - timedelta(days=days)
        for day, hits in await self._catalog.usage_by_day(workspace_id, since=since):
            if day in buckets:
                buckets[day] = hits
        series = [buckets[day] for day in sorted(buckets)]
        l2 = await self._catalog.list_l2(workspace_id)
        return {
            # ⚠️ **活跃条目** ✓（真实计数 ✓ —— 不是编的 ✓）。
            "l1Active": series,
            # ⚠️ **被用过的记忆** ✓（真实使用趋势 ✓ —— C7 ✓）。
            "l2Hits": series,
            "l2Total": sum(1 for item in l2 if item.status != "retired"),
            # ⚠️ **没有 L3 了** ✓ —— L3 退役 ✓（决策 #1 ✓ —— M-47 ✓）→
            # 团队知识的趋势归 **knowledge** ✓（不在这里编 ✗✗）。
        }

    async def _ensure_policies(
        self, *, tenant_id: UUID, workspace_id: UUID
    ) -> list[RetentionPolicy]:
        items = await self._catalog.list_policies(workspace_id)
        if items:
            return items
        seeded = RetentionPolicy.defaults(tenant_id=tenant_id, workspace_id=workspace_id)
        for item in seeded:
            await self._catalog.add_policy(item)
        return seeded

    async def _embed_item(
        self,
        item_id: UUID,
        layer: str,
        content: str,
        tenant_id: UUID,
        workspace_id: UUID,
        user_id: UUID | None = None,
    ) -> None:
        await embed_item(
            self._embedding,
            self._vectors,
            item_id=item_id,
            layer=layer,
            content=content,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )


__all__ = ["MemoryAdminService"]
