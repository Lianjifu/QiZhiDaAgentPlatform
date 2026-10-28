# Router 层重构方案

> 版本：1.1（2026-10-29：按方案集统一更新——文档集入口、清理机制归属、阶段分期口径）
> 适用项目：`QiZhiDaAgentPlatform`
> 状态：**待评审**（附录 A 的 6 条决策待确认；#1 并发语义、#2 表选择会直接决定 Session 层方案的形态）
> 方案集入口：[`README.md`](README.md)
> 上位基线：[`session-lifecycle-sequence.md`](session-lifecycle-sequence.md) —— 本方案实现其中 **Router 泳道**
> 兄弟方案：[`gateway-refactor-plan.md`](gateway-refactor-plan.md)（已定稿）
> 收敛机制：[`cleanup-ledger.md`](cleanup-ledger.md) —— 本方案对应条目 **R1–R4**
> 硬约束：**最终态只有一个实现**；先上新、后清旧（清理机制见 §0.4 与台账）

---

## 0. 定位与范围

### 0.1 Router 在基线图上的位置

```
用户/渠道 → Gateway ──标准消息──▶ Router ──路由到会话──▶ Session ──▶ Context ──▶ …
```

### 0.2 两个子职责（按需求定义）

| 子件 | 职责 | 回答的问题 |
|---|---|---|
| **Strategy** | 路由策略：按业务线、按用户标签等 | **处理单元是哪个 agent？** |
| **Session Routing** | 将消息路由到正确的会话实例，保证同一用户/会话的消息**有序处理** | **处理单元是哪个会话？消息什么时候轮到？** |

合起来：**Router 决定一条消息流向哪个处理单元**。

> **处理单元** = (目标 agent, 目标会话实例, 入站序号)

### 0.3 Router 明确不做

| 不做 | 归属 |
|---|---|
| 协议解析、鉴权、幂等去重 | Gateway |
| 建会话 / 起轮次 / 执行 / 落库 | Session |
| 组装上下文、压缩、摘要 | Context |
| 召回与写入记忆 | Memory |
| **选模型 / 选工具** | **Agent Router**（见 §5.1，这是最易混的一处） |
| 判任务类型是否「深度任务」 | Agent Router（需要完整上下文，见 §5.2） |

### 0.4 实现收敛规则：最终态只有一个实现

**最终态**：任一职责在全仓只有一套实现承接。**推进方式**：先上新、后清旧——新实现接管并稳定运行后删除旧实现。

**清理机制统一由 [`cleanup-ledger.md`](cleanup-ledger.md) 管理**（弃用标记 → 调用打点 → 指标归零 → 删除 → 扫描脚本进 CI）。本方案涉及的条目：**R1–R4**，详见 §7.4。

> 为什么不写在同一次提交里一起删：新旧并存期可以用真实流量对照新旧行为，这是唯一可靠的验证方式；一次提交里同时上新 + 删旧，出问题时无法区分「新的错了」还是「旧的删早了」，且失去回退窗口。
>
> **代价要认**：清理完成后旧实现不复存在，回退需重新上线旧版本。

---

## 1. 现状盘点

### 1.1 现状的路由策略：几乎不存在

| 场景 | 现状 | 证据 |
|---|---|---|
| **Web Copilot** | 前端建会话时直接传 `agentId`，后端不判断 | `modules/agent_runtime/adapter/http/session_router.py:162`（`if not agent_id: 400`） |
| **IM 渠道** | **硬编码** `SYSTEM_AGENT_ID = 00000000-...-c0c1` | `modules/channel/adapter/dispatch/dispatch_subscriber.py:43` |
| **模型策略链** | 存在（`route_id` → `select_chain_for_strategy`），但只由前端 body 传入，且在 graph 内部生效 | `modules/agent_runtime/adapter/graph/chat_model.py:90` → `modules/model/application/services.py:980` |
| **task_kind 分类** | 旧路径**零实现**；只有新 runtime 有启发式 | `runtimes/agent_runtime/src/qzdap_agent_runtime/graph/routing.py:91` |
| **业务线 / 用户标签** | **无**。`catalog.py:274-281` 的 `category` 映射只是**前端展示文案**（「销售」→「销售支持」），不参与任何路由 | `modules/agent_runtime/src/qzdap/modules/agent_runtime/domain/catalog.py:274` |

> **结论**：现状的「路由」= 前端指定 agentId + 渠道硬编码 agentId。Strategy 是**从零新建**，不是改造。

### 1.2 现状的会话路由与有序性

| 场景 | 现状 | 证据 |
|---|---|---|
| **Web** | 会话 id 由前端持有 → 指向正确；但并发消息被**拒绝**（`try_claim` CAS → `SESSION_BUSY`），不是排队 | `modules/agent_runtime/adapter/persistence/repositories.py:85`；`application/copilot.py:225` |
| **IM 渠道** | **每条消息新建一个 session** → 完全无会话、无连续性、无顺序 | `modules/channel/adapter/dispatch/dispatch_subscriber.py:175-186` |
| **外部会话 → 会话实例映射** | `agent_sessions.channel_session_key` 列**已存在且有索引**，但**全仓无任何读写** | `adapter/persistence/models.py:80` |
| **跨 worker 顺序保证** | 无。无队列、无会话内序号、无 FIFO | — |
| **审批中断时的后续消息** | 无定义（旧路径 `try_claim` 会直接拒绝） | — |

### 1.3 现状的两个会话/turn 实现（Session Routing 的下游）

| 实现 | claim | 幂等 | 取消 | 审批 | 谁在用 |
|---|---|---|---|---|---|
| ① Copilot（`application/copilot.py` + `adapter/graph/runner.py`） | ✅ | ⚠️ | ✅ | ⚠️ 决策不落库 | 前端 Copilot 页 |
| ② use_cases（`application/use_cases/run_turn.py` + `run_turn_to_completion.py`） | ❌ | ❌ | ❌ | ❌ | 渠道入站、子代理、catalog 评测 |

**Router 的 Session Routing 必须建立在「只有一套 turn 实现」之上**——否则「有序处理」只对其中一条路径成立。这是本方案与 Session 层方案的强耦合点（§0.1 前置依赖）。

### 1.4 已有可复用资产

| 资产 | 位置 | 状态 |
|---|---|---|
| `agent_sessions.channel_session_key`（String 512，**已建索引**） | `adapter/persistence/models.py:80` | ✅ 表已建，**无人用** → 正是「外部会话 → 会话实例」的落点 |
| `admin_agents.visible_scope`（JSONB，默认 `["部门"]`） | `adapter/persistence/catalog_models.py` | ✅ 语义就是「哪些部门可见这个 agent」→ **用户标签路由的直接依据** |
| `admin_agents.category`（业务线） | 同上 | ✅ 业务线策略的依据 |
| `admin_agents.tags` / `profile` | 同上 | ✅ 标签与扩展策略配置 |
| `ActorContext.roles`（来自 JWT claims） | `libs/auth/src/qzdap_auth/dependencies.py:49` | ✅ 角色维度策略依据 |
| `build_session_key` | `runtimes/.../channels/gateway.py` | ✅ 可用 |
| `select_chain_for_strategy`（模型策略链） | `modules/model/application/services.py:980` | ✅ 真实现 → 归 Agent Router 调用 |
| `classify_task_kind_heuristic` | `runtimes/.../graph/routing.py:91` | ✅ 可用 → 归 Agent Router |
| `ErrorCode.SESSION_BUSY` / `REVISION_CONFLICT` | `libs/schema/.../errors.py:39` | ✅ 可用 |

### 1.5 缺口：用户标签没有一等公民

「按用户标签路由」需要能按**用户的部门 / 角色 / 画像**筛 agent，但现状：

- `identity` 的 `User` 实体只有 `id / email / display_name / metadata(JSONB 自由格式)`（`modules/identity/src/qzdap/modules/identity/domain/user.py:27`）——**部门等属性没有结构化字段**；
- `ActorContext.roles` 只有 JWT 里的 roles，**没有部门**；
- `admin_agents.visible_scope` 写的是「部门」，但**系统里没有可信的「用户属于哪些部门」数据源**。

> **结论**：Strategy 的「按用户标签路由」在数据源补齐前**只能靠 `visible_scope` 与 `ActorContext.roles` 的交集近似**，或依赖 `User.metadata` 里的自由格式约定。Router 方案需要显式引入一个 `UserDirectoryPort`（由 identity 模块提供），把「用户属性」变成可查询的数据，而不是散落的 JSONB。

---

## 2. 目标架构

```
InboundMessage（来自 Gateway）
   │
   ├─▶ ① Strategy ──────────────── 选 agent（处理单元的 agent 维度）
   │      输入：actor / channel_type / text / 已存在会话的绑定
   │      依据：显式指定 · 业务线(category) · 用户标签(visible_scope ∩ roles) · 兜底
   │      输出：AgentTarget{agent_id, agent_version, strategy_id, rule_version,
   │                       confidence, reason, candidates[]}
   │
   └─▶ ② Session Routing ───────── 选会话实例 + 保证有序
          2a. 会话 key 派生（tenant+workspace+channel+chat+user）
          2b. 映射到会话实例（channel_session_key → session_id），不存在则创建
          2c. 分配会话内单调序号 ingress_seq（原子）
          2d. 入队（status=queued）
          输出：SessionAssignment{session_id, agent_id, ingress_seq,
                                predecessor_seq, queue_position}
   │
   ▼
Session（执行）
```

**两个子件的关系**：Strategy 先定 agent（因为会话要绑定 agent），Session Routing 再定会话实例（会话沿用既有绑定）。

---

## 3. Strategy 设计

### 3.1 决策链（优先级从高到低）

| 优先级 | 规则 | 依据 | 备注 |
|---|---|---|---|
| 1 | **会话粘性** | 目标会话已存在 → 沿用其 `agent_id` / `agent_version` | 只在会话已存在时生效。会话中途换 agent 会让历史上下文的解释方式突变 |
| 2 | **显式指定** | `InboundMessage` 携带 `agent_id` | Web 场景前端建会话时选定 |
| 3 | **业务线策略** | `category` 命中 + `status='published'` | 渠道/工作区/业务线 → agent |
| 4 | **用户标签策略** | `visible_scope` ∩ 用户属性非空，且 `status='published'` | 依赖 `UserDirectoryPort`（§1.5） |
| 5 | **兜底默认 agent** | 工作区配置的默认 agent | 无匹配时的安全兜底 |

**规则 1 与 2 的关系**：会话已存在时，粘性**压过**显式指定。此时决策记录里必须留痕（`reason="sticky_session_binding"`, `overridden_agent_id=...`），否则用户「换个 agent 重新问」会发现没生效。

**兜底必须安全**：命中不了任何规则时，走默认 agent，**不得**因为路由失败而丢消息。

### 3.2 `RouteDecision`（输出契约）

```python
@dataclass(frozen=True, slots=True)
class RouteDecision:
    agent_id: UUID
    agent_version: str
    strategy_id: str                  # 命中的策略标识
    rule_version: str                 # 策略规则版本（回放/评估用）
    confidence: float                 # 0..1
    reason: str                       # 人类可读原因
    candidates: tuple[AgentCandidate, ...]   # 落选候选 + 各自得分
    model_hint: str | None = None     # 给 Agent Router 的模型偏好（不强制）
    source: Literal["sticky", "explicit", "business_line", "user_tag", "fallback"]
```

**为什么必须落 `candidates` / `confidence` / `rule_version`**：路由决策是「可评估的」——上线后要能回答「这条消息为什么走了这个 agent」「改了策略规则后命中分布变了没有」。没有这些字段，策略调优只能靠猜。

### 3.3 策略配置的落点：**不新建策略表**

复用 `admin_agents` 已有字段：

| 策略维度 | 落点 | 说明 |
|---|---|---|
| 业务线 | `admin_agents.category` | 已是业务线语义 |
| 用户可见范围 | `admin_agents.visible_scope` | 已是「部门」语义 |
| 标签 | `admin_agents.tags` | 已有 |
| 扩展配置（策略偏好、模型偏好、场景） | `admin_agents.profile`（JSONB） | 已存在，无需 DDL |
| 默认 agent / 业务线→agent 映射 | `profile` 或工作区级配置 | 见 §6.3 的决策点 |

> **不新建策略表**是刻意的：策略是**agent 的属性**，不是独立实体。新建 `routing_rules` 表会带来「策略与 agent 两套真相」——正是我们要消灭的那类重复。

### 3.4 可解释性与评估

- 每次路由产出 `RouteDecision`，随 turn 落库（见 §6.2）；
- 评估指标：**误路由率**（事后人工/评测集标注）、**兜底命中率**（落 fallback 的比例，突增说明策略覆盖不足）、**候选首位命中率**（candidates[0] 与最终选中的偏差）。

---

## 4. Session Routing 设计

### 4.1 会话 key 派生与映射

**会话 key**（稳定、可跨 worker 计算）：

```
session_key = sha256(
    tenant_id | workspace_id | channel_type | channel_id | external_chat_id | external_user_id
)
```

> 沿用 `runtimes/.../channels/gateway.py` 的 `build_session_key` 语义，但**存哈希而非冒号拼接**——`agent_sessions.channel_session_key` 是 String(512)，哈希定长且不含分隔符歧义。

**映射**：`(tenant_id, channel_session_key)` → `session_id`

- 复用 `agent_sessions.channel_session_key` 列（**已存在、已建索引、无人使用**）；
- **需要新增唯一约束** `(tenant_id, channel_session_key)`——否则并发首条消息会建出两个会话；
- 查不到 → 创建会话（绑定 Strategy 选出的 agent）。

> **web 场景**：前端先 `POST /api/sessions` 建会话再发消息，web 的 `external_chat_id` = session_id。因此 web 走「**会话已存在 → 粘性**」路径，不走 channel_session_key 映射。

### 4.2 有序处理：三个机制

#### (a) 序号分配（会话内单调、原子）

```sql
UPDATE agent_sessions
   SET next_ingress_seq = next_ingress_seq + 1
 WHERE id = :session_id
RETURNING next_ingress_seq;
```

`next_ingress_seq` 是**新增列**（Integer，默认 0）。分配是原子的，跨 worker 有效。

#### (b) 入队

消息落成一行 `status='queued'` 的 turn，携带 `ingress_seq`。

#### (c) 放行规则（FIFO）

一个 turn 允许开始执行，当且仅当：

```
turn.ingress_seq == session.last_completed_seq + 1
AND 该会话当前没有正在执行的 turn
```

「没有正在执行的 turn」用会话级 advisory lock 保证：

```sql
SELECT pg_try_advisory_xact_lock(hashtext('session:' || :session_id))
```

- 拿到锁 → 该会话当前归我 → 检查 FIFO 条件 → 执行；
- 没拿到 → 别的 worker 正在处理这个会话 → 本轮**排队等待**（不报错）。

> **跨会话并行**：advisory lock 按 session_id 粒度，不同会话互不阻塞。

### 4.3 「有序」的准确边界

必须说清楚，否则会实现出错误的语义：

| 情形 | 是否受 FIFO 约束 | 说明 |
|---|---|---|
| 同一会话的连续消息 | ✅ 严格按 `ingress_seq` | 本节的核心保证 |
| 不同会话的消息 | ❌ 不约束 | 并行处理 |
| 同一用户、不同会话 | ❌ 不约束 | 用户可以同时开多个会话 |
| **审批中断中的 turn** | ⚠️ **不占用执行位** | 见下 |
| 被幂等判重的重复消息 | — | 在 Gateway 就短路了，不进队列 |

**审批中断的处理**（重要）：

审批等待中的 turn 状态是 `waiting_approval`，**不是 `running`**。它**不持有 advisory lock**（lock 在 turn 完成时释放）。因此：

- 用户在等待审批时发的**新消息**可以立即入队并执行（不会被审批卡住）；
- 但**审批恢复的那一轮**必须与同一会话的其他执行互斥；
- 审批恢复的 turn **不参与 `ingress_seq` 的 FIFO 排队**——它是「挂起轮的延续」，不是新消息。

> **这是「有序」的一个例外，必须在方案里显式承认**，否则会出现「等审批 → 后续消息全部堵死」的死锁。

### 4.4 与 Gateway 幂等的分工

| 关注点 | 归属 | 机制 |
|---|---|---|
| 同一条消息投递两次 | **Gateway** | `session_inbox` 原子 claim（幂等键） |
| 同一会话的多条**不同**消息的先后 | **Router** | `ingress_seq` + FIFO |
| 同一会话同时只能跑一轮 | **Session** | 会话级 advisory lock（执行权） |

三者是**互补**的，不是重复：幂等防「同一条」，有序防「不同条的乱序」，互斥防「同时跑」。

### 4.5 并发消息的语义：排队 vs 拒绝（决策点）

现状是**拒绝**（`try_claim` 失败 → `SESSION_BUSY` → HTTP 409）。需求是「保证有序处理」→ 应为**排队**。但语义变化会影响前端契约：

| 方案 | 行为 | 代价 |
|---|---|---|
| **S1 严格排队**（推荐） | 第二条等第一条完成后再跑 | 需要新增「排队中」的前端信号；队列积压需超时/丢弃策略 |
| S2 拒绝（现状） | 返回 409 `SESSION_BUSY` | 用户连发两条要手动重试；与「有序处理」需求不符 |
| S3 合并 | 短窗口内多条消息合并成一轮 | 语义复杂，用户预期难对齐 |

**S1 的配套要求**：

1. **前端需要知道「在排队」**。当前 16 种 `TurnChunk` 里**没有 `queued` 类型** → 需要新增 `QueuedChunk`（含 `position` / `waited_ms`），否则前端只能转圈直到首 chunk 到达。
2. **队列上限与超时**：单会话排队上限（建议 N 条）与最长等待时间（建议 T 秒），超限则返回明确错误码（`ErrorCode` 需新增，如 `QUEUE_FULL` / `QUEUE_TIMEOUT`），**不得静默丢弃**。

> 这两条是 S1 相对 S2 的**额外成本**，也是决策 #1 的连带义务。

---

## 5. 四个必须澄清的边界

### 5.1 Strategy 选 agent ≠ Agent Router 选模型/工具

| | Router.Strategy | Agent Router（基线图） |
|---|---|---|
| 时机 | **入站时**（拿到标准消息后立刻） | **Agent Loop 内**，每一步推理之后 |
| 决定 | **哪个 agent**（处理单元） | **哪个模型 / 调哪个工具** |
| 依据 | 业务线、用户标签、显式指定、会话粘性 | 推理意图、工具白名单、模型可用性、预算 |
| 上下文依赖 | **不需要**完整上下文 | 需要 |

> **推论**：v3.1 里放在 `route` 节点的「模型策略链选择」与「深度任务判定」**不属于本层**，应归 Agent Router。Router 层最多给一个 `model_hint`（偏好，不强制）。

### 5.2 `deep_task` 判定不在 Strategy

v3.1 §5.5 的启用规则依赖「消息数 > 20」「工具数 > 5」等**完整上下文信息**——入站时拿不到。→ 归 Agent Router。

### 5.3 Router 的 `ingress_seq` ≠ Session 的 `revision`

| | `ingress_seq` | `revision`（`agent_sessions.current_revision`，**列已存在但旧路径从不使用**） |
|---|---|---|
| 含义 | 消息在会话内的**到达序号** | 会话状态的**版本号**（乐观并发） |
| 归属 | Router | Session |
| 用途 | 排序 | 并发修改检测（`REVISION_CONFLICT`） |

两者都会单调递增但**语义不同**，不可复用同一列。

### 5.4 Router 的排队 ≠ Session 的 claim

- **Router** 管「**什么时候轮到**」（FIFO 顺序）；
- **Session** 管「**能不能执行**」（执行权、幂等、取消、审批）。

旧路径的 `try_claim` 二者混在一起（一个 CAS 同时管顺序和执行权）→ 拆分后 `try_claim` 的「顺序」语义归 Router，「执行权」语义归 Session。

---

## 6. 数据与表

### 6.1 表选择：这是一个必须先拍板的决策

现状有两套并存的表：

| 旧表（在用，有数据） | 新表（迁移 0035 已建，无人用） |
|---|---|
| `agent_sessions` | `session_turns`（含 `idempotency_key` / `expected_revision` / `agent_version` / `cost_usd`） |
| `agent_turns` | `session_messages` |
| `agent_session_messages` | `session_events` |

新表多了幂等键、乐观并发、agent 版本冻结、成本——**这些正是 Router 与 Session 需要的字段**（旧表没有）。

> **决策 #2**：启用新表 `session_turns` / `session_messages` / `session_events`，旧表 `agent_turns` / `agent_session_messages` 在切换时**迁数据后废弃**。理由：新表是 Gateway 方案 §9 已定的目标形态，两层用同一套表才不产生第二套真相。
>
> 影响：`agent_sessions` 是否也换成新表？Gateway 方案 §9 已定「`agent_sessions` 保留」。本方案沿用 `agent_sessions` 作为会话主表，只在其上加列。

### 6.2 Router 需要的状态落点

| 状态 | 落点 | 动作 |
|---|---|---|
| 外部会话 → 会话实例映射 | `agent_sessions.channel_session_key`（**已存在**） | 启用 + 加唯一约束 `(tenant_id, channel_session_key)` |
| 会话内入站序号 | `agent_sessions.next_ingress_seq`（**新增列**） | `Integer NOT NULL DEFAULT 0` |
| 排队中的消息 | `session_turns`（`status='queued'` + `ingress_seq`） | 启用新表 |
| 路由决策留痕 | `session_turns` 新增 `route_decision`（JSONB） | 记录 `RouteDecision` |
| 用户属性 | `identity` 的 `User.metadata` + 新增 `UserDirectoryPort` | 结构化字段待补（§1.5） |

### 6.3 迁移草案（0041）

```sql
-- migrations/versions/0041_router_session_routing.py

-- 1) agent_sessions：外部会话映射唯一化 + 入站序号
ALTER TABLE agent_sessions
    ADD COLUMN next_ingress_seq Integer NOT NULL DEFAULT 0;

CREATE UNIQUE INDEX uq_agent_sessions_channel_key
    ON agent_sessions (tenant_id, channel_session_key)
    WHERE channel_session_key IS NOT NULL;      -- 部分唯一索引：web 会话无 key

-- 2) session_turns：排队 + 序号 + 路由留痕
ALTER TABLE session_turns
    ADD COLUMN ingress_seq      Integer,
    ADD COLUMN route_decision   JSONB;

CREATE UNIQUE INDEX uq_session_turns_session_ingress
    ON session_turns (session_id, ingress_seq)
    WHERE ingress_seq IS NOT NULL;

ALTER TABLE session_turns
    ADD CONSTRAINT ck_session_turns_status
    CHECK (status IN ('queued','running','waiting_approval','succeeded','failed','cancelled'));
```

### 6.4 默认 agent 与业务线映射的配置落点

两个候选：

- `admin_agents.profile`（JSONB，已存在）里放「默认 agent 标记」与「业务线→agent 优先级」；
- 工作区级配置（`admin_ops` 的 collection 机制）。

> **决策 #3**：放 `admin_agents.profile`——策略是 agent 的属性，与 §3.3 的「不新建策略表」一致。

---

## 7. 逐文件改造与删除清单

### 7.1 新增（`backend/runtimes/agent_runtime/src/qzdap_agent_runtime/router/`）

| 文件 | 内容 |
|---|---|
| `types.py` | `RouteDecision` / `AgentTarget` / `AgentCandidate` / `SessionAssignment` |
| `strategy.py` | `Strategy` Protocol + 规则链实现 + `RouteDecision` 留痕 |
| `session_router.py` | 会话 key 派生 · 映射与创建 · `ingress_seq` 分配 · 入队 |
| `sequencer.py` | `SessionSequencer` Protocol + FIFO 放行判定 + advisory lock 端口 |

### 7.2 迁移

| 旧位置 | 迁到 | 动作 |
|---|---|---|
| `modules/channel/adapter/dispatch/dispatch_subscriber.py:43,175-186` 硬编码 agent + 每消息建 session | `router/strategy.py` + `router/session_router.py` | **删除**，改走 Strategy + 会话映射 |
| `modules/agent_runtime/adapter/http/session_router.py:162` `agentId` 直取 | `router/strategy.py` | 改为「显式指定」规则，优先级 2 |
| `modules/agent_runtime/adapter/persistence/repositories.py:85-108` `try_claim` | 拆成 Router（FIFO）+ Session（执行权） | 改造 |
| `runtimes/.../channels/gateway.py` `build_session_key` | `router/session_router.py` | 改为哈希版 |
| `runtimes/.../graph/routing.py:91` `classify_task_kind_heuristic` | `agent_router`（**不属本层**） | 迁出，Router 只留 `model_hint` |

### 7.3 保留但改造

| 文件 | 改造点 |
|---|---|
| `modules/agent_runtime/adapter/persistence/models.py` | `agent_sessions` 加 `next_ingress_seq`；`channel_session_key` 加部分唯一索引 |
| `modules/agent_runtime/adapter/persistence/catalog_models.py` | `admin_agents` 无需 DDL（策略走已有字段） |
| `modules/model/application/services.py:980` `select_chain_for_strategy` | **保留**，但调用方从 graph 移到 Agent Router |

### 7.4 删除清单（Stage 4 停用 + 打点 → Stage 5 删除）

| 类别 | 具体 |
|---|---|
| 硬编码路由 | `dispatch_subscriber.py` 的 `SYSTEM_AGENT_ID` / `SYSTEM_USER_ID` |
| 每消息建会话 | `dispatch_subscriber.py:175-186` 的临时 session 创建 |
| 进程内去重 | `dispatch_subscriber.py` 的 `OrderedDict` LRU（Gateway 方案已列） |
| 旧的顺序语义 | `try_claim` 中混在一起的「顺序」职责 → 拆到 Router |
| 展示用 category 映射 | `catalog.py:274-281`（若策略改用 `category` 原值，需同步改展示层） |

---

## 8. 实施阶段

> 每阶段验收都含「**旧代码减少了什么**」。

### Stage 0：契约与配置（不改行为）

| 动作 | 细节 |
|---|---|
| 建 `router/` 骨架 + `types.py` | 4 个类型定稿 |
| 迁移 0041 | `next_ingress_seq` + 唯一索引 + `session_turns` 加列 |
| 策略配置规范 | `admin_agents.profile` 的路由配置 schema（文档化，不强制） |
| `UserDirectoryPort` 契约 | 定义在 router 侧，实现在 identity 侧 |

**旧代码减少**：无（纯新增）。
**验收**：类型有单测；迁移在 dev 库跑通。

### Stage 1：Strategy 落地（web 路径先行）

| 动作 | 细节 |
|---|---|
| 规则链实现 | 粘性 > 显式 > 业务线 > 用户标签 > 兜底 |
| `RouteDecision` 留痕 | 写入 `session_turns.route_decision` |
| web 建会话改走 Strategy | `session_router.py:162` → Strategy |

**旧代码减少**：`agentId` 直取逻辑收进 Strategy 规则。
**验收**：兜底命中率可查；显式指定与策略冲突时按粘性规则并留痕。

### Stage 2：Session Routing 落地（IM 路径）

| 动作 | 细节 |
|---|---|
| 会话 key 派生 + 映射 | 启用 `channel_session_key` + 唯一索引 |
| 会话创建/复用 | IM 首条消息建会话并绑定 Strategy 的 agent |
| `ingress_seq` 分配 + 入队 | 新增列 + `session_turns.status='queued'` |
| **删除** IM 临时 session 创建 | `dispatch_subscriber.py:175-186` |

**旧代码减少**：每消息建会话的行为消失。
**验收**：同一飞书群连续 3 条消息 → **同一个 session_id**；跨 worker 一致。

### Stage 3：有序处理落地

| 动作 | 细节 |
|---|---|
| FIFO 放行判定 | `ingress_seq == last_completed_seq + 1` |
| 会话级 advisory lock | `pg_try_advisory_xact_lock` |
| 审批中断不占执行位 | 状态机区分 `waiting_approval` 与 `running` |
| 并发语义切换 | 从「拒绝 SESSION_BUSY」改为「排队」 |

**旧代码减少**：`try_claim` 的顺序职责移除。
**验收**：并发 5 条同会话消息 → **按入站顺序执行**，不丢不乱；不同会话并行不互相阻塞；审批等待期间新消息可执行。

### Stage 4：新实现接管与弃用

> **本阶段只上新，不删旧**。旧实现打 `@deprecated` + 调用打点（`qzdap_legacy_calls_total{path="..."}`），进入清理窗口。清理机制见 [`cleanup-ledger.md`](cleanup-ledger.md) R1–R4。

| 动作 | 细节 |
|---|---|
| 渠道入站改走 Strategy + Session Routing | IM 消息不再硬编码 agent、不再建临时 session |
| `dispatch_subscriber.py` | **停用**（打弃用标记 + 打点），不立即删 |
| 第二套 turn 实现 | **停用**（打弃用标记 + 打点）；合并是 Session 层的主战场，Router 侧只配合 |
| 更新 [`cleanup-ledger.md`](cleanup-ledger.md) R1–R4 状态 | → 已弃用 |

**旧代码减少**：无删除，但 R1–R4 全部进入弃用与观测状态。
**验收**：§10 全部检查项通过；旧路径调用指标归零。

### Stage 5：旧实现清理

> **进入条件（硬性）**：R1–R4 的调用指标**归零**且**已稳定运行 ≥ 1 个发布周期**。

| 动作 | 细节 |
|---|---|
| 删 `dispatch_subscriber.py` | 渠道不再绕道 EventBus + 第二套 turn |
| 删第二套 turn 实现 | `use_cases/run_turn.py` + `run_turn_to_completion.py` 与 `copilot.py` 合一（**Session 层方案的主战场**） |
| 删 `build_session_key` 冒号拼接版 | 台账 R4 |
| 启用扫描脚本的 Router 段 | 进 CI |
| 更新台账状态 | R1–R4 → 已清理 |
| 更新 `docs/copilot-chat-module-architecture.md` | 现状文档同步 |

**旧代码减少**：§7.4 删除清单**归零**。
**验收**：§10 全部检查项通过；台账 Router 域条目全部「已清理」。

### 阶段与「旧代码减少」对照

| 阶段 | 删除/替换 | 量级 | 旧路径状态 |
|---|---|---|---|
| Stage 1 | `agentId` 直取 | ~10 行 | 直接替换（无残留调用方） |
| Stage 2 | IM 临时 session 创建 + 硬编码 agent | ~40 行 | 直接替换 |
| Stage 3 | `try_claim` 顺序职责 | ~20 行 | 直接替换 |
| Stage 4 | — | 0 | **停用 + 打点**（进入清理窗口） |
| Stage 5 | `dispatch_subscriber.py` + 第二套 turn 实现 + `build_session_key` | **~290 行** | 删除（台账清零） |

---

## 9. 与相邻层的接口

| 方向 | 契约 |
|---|---|
| Gateway → Router | `InboundMessage`（含 `actor` / `channel_type` / `external_chat_id` / `external_user_id` / `text` / `idempotency` / 附件） |
| Router → Session | `SessionAssignment{session_id, agent_id, agent_version, ingress_seq, predecessor_seq, queue_position}` + `RouteDecision`（留痕用） |
| Router ← Agent Catalog | `AgentCatalogService`（已有）→ 提供 `category` / `visible_scope` / `tags` / `profile` / `version` |
| Router ← Identity | `UserDirectoryPort`（新增）→ 用户属性 |
| Router ← Model | **不调用**；模型策略链归 Agent Router |

---

## 10. 验收标准

1. **路由正确性**：5 类入口 × 3 类策略来源 → 命中的 agent 符合规则链，且 `RouteDecision` 完整留痕；
2. **粘性**：同一会话内 Strategy 始终返回同一 agent，即使策略配置在会话中途变化；
3. **会话稳定性**：同一 IM 群连续 3 条消息 → 同一个 `session_id`；
4. **严格有序**：并发 5 条同会话消息 → 执行顺序 == 入站顺序，无丢失、无乱序；
5. **跨会话并行**：N 个会话并发 → 互不阻塞；
6. **审批不阻塞**：审批等待期间发新消息 → 新消息正常执行；
7. **跨 worker 一致**：两个 worker 分别处理同一会话的不同消息 → 顺序仍然正确；
8. **兜底安全**：无任何策略命中 → 走默认 agent，**消息不丢**；
9. **可解释**：`route_decision` 可查询，能回答「为什么是这个 agent」；
10. **架构测试**：Router 层不得 import FastAPI / SQLAlchemy（与 Gateway 方案同一条规则）。

---

## 11. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| **并发语义从「拒绝」改为「排队」** | 前端契约变化（需 `queued` 事件）；用户预期变化 | 决策 #1 明确取舍；新增 `QueuedChunk`；队列上限与超时显式化 |
| **「唯一 turn 实现」未先落地** | Router 的有序性只对一条路径成立 | §0.1 前置依赖：Session 层方案先落地；否则 Stage 3 不得开启 |
| **表选择未定** | Router 落 `session_turns` 还是 `agent_turns` | 决策 #2；两表并存即第二套真相 |
| 用户标签无结构化数据源 | 「按用户标签路由」只能近似 | §1.5；`UserDirectoryPort` 契约先行；不做大范围 identity 改造 |
| `channel_session_key` 唯一约束加不上 | 并发首条消息可能建两个会话 | 部分唯一索引 + 冲突后重查 |
| advisory lock 依赖 Postgres | 多副本部署需共享 DB | 现状已是共享 Postgres；不引入 Redis |

---

## 附录 A：待确认的决策

| # | 决策 | 本方案建议 | 备选 | 影响 |
|---|---|---|---|---|
| 1 | 并发消息语义 | **S1 严格排队**（FIFO） | S2 拒绝（现状）/ S3 合并 | 前端契约、用户体验、工作量 |
| 2 | 表选择 | **启用新表** `session_turns` / `session_messages`，旧 `agent_turns` / `agent_session_messages` 迁数据后废弃 | 沿用旧表（缺幂等键/revision/版本冻结字段） | 与 Gateway 方案 §9 一致性 |
| 3 | 默认 agent / 业务线映射的配置落点 | **`admin_agents.profile`**（不新建策略表） | 工作区级配置 / 新建 `routing_rules` 表 | 配置模型 |
| 4 | 深度任务判定与模型链选择 | **不在本层**，归 Agent Router | 放 Strategy（但入站拿不到上下文） | 与基线图的一致性 |
| 5 | `ingress_seq` 分配方式 | **会话行原子自增**（`next_ingress_seq` 列） | 全局序列 / 分布式锁 | 跨 worker 正确性 |
| 6 | 审批中断是否占用 FIFO 执行位 | **不占用**（等待审批不阻塞新消息） | 占用（严格全局有序，但会堵死） | 死锁风险 |

---

## 附录 B：与 Gateway 方案的分工（避免重复）

| 关注点 | Gateway | Router |
|---|---|---|
| 协议解析、鉴权、归一化 | ✅ | — |
| 重复消息识别 | ✅（`session_inbox` 幂等键） | — |
| 选 agent | — | ✅ **Strategy** |
| 选会话实例 | — | ✅ **Session Routing** |
| 同一会话的先后顺序 | — | ✅ **`ingress_seq` + FIFO** |
| 同一会话同时只能跑一轮 | — | 只提供 advisory lock 端口，**执行权归 Session** |
| 渠道回包 | ✅ | — |
