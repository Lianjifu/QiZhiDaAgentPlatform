# Session 层重构方案

> 版本：1.2（审查修正后 + 按审查结论重排骨架）
> 适用项目：`QiZhiDaAgentPlatform`
> 状态：**已定稿**（15 条审查问题已修正 + **本轮重排**，逐条见附录 C；附录 A 的 7 条决策于 2026-10-29 逐条确认）
> 方案集入口：[`README.md`](README.md)
> 上位基线：[`session-lifecycle-sequence.md`](session-lifecycle-sequence.md) —— 本方案实现其中 **Session 泳道**
> 收敛机制：[`cleanup-ledger.md`](cleanup-ledger.md) —— 本方案对应条目 **X2、X3、X4、X6、X7、X18**
> 硬约束：**最终态只有一个实现**；先上新、后清旧（清理机制见 §0.4 与台账）
> 方案集导航：落地路线与里程碑见 [`README.md`](README.md) §6 · 系统级验收见 §7 · 外部前置依赖见 §8 · 跨层不变量见 [`session-lifecycle-sequence.md`](session-lifecycle-sequence.md) §6

---

## 0. 定位与范围

### 0.1 Session 在基线图上的位置

```
Router ──路由到会话──▶ Session ──构建上下文──▶ Context ──▶ Agent Loop
             ▲              │
             └────更新会话状态─┘
```

### 0.2 三个子件 + 一个执行器

| 子件 | 职责 | 回答的问题 |
|---|---|---|
| **Manager** | 会话创建、销毁、超时管理 | 这个会话**从哪来、什么时候消失、什么时候被判死** |
| **State** | 会话状态机（进行中 / 等待用户 / 已结束） | 会话**现在处于什么状态、允许什么转移** |
| **Thread** | 多轮对话的线程管理，支持并发会话 | 一个会话里的**多轮**怎么串起来、多个会话怎么并行 |
| **turn 执行器**（§9） | **唯一**的一套 turn 编排：claim · 幂等 · 取消 · 审批中断恢复 | 这一轮**由谁执行、按什么顺序** |

> **为什么执行器单独成章**：它是**本层最大的一块工作量**，也是**全局唯一 turn 实现** —— 多个 Agent 方案（Agent Loop / Execution）都依赖它。埋在「Thread」里会让依赖关系看不出来。

### 0.3 Session 明确不做

| 不做 | 归属 |
|---|---|
| 协议解析、鉴权、幂等去重、渠道回包 | Gateway |
| 选 agent / 路由到哪个会话 / 消息排序 | Router |
| 组装上下文、压缩、摘要 | Context |
| 召回与写入记忆 | Memory |
| 推理循环、**模型与工具的取值**、实际执行 | Agent Loop / Agent Router / Execution |

> **一句话**：Session 管的是「**这个会话存在多久、现在什么状态、第几轮、跑到哪了**」。

### 0.4 实现收敛规则

**最终态只有一个实现**；**先上新、后清旧**。清理机制由 [`cleanup-ledger.md`](cleanup-ledger.md) 统一管理（弃用标记 → 调用打点 → 指标归零 → 删除 → CI 扫描脚本 → 阶段门禁）。

本方案涉及台账条目 **X2**（第二套 turn 实现）、**X3**（`graph_state` 混装）、**X4**（旧 turn / 消息表）、**X6**（`wait_status` 重复状态字段）、**X7**（审批校验被吞异常）、**X18**（Copilot 侧旧 turn 编排）。

---

## 1. 现状盘点

### 1.1 🔴 两套 turn 实现并存

| 实现 | 位置 | claim | 幂等 | 取消 | 审批 | 谁在用 |
|---|---|---|---|---|---|---|
| ① Copilot | `application/copilot.py` + `adapter/graph/runner.py` | ✅ | ⚠️ | ✅ | ⚠️ 校验被吞 | 前端 Copilot 页 |
| ② use_cases | `application/use_cases/run_turn.py` + `run_turn_to_completion.py` | ❌ | ❌ | ❌ | ❌ | 渠道入站、子代理、catalog 评测 |

**同一模块内两套「跑一轮」的语义**，长期漂移。旧路径的唯一 turn 实现在 `application/copilot.py`（647 行）与 `adapter/graph/runner.py`（914 行）里横向铺开——会话生命周期、消息落库、取消轮询、审批恢复、chunk 转发全混在这两个文件。

### 1.2 🔴 审批的校验被静默吞掉

`ApprovalService` **本身是落库且校验正确的**（`modules/governance/src/qzdap/modules/governance/application/approval_service.py`）：

- `approvals` 表存在，审批请求与决策都写库；
- `approve()` / `deny()` 都调用 `_ensure_not_expired()` → **过期审批会被拒绝**；
- `approve()` / `deny()` 都检查 `approver_id == requester_id` → **自审批会被拒绝**（`ApproverMustDiffer`）；
- `expire_if_due()` 能把超期审批自动置为过期。

**但调用方把异常吞了**：

```python
# modules/agent_runtime/src/qzdap/modules/agent_runtime/application/copilot.py:464-471
try:
    if approved:
        await approval_service.approve(...)
    else:
        await approval_service.deny(...)
except Exception:  # noqa: BLE001
    pass          # ← 吞掉 ApproverMustDiffer / ApprovalExpired / ApprovalAlreadyDecided
pending["decision"] = "approved" if approved else "denied"
# 随后无条件执行工具
```

后果：

| 触发条件 | governance 的判定 | 实际结果 |
|---|---|---|
| 审批人 == 请求人 | 抛 `ApproverMustDiffer` | **被吞 → 工具照常执行** |
| 审批已过期 | 抛 `ApprovalExpired` | **被吞 → 工具照常执行** |
| 审批已被决定过 | 抛 `ApprovalAlreadyDecided` | **被吞 → 工具照常执行** |

**另外**：`expire_if_due()` **没有任何生产调用者**（`grep` 只命中 governance 与 self_evolution 的单测）→ 审批**不会自动过期**，只有在有人 approve/deny 时才被检查。

> **这是本层要修的第一个安全问题**，且与「重复点击审批导致工具重复执行」（上一轮已识别）同源。

### 1.3 🔴 事件不落库

旧路径的 chunk 是**边跑边推**给 SSE（`copilot.py:341`），没有任何事件表。后果：

- SSE 一断，客户端只能靠 `agent_session_messages` 里的最终 assistant 消息补，**中间 chunk 全丢**；
- 审批中断只靠 session 行里的 `graph_state` 残留；
- **Gateway 方案的「无感重放」决策 #4 直接依赖 `session_events` 落库** —— 这是本层对 Gateway 的硬交付。

### 1.4 🔴 `graph_state` 混装

`agent_sessions.graph_state`（JSONB）同时存：

| 内容 | 性质 |
|---|---|
| `messages` | 业务数据（对话内容） |
| `pending_approval` | 运行时续传状态 |
| `step` / `stall_count` / `last_tool_sig` | 运行时续传状态 |
| `rolling_summary` | 业务数据（摘要） |
| `plan_decisions` | 业务数据（用户对 plan 的决策） |

**五种语义混在同一列**，且没有 schema 约束——这是「不能出现两套真相」在数据层的体现。

### 1.5 状态字段重复：`status` 与 `wait_status`

`agent_sessions` 有两个表达同一件事的字段：

| 字段 | 取值 | 来源 |
|---|---|---|
| `status`（有 check constraint） | `open` / `running` / `waiting_approval` / `closed` / `cancelled` | 迁移 0035 |
| `wait_status`（**无约束**） | `idle` / `running` / `waiting_approval` | 现有代码 |

`wait_status='running'` 被 `try_claim` 用作互斥标志（`repositories.py:99-104`），`wait_status='waiting_approval'` 被审批流使用（`copilot.py:361`）。**两个字段表达同一状态机，取值还不一样**（`idle` vs `open`）。

### 1.6 乐观并发：有列无逻辑

`agent_sessions.current_revision`（迁移 0035 加的 Integer）与 `session_turns.expected_revision`（新表已有）**旧路径从不读写**。一旦新旧两套实现并存，消息 seq 竞争必然出现。

### 1.7 ✅ 取消：已有的跨进程机制可复用

`agent_sessions.metadata.cancel_requested` 标记 + 1 秒轮询（`copilot.py:348-351`）—— 标记写库、读库直读，**跨 worker 有效**。这是现状里做得对的少数机制之一，Session 层应保留并规范化（从 `metadata` JSONB 提到独立列）。

### 1.8 超时管理：只有一种

现状只有 `CLAIM_STALE_MINUTES = 30` 的**僵尸轮次接管**（`repositories.py:34,93`）—— 上一轮异常退出、30 分钟没释放就当它死了，让新轮次接管。

**缺失**：会话空闲超时、审批自动过期（§1.2）、队列积压超时（Router 方案 §4.5）。

### 1.9 已有可复用资产

| 资产 | 位置 | 状态 |
|---|---|---|
| `session_turns` | 迁移 0035 | ✅ 表已建；含 `idempotency_key` / `expected_revision` / `agent_version` / `model_version` / `cost_usd` / `trace_id`；status 枚举 `('running','waiting','succeeded','failed','cancelled')` |
| `session_messages` | 迁移 0035 | ✅ 表已建；PK `(turn_id, seq)`；**无会话内序号** |
| `session_events` | 迁移 0035 | ✅ 表已建；PK `(turn_id, seq)`；含 `delivery_status` / `delivery_attempts` / `delivered_at` → **Gateway 重放的落点** |
| `outbox_dead_letters` | 迁移 0035 | ✅ 表已建 |
| `agent_sessions.current_turn_id` | 迁移 0035 | ✅ 列已建 → **替代 `wait_status` 的现成落点** |
| `agent_sessions.current_revision` | 迁移 0035 | ✅ 列已建，**旧路径从不使用** |
| `approvals` / `decision_events` 表 | `modules/governance/.../persistence/models.py:89,129` | ✅ 审批已落库且校验正确（问题在调用方吞异常） |
| outbox 投递状态机（8 次重试、指数退避+jitter、死信） | `runtimes/.../outbox/__init__.py` | ✅ 逻辑真，**未接线** |
| `Last-Event-ID` 重放语义 | `runtimes/.../result/sink.py:54-86` | ✅ 内存实现 |

| `PostgresSaver.from_conn_string` | `runtimes/.../graph/builder.py:144-175` | ⚠️ **反例，不算可复用资产** —— 它是**同步版** saver，在全异步仓库里会阻塞事件循环（§5.3）；只能作为「同步版长什么样」的参照，**不得复用** |

> **注意**：表中最后一行是**反例**（同步 saver），不计入「可复用资产」。

---

## 2. 目标架构：三个子件

```
                    ┌────────────────────────────────────────┐
                    │  SessionManager（生命周期）             │
                    │  创建 · 销毁 · 归档 · 超时清扫           │
                    └───────────────┬────────────────────────┘
                                    │ 拥有
                    ┌───────────────▼────────────────────────┐
                    │  SessionState（状态机）                 │
                    │  会话状态 · 轮次状态 · 转移 · 事件       │
                    └───────────────┬────────────────────────┘
                                    │ 约束
                    ┌───────────────▼────────────────────────┐
                    │  SessionThread（多轮线程）               │
                    │  轮次序列 · 消息序列 · checkpoint · 并发  │
                    └───────────────┬────────────────────────┘
                                    │
                    ┌───────────────▼────────────────────────┐
                    │  唯一 turn 实现（执行器）                │
                    │  claim · 幂等 · 取消 · 审批中断恢复        │
                    └────────────────────────────────────────┘
```

**关键分工**：

- **Manager** 只管「会话这个对象的存在」——不碰轮次内容；
- **State** 只管「允许什么转移」——不碰执行细节；
- **Thread** 只管「多轮怎么串、消息怎么排、状态怎么存」——不碰推理；
- **turn 执行器** 承接 Agent Loop 的调用，是**唯一**的一套 turn 编排。

---

## 3. Manager：会话生命周期

### 3.1 创建

```
Router ──lookup（只读）──▶ SessionManager     ← 先问「有没有既有会话」
Router ──resolve_or_create──▶ SessionManager  ← 再决定「创建还是复用」
```

**边界**：Router 决定「这条消息属于哪个 agent / 哪个外部会话」，但**会话实例的创建与查理由 Session 拥有**——Router 不直接查会话表，通过端口调用。

```python
class SessionManagerPort(Protocol):
    async def lookup(
        self, *, session_key: str
    ) -> SessionRef | None: ...          # ← 只读：查既有会话，**不创建**
    async def resolve_or_create(
        self, *, identity: SessionIdentity, agent: AgentBinding
    ) -> SessionRef: ...
    async def close(self, *, session_id: UUID, reason: CloseReason) -> None: ...
    async def archive(self, *, session_id: UUID) -> None: ...
    async def sweep(self, *, now: datetime) -> SweepReport: ...
```

> **⚠️ `lookup` 为什么必须有（2026-10-29 审查修正）**
>
> Router 的策略链**规则 1 是「会话粘性」**（目标会话已存在 → 沿用其 `agent_id`）。但 Gateway 的 `InboundMessage` **不含会话绑定字段** —— 粘性需要「会话是否已存在 + 既有绑定」这个事实。
>
> 而 `resolve_or_create` 需要 `agent_binding` 作为**入参** —— 若只能靠它拿到绑定，就是**鸡生蛋**。
>
> **所以必须是两步**：
> 1. `lookup(session_key)` → `SessionRef | None`（**只读**，不创建任何东西）→ 命中则粘性生效；
> 2. 未命中 → Router 走完整策略链选出 agent → `resolve_or_create(session_key, agent_binding)`。
>
> **`lookup` 的性质**：纯读、可单独实现、**不写任何表**、失败时返回 `None`（不抛错）。它与「决策 #10（Router 不写会话表）」**不冲突** —— #10 约束的是**写**。

**并发创建**：两个 worker 同时为同一外部会话首条消息建会话 → 必须唯一。落点：`agent_sessions.channel_session_key` + **部分唯一索引 `(tenant_id, channel_session_key) WHERE channel_session_key IS NOT NULL`**（**由本方案的迁移 0046 建** —— 会话创建归 Session，Router 决策 #10）→ 冲突后重查。

> **为什么索引归 Session 而非 Router**：Router 只**派生** `session_key`，**不建会话**（**Router 决策 #10**）。唯一索引保护的是「同一外部会话不会被建出两个会话」——这是**会话创建**的正确性，属会话域。

**幂等键与轮次幂等**：`session_turns` 的 `idempotency_key` + 唯一约束 `(session_id, idempotency_key)` —— 同一 `clientRequestId` 重复到达 → 唯一约束冲突 → 读回既有 turn（Gateway 幂等的第二道防线，见 Gateway 方案 §4.6 三层键传递链）。

### 3.2 销毁

| 动作 | 语义 | 现状 |
|---|---|---|
| `close` | 会话结束，不再接受新消息 | ✅ 已有（`copilot.py:140`） |
| `archive` | close + 标记归档（「我的任务」里的「已完成」） | ✅ 已有（`copilot.py:152`） |
| `delete` | 物理删除 | ⚠️ 现状是 `DELETE /api/sessions/{id}` → 调 `close_session`（**软关闭，不是删**）→ 命名与行为不符，需澄清 |

> **决策 #1（已定稿）**：`DELETE /api/sessions/{id}` 的语义 → **对外路径与语义统一为「关闭」，删除走独立的用户数据删除流程（治理域）** —— 避免「以为删了其实还在」。

### 3.3 超时管理

> **决策 #7（已定稿）**：**空闲超时阈值取 30 天（可配）**。不按 agent / 工作区分别配置 —— 那会让配置面爆炸，而 30 天对绝大多数场景既不浪费也不影响体验。

**四类超时**，**现状只有第一类**：

| 超时 | 对象 | 默认阈值 | 触发动作 | 现状 |
|---|---|---|---|---|
| **僵尸轮次** | turn 卡在 `running` | 30 分钟（沿用 `CLAIM_STALE_MINUTES`） | 置 `failed`（`TURN_TIMEOUT`）+ 释放会话 | ✅ 已有（`repositories.py:93`） |
| **审批过期** | approval 停在 `pending` | 15 分钟（沿用 v3.1 §5.7 `APPROVAL_TTL_SECONDS=900`） | 自动 `deny` + 审计 `decision=timeout` | ❌ `expire_if_due()` **无生产调用者** |
| **会话空闲** | 会话最后活动后无新消息 | 30 天（可配） | `close`（reason=`idle_timeout`） | ❌ 无 |
| **幂等键过期** ⚠️ **新增** | `session_inbox` 里 `expires_at < now()` 的行 | 按行（24h / 7d / 120s 三档，Gateway 写入时定） | **删除该行**（单批 ≤1000 行） | ❌ 无 —— ⚠️ **不清理会导致 Gateway 的幂等在 TTL 之后持续误杀** |

> **第四类是 Gateway 方案的硬依赖**（2026-10-29 审查发现）：`session_inbox` 的表归属是 Session（[Gateway 方案](gateway-refactor-plan.md) §8），唯一约束不含 `expires_at` —— **过期行留在表里，同一个键重发时仍会命中冲突**。Gateway 侧的 claim 分支有「过期即当作不存在」作为第二道保险，但**表会无限膨胀**，所以必须有人定期删。
>
> **归属**：本层负责删（表归本层）；Gateway 只负责**写入时把 `expires_at` 定对**（三档 TTL 由幂等键的来源决定，见 Gateway 方案 §4.2）。**两侧都要做，只做一边不够。**

**清扫器的归属**：Session 层提供 `SweepReport` 与清扫逻辑；**调度由 composition 启动定时任务**（与 outbox worker 同类）。现状 outbox worker 有实现但未接线——**两个清扫任务一起接线**。

### 3.4 空闲超时的副作用

会话被超时关闭后，用户再发消息 → 必须有明确行为：

- **推荐**：自动**复活**（= **新建一个会话**接管该外部会话，旧会话保持 `closed` 终态；**不是**状态转移，见 §4.2），而不是报错——对 IM 渠道尤其重要，否则用户「隔了一周再问一句」就得到一个死会话错误；
- **与唯一约束的相容性**：**Session 迁移 0046 建的是** `(tenant_id, channel_session_key)` 的**部分唯一索引**（`WHERE channel_session_key IS NOT NULL`；Router 只派生 key，不建会话 —— 见决策 #10 与 §3.1）。复活的做法必须是「**旧会话的 `channel_session_key` 置 NULL，新会话占用该 key**」——部分唯一索引允许多行 NULL，因此旧行释放 key、新行占用 key 不会冲突。**不能**让两个会话同时持有同一个 key。

> **决策 #2（已定稿）**：空闲超时后同一外部会话再次来消息 → **复活为新会话**（不返回错误码）。

---

## 4. State：会话状态机

### 4.1 会话状态定义

沿用 `agent_sessions.status` **已有的** check constraint（`('open','closed','running','waiting_approval','cancelled')`），不新增枚举：

| 状态 | 含义 | 用户可见（前端「我的任务」） |
|---|---|---|
| `open` | 进行中，等待新消息 | 待处理 |
| `running` | 有一轮正在执行 | 执行中 |
| `waiting_approval` | 等待用户确认（工具审批 / plan 审批） | 待处理（等你确认） |
| `closed` | 已结束 | 已完成 |
| `cancelled` | 被取消 | 异常 |

### 4.2 状态转移表

| 从 | 到 | 触发 | 约束 |
|---|---|---|---|
| （无） | `open` | 创建 | — |
| `open` | `running` | 轮次开始执行 | 该会话无其他 `running` 轮次 |
| `running` | `open` | 轮次结束（成功/失败/取消） | 存在 `current_turn_id` 指向的终态轮次 |
| `running` | `waiting_approval` | 工具审批挂起 | 审批已落 `session_turns.pending_approval` |
| `waiting_approval` | `running` | 审批恢复执行 | 审批校验通过（见 §8） |
| `waiting_approval` | `open` | 审批拒绝 / 审批过期 | — |
| `open` / `running` / `waiting_approval` | `cancelled` | 用户取消 | — |
| `open` / `running` / `waiting_approval` | `closed` | 关闭 / 归档 / 空闲超时 | — |

> **非法转移必须报错**（不是静默忽略）：如 `closed → running`。状态机是**显式的**，集中在 State 子件里，不散落在各处赋值。
>
> **`closed` 是终态**（决策 #2）：空闲超时后的「复活」**不是状态转移**，而是**新建一个会话接管该外部会话**（旧会话保持 `closed` 终态，新会话占用该 `channel_session_key`，§3.4）。因此本表**没有** `closed → open` 这一行 —— 状态机里不存在「复活」这个转移，复活是**创建侧**的行为。

### 4.3 轮次状态机

沿用 `session_turns.status` 已有枚举 `('running','waiting','succeeded','failed','cancelled')`，**需加 `queued`**（迁移 0046 已含）：

| 从 | 到 | 触发 |
|---|---|---|
| （无） | `queued` | Router 分配 `ingress_seq` 后入队 |
| `queued` | `running` | FIFO 轮到它 + 拿到会话执行权 |
| `queued` | `cancelled` | 队列超时 / 会话关闭 |
| `running` | `waiting` | 审批挂起 |
| `running` | `succeeded` / `failed` | 执行结束 |
| `running` | `cancelled` | 用户取消 |
| `waiting` | `running` | 审批恢复 |
| `waiting` | `failed` | 审批过期 / 拒绝 |

### 4.4 状态与字段的归一：**废弃 `wait_status`**

`wait_status` 与 `status` 表达同一件事且取值不一致（`idle` vs `open`）——这是数据层的「第二套真相」。

**替代方案**：用**已有的** `agent_sessions.current_turn_id` 列 + `session_turns.status` 推导：

```
会话是否在跑  ⇔  current_turn_id 指向的轮次 status ∈ {running, waiting}
会话是否空闲  ⇔  current_turn_id 为空，或指向的轮次是终态
```

**取舍**：`try_claim` 原来靠 `wait_status='running'` 做单条 UPDATE 的 CAS（`repositories.py:99-104`），改成推导后要多一次查询。**解法**：CAS 改到轮次表上——`UPDATE session_turns SET status='running' WHERE id=:current_turn AND status='queued'`（配合 FIFO 判定），会话行的 `current_turn_id` 只作指针，不承担互斥语义。

> **决策 #3（已定稿）**：**废弃 `wait_status`**（消灭重复真相），用 `current_turn_id` + `session_turns.status` 推导。**前提**：轮次表需有 `queued` 态 —— 来自 **Router 决策 #1（S1 严格排队）**，两者同日定稿。

### 4.5 状态变更的事件

每次状态转移发布领域事件（复用现有 `EventPublisher`）：

| 事件 | 何时 |
|---|---|
| `SessionOpened` / `SessionClosed` / `SessionCancelled` | 已有（`domain/events.py`） |
| `SessionTurnQueued` | 轮次入队 |
| `SessionTurnStarted` / `SessionTurnSucceeded` / `SessionTurnFailed` | 已有 `TurnStarted` / `TurnCompleted` / `TurnFailed` |
| `SessionApprovalPending` / `SessionApprovalDecided` | 审批挂起 / 决策 |

事件是**审计与回放**的依据，不是通知机制（通知走 outbox）。

---

## 5. Thread：多轮对话的线程管理

### 5.1 thread ≡ session

`thread_id = session_id`（沿用 v3.1 §4.1）。含义：**一个会话就是一条消息线程**，多轮对话是这条线程上的连续 turn。

**并发会话**：不同 session → 不同 thread → 互不干扰；checkpoint 按 `thread_id` 隔离。

### 5.2 轮次序列与消息序列

| 序列 | 落点 | 保证 |
|---|---|---|
| **轮次序**（会话内） | `session_turns.ingress_seq` + 唯一索引 `(session_id, ingress_seq)` | Router 分配的入站顺序 = FIFO 顺序 |
| **轮次内消息序** | `session_messages` PK `(turn_id, seq)` | 已有 ✅ |
| **会话内消息序** | `session_messages.session_seq`（**新增列**） | 上下文重建 / 重放需要跨 turn 的全局顺序 |

> **为什么需要 `session_seq`**：`session_messages` 只有 `(turn_id, seq)`，取「整个会话的消息序列」必须 join `session_turns` 再排序。加一列会话内单调序号后，消息序列是单表内有序扫描——**上下文重建与事件重放都靠它**。

### 5.3 checkpoint

- **归属**：Agent Loop 的图状态（LangGraph checkpoint）按 `thread_id=session_id` 存储，用 Postgres saver；
- **接线**：改用 **`AsyncPostgresSaver`**（`langgraph.checkpoint.postgres.aio`）—— 仓库全异步，同步 saver 会在事件循环里阻塞。`runtimes/.../graph/builder.py:144` 的 `PostgresSaver.from_conn_string` 是**同步版**，不能直接用（`builder.py` 里那段本身也无调用者）；
- **依赖声明**：`psycopg` 当前**已安装但未在根 `pyproject.toml` 声明**（只有 asyncpg / pgvector）→ 异步 saver 需要 `psycopg[binary]`，**必须在本次补进依赖声明**，否则生产镜像缺驱动；
- **表缺失**：checkpoint 系列表**不在任何迁移里** → 必须在迁移 0046 里一并建表（saver 的 `setup()` 会建，但**迁移必须可重复执行且可回滚**，不能依赖运行期自动建表）。
  > **⚠️ 2026-10-29 实施核对修正**：表名按**已安装的 `langgraph-checkpoint-postgres` 3.1.3** 的实际 DDL 为 `checkpoints` / `checkpoint_blobs` / `checkpoint_writes` / `checkpoint_migrations` —— **无 `langgraph_` 前缀、无 `_v2` 变体**（那是 2.x 的命名，3.x 已不存在）。迁移建完把 `checkpoint_migrations` 的版本行写成 `9`（`len(MIGRATIONS) - 1`），saver 的 `setup()` 就不会重复执行它自己的迁移。已实测：`setup()` 跑完 `checkpoint_migrations` 仍是单行 `v=9`。
- **归属**：本层负责把 saver 接进 lifespan（**不是** Agent Loop 方案负责，因为连接串与生命周期由 composition 管）；
- **回退路径**：checkpoint 缺失或损坏 → 从 `session_messages` 重建（会话的规范真相是消息序列，不是 checkpoint）；
- **禁止**把 checkpoint 只放在进程内存——重启即丢。

### 6. 唯一 turn 实现（执行器 · 本层最大的工作量）

**合并两套为一套**，保留 Copilot 版的治理语义：

```
新：runtimes/agent_runtime/src/qzdap_agent_runtime/session/
    manager.py     # SessionManager
    state.py       # 状态机（会话 + 轮次）
    thread.py      # Thread（轮次/消息/checkpoint）
    turn_runner.py # ★ 唯一 turn 实现
    sweeper.py     # 超时清扫
```

`turn_runner.py` 的能力（取自 Copilot 版，丢掉 use_cases 版的简化语义）：

| 能力 | Copilot 版 | use_cases 版 | 合并后 |
|---|---|---|---|
| 会话执行权互斥 | ✅ `try_claim`（**仅互斥，无顺序语义**，见 §11.2） | ❌ | ✅ **轮次表 CAS 是唯一权威**；advisory lock 仅作优化 |
| 轮次幂等 | ⚠️ metadata 存 8 个 id | ❌ | ✅ `session_turns.idempotency_key` 唯一约束 |
| 取消 | ✅ 跨进程 | ❌ | ✅ 独立列 `cancel_requested` |
| 审批中断/恢复 | ⚠️ 校验被吞 | ❌ | ✅ 见 §8 |
| chunk 语义 | ✅ 完整 | ⚠️ 简化 | ✅ 取 Copilot 版 |
| 事件产出 | ❌ 不落库 | ❌ | ✅ 落 `session_events`（§7） |
| 成本归属 | ✅ `_price_of` | ❌ | ✅ 写 `session_turns.cost_usd` |

### 7. 事件落库与 outbox（Gateway 重放的硬交付）

**每个 chunk 先落库，再投递**：

```
产出 chunk
   → 写 session_events (turn_id, seq, event_type, payload, delivery_status='pending')
   → 提交
   → dispatcher 调度投递（**编码与渠道投递归 Gateway**，见 §9.1；本层只负责调度、重试与死信）
   → 更新 delivery_status = delivered / failed（+ delivery_attempts）
   → 超过 MAX_DELIVERY_ATTEMPTS=8 → outbox_dead_letters
```

**顺序保证**：`(turn_id, seq)` 严格递增，同一 turn 内按 seq 升序投递。

> **⚠️ 取值必须小写**：0035 建的 check constraint 是 `delivery_status IN ('pending','delivered','failed','dead_letter')`（**小写**）—— 写 `'PENDING'` 会被 check 约束拒绝，**每个 chunk 的落库都会失败**。

**断线重放**：客户端带 `Last-Event-ID=N` → 从 `session_events` 取 `seq > N` 的事件重放。

> ⚠️ **「未投递」不是重放的过滤条件**（2026-10-29，Gateway 附录 C.6 的 G-36 一族）：`delivery_status` 说的是 **outbox（IM 渠道投递）**的状态；web 的「投递」是把 chunk 交给 SSE 传输，客户端自己就是消费者。Gateway 的重放按 **`seq > N`** 取，**不按 `delivery_status` 过滤** —— 否则「客户端重连补齐自己漏掉的那几段」会取不到（那些段早已被标成 `delivered`）。

**副作用先于投递**：模型结果、工具结果、记忆写入必须在事件入队**之前**提交；投递失败**不回滚** turn，只标 degraded。

> **这是 Gateway 方案决策 #4「无感重放」的落地依赖**。没有它，Gateway 的重复请求只能返回 202 + turn_id。

### 8. 审批中断与恢复（安全加固）

**目标**：审批的挂起与决策**全部落库**，恢复时**逐项校验**，异常**不吞**。

**挂起**：轮次转 `waiting`，`session_turns.pending_approval`（JSONB，新增列，**决策 #6**：落 `session_turns` 而不是独立 `session_approvals` 表）记录：

```json
{ "approval_id": "...", "tool_name": "...", "tool_call_id": "...",
  "arguments_digest": "...", "policy_id": "...", "created_at": "..." }
```

**决策**：以 **governance 的 `approvals` 表为准**（已落库且校验正确）。Session 只存 `approval_id` 引用，**不复制决策**。

**恢复时的校验清单**（任一不过 → 返回明确错误码，**不执行工具**）：

| # | 校验 | 不通过的错误码 |
|---|---|---|
| 1 | 审批存在且 `status='approved'` | `APPROVAL_NOT_MATCH` |
| 2 | 审批未过期 | `APPROVAL_EXPIRED` |
| 3 | 审批绑定的 `(session_id, turn_id, tool_call_id)` 与当前一致 | `APPROVAL_NOT_MATCH` |
| 4 | `approver_id != requester_id` | `APPROVER_MUST_DIFFER`（**新增错误码**） |
| 5 | 审批的 `request_hash` 与当前工具参数一致 | `TOOL_ARGUMENT_INVALID` |

**并去掉 `except Exception: pass`** —— 审批失败必须变成用户可见的错误（`ErrorChunk`），而不是静默放行。

**审批重复点击**：恢复时幂等键必须参与（§6 轮次幂等），同一个 `(session_id, tool_call_id, request_hash)` 复用同一 approval ID，不重复执行工具。

> **决策 #4（已定稿）**：审批恢复失败时的错误**对用户可见**（`ErrorChunk` + 明确错误码），**不执行工具**，不静默降级为「工具未执行」并继续本轮。
>
> **本方案取「对用户可见」**：`ErrorChunk` + 对应的 `ErrorCode`（`APPROVAL_NOT_MATCH` / `APPROVAL_EXPIRED` / `APPROVER_MUST_DIFFER` / `TOOL_ARGUMENT_INVALID`），**不执行工具**。

---

## 9. 与相邻层的边界

| 方向 | 契约 | 它欠本层的 |
|---|---|---|
| **Gateway → Session** | `IdempotencyStore` 实现（`session_inbox` 表，**表归本层**）+ `InboundMessage.idempotency.value` → `session_turns.idempotency_key` | **无**（Gateway 方案 §7 已同步）|
| **Router → Session** | **两步**：① **只读** `lookup(session_key)` → `SessionRef` 或 `None`（供粘性规则用）② `resolve_or_create(session_key, agent_binding)` → `SessionRef`；随后分配 `ingress_seq` 并**向 Session 请求入队** | **无**（Router 方案 §0.6 / §5）|
| **Session → Context** | `SessionRef` + **消息序列** + 轮次上下文（审批状态）—— 供组装 | **无** |
| **Session → Agent Loop** | ⚠️ **只有审批句柄**：审批挂起 / 恢复所需的 `pending_approval` 与 `approval_id`。⚠️ **不含 messages**（消息由 **Context** 装配成 `AssembledContext.messages`）、**不含工具白名单**（工具集来自 **agent 配置的绑定集**，Agent 方案 §5.3.1）| **无** |
| **Session → Gateway** | **读取端口** `EventStore.get_events(turn_id, tenant_id, after_seq)` → `list[SessionEvent]`（供 Gateway 的 `Last-Event-ID` 无感重放，见 Gateway 方案 §4.5）+ `ResultEvent` 流。⚠️ **`tenant_id` 是必需的**（2026-10-29，Gateway 附录 C.6 的 G-36）—— `session_events` 表**没有 `tenant_id` 列**，事件行的租户归属由它的**轮次**决定 → 实现必须 JOIN `session_turns` 并按租户过滤 | **无** |
| **Session ← Router** | 执行权由 Session 持有（**`session_turns.status` 的 CAS 是唯一权威**，advisory lock 仅作优化 —— 与 Router 方案 §4.2(c) 同一口径） | **无** |

**与 Router 的分工**（两处容易混）：

| | Router | Session |
|---|---|---|
| 「路由到会话」 | ✅ 决定路由到哪个会话（外部标识 → 会话） | 提供创建/查回 |
| 「消息什么时候轮到」 | ✅ `ingress_seq` + FIFO 判定 | 提供轮次表 |
| 「能不能执行」 | ❌ | ✅ 执行权（**CAS 是唯一权威**，advisory lock 仅作优化） |

### 9.1 出站投递的分工（与 Gateway 决策 #1 对齐）

Gateway 决策 #1 把「**出站编码 + 渠道投递**」归 **Gateway 的 ① Channel Gateway**。因此本层的 outbox 职责被收窄为：

| 职责 | 归属 |
|---|---|
| 事件落库（`session_events`） | **Session** |
| 投递调度、重试退避、死信（`outbox_dead_letters`） | **Session** |
| **编码成渠道消息格式**（卡片 / 纯文本降级 / 附件） | **Gateway**（`ResultSink`） |
| **实际投递到渠道** | **Gateway**（`ChannelGateway.emit`） |

> Session 交付给 Gateway 的是**结构化事件**（`ResultEvent`），不是渠道报文。Gateway 负责把 `ResultEvent` 编成渠道格式并投递。
>
> ⚠️ **投递状态由 Session 自持，不依赖 Gateway 回传** —— Gateway 方案只承诺「只读 `session_events`」，**没有 `emit_result` 回执契约**。Session 的 `delivery_status` 由**本层的 dispatcher** 在投递尝试后自行更新；若将来要让 Gateway 回传投递结果，需要**在 Gateway 方案 §6 补一条契约**，而不是在本层假设它存在。

---

## 10. 数据与表

### 10.1 表终态

| 表 | 处置 | 说明 |
|---|---|---|
| `agent_sessions` | **保留**（会话主表） | 删 `wait_status`；`graph_state` 迁移后废弃 |
| `session_turns` | **启用**（**决策 #5**：与 Router 决策 #2 同值） | 加 `pending_approval`、`ingress_seq`（0046 已含）、`cancel_requested`、`route_decision`（**Router 写**）、`agent_decision`（**Agent 写**） |
| `session_messages` | **启用** | 加 `session_seq` |
| `session_events` | **启用** | Gateway 重放的落点 |
| `outbox_dead_letters` | **启用** | 投递死信 |
| `agent_turns` | **迁数据后废弃** | 缺幂等键 / revision / 版本冻结字段 |
| `agent_session_messages` | **迁数据后废弃** | 缺会话内序号 |
| `langgraph_checkpoints` / `langgraph_store` | **启用** | Postgres saver |

### 10.2 迁移草案（0046）

```sql
-- migrations/versions/0046_session_runtime.py

-- 1) agent_sessions：外部会话映射唯一化 + 废弃 wait_status
--    唯一索引保护「会话创建的唯一性」，属会话域（Router 只派生 key，不建会话）
CREATE UNIQUE INDEX uq_agent_sessions_channel_key
    ON agent_sessions (tenant_id, channel_session_key)
    WHERE channel_session_key IS NOT NULL;      -- 部分唯一索引：web 会话无 key

-- 4b) 0035 已建普通索引 ix_agent_sessions_channel_session_key (channel_session_key)
--     ⚠️ 新索引前导列是 tenant_id —— **不等价**：
--       仅按 channel_session_key 查询的路径仍需要普通索引。
--     处置：Stage 0 前 grep 确认是否存在「仅按 channel_session_key」的查询：
--       · 无  → DROP（回滚脚本里有重建语句）
--       · 有  → 保留，并在 Stage 6 的清理迁移里统一处理
-- DROP INDEX IF EXISTS ix_agent_sessions_channel_session_key;

-- ⚠️ Stage 0 只做「停止写入 + 保留列」；DROP COLUMN 放在 Stage 6（清理阶段）
--    （迁移 0046 与 Stage 6 分离，避免「迁移即删列」无法回滚）

-- 2) session_turns：审批挂起 + 取消标记 + 路由留痕 + 入站序号
--    （ingress_seq / route_decision / agent_decision 的**唯一 owner 是本迁移**，
--     Router 方案 0045 只引用不建）
--
--    ⚠️ route_decision 与 agent_decision **是两个列、两个写者**（唯一 owner 规则）：
--       · route_decision  → Router 写（会话入口的策略决策，可解释性）
--       · agent_decision  → Agent 层写（每步的专家选择 + 模型/工具取值结果）
--      两者语义不同、写入时刻不同，共用一列会互相覆盖。
ALTER TABLE session_turns
    ADD COLUMN pending_approval  JSONB,
    ADD COLUMN cancel_requested  Boolean NOT NULL DEFAULT false,
    ADD COLUMN ingress_seq       Integer,
    ADD COLUMN route_decision    JSONB,
    ADD COLUMN agent_decision    JSONB;

CREATE UNIQUE INDEX uq_session_turns_session_ingress
    ON session_turns (session_id, ingress_seq)
    WHERE ingress_seq IS NOT NULL;

-- 2b) 轮次状态枚举加 'queued'
-- 0035 建的是 session_turns_status_enum
--   ('running','waiting','succeeded','failed','cancelled')
-- Postgres 不能直接改 check 约束，必须先 DROP 再重建
ALTER TABLE session_turns DROP CONSTRAINT session_turns_status_enum;
ALTER TABLE session_turns
    ADD CONSTRAINT session_turns_status_enum
    CHECK (status IN ('queued','running','waiting','succeeded','failed','cancelled'));

-- 3) session_messages：会话内序号
--    ⚠️ session_id 无 DEFAULT —— `ADD COLUMN ... NOT NULL` 在**非空表**上直接报错。
--    必须三步：可空列 → 回填 → SET NOT NULL。
ALTER TABLE session_messages
    ADD COLUMN session_id  UUID,
    ADD COLUMN session_seq Integer NOT NULL DEFAULT 0;

-- 3a) 回填：session_messages 只有 turn_id，session_id 来自 session_turns
UPDATE session_messages m
   SET session_id = t.session_id
  FROM session_turns t
 WHERE t.id = m.turn_id          -- ⚠️ 主键列名是 id（0035 建表），不是 turn_id
   AND m.session_id IS NULL;

-- 3b) 孤儿检查：turn_id 在 session_turns 无对应 → 回填留 NULL → SET NOT NULL 会失败
--     必须为 0；非 0 时先处置孤儿行（迁到 agent_session_messages 或标记废弃），再继续。
-- SELECT count(*) FROM session_messages m
--  WHERE m.session_id IS NULL
--    AND NOT EXISTS (SELECT 1 FROM session_turns t WHERE t.id = m.turn_id);

-- 3c) 回填完成后才加 NOT NULL
ALTER TABLE session_messages
    ALTER COLUMN session_id SET NOT NULL;

CREATE UNIQUE INDEX uq_session_messages_session_seq
    ON session_messages (session_id, session_seq);

-- 4) session_events：**无新索引**
--    ⚠️ 0035 已建 PRIMARY KEY (turn_id, seq)（pk_session_events）—— PK 自带同组合 B-tree 索引。
--    再建 ix_session_events_turn_seq 是纯冗余（写放大）。
--    「按状态捞待投递」用 0035 已有的 ix_session_events_pending (delivery_status, created_at)。
```

> **索引去重**：本层**不新增** `session_events` 的索引 —— 0035 的 PK 已覆盖 `(turn_id, seq)`，`ix_session_events_pending` 已覆盖待投递扫描。

> **`session_messages.session_id` 需要回填**：从 `session_turns.session_id` 回填，再建唯一索引 —— **顺序不能颠倒**（先 `SET NOT NULL` 会因非空表报错）。回填 SQL 见 §10.2 第 3 步。
>
> **前提**：0035 建表后该表**当前无生产写入**，所以现库上回填是空操作；但迁移**不能依赖这个前提** —— 按上面三步写，将来在有数据的库上跑也安全。

### 10.2.1 0046 的回滚

0046 是**纯新增**（列 + 索引 + 1 组 checkpoint 表），但有**两处不可逆点**必须显式处理：

```sql
-- 1) 删新增的索引
--    （若 0046 里 DROP 了 0035 的普通索引，回滚时重建）
-- CREATE INDEX IF NOT EXISTS ix_agent_sessions_channel_session_key
--     ON agent_sessions (channel_session_key);
DROP INDEX IF EXISTS uq_session_messages_session_seq;
DROP INDEX IF EXISTS uq_session_turns_session_ingress;
DROP INDEX IF EXISTS uq_agent_sessions_channel_key;

-- 2) 删新增的列
ALTER TABLE session_turns
    DROP COLUMN IF EXISTS route_decision,
    DROP COLUMN IF EXISTS agent_decision,
    DROP COLUMN IF EXISTS ingress_seq,
    DROP COLUMN IF EXISTS cancel_requested,
    DROP COLUMN IF EXISTS pending_approval;
ALTER TABLE session_messages
    DROP COLUMN IF EXISTS session_seq,
    DROP COLUMN IF EXISTS session_id;

-- 3) 恢复轮次状态枚举（0035 建的是 session_turns_status_enum）
ALTER TABLE session_turns DROP CONSTRAINT session_turns_status_enum;
ALTER TABLE session_turns
    ADD CONSTRAINT session_turns_status_enum
    CHECK (status IN ('running','waiting','succeeded','failed','cancelled'));

-- 4) checkpoint 表（若由 0046 建）
DROP TABLE IF EXISTS checkpoint_writes;
DROP TABLE IF EXISTS checkpoint_blobs;
DROP TABLE IF EXISTS checkpoint_migrations;
DROP TABLE IF EXISTS checkpoints;
```

> **⚠️ 回滚会丢数据**：
> - `session_messages.session_id` / `session_seq` 是**回填出来的**（从 `session_turns.session_id` 与消息顺序推导），删列即丢；回滚后消息顺序要重新从 `session_messages` 的 `(turn_id, seq)` 推导 —— **可恢复**。
> - `session_turns.route_decision`（Router 写）与 `session_turns.agent_decision`（Agent 写）是路由留痕，删列即丢 —— **不可恢复**，但它们只用于审计，不影响主链路。
> - `session_turns.pending_approval` 是**审批挂起态**。回滚时若还有轮次停在 `waiting`，这些审批记录会丢 → **恢复后这些轮次无法再恢复执行**。因此回滚前必须先让挂起的轮次跑完或显式取消。
>
> **`wait_status` 不在回滚范围内**：Stage 0 只**停止写入**、保留列；物理 DROP 在 Stage 6 的独立迁移里。因此 0046 回滚后 `wait_status` 列仍在（值已停更），**旧代码仍可读**（读到旧值）—— 这正是「先停写、后删列」的设计意图。
>
> **checkpoint 表**：若用 saver 的 `setup()` 运行期建表，删除前必须先停 saver 的连接。

### 10.3 `graph_state` 的拆分去向

| 原 `graph_state` 内容 | 新落点 |
|---|---|
| `messages` | `session_messages` |
| `rolling_summary` | **`agent_sessions.rolling_summary`**（新增列，**由 Context 层的迁移 0047 建**，本方案只迁数据不建列） |
| `pending_approval` | `session_turns.pending_approval` |
| `step` / `stall_count` / `last_tool_sig` | **checkpoint**（LangGraph），不落业务表 |
| `plan_decisions` | `session_events`（事件流里重放） |

迁移期双写，切换后停止写 `graph_state`，**保留 ≥95% 流量后 ≥7 天的只读期**（量化口径见 `cleanup-ledger.md` §3.3；v3.1 §4.2 原写作「一个发布周期」，但本项目无可定义的发布单元）。

> **`rolling_summary` 的唯一落点是 `agent_sessions.rolling_summary`**（Context 层方案 §7.1 / 迁移 0047 定义）。本方案**不建这一列**，只负责把 `graph_state->'rolling_summary'` 的存量回填进去。
>
> **回填顺序（Context 迁移 0047 内执行）**：先从 `graph_state->>'rolling_summary'` 回填，再从 `metadata->>'rolling_summary'` 回填（两者可能同时存在，**`graph_state` 优先**，为空时取 `metadata`），最后清空 `metadata['rolling_summary']`。

---

## 11. 逐文件改造与删除清单

### 11.1 新增（`backend/runtimes/agent_runtime/src/qzdap_agent_runtime/session/`）

| 文件 | 内容 |
|---|---|
| `manager.py` | `SessionManager`：`lookup` / `resolve_or_create` / `close` / `archive` / `sweep` |
| `state.py` | 会话状态机 + 轮次状态机 + 转移校验 + 事件发布 |
| `thread.py` | `SessionThread`：轮次序列 / 消息序列 / checkpoint 句柄 |
| `turn_runner.py` | **唯一 turn 实现** |
| `sweeper.py` | **四类**超时清扫 + `SweepReport`（轮次 / 审批 / 会话空闲 / **`session_inbox` 幂等键过期**） |
| `outbox.py` | 事件落库 + dispatcher 接线（复用 `runtimes/.../outbox/`） |

### 11.2 迁移

| 旧位置 | 迁到 | 动作 |
|---|---|---|
| `application/copilot.py`（647 行） | `session/manager.py` + `session/turn_runner.py` | 拆解；会话生命周期 → Manager，轮次编排 → turn_runner |
| `adapter/graph/runner.py`（914 行） | `session/turn_runner.py` + Agent Loop 方案 | 推理部分归 Agent Loop；编排部分归 turn_runner |
| `application/use_cases/run_turn.py` | `session/turn_runner.py` | **删除**，语义并入唯一实现 |
| `application/use_cases/run_turn_to_completion.py` | `session/turn_runner.py` | **删除** |
| `adapter/persistence/repositories.py:85-108` `try_claim` | **只管执行权（互斥），不管顺序** —— 实测其 CAS 条件只有 `wait_status != 'running' OR updated_at < stale_before`，**无任何序号语义**；`modules/` 里 `ingress_seq` 零命中 → 旧路径**从未有过顺序机制**。改造后：执行权用 `session_turns.status` 的 CAS；顺序是 Router 的**新建**能力 | 改造 |
| `adapter/persistence/repositories.py:155-170` `record_request_id` | `session_turns.idempotency_key` 唯一约束 | ⚠️ **owner 是 Gateway（台账 G1，Gateway · Stage 1）** —— 本层只保证无残留调用方，**不在自己的 Stage 里删别人的条目** |
| `domain/entities.py` `Session.with_runtime` / `graph_state` | `session/state.py` | 改造 |
| `modules/governance/.../approval_service.py` `expire_if_due` | 接到 sweeper | **启用**（现在无调用者） |

### 11.3 保留但改造

| 文件 | 改造点 |
|---|---|
| `adapter/persistence/models.py` | `SessionORM` 删 `wait_status`；`TurnORM` → `session_turns` |
| `adapter/http/router.py`（`/v1/*`） | 与 `/api/*` 合并（Gateway 方案 G7） |
| `adapter/http/session_router.py` | 降级为 HTTP 薄壳 |
| `composition/.../lifespan.py` | 装配 SessionManager / sweeper / outbox worker / Postgres saver |

### 11.4 删除清单（**按 Stage 执行**）

> **「停用」≠「删除」** —— 每个删除项都必须落在**具体的 Stage** 上，不能停在「已弃用」。
> **唯一 owner 规则**：一个旧实现只由一个方案负责删除；别人的条目（如 G1）不在本表出现。

| 阶段 | 类别 | 具体 | 台账 |
|---|---|---|---|
| **Stage 5** | 审批异常吞噬 | `copilot.py` 的 `except Exception: pass` | X7 |
| **Stage 5b** | 第二套 turn 实现 | `application/use_cases/run_turn.py`、`run_turn_to_completion.py` | X2 |
| **Stage 3b** | Copilot 侧旧 turn 编排 | `copilot.py` 的 turn 编排（会话执行 / chunk 转发 / 取消轮询 / 审批恢复） | X18 |
| **Stage 6** | 重复状态字段 | `agent_sessions.wait_status` 列 | X6 |
| **Stage 6** | 混装状态列 | `agent_sessions.graph_state`（迁移期双写后废弃） | X3 |
| **Stage 6** | 旧表 | `agent_turns`、`agent_session_messages`（迁数据后 DROP） | X4 |
| **Stage 6** | 冗余索引 | `ix_agent_sessions_channel_session_key`（若 §10.2 的 grep 确认它已无独立用途） | — |
| **Stage 6** | 孤儿索引 / 废弃常量 | | — |

> **X18 为什么单独落在 Stage 3b**：Stage 3 切完 web/api 入口后，`copilot.py` 的 turn 编排**已无调用方**，但它仍是一份**可被误接回去的第二实现**（~600 行）。删除必须发生在具体的 Stage 上，否则 X18 会永远停在「已弃用」。见 §12 Stage 3b。

---

## 12. 实施阶段

> 每阶段验收都含「**旧代码减少了什么**」。

### Stage 0：契约与迁移

| 动作 | 细节 |
|---|---|
| 建 `session/` 骨架 + `state.py` | 状态机定义 + 转移校验 |
| 迁移 0046 | 加 `pending_approval` / `cancel_requested` / `ingress_seq` / `route_decision`（**Router 写**）/ `agent_decision`（**Agent 写**）（L2）；`session_messages` 加 `session_seq` / `session_id`（L3）；`session_turns.status` 枚举加 `queued`（先 DROP `session_turns_status_enum` 再重建）；建 checkpoint 表（`checkpoints` / `checkpoint_blobs` / `checkpoint_writes` / `checkpoint_migrations`）；**`wait_status` 仅停止写入，列保留到 Stage 6 再 DROP** |
| `session_messages.session_id` 回填 | 从 `session_turns` 回填后建唯一索引 |
| `ErrorCode` 补 `APPROVER_MUST_DIFFER` | `libs/schema/.../errors.py` |
| **Async** Postgres saver 接线 | **`AsyncPostgresSaver`**（`langgraph.checkpoint.postgres.aio`）接进 lifespan。⚠️ **不能用 `PostgresSaver.from_conn_string`** —— 那是**同步版**，会在全异步仓库里阻塞事件循环（§5.3） |
| **收敛基础设施** | 建 `qzdap_legacy_calls_total` 指标（若尚未建立），并给本层台账条目的旧入口打点（`record_legacy_call("<编号>")`）。**没有打点就没有清理判据** —— 见 `cleanup-ledger.md` §3.2 |

**旧代码减少**：无（纯新增 + 迁移）。
**验收**：状态机单测覆盖全部合法/非法转移；迁移在 dev 库跑通。
**验收补充**：本层每个台账条目的旧入口都有打点；`/metrics` 能查到 `qzdap_legacy_calls_total`。

### Stage 1：Manager 落地

| 动作 | 细节 |
|---|---|
| `lookup` | **只读**查既有会话（`session_key` → 会话实例 + 其 agent 绑定）；**不创建**。Router 粘性规则的依据（§3.1） |
| `resolve_or_create` | 外部会话 → 会话实例；并发创建靠唯一约束 |
| `close` / `archive` | 复用现有语义 |
| sweeper 骨架 + 僵尸轮次接管 | 复用 `CLAIM_STALE_MINUTES` 经验 |
| **sweeper 补第四类清扫** | 删 `session_inbox` 中 `expires_at < now()` 的行（单批 ≤1000）—— **Gateway 的幂等 TTL 依赖它**（Gateway 方案 §4.3.1） |
| **删除** `try_claim` 的 `wait_status` 分支 | 改用轮次表 CAS |

**旧代码减少**：`wait_status` 写入点归零。
**验收**：并发建会话只有一个成功；僵尸轮次 30 分钟后被接管。

#### 实施记录（2026-10-30 · Stage 0 + Stage 1）

| 项 | 结果 |
|---|---|
| 契约包 | `runtimes/agent_runtime/src/qzdap_agent_runtime/session/` —— `state.py`（状态机）· `manager.py`（Manager + 端口）· `sweeper.py`（清扫端口） |
| 适配器 | `modules/agent_runtime/.../adapter/persistence/session_store.py`（`PostgresSessionStore`）· `session_sweeper.py`（`PostgresSessionSweeper`） |
| 接线 | **composition 的 lifespan**：① 周期清扫任务（默认 300s）② `AsyncPostgresSaver`（异步 saver；**同步 saver 工厂已删**，台账 X20）③ `app.state.session_manager_factory` |
| ⚠️ saver 的**消费方**在 Stage 2 | `AsyncPostgresSaver` 现在只被**持有**（建连接 / `setup()` / 关停释放）—— 真正用它跑图（`thread_id=session_id`）是 **Stage 2 的 S-14**。本轮不假装「已接线即已接管」 |
| 领域收敛 | 模块领域的 `SessionStatus` **删除**，改为**再导出**契约层的 5 值枚举（旧枚举只有 2 值，落后于表的 check constraint） |
| 测试 | `test_session_state.py`（合法/非法转移全覆盖）· `test_session_manager.py` · `test_session_store.py`（**真库**）· `test_session_sweeper.py`（**真库**）· `tests/architecture/test_session_boundary.py`（架构边界）· `test_session_lifespan_wiring.py`（接线不静默失败） |

**偏差与未接管**（不假装完成）：

| # | 事项 | 原因 | 归属 |
|---|---|---|---|
| **S-06 / S-11** | `wait_status` 写入点归零 / 删 `try_claim` 的 `wait_status` 分支 | **第二套 turn 实现（X2）仍靠它做互斥** —— 删了 IM 侧就没有互斥 ✗✗ | **Stage 3**（唯一 turn 实现）落地后才能做；本轮改为**旧入口打点**（`record_legacy_call("X6")` / `("R3")`） |
| **清扫第 2 类** | 审批过期 | 归**治理域**（`approval_service.expire_if_due`） | 治理域 / Session Stage 5（S-30） |
| **清扫第 3 类** | 会话空闲（30 天） | **必须等「复活」路径**（Stage 2）—— 只关不复活 = 用户的旧对话从列表里消失 ✗✗ | Stage 2 |
| **S-07** | `X7`（审批吞异常）**提前清理** | 该缺陷 = 审批失败后**工具照常执行**；本轮改成「记日志 + **再抛**」（旧打点撤除） | 比原定的 Stage 5 提前到 Stage 1 |
| **两套 `TurnStatus`** | 契约层 `session/state.py` 的 `TurnStatus`（`queued`/`running`/`waiting`/`succeeded`/`failed`/`cancelled` = `session_turns` 的 check constraint）与模块领域 `entities.py` 的 `TurnStatus`（`running`/`succeeded`/`failed`/`denied` = 旧 `agent_turns` 的语义） | **语义不同** —— `denied` 在新表里没有对应值，不能直接换掉 | **Stage 3**（唯一 turn 实现时合并）。本轮只收敛了 `SessionStatus`（两边语义完全一致，只是取值集合落后于表约束） |
| **§13.2 规则 1 / 2** | 架构测试里的「只有一个 turn 实现」「状态机是唯一状态写入点」 | 依赖 Stage 3 的唯一 turn 实现 —— 现在跑必然红（两套都在） | Stage 3；本轮只落**能判真**的规则（框架禁令 / 不反向依赖 / 不用同步 saver / `SessionStatus` 只有一处定义） |

### Stage 2：Thread 落地

| 动作 | 细节 |
|---|---|
| 轮次序列（`ingress_seq`） | 与 Router 方案合并（DDL 归迁移 0046，由 Session 层拥有） |
| 消息序列（`session_seq`） | 会话内单调 |
| checkpoint 接线 | Postgres saver，`thread_id=session_id` |
| 启用 `session_turns` / `session_messages` | 写入切换 |

**旧代码减少**：旧表写入点归零（读还在，用于迁移）。
**验收**：会话消息序列可单表有序取出；进程重启后 checkpoint 可恢复。

### Stage 3：唯一 turn 实现

| 动作 | 细节 |
|---|---|
| `turn_runner.py` 落地 | 合并两套的治理语义 |
| 轮次幂等 | `session_turns.idempotency_key` 唯一约束 |
| 取消 | 独立列 `cancel_requested` + 轮询（保留现有跨进程机制） |
| 成本归属 | 写 `session_turns.cost_usd` |
| **切换 web/api 入口** → 新 `turn_runner` | `session_router.py` 的 turn 部分改走新实现 |
| **停用 + 打点** `copilot.py` 的 turn 编排 | 台账 **X18**（Copilot 侧）→ 已弃用；**它已无调用方**。注意：X2 只指 IM 侧的第二套 turn 实现（`use_cases/run_turn*.py`）。⚠️ **本 Stage 只停用、不删** —— 删除落在 **Stage 3b**（§11.4） |
| **停用 + 打点** `use_cases/run_turn*.py` | 台账 X2（IM 侧）→ 已弃用。⚠️ **但 IM 渠道仍在调它** —— 只有 Stage 5b 切了 IM 入口才真能删 |

**旧代码减少**：**本 Stage 不删行** —— X18 与 X2 都只「停用 + 打点」；**X18 的删除在 Stage 3b**（7 天清理窗口后），**X2 的删除在 Stage 5b**（与 Gateway 的 IM 入口切换同 PR）。旧路径**变小**：web/api 的旧编排不再被任何入口调用（**存活实现只剩一套**，代码行数待 Stage 3b / 5b 兑现）。
**验收**：同一 `clientRequestId` 重复到达 → 只起一轮；取消跨 worker 生效；**web/api 上只有一套「跑一轮」的语义**。

### Stage 3b：删 Copilot 侧旧 turn 编排（**X18**）

> **为什么单独拆一个 Stage**：Stage 3 切完 web/api 入口后，`copilot.py` 的 turn 编排**已无调用方** —— 但「已弃用」不是终点，它仍是一份**可被误接回去的第二实现**（~600 行）。删除必须落在具体的 Stage 上，否则 X18 会永远停在「已弃用」，违反「停用 ≠ 删除」。
>
> **为什么不与 Stage 3 同 PR 删**：同 PR 删会让本层**立刻不可 revert**（旧编排没了，回退只能重上线旧版本）。这里保留 **≥7 天的回退窗口** —— 窗口内 `git revert` 切换提交即可回到旧路径。

| 动作 | 细节 |
|---|---|
| **进入条件** | ① `qzdap_legacy_calls_total{entry="X18"}` **连续 ≥7 天为 0**；② 新路径流量 ≥95%（`cleanup-ledger.md` §3.2 口径）；③ 备份已完成并验证可恢复 |
| 删 `copilot.py` 的 turn 编排 | 会话执行 / chunk 转发 / 取消轮询 / 审批恢复 —— 语义已在 Stage 3 迁入 `session/turn_runner.py` |
| `copilot.py` 剩余部分 | 降级为 HTTP 薄壳（`close_session` / `archive_session`）；会话生命周期已迁到 `session/manager.py` |
| 更新台账 | **X18 → 已清理** |

**旧代码减少**：**~600 行**（`copilot.py` 647 行减去 HTTP 薄壳后的剩余）—— **X18 的终结点**。
**验收**：全仓 `grep` 无旧 turn 编排符号；`copilot.py` 只剩 HTTP 薄壳（≤120 行）；台账 X18 → 已清理；CI 扫描规则「X18」启用（§13.3）。

### Stage 4：事件落库与 outbox

| 动作 | 细节 |
|---|---|
| chunk 写 `session_events` | 先落库再投递 |
| dispatcher 接线 | 复用 `runtimes/.../outbox/` 的重试与死信 |
| `Last-Event-ID` 重放 | 从 `session_events` 按 seq 重放 |
| outbox worker 接线 | 与 sweeper 一起进 lifespan |

**旧代码减少**：无（新增）。
**验收**：SSE 断开后带 `Last-Event-ID` 重连 → 内容完整；投递失败进死信。

> **这是 Gateway 决策 #4「无感重放」的落地依赖**，完成后 Gateway 的重复请求才能真正无感。

### Stage 5：审批中断恢复加固

| 动作 | 细节 |
|---|---|
| 审批挂起落库 | `session_turns.pending_approval` |
| 恢复校验清单 | 5 项校验（§8） |
| **删除** `except Exception: pass` | 审批失败 → `ErrorChunk` + 明确错误码 |
| 审批自动过期 | `expire_if_due()` 接入 sweeper |
| 审批幂等 | 同 `(session_id, tool_call_id, request_hash)` 复用 approval ID |

**旧代码减少**：审批异常吞噬点归零。
**验收**：过期审批、自审批、参数被改、重复点击 → **四种情况都不执行工具**，且返回明确错误码。

### Stage 5b：删第二套 turn 实现（**与 Gateway 的 IM 入口切换原子**）

> **为什么单独拆一个 Stage**：第二套 turn 实现（`use_cases/run_turn.py` + `run_turn_to_completion.py`）服务的是 **IM 渠道**（`dispatch_subscriber.py → run_turn_to_completion`）。**只要 IM 入口还没切到新链路，删了它 IM 就断** —— 这是台账 §3.4 列的「必须原子切换」条目之一。
>
> **因此本 Stage 与 Gateway Stage 4a 的「切 IM 入口」必须同一个 PR**（见 [`implementation-plan.md`](implementation-plan.md) §3.1 G-20 与 §3.3 S-32 —— **同一个 PR**）。

| 动作 | 细节 |
|---|---|
| **切 IM 入口** | `dispatch_subscriber.py` → 新链路（**与 Gateway 同 PR**） |
| **删 `use_cases/run_turn.py`** | 第二套 turn 实现（~476 行） |
| **删 `use_cases/run_turn_to_completion.py`** | 同上 |
| 删 `dispatch_subscriber.py` | ⚠️ **文件删除归 Gateway（台账 G9）**，本层只保证无残留调用方 |

**旧代码减少**：第二套 turn 实现（~600 行）—— **这是「两套 turn 实现并存」的终结点**。
**验收**：IM 渠道上**只剩一套**「跑一轮」的语义；台账 X2 → 已清理。

### Stage 6：清理与封口

> **进入条件**：本层台账条目（X2 / X3 / X4 / X6 / X7）全部满足 `cleanup-ledger.md` §3.2 的量化判据。

| 动作 | 细节 |
|---|---|
| **DROP `agent_sessions.wait_status` 列** | 迁移 0046 只停写，本阶段才物理删（**单独迁移，不与 0046 合并**） |
| 删 `wait_status` 列 | 数据清理（物理 DROP；**停写已在 Stage 0**，读端已随 Stage 5b 删除） |
| 停写 `graph_state` → 废弃 | 保留 ≥95% 流量后 ≥7 天的只读期 |
| 迁数据 + DROP 旧表 | `agent_turns` / `agent_session_messages` |
| 启用 CI 扫描脚本 | 台账 **X2 / X3 / X4 / X6 / X7** 段（脚本唯一来源：`cleanup-ledger.md` §3.1） |
| 更新台账状态 | **X2 / X3 / X4 / X6 / X7** → 已清理 |
| 更新现状文档 | `docs/copilot-chat-module-architecture.md` |

**旧代码减少**：§11.4 删除清单**归零** —— `wait_status` 列 + `graph_state` 列 + `agent_turns` / `agent_session_messages` 两张旧表，**合计约 300 行 + 2 表 + 2 列**（第二套 turn 实现的 ~600 行已在 Stage 5b 删除）。
**验收**：台账本层条目全部「已清理」；扫描脚本无命中。

### 阶段与「旧代码减少」对照

| 阶段 | 删除/替换 | 旧代码减少（行） | **新写入量（估算）** | 旧路径状态 |
|---|---|---|---|---|
| Stage 0 | 无（纯新增 + 迁移 0046） | 0 | `session_turns` / `session_messages` / `session_events` 三表开始写入；checkpoint 四表 | — |
| Stage 1 | `wait_status` 写入点 | ~20 行 | 同上 | 直接替换 |
| Stage 2 | 旧表写入点 | — | **双写期**：新旧两套表同时写（迁移期成本翻倍） | 直接替换（读保留用于迁移） |
| Stage 3 | `copilot.py` 的 turn 编排（**X18**）**停用 + 打点** | 0（删除见 Stage 3b） | 同上 | **停用 + 打点** → 清理窗口 → **Stage 3b 删除**。`runner.py` 的 ReAct 循环（**X17**）**归 Agent 层**（Stage 5 接线 → Stage 7 删），本层不碰 |
| Stage 4 | 无（事件落库 + outbox） | 0 | **`session_events`：每个 chunk 一行**（一次对话平均 5–20 行）；`outbox_dead_letters` 少量 | ⚠️ **事件落库已随 Gateway Stage 4b 连带落地**（2026-10-29：`session_turns` 轮次双写 + `session_events` 每个 chunk 一行 + 按 seq 的读取端口）；**outbox 调度 / 重试退避 / 死信 / 保留期仍在 Stage 4** |
| Stage 5 | 审批异常吞噬（`copilot.py` 的 `except Exception: pass`） | ~5 行 | 同上 | **删除**（X7） |
| Stage 5b | 第二套 turn 实现（`use_cases/run_turn.py` + `run_turn_to_completion.py`） | ~600 行 | 同上 | **删除**（与 Gateway 的 IM 入口切换同 PR · X2 的 IM 侧） |
| Stage 3b | Copilot 侧旧 turn 编排（`copilot.py` 的 turn 编排 · **X18**） | ~600 行 | 同上 | **删除**（清理窗口 ≥7 天且指标归零后；与 Stage 3 的切换分离，留回退窗口） |
| Stage 6 | `wait_status` 列 + `graph_state` + 旧表 | ~300 行 + 2 表 + 2 列 | 停旧写后回到单写 | **删除**（台账清零） |

> **新写入量的量级对照**：本层的写入量主要来自 `session_events` —— **每个 chunk 一行**。粗估：单租户日均 1 万轮、平均每轮 10 个 chunk → **约 10 万行/天**，每行 payload 约 0.5–4 KB → **约 50–400 MB/天**。这是**方案集里写入量最大的一张表**（大于 Context 的 manifest，因为 chunk 数 ≥ 模型调用数），需要保留期策略。
>
> **`session_turns` / `session_messages` 反而不是瓶颈**：每轮 1 行 turn + 平均 2–4 行 message。

---

## 13. 验收标准

> **本层在系统级验收中的责任**：
> 本层负责系统级验收的 **#3（重复消息只跑一次）的轮次侧 · #4（同会话严格有序）的互斥侧 · #5（审批中断可恢复）的挂起侧**（完整清单见 [`README.md`](README.md) §7）。

### 13.1 功能验收

1. **状态机**：全部合法转移可用、全部非法转移报错（会话 + 轮次）；
2. **唯一实现**：全仓只有一套 turn 编排（CI 扫描脚本把关）；
3. **审批安全**：过期审批 / 自审批 / 参数被改 / 重复点击 → **四种情况都不执行工具**，返回明确错误码；
4. **审批可恢复**：进程重启后审批仍能恢复（挂起与决策都在库里）；
5. **事件可重放**：SSE 断开重连 → 中间 chunk 不丢；投递失败进死信；
6. **幂等**：同一 `clientRequestId` → 只起一轮；跨 worker 有效；
7. **取消**：跨 worker 生效；取消后轮次落 `cancelled` 而非永远 `running`；
8. **超时**：僵尸轮次、审批过期、会话空闲、**`session_inbox` 幂等键过期**四类都自动生效；
9. **并发**：不同会话并行不互相阻塞；同会话严格按 `ingress_seq`；
10. **一致性**：`session_turns.cost_usd` / `agent_version` / `model_version` 正确写入；`current_revision` 真正用于乐观并发；
11. **架构测试**：Session 层不得 import FastAPI / SQLAlchemy。


---

### 13.2 架构测试

```python
# tests/architecture/test_session_boundary.py
FORBIDDEN = ("fastapi", "starlette", "sqlalchemy", "asyncpg", "psycopg")

def test_session_layer_has_no_framework_imports():
    """Session 层不得依赖框架 —— 由 README §3.2 的边界判据派生。"""
    for path in _py_files(("backend/runtimes/agent_runtime/src/qzdap_agent_runtime/session",)):
        for mod in FORBIDDEN:
            assert mod not in _imports_of(path), f"{path} 引入了 {mod}"
```

另加三条本层特有的规则：

| # | 规则 | 检查方式 |
|---|---|---|
| 1 | **只有一个 turn 实现** | 全仓 `run_turn` / `_run_turn` 的实现类只允许一处（Session 的 `turn_runner.py`）；`use_cases/` 下的旧实现在 Stage 6 后必须不存在 |
| 2 | **状态机是唯一的状态写入点** | 关键字扫描：`session_turns.status` 的**裸赋值**（`SET status =` / `status =`）只允许出现在 `session/state.py`；其他位置必须调用状态机暴露的转换函数。**放行 CAS（`queued → running`）是状态机的入口**：其 SQL 由 `session/state.py` 的 `claim_turn()` 实现，`turn_runner` 只调用该函数 —— 否则 §4.4 / Router §4.2(c) 的放行判定会被本规则误杀 |
| 3 | **不使用同步 saver** | import 扫描：`langgraph.checkpoint.postgres`（同步）**禁止**出现，只允许 `langgraph.checkpoint.postgres.aio` |

### 13.3 「没有第二套实现」的扫描

**扫描脚本的唯一来源是 [`cleanup-ledger.md`](cleanup-ledger.md) §3.1**，本层不另写一份。Session 域对应的规则：

| 旧符号 | 台账条目 |
|---|---|
| `wait_status` | X6 |
| `graph_state` | X3 |
| `agent_turns` / `agent_session_messages` | X4 |
| `RunTurnCompletionUseCase` / `use_cases.run_turn` | X2 |
| Copilot 侧旧 turn 编排（符号：`_fail_turn` / `async def _run_turn(`，见台账 §3.1） | X18 |

> 启用时点：**X18 的规则在 Session Stage 3b 合并时启用**（与 X18 的删除在同一个提交里完成）；**其余条目在 Session Stage 6 合并时启用**。

---

## 14. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| **表切换涉及数据迁移** | 历史会话丢失或错乱 | 迁移期双写 + 读校验；旧表 DROP 放在最后一个阶段 |
| **`graph_state` 双写期** | 两侧不一致 | 双写期以新表为准，切换前做一次全量对账 |
| **审批语义变更**（不再吞异常） | 原本「静默放行」的场景开始报错 | 属**修复而非破坏**；前端已有 `ErrorChunk` 通道；需在灰度期观察 `APPROVAL_EXPIRED` 计数 |
| **事件落库增加写入量** | 每轮多 N 次写 | 与轮次写入同事务；批量投递；必要时按 `delivery_status` 归档 |
| **checkerpointer 引入外部依赖** | 迁移失败 → 图不可用 | 保留「从 `session_messages` 重建」的回退路径 |
| **与 Gateway / Router 的阶段耦合** | 本层 Stage 4 未完成 → Gateway 重放不可用 | 已在 §0.5 与 README 记录依赖顺序 |

### 14.1 回退

| 时点 | 回退方式 | 代价 |
|---|---|---|
| Stage 0–2（双写期） | `git revert` 提交；**双写本身是安全的** | 旧表仍在写，新表数据可弃 |
| Stage 3（已接管） | `git revert` 切换提交 → 旧 turn 实现接管 | 无（旧实现在场，**Stage 3b 之前随时可退**） |
| Stage 3b（X18 已删） | 需**重新上线旧版本**（`copilot.py` 的 turn 编排已删，无法 revert 切换提交） | 旧编排需从 git 历史恢复 |
| Stage 6（已清理） | 需**重新上线旧版本** | 旧表已 DROP，`graph_state` 已废弃 → **数据不可恢复** |

> **本层特有的不可逆点**（四个，按发生顺序）：
> 0. **X18 删除**（Stage 3b）—— `copilot.py` 的旧 turn 编排被删后，Stage 3 的切换提交**不再可 revert**（只能从 git 历史恢复代码 + 重新上线）；
> 1. **`graph_state` 停写**（Stage 6）—— 停写后旧路径若复活会缺续传状态；
> 2. **`wait_status` 列 DROP**（Stage 6）—— 旧路径若复活需要重新加列；
> 3. **旧表 DROP**（Stage 6）—— 不可逆。
>
> **因此 Stage 6 必须满足两个条件才能执行**：① 台账 **X3 / X4 / X6** 全部「已清理」且指标归零（**X2 与 X7 已在 Stage 3 / Stage 5 提前清理**）；② 备份已完成并验证过可恢复。**「测试环境验证过」不算**。
---

## 15. 治理与可观测性落点

### 15.1 治理落点（Governance）

| 本层步骤 | 闸门 | 拒绝 / 降级时的行为 |
|---|---|---|
| 会话创建 | 租户 / 工作区 / 用户的会话归属校验 | 越权访问 → `SESSION_FORBIDDEN`；**不泄露会话是否存在** |
| 状态机迁移 | 只允许状态机定义的迁移（§4） | 非法迁移 → `INVALID_STATE_TRANSITION`，**不静默吞掉** |
| 轮次幂等 | `session_turns.idempotency_key` 唯一约束 | 冲突 → 返回既有轮次（**幂等命中，不是错误**） |
| 审批挂起 | 轮次进入 `waiting` 时绑定审批记录 | 审批过期 → 轮次转 `cancelled`（§4 状态机） |
| 事件投递 | outbox 投递状态机 | 投递失败按退避重试；超过上限 → 死信（`outbox_dead_letters`） |

> **本层不拥有的治理**：消息级限流（Gateway）、工具执行审批的**语义判定**（Governance 决策）、记忆可见范围（Memory）。

### 15.2 可观测性指标（Observability）

指标名进 `qzdap_*` 命名空间，实现落在 `backend/libs/observability/src/qzdap_observability/metrics.py`。

| 指标名 | 类型 | 标签 | 说明 |
|---|---|---|---|
| `qzdap_sessions_active` | Gauge | `tenant_id` | 活跃会话数（按 §4 状态机处于活动态的会话） |
| `qzdap_sessions_created_total` | Counter | `tenant_id`, `source` | 会话创建数 |
| `qzdap_sessions_expired_total` | Counter | `tenant_id` | 超时销毁的会话数 |
| `qzdap_turns_total` | Counter | `status` | 轮次终态计数（`succeeded` / `failed` / `cancelled` / `waiting`） |
| `qzdap_turn_duration_seconds` | Histogram | `status` | 轮次从受理到终态的耗时 |
| `qzdap_turn_idempotent_hit_total` | Counter | `layer` | 幂等命中数（`layer`：`turn` / `tool`） |
| `qzdap_outbox_pending` | Gauge | `event_type` | 待投递事件数 |
| `qzdap_outbox_delivery_total` | Counter | `event_type`, `outcome` | 投递结果（`delivered` / `retried` / `dead_letter`） |
| `qzdap_legacy_calls_total` | Counter | `entry` | 旧实现调用计数（标签 `entry` 为台账编号） |

**Span 划分**：

| Span | 父子关系 | 属性 |
|---|---|---|
| `session.turn` | 根 | `session_id`, `turn_id`, `status` |
| `session.turn.state_transition` | `session.turn` | `from`, `to` |
| `session.event.persist` | `session.turn` | `event_type`, `seq` |
| `session.outbox.deliver` | `session.event.persist` | `event_type`, `attempt`, `outcome` |

### 15.3 审计

| 事件 | 何时写 | 内容 |
|---|---|---|
| `session.turn.state_changed` | 轮次状态迁移 | from / to / 原因 / 操作者 |
| `session.turn.cancelled` | 轮次被取消（含审批过期） | 原因、触发方 |
| `session.event.dead_letter` | 事件投递进死信 | 事件类型、重试次数 |

> 审计写入走 Governance 模块，Session 只投递事件。
---

## 附录 A：已定稿的决策（2026-10-29 逐条确认）

> 以下 **7 条**决策（#1–#7）已逐条确认并定稿。**改动其中任何一条，都必须同步修改正文对应章节，并在 §10 补记受影响的阶段。**

| # | 决策 | 定稿结果 | 备选 | 影响 |
|---|---|---|---|---|
| 1 | `DELETE /api/sessions/{id}` 的语义 | **关闭**（不是物理删除）；删除走治理域的用户数据删除流程 | 改为真删除 | API 语义、前端预期 |
| 2 | 空闲超时后再来消息 | **复活为新会话** | 拒绝并返回错误码 | IM 渠道体验 |
| 3 | `wait_status` | **废弃**，用 `current_turn_id` + `session_turns.status` 推导 | 保留但与 `status` 对齐取值 | 消灭重复真相 vs 多一次查询。**前提：轮次表需有 `queued` 态**——这来自 **Router 决策 #1（S1 严格排队）**，两者是同一件事的两面，**已于同日定稿** |
| 4 | 审批恢复失败 | **对用户可见**（`ErrorChunk` + 明确错误码），不执行工具 | 静默降级为「工具未执行」并继续 | 安全 vs 体验 |
| 5 | 旧表处置 | **`session_turns` / `session_messages` 启用，旧表迁数据后 DROP**（Stage 6） | 沿用旧表并补列 | **与 Router 决策 #2 同值**（两者是同一决策的两面，已同日定稿）。**注意**：第二套 turn 实现的删除在 **Stage 5b**（与 Gateway 的 IM 入口切换原子），不随旧表一起 |
| 6 | 审批挂起的落点 | `session_turns.pending_approval`（JSONB） | 独立 `session_approvals` 表 | 查询与审计便利性 |
| 7 | 空闲超时阈值 | 30 天（可配） | 按 agent / 工作区分别配置 | 存储成本与体验 |

> **与 Router 方案的一致性要求**：决策 #5 必须与 Router 方案附录 A 决策 #2（表选择）**取同一个值**，否则两层会落在两套表上——这正是「不能出现两套真相」要消灭的情况。

---

## 附录 B：现状 → 目标 文件对照速查

| 现状文件 | 目标状态 |
|---|---|
| `application/copilot.py`（647 行） | 拆为 `session/manager.py` + `session/turn_runner.py` + HTTP 薄壳 |
| `adapter/graph/runner.py`（914 行） | 编排 → `session/turn_runner.py`；推理 → Agent Loop 方案 |
| `application/use_cases/run_turn.py`（476 行） | **删除** |
| `application/use_cases/run_turn_to_completion.py` | **删除** |
| `adapter/persistence/repositories.py` `try_claim` / `record_request_id` | `try_claim`：**只管执行权**（互斥），改用轮次表 CAS（顺序是 Router 的**新建**能力，旧路径从无顺序机制）；`record_request_id`：**由 Gateway 删除**（台账 G1） |
| `domain/entities.py` `Session.with_runtime` / `graph_state` | 拆为 `session/state.py` + 各表 |
| `agent_sessions.wait_status` | **废弃** |
| `agent_sessions.graph_state` | 迁往 `session_turns` / `session_messages` / checkpoint，随后废弃 |
| `agent_turns` / `agent_session_messages` | 迁数据后 **DROP** |
| （新增）`runtimes/.../session/` | manager / state / thread / turn_runner / sweeper / outbox |
| （复用）`runtimes/.../outbox/`、`result/sink.py`、`graph/builder.py` 的 `PostgresSaver` | 接线（⚠️ `PostgresSaver` 是**同步版**，只作参照，**不得复用** —— 用 `AsyncPostgresSaver`） |

---

## 附录 C：2026-10-29 审查修正记录

> 本方案 v1.0 → **v1.1** 的全部修正。**每条都对着 `backend/` 的代码或迁移文件核实过**。
>
> **决策定稿（2026-10-29）**：附录 A 的 **7 条**决策已由用户拍板，取值为本方案的建议值；其中 **#5 与 Router #2 同值**、**#3 的前提来自 Router #1（S1 严格排队）**，两组跨层耦合同日落定。

| # | 级别 | 问题 | 修正 | 落点 |
|---|---|---|---|---|
| **S1** | 严重 | `delivery_status='PENDING'`（大写）与 0035 的 check constraint（**小写**）冲突 → 每个 chunk 落库都失败 | 改为小写，并加显式告警 | §7 |
| **S2** | 严重 | `ADD COLUMN session_id UUID NOT NULL` 在非空表上**直接报错** | 改三步式：可空列 → 回填 → `SET NOT NULL`，并加孤儿检查 | §10.2 第 3 步 |
| **S3** | 严重 | `ix_session_events_turn_seq` 与 0035 的 PK `(turn_id, seq)` **完全重复**（写放大） | 删除该索引；说明待投递扫描用 `ix_session_events_pending` | §10.2 第 4 步 |
| **S4** | 严重 | 把 `try_claim` 说成「拆：顺序 → Router、执行权 → Session」 —— 实测它**只有互斥**，`modules/` 里 `ingress_seq` 零命中 | 改为「只管执行权」；顺序是 Router 的**新建**能力 | §11.2 / 附录 B |
| **S5** | 严重 | X18（`copilot.py` 的 turn 编排）**没有删除落点** → 会永远停在「已弃用」 | 新增 **Stage 3b**（清理窗口 ≥7 天 + 指标归零后删除）；§11.4 改为「按 Stage 执行」 | §11.4 / §12 Stage 3b |
| **M1** | 中 | 复活语义矛盾：§4.2 有 `closed → open`，§3.4 却是「新建会话」 | **`closed` 定为终态**，复活 = 创建侧行为（新建会话），删掉 `closed → open` | §4.2 / §3.4 |
| **M2** | 中 | 架构测试规则 2（「`status` 赋值只能在 `state.py`」）会误杀 §4.4 / Router §4.2(c) 的放行 CAS | 改为「**裸赋值**只能在 `state.py`；放行 CAS 是状态机入口（`claim_turn()`）」 | §13.2 |
| **M3** | 中 | 执行权口径与 Router 方案相反（advisory lock + CAS ↔ CAS 是唯一权威） | 统一为「**CAS 是唯一权威**，advisory lock 仅作优化」 | §9 / §6 |
| **M4** | 中 | 验收第 8 项只列三类超时（sweeper 已是四类） | 补上 `session_inbox` 幂等键过期 | §13.1 |
| **M5** | 中 | `runner.py` 行数写 915，实测 **914**（三处） | 全部改为 914 | §1.1 / §11.2 / 附录 B |
| **M6** | 中 | 0035 的普通索引 `ix_agent_sessions_channel_session_key` 与新部分唯一索引**前导列不同**，非等价 | 加 grep 前置判断：有独立用途则保留，无则 0046 DROP / Stage 6 清理 | §10.2 第 4b 步 / Stage 6 |
| **L1** | 轻 | 代码块行号 `copilot.py:457-471` 偏早（`try` 在 464） | 改为 `464-471` | §1.2 |
| **L2** | 轻 | 把同步 `PostgresSaver.from_conn_string` 列为「可复用资产」，而 §5.3 说不能用 | 改标为**反例**，不计入资产 | §1.9 |
| **L3** | 轻 | §11.2 把 Gateway 的 **G1** 放进 Session 的删除清单 | 改为「**owner 是 Gateway**；本层只保证无残留调用方」 | §11.2 |
| **L4** | 轻 | §13.3 扫描规则表缺 X18 | 补上，并区分启用时点（X18 → Stage 3b，其余 → Stage 6） | §13.3 |

> **同步改动**：`implementation-plan.md` §3.3 / 附录 A / B、`cleanup-ledger.md`（X18 的停用与删除两列）、`README.md` §2 / §3.3 / §9.

### 本轮（v1.1 → v1.2）骨架重排

| # | 级别 | 问题 | 修正 | 落点 |
|---|---|---|---|---|
| **D1** | 严重 | **§5「Thread」实际承载了 §2 架构图里的第四个盒子** ——「唯一 turn 实现」「事件落库」「审批恢复」都埋在 Thread 章下，而它们是**全局关键路径**上被四个下游依赖的东西 | **§5.4–§5.6 提升为独立章**（§6 唯一 turn 实现 / §7 事件落库与 outbox / §8 审批中断与恢复），后续章顺延；§0.2 补第四子件「turn 执行器」；§2 架构图的「关键分工」同步 | §0.2 / §2 / §5 / §6 / §7 / §8 / §9–§15 |
| **D2** | 严重 | **`route_decision` 一列两写者**：Router 写 `RouteDecision`（会话入口策略决策），Agent 层也写同一列（每步专家选择）→ **后写覆盖先写**，Router 的可解释性留痕被冲掉 | **拆成两列**：0046 建 `route_decision`（**Router 唯一写者**）与 `agent_decision`（**Agent 写**） | §10.1 / §10.2 / §10.2.1 |
| **D3** | 严重 | **§9 边界表缺 `Gateway → Session` 行**，且冒出**悬空契约 `start_turn`**（`SessionManagerPort` 里没有这个方法，全文无定义） | 补 Gateway 行；`start_turn` 换成已定义的 `lookup` + `resolve_or_create` 两步 | §9 |
| **D4** | 严重 | **§9 的 `Session → Agent Loop` 契约与 Agent 决策 #4 冲突**：写着「含 messages、工具白名单」，但消息由 Context 装配、工具集来自 **agent 配置的绑定集** | 该行收窄为「**只有审批句柄**」，并在表里注明消息与工具的真实来源 | §9 |
| **D5** | 严重 | **§10.1 表终态漏 `session_inbox`** —— 该表归本层（Gateway 决策 #2b），且本层负责 sweeper 的第四类清扫 | §10.1 补一行，写明「**DDL 在 Gateway 0044，语义在本层**」| §10.1 |
| **D6** | 中 | **§9.1 假设 Gateway 会回传投递结果**，但 Gateway 方案**没有这条契约**（它只承诺「只读 `session_events`」）| 改为「**投递状态由 Session 自持**」；若要 Gateway 回传，需**先在 Gateway 方案补契约** | §9.1 |
| **D7** | 中 | **缺 §0.5 前置与下游依赖清单** —— §14 风险表写「已在 §0 与 README 记录依赖顺序」，但 §0 没有依赖表；而 Session 实际**阻塞四个下游**（Router 3 / Memory 3 / Agent 5 / Context 4）| 新增 §0.5：上游前置表 + **下游阻塞表** | §0.5 / §14 风险表 |
| **D8** | 轻 | **§1.9 的表格被段落截断** —— 「反例」那一行掉到引用块之后，Markdown 渲染成独立表 | 把该行移回表体，引用块移到表后 | §1.9 |
| **D9** | 轻 | **章节号顺延后，多处内部引用错位**（§5.3/§5.4/§5.5 等）| 逐条对照旧编号改正（§5.3 checkpoint 未变；§5.4→§6；§5.5→§7；§5.6→§8）| 全篇 |

> **同步改动**：`router-refactor-plan.md`（§6.2 / Stage 1 声明唯一写者）、`agent-refactor-plan.md`（§4.1 / §7.1 / Stage 4 改写 `agent_decision`）、`session-lifecycle-sequence.md`（§4 契约表补两列写者）、`implementation-plan.md`（A-24 / R-08 / S-02）、`README.md`（§3.3.2 表归属）。