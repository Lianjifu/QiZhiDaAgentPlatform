"""Memory catalog unit tests — admin layers + recall."""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from qzdap_kernel.errors import ValidationError

from qzdap.modules.memory.application.admin_service import MemoryAdminService
from qzdap.modules.memory.application.ports import (
    MemoryCatalogRepository,
    VectorHit,
    VectorSearchPort,
)
from qzdap.modules.memory.application.services import MemoryRuntimeService
from qzdap.modules.memory.domain.entities import (
    L1Session,
    L2Fact,
    L3Entry,
    PromotionEvent,
    RetentionPolicy,
)
from qzdap.modules.memory.domain.errors import MemoryNotFound

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
            score = sum(a * b for a, b in zip(query_embedding, vector, strict=True)) / (
                qn * vn
            )
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
        self.l1: dict[UUID, L1Session] = {}
        self.l2: dict[UUID, L2Fact] = {}
        self.l3: dict[UUID, L3Entry] = {}
        self.promotions: dict[UUID, PromotionEvent] = {}
        self.policies: dict[UUID, RetentionPolicy] = {}

    async def add_l1(self, item: L1Session) -> None:
        self.l1[item.id] = item

    async def get_l1(self, item_id: UUID) -> L1Session | None:
        return self.l1.get(item_id)

    async def list_l1(self, workspace_id: UUID) -> list[L1Session]:
        return [item for item in self.l1.values() if item.workspace_id == workspace_id]

    async def update_l1(self, item: L1Session) -> None:
        self.l1[item.id] = item

    async def add_l2(self, item: L2Fact) -> None:
        self.l2[item.id] = item

    async def get_l2(self, item_id: UUID) -> L2Fact | None:
        return self.l2.get(item_id)

    async def list_l2(
        self, workspace_id: UUID, *, user_id: UUID | None = None
    ) -> list[L2Fact]:
        items = [item for item in self.l2.values() if item.workspace_id == workspace_id]
        if user_id is not None:
            items = [item for item in items if item.user_id == user_id]
        return items

    async def update_l2(self, item: L2Fact) -> None:
        self.l2[item.id] = item

    async def add_l3(self, item: L3Entry) -> None:
        self.l3[item.id] = item

    async def get_l3(self, item_id: UUID) -> L3Entry | None:
        return self.l3.get(item_id)

    async def list_l3(self, workspace_id: UUID) -> list[L3Entry]:
        return [item for item in self.l3.values() if item.workspace_id == workspace_id]

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

    async def list_l2_updated_since(
        self, since: datetime, *, limit: int = 100
    ) -> list[L2Fact]:
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
            and any(
                token in item.key.lower() or token in item.value.lower()
                for token in tokens
            )
        ]
        return rows[:limit]

    async def search_l3_by_keyword(
        self,
        workspace_id: UUID,
        *,
        keyword: str,
        limit: int,
    ) -> list[L3Entry]:
        tokens = [part for part in keyword.strip().lower().split() if part]
        rows = [
            item
            for item in self.l3.values()
            if item.workspace_id == workspace_id
            and item.status == "published"
            and any(
                token in item.title.lower() or token in item.summary.lower()
                for token in tokens
            )
        ]
        return rows[:limit]

    async def update_l3(self, item: L3Entry) -> None:
        self.l3[item.id] = item

    async def add_promotion(self, item: PromotionEvent) -> None:
        self.promotions[item.id] = item

    async def list_promotions(self, workspace_id: UUID) -> list[PromotionEvent]:
        return [
            item
            for item in self.promotions.values()
            if item.workspace_id == workspace_id
        ]

    async def add_policy(self, item: RetentionPolicy) -> None:
        self.policies[item.id] = item

    async def list_policies(self, workspace_id: UUID) -> list[RetentionPolicy]:
        return [
            item for item in self.policies.values() if item.workspace_id == workspace_id
        ]

    async def get_policy_by_label(
        self, workspace_id: UUID, label: str
    ) -> RetentionPolicy | None:
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


def _svc() -> tuple[MemoryRuntimeService, MemoryAdminService, InMemoryCatalog]:
    """两个平面各一个服务，**共用同一份目录** ✓（模拟生产的两条路 ✓）。

    ⚠️ **第三个返回值是目录** ✓ —— 测试要往库里放行时**直接放** ✓
    （「库里有这一行」✓ —— 不是「某个写入路径能写」✓ —— 写入路径另有测试 ✓）。
    """
    catalog = InMemoryCatalog()
    return (
        MemoryRuntimeService(
            catalog, embedding=HashEmbedding(), vectors=InMemoryVectors()
        ),
        MemoryAdminService(
            catalog,
            embedding=HashEmbedding(),
            vectors=InMemoryVectors(),
            knowledge=_FakeKnowledge(),
        ),
        catalog,
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


async def _seed_l1(
    catalog: InMemoryCatalog,
    *,
    content: str,
    workspace_id: UUID = WORKSPACE,
    tenant_id: UUID = TENANT,
    status: str = "active",
) -> L1Session:
    """往目录里放一条 L1 会话缓冲 ✓（L1 已退役写侧 ✓ —— 只剩读侧 ✓）。"""
    now = datetime.now(UTC)
    session = L1Session(
        id=uuid4(),
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        user_name="张文佳",
        agent_name="助手",
        buffer_size=1,
        tokens_used=max(1, len(content) // 4),
        ttl_minutes=60,
        ttl_remain_min=60,
        status=status,
        updated_at=now,
        created_at=now,
        buffer_text=content,
    )
    await catalog.add_l1(session)
    return session


@pytest.mark.asyncio
async def test_the_lists_and_policies_are_readable() -> None:
    """管理面**读得到** L1 / L2 / 提升事件 / 策略 ✓。

    ⚠️ **L1 的写侧已退役** ✓（决策 #5 ✓ —— 旧写入点随 `_remember` 一起删了
    ✓）→ 这里**只放行不写** ✓（「库里有这一行」✓）。
    """
    _, admin, catalog = _svc()
    await _seed_l2(
        catalog,
        content="喜欢精简答复,3 行内给结论",
        key="答复风格",
        workspace_id=WORKSPACE,
    )
    await _seed_l1(catalog, content="会议纪要要点", workspace_id=WORKSPACE)
    l1 = await admin.list_l1(workspace_id=WORKSPACE)
    l2 = await admin.list_l2(workspace_id=WORKSPACE)
    assert len(l1) == 1
    assert len(l2) == 1
    detail = await admin.get_l2(UUID(l2[0]["id"]))
    assert detail["value"].find("精简") >= 0
    policies = await admin.list_policies(tenant_id=TENANT, workspace_id=WORKSPACE)
    assert len(policies) == 3
    short = await admin.get_policy(workspace_id=WORKSPACE, label="短期记忆")
    assert short["layer"] == "l1"
    trend = await admin.trend(workspace_id=WORKSPACE)
    assert len(trend["l1Active"]) == 8


@pytest.mark.asyncio
async def test_the_retiring_tables_are_measured() -> None:
    """**要退役的表在用** → 打点 ✓（台账 §3.2：没有打点就没有清理判据 ✓）。

    X15 = ``admin_memory_l3``（决策 #1 退役 ✓）—— 指标非零才说明「还没退干净」✓。
    ⚠️ **X13（``admin_memory_l1``）的写侧已退役** ✓（决策 #5 ✓ —— 旧写入
    点随旧循环的删除一起没了 ✓）→ **不再有 X13 打点** ✓（指标归零 ✓ =
    「写侧清干净了」✓ —— 表本身还在 ✓，只剩管理端的读侧 ✗）。
    """
    from qzdap_observability.metrics import LEGACY_CALLS_TOTAL

    _, admin, _catalog = _svc()
    l3_before = LEGACY_CALLS_TOTAL.labels(entry="X15")._value.get()

    await admin.create_l3(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        team="平台",
        title="团队知识",
        summary="摘要",
    )

    assert LEGACY_CALLS_TOTAL.labels(entry="X15")._value.get() == l3_before + 1


@pytest.mark.asyncio
async def test_recall_ranks_matching_fact() -> None:
    runtime, _, catalog = _svc()
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
async def test_missing_l3_raises() -> None:
    _, admin, _catalog = _svc()
    with pytest.raises(MemoryNotFound):
        await admin.get_l3(UUID("00000000-0000-0000-0000-000000000099"))


@pytest.mark.asyncio
async def test_flush_l1_expires_session() -> None:
    _, admin, catalog = _svc()
    await _seed_l1(catalog, content="会议纪要要点", workspace_id=WORKSPACE)
    sessions = await admin.list_l1(workspace_id=WORKSPACE)
    assert len(sessions) == 1
    flushed = await admin.flush_l1(UUID(sessions[0]["id"]), workspace_id=WORKSPACE)
    assert flushed["status"] == "expired"
    assert flushed["bufferSize"] == 0
    again = await admin.list_l1(workspace_id=WORKSPACE)
    assert again[0]["status"] == "expired"


@pytest.mark.asyncio
async def test_flush_all_l1_only_counts_active() -> None:
    _, admin, catalog = _svc()
    await _seed_l1(catalog, content="第一条", workspace_id=WORKSPACE)
    await _seed_l1(catalog, content="第二条", workspace_id=WORKSPACE)
    first = await admin.flush_all_l1(workspace_id=WORKSPACE)
    assert first["flushed"] == 2
    second = await admin.flush_all_l1(workspace_id=WORKSPACE)
    assert second["flushed"] == 0


@pytest.mark.asyncio
async def test_flush_rejects_other_workspace() -> None:
    _, admin, catalog = _svc()
    await _seed_l1(catalog, content="内容", workspace_id=WORKSPACE)
    sessions = await admin.list_l1(workspace_id=WORKSPACE)
    with pytest.raises(MemoryNotFound):
        await admin.flush_l1(
            UUID(sessions[0]["id"]),
            workspace_id=UUID("00000000-0000-0000-0000-0000000000ff"),
        )


@pytest.mark.asyncio
async def test_update_l2_confirms_and_validates_status() -> None:
    _, admin, catalog = _svc()
    await _seed_l2(
        catalog,
        content="偏好中文回复",
        key="语言",
        workspace_id=WORKSPACE,
    )
    facts = await admin.list_l2(workspace_id=WORKSPACE)
    fact_id = UUID(facts[0]["id"])
    updated = await admin.update_l2(
        fact_id, workspace_id=WORKSPACE, patch={"status": "confirmed"}
    )
    assert updated["status"] == "confirmed"
    with pytest.raises(ValidationError):
        await admin.update_l2(
            fact_id, workspace_id=WORKSPACE, patch={"status": "nonsense"}
        )


@pytest.mark.asyncio
async def test_promote_l2_creates_a_knowledge_candidate_and_marks_facts() -> None:
    """**提升 → 团队知识候选** ✓（决策 #1 ✓ —— **不再写 L3 表** ✓）。"""
    _, admin, catalog = _svc()
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
    # ⚠️ **L3 表不再被写** ✓（L3 已定退役 ✓ —— 台账 X15 ✓）。
    assert catalog.l3 == {}
    assert (await admin.get_l2(fact_id))["promotedToL3"] is True
    events = await admin.list_promotions(workspace_id=WORKSPACE)
    assert any(event["layer"] == "l2→knowledge" for event in events)
    assert any(event["fromLayer"] == "l2" for event in events)
    assert any(event["toLayer"] == "knowledge" for event in events)


@pytest.mark.asyncio
async def test_promote_l2_rejects_empty_selection() -> None:
    _, admin, _catalog = _svc()
    with pytest.raises(ValidationError):
        await admin.promote_l2(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            ids=[],
            team="售后组",
            title="空",
            summary="空",
        )


@pytest.mark.asyncio
async def test_create_l3_publishes_entry() -> None:
    _, admin, _catalog = _svc()
    entry = await admin.create_l3(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        team="增长组",
        title="定价口径",
        summary="新客首单 8 折",
        contributor="李明",
    )
    assert entry["status"] == "published"
    assert entry["hits"] == 0
    listed = await admin.list_l3(workspace_id=WORKSPACE)
    assert [item["id"] for item in listed] == [entry["id"]]


@pytest.mark.asyncio
async def test_create_l3_rejects_unknown_status() -> None:
    _, admin, _catalog = _svc()
    with pytest.raises(ValidationError):
        await admin.create_l3(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            team="增长组",
            title="定价口径",
            summary="",
            status="archived",
        )


@pytest.mark.asyncio
async def test_update_l3_publishes_and_retires() -> None:
    _, admin, _catalog = _svc()
    entry = await admin.create_l3(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        team="增长组",
        title="定价口径",
        summary="新客首单 8 折",
    )
    item_id = UUID(entry["id"])
    published = await admin.update_l3(
        item_id, workspace_id=WORKSPACE, patch={"status": "published"}
    )
    assert published["status"] == "published"
    retired = await admin.update_l3(
        item_id, workspace_id=WORKSPACE, patch={"status": "retired"}
    )
    assert retired["status"] == "retired"
    with pytest.raises(ValidationError):
        await admin.update_l3(
            item_id, workspace_id=WORKSPACE, patch={"status": "unknown"}
        )
    with pytest.raises(MemoryNotFound):
        await admin.update_l3(
            item_id,
            workspace_id=UUID("00000000-0000-0000-0000-0000000000ff"),
            patch={"status": "published"},
        )
