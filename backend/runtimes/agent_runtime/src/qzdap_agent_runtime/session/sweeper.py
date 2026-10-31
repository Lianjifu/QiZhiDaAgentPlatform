"""超时清扫（Session 方案 §3.3）。

**四类超时** —— **四类都有兜底** ✓（2026-10-31 ✓）：

| # | 超时 | 对象 | 阈值 | 触发动作 | 现状 |
|---|---|---|---|---|---|
| 1 | **僵尸轮次** | turn 卡在 `running` | 30 分钟（`CLAIM_STALE_MINUTES`） | 置 `failed` + 释放会话 | ✅ |
| 2 | **审批过期** | approval 停在 `pending` | 15 分钟（`APPROVAL_TTL_SECONDS`） | 自动 `deny` + 审计 | ✅ 归治理域判定 ✓ |
| 3 | **会话空闲** | 会话长期没新消息 | 30 天（决策 #7 ✓ —— 可配 ✓） | `close`（reason=`idle_timeout`） | ✅ **只关「有复活路径」的** ✓ |
| 4 | **幂等键过期** | `session_inbox` 里 `expires_at < now()` 的行 | 按行（24h / 7d / 120s） | 删该行（单批 ≤1000） | ✅ |

⚠️ **第四类是 Gateway 的硬依赖**（Gateway 方案 §4.3.1）：唯一约束**不含**
`expires_at` → 过期行留在表里，同一个键重发时**仍会命中冲突**。Gateway 的
claim 分支有「过期即当作不存在」作为第二道保险，但**表会无限膨胀** →
必须有人定期删 ✓。**两侧都要做，只做一边不够** ✓。

⚠️ **第三类的前置是「复活」路径** ✓（方案 §3.4 ✓）—— 复活 = **新建一个
会话接管** ✓（旧行让出外部会话键 ✓ —— 部分唯一索引 ✓）；**Web 会话没有
复活路径** ✓ → 不关 ✓（关了就是「用户的旧对话从列表里消失」✗✗）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class SweepReport:
    """一次清扫的结果 —— **每类各一个数**，便于判断「哪类在堆积」✓。"""

    zombie_turns: int = 0
    expired_idempotency_rows: int = 0
    expired_approvals: int = 0
    idle_sessions: int = 0

    @property
    def total(self) -> int:
        return (
            self.zombie_turns
            + self.expired_idempotency_rows
            + self.expired_approvals
            + self.idle_sessions
        )


@runtime_checkable
class SessionSweeperPort(Protocol):
    """清扫器端口 —— **调度由 composition 负责**（与 outbox worker 同类 ✓）。"""

    async def sweep(self, *, now: datetime) -> SweepReport: ...


__all__ = ["SessionSweeperPort", "SweepReport"]
