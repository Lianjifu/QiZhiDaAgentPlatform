"""Phase 20: 健康告警聚合 + cooldown 抑制.

事件流: ``ModelService.stream`` / ``ModelService.health_check`` 写完
``admin_model_health`` 行后调用 :meth:`AlertService.evaluate` 聚合最近事件:

  - incident 计数 < 1 → ``ok`` (不发告警)
  - incident 计数 ∈ [1, threshold) → ``degraded`` (不发告警, 仅 log)
  - incident 计数 ≥ threshold → ``down`` (触发 alert)

抑制: 每个 ``(tenant_id, workspace_id, provider_id)`` 进入 cooldown
(cooldown_window_seconds), 期间重复 ``down`` 不再发 alert. 同一 process 用
``_cooldowns`` dict (single-instance 部署够用; 多实例需要换成 DB row 或
redis SETEX, 留给后续 Phase).

设计要点:
  - 不发网络请求 (邮件/钉钉) — 仅通过 stdlib logging 输出一行结构化
    ``alert.level=down provider_id=...`` 给上层钩走 (lifespan 可挂
    OpenTelemetry / filebeat).
  - 拉取最近事件: SqlHealthRepository.list_for_workspace(workspace_id, limit=50)
    + Python 端按时间窗 + provider_id 过滤. 简单 in-place 聚合, 不引入
    额外 SQL.
  - 不改 schema: cooldown 进程内存, 重启后清空 (acceptable for now).
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from qzdap.modules.model.application.ports import HealthRepository

_log = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class AlertDecision:
    """Evaluate 输出."""

    level: str  # "ok" | "degraded" | "down"
    incident_count: int
    sample_message: str  # 最近一次 incident 的 message, 给人看
    cooldown_remaining: float  # 0 = 允许发; >0 = 抑制剩余秒数


@dataclass(slots=True)
class _Cooldown:
    last_fired_at: float  # monotonic time when alert was sent


class AlertService:
    """评估 provider 健康状态 → 告警决策 + 抑制.

    阈值 (默认):
      - incident_threshold = 3: 触发 down 告警的连续失败数
      - incident_window_seconds = 300: 5 分钟内计数
      - cooldown_window_seconds = 600: 同 provider 告警后 10 分钟不再重发
    """

    def __init__(
        self,
        health: HealthRepository,
        *,
        incident_threshold: int = 3,
        incident_window_seconds: float = 300.0,
        cooldown_window_seconds: float = 600.0,
        clock: Any = None,  # callable returning float seconds; default=time.monotonic
    ) -> None:
        self._health = health
        self._threshold = incident_threshold
        self._window = incident_window_seconds
        self._cooldown = cooldown_window_seconds
        self._clock = clock or time.monotonic
        # key = (tenant_id, workspace_id, provider_id)
        self._cooldowns: dict[tuple[UUID, UUID, UUID], _Cooldown] = {}

    async def evaluate(
        self,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        provider_id: UUID,
        provider_name: str = "",
        now_epoch: float | None = None,
    ) -> AlertDecision:
        """读最近 health 事件, 评估告警级别.

        ``now_epoch`` 用来在测试里注入固定时间 (避免依赖 wall clock).
        返回的 AlertDecision 中 cooldown_remaining 0 = 允许发.
        """
        if now_epoch is None:
            now_epoch = time.time()
        # 拉最近事件 (limit 50, 够覆盖窗口)
        events = await self._health.list_for_workspace(workspace_id, limit=50)
        # 过滤: provider + tenant + window + type
        window_start = now_epoch - self._window
        recent_incidents: deque[float] = deque()
        sample_msg = ""
        for ev in events:
            if ev.tenant_id != tenant_id or ev.provider_id != provider_id:
                continue
            if ev.type != "incident":
                continue
            try:
                ev_time = _parse_occurred_at(ev.occurred_at)
            except ValueError:
                continue
            if ev_time < window_start:
                continue
            recent_incidents.append(ev_time)
            sample_msg = ev.message or sample_msg
        count = len(recent_incidents)
        # 决策
        if count == 0:
            return AlertDecision("ok", 0, "", 0.0)
        if count < self._threshold:
            return AlertDecision("degraded", count, sample_msg, 0.0)
        # 触发 down — 检查 cooldown
        key = (tenant_id, workspace_id, provider_id)
        last = self._cooldowns.get(key)
        now_mono = self._clock()
        if last is not None:
            elapsed = now_mono - last.last_fired_at
            if elapsed < self._cooldown:
                return AlertDecision(
                    "down", count, sample_msg, self._cooldown - elapsed
                )
        # 记 cooldown
        self._cooldowns[key] = _Cooldown(last_fired_at=now_mono)
        # 触发告警 (logging 钩, 上层可挂 otel/filebeat)
        _log.warning(
            "model_health_alert",
            extra={
                "level": "down",
                "tenant_id": str(tenant_id),
                "workspace_id": str(workspace_id),
                "provider_id": str(provider_id),
                "provider_name": provider_name,
                "incident_count": count,
                "incident_window_seconds": self._window,
                "sample_message": sample_msg,
            },
        )
        return AlertDecision("down", count, sample_msg, 0.0)

    # 测试辅助
    def reset_cooldowns(self) -> None:
        self._cooldowns.clear()


def _parse_occurred_at(value: str) -> float:
    """Parse ISO 8601 to epoch seconds. 失败抛 ValueError."""
    from datetime import datetime

    if not value:
        raise ValueError("empty occurred_at")
    # Python 3.11+ supports fromisoformat for 'Z' suffix
    cleaned = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        # naive — assume UTC (写表时 datetime.now(UTC).isoformat() 会带 +00:00)
        from datetime import UTC

        dt = dt.replace(tzinfo=UTC)
    return dt.timestamp()


__all__ = ["AlertDecision", "AlertService"]
