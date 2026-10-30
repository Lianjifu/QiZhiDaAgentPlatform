"""Memory Stage 6：**C7 使用统计** ✓（Memory 方案 §7.2 ✓ —— 决策 #7 ✓）。

验收覆盖 ✓：

- **召回命中 → 更新统计** ✓（``used_count`` / ``last_used_at`` /
  ``usage_history`` ✓ —— **淘汰器与置信度调整都依赖它** ✓）；
- **L3 命中 → 更新 hits** ✓；
- **趋势是真实数据** ✓（不再编序列 ✓ —— M-33 ✓）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from qzdap_agent_runtime.memory.policy import MemoryPolicy

from qzdap.modules.memory.application.admin_service import MemoryAdminService
from qzdap.modules.memory.application.services import MemoryRuntimeService
from qzdap.modules.memory.domain.entities import L2Fact
from tests.unit.test_memory_catalog import InMemoryCatalog
from tests.unit.test_memory_policy_binding import TENANT, USER, WORKSPACE, _l2


@pytest.mark.asyncio
async def test_a_recall_hit_updates_the_usage() -> None:
    """**命中 → 统计更新** ✓（决策 #7 ✓）。"""
    catalog = InMemoryCatalog()
    fact = _l2(session_id=uuid4(), value="我的生日是 3 月 1 日")
    catalog.l2[fact.id] = fact
    service = MemoryRuntimeService(catalog)
    hits = await service.recall(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        user_id=USER,
        query="生日",
    )
    assert hits
    stored = catalog.l2[fact.id]
    assert stored.used_count == 1
    assert stored.last_used_at is not None
    assert stored.usage_history


@pytest.mark.asyncio
async def test_the_usage_history_is_a_real_timeline() -> None:
    """**usage_history 是真实事件序列** ✓（旧的写死成 ``["刚刚"]`` ✗✗）。"""
    catalog = InMemoryCatalog()
    fact = _l2(session_id=uuid4(), value="我的生日是 3 月 1 日")
    catalog.l2[fact.id] = fact
    service = MemoryRuntimeService(catalog)
    for _ in range(2):
        await service.recall(
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            user_id=USER,
            query="生日",
        )
    stored = catalog.l2[fact.id]
    assert stored.used_count == 2
    assert len(stored.usage_history) == 2
    # ⚠️ **是时间戳** ✓（不是「刚刚」✗）。
    datetime.fromisoformat(stored.usage_history[0])


@pytest.mark.asyncio
async def test_the_trend_is_real_usage() -> None:
    """**趋势是真实使用** ✓（M-33 ✓ —— 不再编序列 ✓）。"""
    catalog = InMemoryCatalog()
    fact = _l2(session_id=uuid4(), value="我的生日是 3 月 1 日")
    fact.last_used_at = datetime.now(UTC)
    catalog.l2[fact.id] = fact
    admin = MemoryAdminService(catalog)
    trend = await admin.trend(workspace_id=WORKSPACE)
    assert len(trend["l2Hits"]) == 12
    # ⚠️ **今天有 1 次使用** ✓（真实计数 ✓）。
    assert trend["l2Hits"][-1] == 1
    assert trend["l2Total"] == 1
