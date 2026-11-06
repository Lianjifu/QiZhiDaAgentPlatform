"""Memory catalog unit tests — admin layers + recall."""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from qzdap.modules.memory.application.admin_service import MemoryAdminService
from qzdap.modules.memory.application.ports import (
    MemoryCatalogRepository,
    VectorHit,
    VectorSearchPort,
)
from qzdap.modules.memory.application.services import MemoryRuntimeService
from qzdap.modules.memory.domain.entities import (
    L2Fact,
    PromotionEvent,
    RetentionPolicy,
)
from qzdap.modules.memory.domain.errors import MemoryNotFound
from qzdap_agent_runtime.memory.refine import BufferRow, SessionBufferView
from qzdap_agent_runtime.memory.writer import content_hash
from qzdap_kernel.errors import ValidationError

TENANT = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")
DIM = 32


class HashEmbedding:
    def __init__(self, dim: int = DIM) -> None:
        self._dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self._dim
            for token in text.lower().split():
                digest = hashlib.md5(token.encode("utf-8")).digest()
                bucket = int.from_bytes(digest[:2], "little") % self._dim
                vec[bucket] += 1.0
            norm = math.sqrt(sum(value * value for value in vec)) or 1.0
            out.append([value / norm for value in vec])
        return out


class InMemoryVectors(VectorSearchPort):
    def __init__(self) -> None:
        self.items: dict[UUID, tuple[list[float], dict[str, str]]] = {}

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
        session_id: UUID | None = None,
    ) -> None:
        _ = tenant_id
        payload = {
            "workspace_id": str(workspace_id),
            "layer": layer,
            "content": content,
        }
        if user_id is not None:
            payload["user_id"] = str(user_id)
        if session_id is not None:
            payload["session_id"] = str(session_id)
        self.items[item_id] = (list(embedding), payload)

    async def delete(self, ids: list[UUID]) -> None:
        for item_id in ids:
            self.items.pop(item_id, None)

    async def search(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        query_embedding: list[float],
        top_k: int,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
    ) -> list[VectorHit]:
        _ = tenant_id
        qn = math.sqrt(sum(value * value for value in query_embedding)) or 1.0
        scored: list[VectorHit] = []
        for item_id, (vector, payload) in self.items.items():
            if payload["workspace_id"] != str(workspace_id):
                continue
            if user_id is not None and payload.get("user_id") != str(user_id):
                # 对齐 pgvector：`payload->>'user_id'` 为 NULL 时不匹配。
                continue
            if session_id is not None and payload.get("session_id") != str(session_id):
                # 对齐 pgvector：没有 session payload 的向量**匹配不上** ✓。
                continue
            vn = math.sqrt(sum(value * value for value in vector)) or 1.0
            score = sum(a * b for a, b in zip(query_embedding, vector, strict=True)) / (qn * vn)
            scored.append(
                VectorHit(
                    item_id=item_id,
                    score=float(score),
                    layer=payload["layer"],
                    content=payload["content"],
                )
            )
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]


class InMemoryCatalog(MemoryCatalogRepository):
    def __init__(self) -> None:
        self.l2: dict[UUID, L2Fact] = {}
        self.promotions: dict[UUID, PromotionEvent] = {}
        self.policies: dict[UUID, RetentionPolicy] = {}

    async def add_l2(self, item: L2Fact) -> None:
        self.l2[item.id] = item

    async def get_l2(self, item_id: UUID) -> L2Fact | None:
        return self.l2.get(item_id)

    async def list_l2(self, workspace_id: UUID, *, user_id: UUID | None = None) -> list[L2Fact]:
        items = [item for item in self.l2.values() if item.workspace_id == workspace_id]
        if user_id is not None:
            items = [item for item in items if item.user_id == user_id]
        return items

    async def delete_l2(self, ids: list[UUID]) -> int:
        """**删掉这些 L2 行** ✓（数据治理 ✓ —— C9 ✓）。"""
        victims = [item for item in ids if item in self.l2]
        for item in victims:
            del self.l2[item]
        return len(victims)

    async def update_l2(self, item: L2Fact) -> None:
        self.l2[item.id] = item

    async def find_l2_by_hash(
        self,
        workspace_id: UUID,
        *,
        user_id: UUID,
        content_hash: str,
    ) -> L2Fact | None:
        """按哈希查 ✓（与 SQL 实现同口径 ✓）。"""
        for item in self.l2.values():
            if (
                item.workspace_id == workspace_id
                and item.user_id == user_id
                and item.content_hash == content_hash
            ):
                return item
        return None

    async def list_l2_updated_since(self, since: datetime, *, limit: int = 100) -> list[L2Fact]:
        """**最近更新过的 L2** ✓（与 SQL 实现同口径 ✓）。"""
        rows = [
            item
            for item in self.l2.values()
            if item.updated_at >= since and item.status != "retired"
        ]
        rows.sort(key=lambda item: item.updated_at, reverse=True)
        return rows[:limit]

    async def search_l2_by_keyword(
        self,
        workspace_id: UUID,
        *,
        user_id: UUID | None = None,
        keyword: str,
        limit: int,
        session_id: UUID | None = None,
    ) -> list[L2Fact]:
        """词法候选 ✓ —— 与 SQL 实现**同口径** ✓（含用户过滤 ✓）。

        ⚠️ **会话作用域** ✓（§7.1 ✓）—— 与 SQL 的 ``source_session`` 过滤
        同口径 ✓。
        """
        tokens = [part for part in keyword.strip().lower().split() if part]
        rows = [
            item
            for item in self.l2.values()
            if item.workspace_id == workspace_id
            and item.status != "retired"
            and (user_id is None or item.user_id == user_id)
            and (session_id is None or item.source_session == str(session_id))
            and any(token in item.key.lower() or token in item.value.lower() for token in tokens)
        ]
        return rows[:limit]

    async def add_promotion(self, item: PromotionEvent) -> None:
        self.promotions[item.id] = item

    async def list_policy_workspaces(self) -> list[UUID]:
        """**有策略的工作区** ✓（与 SQL 实现同口径 ✓）。"""
        return list({policy.workspace_id for policy in self.policies.values()})

    async def usage_by_day(self, workspace_id: UUID, *, since: datetime) -> list[tuple[date, int]]:
        """**每天被用过的条数** ✓（与 SQL 实现同口径 ✓）。"""
        buckets: dict[date, int] = {}
        for item in self.l2.values():
            if item.workspace_id != workspace_id or item.last_used_at is None:
                continue
            if item.last_used_at < since:
                continue
            day = item.last_used_at.date()
            buckets[day] = buckets.get(day, 0) + 1
        return sorted(buckets.items())

    async def list_promotions(self, workspace_id: UUID) -> list[PromotionEvent]:
        return [item for item in self.promotions.values() if item.workspace_id == workspace_id]

    async def add_policy(self, item: RetentionPolicy) -> None:
        self.policies[item.id] = item

    async def list_policies(self, workspace_id: UUID) -> list[RetentionPolicy]:
        return [item for item in self.policies.values() if item.workspace_id == workspace_id]

    async def get_policy_by_label(self, workspace_id: UUID, label: str) -> RetentionPolicy | None:
        for item in self.policies.values():
            if item.workspace_id == workspace_id and item.label == label:
                return item
        return None


class _FakeKnowledge:
    """**团队知识候选**的替身 ✓（决策 #1 ✓ —— 落点是 knowledge ✓）。"""

    def __init__(self) -> None:
        self.candidates: list[dict] = []

    async def create_candidate(self, **kwargs) -> dict:  # type: ignore[no-untyped-def]
        candidate = {
            "id": str(uuid4()),
            "kbId": str(uuid4()),
            "title": kwargs["title"],
            "summary": kwargs["summary"],
            "content": kwargs["content"],
            "sourceIds": list(kwargs["source_ids"]),
        }
        self.candidates.append(candidate)
        return candidate


class InMemoryBuffer:
    """**内存版**的会话缓冲 ✓（L1 表退役后的唯一来源 ✓ —— M-46 ✓）。"""

    def __init__(self) -> None:
        self.rows: dict[UUID, BufferRow] = {}

    async def add(self, row: BufferRow) -> None:
        self.rows[row.id] = row

    async def list_pending(self, *, before: datetime, limit: int = 100) -> list[BufferRow]:
        _ = before
        return list(self.rows.values())[:limit]

    async def delete(self, row_ids: tuple[UUID, ...]) -> None:
        for row_id in row_ids:
            self.rows.pop(row_id, None)

    async def list_workspace_views(self, *, workspace_id: UUID) -> list[SessionBufferView]:
        grouped: dict[UUID, list[BufferRow]] = {}
        for row in self.rows.values():
            if row.workspace_id == workspace_id:
                grouped.setdefault(row.session_id, []).append(row)
        return [
            SessionBufferView(
                session_id=session_id,
                workspace_id=rows[0].workspace_id,
                user_id=rows[0].user_id,
                items=len(rows),
                total_chars=sum(len(row.content) for row in rows),
                created_at=min(row.created_at for row in rows),
                last_write_at=max(row.created_at for row in rows),
            )
            for session_id, rows in grouped.items()
        ]

    async def list_session_rows(self, *, session_id: UUID) -> list[BufferRow]:
        return [row for row in self.rows.values() if row.session_id == session_id]

    async def delete_session(self, *, session_id: UUID) -> int:
        victims = [row.id for row in self.rows.values() if row.session_id == session_id]
        await self.delete(tuple(victims))
        return len(victims)


def _svc() -> tuple[MemoryRuntimeService, MemoryAdminService, InMemoryCatalog, InMemoryBuffer]:
    """两个平面各一个服务，**共用同一份目录** ✓（模拟生产的两条路 ✓）。

    ⚠️ **第三个返回值是目录** ✓ —— 测试要往库里放行时**直接放** ✓
    （「库里有这一行」✓ —— 不是「某个写入路径能写」✓ —— 写入路径另有测试 ✓）。
    """
    catalog = InMemoryCatalog()
    buffer = InMemoryBuffer()
    return (
        MemoryRuntimeService(catalog, embedding=HashEmbedding(), vectors=InMemoryVectors()),
        MemoryAdminService(
            catalog,
            embedding=HashEmbedding(),
            vectors=InMemoryVectors(),
            knowledge=_FakeKnowledge(),
            buffer=buffer,
        ),
        catalog,
        buffer,
    )


async def _seed_l2(
    catalog: InMemoryCatalog,
    *,
    content: str,
    key: str = "记忆",
    user_id: UUID = TENANT,
    workspace_id: UUID = WORKSPACE,
    tenant_id: UUID = TENANT,
) -> L2Fact:
    """往目录里放一条 L2 ✓（等价于「库里有这一行」✓）。"""
    now = datetime.now(UTC)
    fact = L2Fact(
        id=uuid4(),
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        user_name="张文佳",
        user_id=user_id,
        key=key,
        value=content,
        category="fact",
        source_session="test",
        confidence=0.8,
        status="confirmed",
        promoted_to_l3=False,
        updated_at=now,
        created_at=now,
        usage_history=["刚刚"],
    )
    await catalog.add_l2(fact)
    return fact


async def _seed_buffer(
    buffer: InMemoryBuffer,
    *,
    content: str,
    workspace_id: UUID = WORKSPACE,
    tenant_id: UUID = TENANT,
    session_id: UUID | None = None,
) -> BufferRow:
    """往**会话缓冲**里放一条待提炼的记忆 ✓（M-46 ✓ —— L1 表退役后的落点 ✓）。"""
    now = datetime.now(UTC)
    row = BufferRow(
        id=uuid4(),
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        session_id=session_id or uuid4(),
        user_id=uuid4(),
        turn_id=uuid4(),
        content=content,
        content_hash=content_hash(content),
        created_at=now,
    )
    await buffer.add(row)
    return row


@pytest.mark.asyncio
async def test_the_lists_and_policies_are_readable() -> None:
    """管理面**读得到** 会话缓冲 / L2 / 提升事件 / 策略 ✓。

    ⚠️ **「L1」现在是会话缓冲** ✓（L1 表退役了 ✓ —— 决策 #5 ✓ —— M-46 ✓）。
    """
    _, admin, catalog, buffer = _svc()
    await _seed_l2(
        catalog,
        content="喜欢精简答复,3 行内给结论",
        key="答复风格",
        workspace_id=WORKSPACE,
    )
    await _seed_buffer(buffer, content="会议纪要要点", workspace_id=WORKSPACE)
    l1 = await admin.list_l1(workspace_id=WORKSPACE)
    l2 = await admin.list_l2(workspace_id=WORKSPACE)
    assert len(l1) == 1
    assert len(l2) == 1
    detail = await admin.get_l2(UUID(l2[0]["id"]))
    assert detail["value"].find("精简") >= 0
    policies = await admin.list_policies(tenant_id=TENANT, workspace_id=WORKSPACE)
    # ⚠️ **只剩 L2 一条默认策略** ✓ —— 「短期记忆」（L1 ✓ —— M-46 ✓）与
    # 「知识记忆」（L3 ✓ —— M-47 ✓）都退役了 ✓。
    assert len(policies) == 1
    keep = await admin.get_policy(workspace_id=WORKSPACE, label="长期记忆")
    assert keep["layer"] == "l2"
    trend = await admin.trend(workspace_id=WORKSPACE)
    # ⚠️ **真实使用趋势** ✓（M-33 ✓）—— 默认 7 天 ✓（range 真的生效 ✓）。
    assert len(trend["l1Active"]) == 7


@pytest.mark.asyncio
async def test_the_retired_tables_are_not_touched_anymore() -> None:
    """**退役的表不再有打点** ✓（台账 §3.2：没有打点就没有清理判据 ✓）。

    ⚠️ **X15（``admin_memory_l3``）已退役** ✓（决策 #1 ✓ —— M-47 ✓）→
    **不再有 X15 打点** ✓（指标归零 ✓ = 「表不用了」✓）。
    ⚠️ **X13（``admin_memory_l1``）同样退役** ✓（决策 #5 ✓ —— M-46 ✓）✓。
    """
    from qzdap_observability.metrics import LEGACY_CALLS_TOTAL

    _, _admin, catalog, _buffer = _svc()
    x15_before = LEGACY_CALLS_TOTAL.labels(entry="X15")._value.get()
    x13_before = LEGACY_CALLS_TOTAL.labels(entry="X13")._value.get()

    # ⚠️ **记忆面只有 L2** ✓ —— 没有 L3 的入口了 ✓。
    await _seed_l2(catalog, content="退款 7 天内申请", key="退款规则", workspace_id=WORKSPACE)

    assert LEGACY_CALLS_TOTAL.labels(entry="X15")._value.get() == x15_before
    assert LEGACY_CALLS_TOTAL.labels(entry="X13")._value.get() == x13_before


@pytest.mark.asyncio
async def test_recall_ranks_matching_fact() -> None:
    runtime, _, catalog, _buffer = _svc()
    await _seed_l2(
        catalog,
        content="订单退款需要 7 天内申请",
        key="退款规则",
        workspace_id=WORKSPACE,
    )
    await _seed_l2(
        catalog,
        content="发票一律开增值税专票",
        key="发票规则",
        workspace_id=WORKSPACE,
    )
    hits = await runtime.recall(
        tenant_id=TENANT, workspace_id=WORKSPACE, query="退款 订单", top_k=2
    )
    assert hits
    assert "退款" in hits[0].content


@pytest.mark.asyncio
async def test_flush_l1_drops_the_buffer() -> None:
    """**冲掉一个会话的缓冲** ✓（M-46 ✓ —— 内容丢弃 ✓）。"""
    _, admin, _catalog, buffer = _svc()
    await _seed_buffer(buffer, content="会议纪要要点", workspace_id=WORKSPACE)
    sessions = await admin.list_l1(workspace_id=WORKSPACE)
    assert len(sessions) == 1
    flushed = await admin.flush_l1(UUID(sessions[0]["id"]), workspace_id=WORKSPACE)
    assert flushed["flushed"] == 1
    assert await admin.list_l1(workspace_id=WORKSPACE) == []


@pytest.mark.asyncio
async def test_flush_all_l1_only_counts_what_is_there() -> None:
    _, admin, _catalog, buffer = _svc()
    await _seed_buffer(buffer, content="第一条", workspace_id=WORKSPACE)
    await _seed_buffer(buffer, content="第二条", workspace_id=WORKSPACE)
    first = await admin.flush_all_l1(workspace_id=WORKSPACE)
    assert first["flushed"] == 2
    second = await admin.flush_all_l1(workspace_id=WORKSPACE)
    assert second["flushed"] == 0


@pytest.mark.asyncio
async def test_flush_rejects_other_workspace() -> None:
    _, admin, _catalog, buffer = _svc()
    await _seed_buffer(buffer, content="内容", workspace_id=WORKSPACE)
    sessions = await admin.list_l1(workspace_id=WORKSPACE)
    with pytest.raises(MemoryNotFound):
        await admin.flush_l1(
            UUID(sessions[0]["id"]),
            workspace_id=UUID("00000000-0000-0000-0000-0000000000ff"),
        )


@pytest.mark.asyncio
async def test_update_l2_confirms_and_validates_status() -> None:
    _, admin, catalog, _buffer = _svc()
    await _seed_l2(
        catalog,
        content="偏好中文回复",
        key="语言",
        workspace_id=WORKSPACE,
    )
    facts = await admin.list_l2(workspace_id=WORKSPACE)
    fact_id = UUID(facts[0]["id"])
    updated = await admin.update_l2(fact_id, workspace_id=WORKSPACE, patch={"status": "confirmed"})
    assert updated["status"] == "confirmed"
    with pytest.raises(ValidationError):
        await admin.update_l2(fact_id, workspace_id=WORKSPACE, patch={"status": "nonsense"})


@pytest.mark.asyncio
async def test_promote_l2_creates_a_knowledge_candidate_and_marks_facts() -> None:
    """**提升 → 团队知识候选** ✓（决策 #1 ✓ —— **不再写 L3 表** ✓）。"""
    _, admin, catalog, _buffer = _svc()
    await _seed_l2(
        catalog,
        content="退款 7 天内申请",
        key="退款规则",
        workspace_id=WORKSPACE,
    )
    facts = await admin.list_l2(workspace_id=WORKSPACE)
    fact_id = UUID(facts[0]["id"])
    candidate = await admin.promote_l2(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        ids=[fact_id],
        team="售后组",
        title="退款规则",
        summary="退款需在 7 天内申请",
        operator="张文佳",
    )
    assert candidate["target"] == "knowledge"
    assert candidate["title"] == "退款规则"
    assert candidate["promoted"] == 1
    # ⚠️ **L3 表不再被写** ✓（L3 已定退役 ✓ —— 台账 X15 ✓）——
    # 候选落在 **knowledge** ✓（由窄端口接的 ✓ —— 这里断言不到 ✓）。
    assert (await admin.get_l2(fact_id))["promotedToL3"] is True
    events = await admin.list_promotions(workspace_id=WORKSPACE)
    assert any(event["layer"] == "l2→knowledge" for event in events)
    assert any(event["fromLayer"] == "l2" for event in events)
    assert any(event["toLayer"] == "knowledge" for event in events)


@pytest.mark.asyncio
async def test_promote_l2_rejects_empty_selection() -> None:
    _, admin, _catalog, _buffer = _svc()
    with pytest.raises(ValidationError):
        await admin.promote_l2(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            ids=[],
            team="售后组",
            title="空",
            summary="空",
        )
