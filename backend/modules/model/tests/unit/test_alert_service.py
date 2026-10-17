"""Phase 20: 健康告警单元测试.

测试 AlertService 在不同 incident 计数下输出正确的 AlertDecision,
并验证 cooldown 抑制.
"""
from __future__ import annotations

import time
from typing import Any
from uuid import UUID, uuid4

import pytest

from qzdap.modules.model.application.alert_service import AlertService
from qzdap.modules.model.application.ports import HealthRepository
from qzdap.modules.model.domain.entities import HealthEvent


class FakeHealthRepository(HealthRepository):
    """In-memory 假仓储, 接受 (tenant, ws, provider, type) 写入, list 时返回."""

    def __init__(self) -> None:
        self._events: list[HealthEvent] = []

    def add_event(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        provider_id: UUID,
        type: str = "incident",
        message: str = "fail",
        seconds_ago: float = 0.0,
    ) -> None:
        from datetime import UTC, datetime, timedelta

        ts = datetime.now(UTC) - timedelta(seconds=seconds_ago)
        ev = HealthEvent(
            id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            type=type,  # type: ignore[arg-type]
            provider_id=provider_id,
            provider_name="prov",
            message=message,
            occurred_at=ts.isoformat(),
        )
        self._events.append(ev)

    async def add(self, event: HealthEvent) -> None:
        self._events.append(event)

    async def get(self, *args: Any, **kwargs: Any) -> HealthEvent | None:
        return None

    async def list_for_workspace(
        self, workspace_id: UUID, limit: int = 50
    ) -> list[HealthEvent]:
        return [e for e in self._events if e.workspace_id == workspace_id][:limit]

    async def delete(self, *args: Any, **kwargs: Any) -> None:
        pass


@pytest.fixture
def fixed_now() -> float:
    return 1_700_000_000.0  # 任意固定 epoch


@pytest.fixture
def fixed_mono() -> float:
    return 1000.0  # monotonic clock 也固定


@pytest.mark.asyncio
async def test_no_incidents_returns_ok(fixed_now: float) -> None:
    repo = FakeHealthRepository()
    svc = AlertService(repo, clock=lambda: 1000.0)
    t, w, p = uuid4(), uuid4(), uuid4()
    d = await svc.evaluate(
        tenant_id=t, workspace_id=w, provider_id=p, now_epoch=fixed_now
    )
    assert d.level == "ok"
    assert d.incident_count == 0
    assert d.cooldown_remaining == 0.0


@pytest.mark.asyncio
async def test_below_threshold_returns_degraded(fixed_now: float) -> None:
    repo = FakeHealthRepository()
    svc = AlertService(repo, incident_threshold=3, clock=lambda: 1000.0)
    t, w, p = uuid4(), uuid4(), uuid4()
    for i in range(2):  # 2 < 3
        repo.add_event(
            tenant_id=t,
            workspace_id=w,
            provider_id=p,
            message=f"err{i}",
            seconds_ago=10 + i,
        )
    d = await svc.evaluate(
        tenant_id=t, workspace_id=w, provider_id=p, now_epoch=fixed_now
    )
    assert d.level == "degraded"
    assert d.incident_count == 2
    assert d.cooldown_remaining == 0.0


@pytest.mark.asyncio
async def test_at_threshold_fires_down(fixed_now: float) -> None:
    repo = FakeHealthRepository()
    svc = AlertService(repo, incident_threshold=3, clock=lambda: 1000.0)
    t, w, p = uuid4(), uuid4(), uuid4()
    for i in range(3):
        repo.add_event(
            tenant_id=t,
            workspace_id=w,
            provider_id=p,
            message=f"err{i}",
            seconds_ago=5 + i,
        )
    d = await svc.evaluate(
        tenant_id=t, workspace_id=w, provider_id=p, now_epoch=fixed_now
    )
    assert d.level == "down"
    assert d.incident_count == 3
    assert d.cooldown_remaining == 0.0  # 第一次允许发
    assert d.sample_message  # 拿到一条 message


@pytest.mark.asyncio
async def test_cooldown_suppresses_repeat_alerts() -> None:
    """Cooldown 内重复 down 仍报 down 但 cooldown_remaining > 0.

    实现: 两次 evaluate 都用真实的 now (事件 occurred_at 来自 wall clock, 不可
    重写). cooldown 由 monotonic clock 控制 — 第一次触发后 mono 走 100s,
    仍在 cooldown 600s 内, 应该返回 down + remaining > 0.
    """
    repo = FakeHealthRepository()
    mono = {"t": 1000.0}
    svc = AlertService(
        repo,
        incident_threshold=3,
        cooldown_window_seconds=600,
        clock=lambda: mono["t"],
    )
    t, w, p = uuid4(), uuid4(), uuid4()
    for i in range(3):
        repo.add_event(
            tenant_id=t, workspace_id=w, provider_id=p, seconds_ago=5 + i
        )
    # 第一次 (mono=1000, 真实 now)
    d1 = await svc.evaluate(
        tenant_id=t, workspace_id=w, provider_id=p, now_epoch=time.time()
    )
    assert d1.level == "down"
    assert d1.cooldown_remaining == 0.0
    # 再加 3 个 incident (现在窗口里), mono 走 100s, 仍在 cooldown 600s 内
    mono["t"] = 1100.0
    for i in range(3, 6):
        repo.add_event(
            tenant_id=t, workspace_id=w, provider_id=p, seconds_ago=5 + i
        )
    d2 = await svc.evaluate(
        tenant_id=t, workspace_id=w, provider_id=p, now_epoch=time.time()
    )
    assert d2.level == "down"
    assert d2.cooldown_remaining > 0  # 还在冷却期 (600 - 100 = 500s)


@pytest.mark.asyncio
async def test_cooldown_releases_after_window() -> None:
    """Cooldown 走完后 (mono > 600s), 再次 evaluate 应允许发 alert."""
    repo = FakeHealthRepository()
    mono = {"t": 1000.0}
    svc = AlertService(
        repo,
        incident_threshold=3,
        cooldown_window_seconds=600,
        clock=lambda: mono["t"],
    )
    t, w, p = uuid4(), uuid4(), uuid4()
    for i in range(3):
        repo.add_event(
            tenant_id=t, workspace_id=w, provider_id=p, seconds_ago=5 + i
        )
    await svc.evaluate(
        tenant_id=t, workspace_id=w, provider_id=p, now_epoch=time.time()
    )
    # 跨过 cooldown: mono 走 700s (> 600)
    mono["t"] = 1700.0
    for i in range(3, 6):
        repo.add_event(
            tenant_id=t, workspace_id=w, provider_id=p, seconds_ago=5 + i
        )
    d = await svc.evaluate(
        tenant_id=t, workspace_id=w, provider_id=p, now_epoch=time.time()
    )
    assert d.level == "down"
    assert d.cooldown_remaining == 0.0  # cooldown 已过, 又允许发


@pytest.mark.asyncio
async def test_old_incidents_outside_window_excluded() -> None:
    repo = FakeHealthRepository()
    # 用真实 time.time() 当 now_epoch — 与 add_event 的 occurred_at 一致
    real_now = time.time()
    svc = AlertService(
        repo, incident_threshold=3, incident_window_seconds=60, clock=lambda: 1000.0
    )
    t, w, p = uuid4(), uuid4(), uuid4()
    # 3 个 10 分钟前的事件 (window=60s 全过期)
    for i in range(3):
        repo.add_event(
            tenant_id=t, workspace_id=w, provider_id=p, seconds_ago=600 + i
        )
    d = await svc.evaluate(
        tenant_id=t, workspace_id=w, provider_id=p, now_epoch=real_now
    )
    assert d.level == "ok"
    assert d.incident_count == 0


@pytest.mark.asyncio
async def test_other_providers_incidents_ignored(fixed_now: float) -> None:
    repo = FakeHealthRepository()
    svc = AlertService(repo, incident_threshold=3, clock=lambda: 1000.0)
    t, w, p1, p2 = uuid4(), uuid4(), uuid4(), uuid4()
    # p2 有 3 个 incident
    for i in range(3):
        repo.add_event(
            tenant_id=t, workspace_id=w, provider_id=p2, seconds_ago=5 + i
        )
    d = await svc.evaluate(
        tenant_id=t, workspace_id=w, provider_id=p1, now_epoch=fixed_now
    )
    assert d.level == "ok"
    assert d.incident_count == 0


@pytest.mark.asyncio
async def test_recovery_event_does_not_count_as_incident(fixed_now: float) -> None:
    repo = FakeHealthRepository()
    svc = AlertService(repo, incident_threshold=3, clock=lambda: 1000.0)
    t, w, p = uuid4(), uuid4(), uuid4()
    # 3 recovery (不计数)
    for i in range(3):
        repo.add_event(
            tenant_id=t,
            workspace_id=w,
            provider_id=p,
            type="recovery",
            seconds_ago=5 + i,
        )
    d = await svc.evaluate(
        tenant_id=t, workspace_id=w, provider_id=p, now_epoch=fixed_now
    )
    assert d.level == "ok"
