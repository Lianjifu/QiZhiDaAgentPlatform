# Router 层重构方案

> 版本：1.6（2026-10-31：**Stage 2 + Stage 3 已落地** —— **IM 也走规则链** ✓（台账 **R19** ✓）+ **同会话 FIFO 排队** ✓（`session/queue.py` + `PostgresTurnQueue` ✓ —— 序号分配 / 入队 / 放行 / 兜底 / 上限 / 超时 ✓）；**Session 层的两道门已开** ✓ —— 见 §13.6）｜ 1.5（2026-10-29：**Stage 2 的会话 key 派生已落地** —— 哈希版 `derive_session_key`（6 维，含 `channel_type`）+ **旧的冒号拼接版删除**（台账 **R4 已清理**）；⚠️ **Stage 2 的主体（Session Routing / IM 路径）与 Stage 3（FIFO）仍被 Session 层硬阻塞** —— 见 §13.5）｜ 1.4（2026-10-29：**Stage 0 + Stage 1 已落地** —— 规则链 + `RouteDecision` 留痕 + web 建会话改走 Strategy（台账 **R2 已清理**）；实施结果与偏差见 **§13**）｜ 1.3（2026-10-29：**独立审查后的 15 项修正** —— `try_claim` 的顺序职责更正、架构测试规则白名单化、粘性规则的两步流程、`last_completed_seq` 的兜底路径、互斥原语口径统一、错误码收敛、扫描规则补全、迁移回滚口径 —— **+ 按 D1 重排骨架**：新增 §0.2 前提、§5.1 改两轴对照、删 `model_hint`、附录 C 记重排）
> 适用项目：`QiZhiDaAgentPlatform`
> 状态：**Stage 0 → Stage 3 已执行**（2026-10-31；§13）—— 台账 **R1–R4 全「已清理」** ✓；**剩下的只有 Stage 4 的接管打点与 Stage 5 的归零核验** ✓（本层的旧实现已随 Session / Agent 层一并退役 ✓ —— 无待清理条目 ✓）
> 方案集入口：[`README.md`](README.md)
> 上位基线：[`session-lifecycle-sequence.md`](session-lifecycle-sequence.md) —— 本方案实现其中 **Router 泳道**
> 兄弟方案：[`gateway-refactor-plan.md`](gateway-refactor-plan.md)（已定稿）
> 收敛机制：[`cleanup-ledger.md`](cleanup-ledger.md) —— 本方案对应条目 **R1–R4**
> 硬约束：**最终态只有一个实现**；先上新、后清旧（清理机制见 §0.5 与台账）
> 方案集导航：落地路线与里程碑见 [`README.md`](README.md) §6 · 系统级验收见 §7 · 外部前置依赖见 §8 · 跨层不变量见 [`session-lifecycle-sequence.md`](session-lifecycle-sequence.md) §6

---

## 0. 定位与范围

### 0.1 Router 在基线图上的位置

```
用户/渠道 → Gateway ──标准消息──▶ Router ──路由到会话──▶ Session ──▶ Context ──▶ …
```

### 0.2 本层的前提：入口一次、每步一次、配置轴不归本层

**读这一节就够理解 Router 层了** —— 三句话：

| # | 前提 | 含义 |
|---|---|---|
| 1 | **Router 的选择只有一次** —— 在**会话入口**（收到第一条消息时）| 选哪个 agent、路由到哪个会话。它决定的是**整个会话**的绑定 |
| 2 | **每步的选择归 Agent 层** —— ⑧ Agent Router 在循环内每步选**专家 Agent** | 两者的层级不同、互不替代（§5.1 有对照表）|
| 3 | **模型与工具不在本层，也不在任何一层的「选择」里** | 它们由管理员在 **agent 配置**里绑定，运行时**查表取值**（Agent 决策 #4）。⚠️ **本层不产出任何模型 / 工具信号** |

> **两条轴**（Agent 层方案 §0.2）：**执行轴**（每步推理）与**配置轴**（管理员配置 → agent 绑定 → 运行时取值）。Router 位于**执行轴的入口一次**，**完全不在配置轴上** —— 这就是为什么它不选模型、不选工具。

### 0.3 两个子职责（按需求定义）

| 子件 | 职责 | 回答的问题 |
|---|---|---|
| **Strategy** | 路由策略：按业务线、按用户标签等 | **处理单元是哪个 agent？** |
| **Session Routing** | 将消息路由到正确的会话实例，保证同一用户/会话的消息**有序处理** | **处理单元是哪个会话？消息什么时候轮到？** |

合起来：**Router 决定一条消息流向哪个处理单元**。

> **处理单元** = (目标 agent, 目标会话实例, 入站序号)

### 0.4 Router 明确不做

| 不做 | 归属 |
|---|---|
| 协议解析、鉴权、幂等去重 | Gateway |
| 建会话 / 起轮次 / 执行 / 落库 | Session |
| 组装上下文、压缩、摘要 | Context |
| 召回与写入记忆 | Memory |
| **模型 / 工具的绑定与取值**（⚠️ **不是选择** —— 管理员在 agent 配置里绑定，运行时查表；Agent 决策 #4） | **Agent 层 Execution**（见 §5.1，这是最易混的一处） |
| **产出模型 / 工具偏好信号** | ❌ **本层不产出** —— D1 之后没有「运行时挑模型 / 挑工具」这件事，任何「模型偏好」字段都没有消费方 |
| 判任务类型是否「深度任务」 | **Agent 层**（需要完整上下文，见 §5.2） |
| **会话级配额**（每会话并发轮次上限、租户级会话数上限） | ✅ **属本层**（§12.1）—— 但**只读**会话表，不写（与决策 #10 一致） |

### 0.5 实现收敛规则：最终态只有一个实现

**最终态**：任一职责在全仓只有一套实现承接。**推进方式**：先上新、后清旧——新实现接管并稳定运行后删除旧实现。

**清理机制统一由 [`cleanup-ledger.md`](cleanup-ledger.md) 管理**（弃用标记 → 调用打点 → 指标归零 → 删除 → 扫描脚本进 CI）。本方案涉及的条目：**R1–R4**，详见 §7.4。

> 为什么不写在同一次提交里一起删：新旧并存期可以用真实流量对照新旧行为，这是唯一可靠的验证方式；一次提交里同时上新 + 删旧，出问题时无法区分「新的错了」还是「旧的删早了」，且失去回退窗口。
>
> **代价要认**：清理完成后旧实现不复存在，回退需重新上线旧版本。

### 0.6 前置依赖清单（**本方案的哪些阶段被别的方案挡住**）

| 本方案阶段 | 前置 | 前置归属 | 阻塞性质 | 不满足时 |
|---|---|---|---|---|
| **Stage 0** | 表选择决策（Router #2 = Session #5） | 跨方案（§ README 3.4） | 契约 | 迁移 0045 无法定稿 |
| **Stage 0** | `ErrorCode` 增 `QUEUE_FULL` / `QUEUE_TIMEOUT` | 本方案 | — | 排队超限无处表达 |
| **Stage 1** | `InboundMessage` 定稿 | Gateway 方案 | 契约 | 无法消费标准消息 |
| **Stage 1** | `session_turns.route_decision` 列存在（`RouteDecision` 留痕要写它） | Session 方案（迁移 0046） | **DDL** | 无法留痕 |
| **Stage 2** | `session_turns.status` 含 `queued` | Session 方案（迁移 0046） | **DDL** | 无法入队 |
| **Stage 3** | **Session 层的唯一 turn 实现落地**（Session Stage 3） | Session 方案 | **语义（硬）** | 有序性只对一条路径成立 → **不得开启** |
| **Stage 3** | 会话级互斥原语（advisory lock 或轮次表 CAS） | 本方案 + Session | 实现 | 无 |

> **Stage 3 是本方案唯一被硬阻塞的阶段**。Session 层方案未落地「唯一 turn 实现」之前，Router 的 FIFO 排队没有意义 —— 因为另一条路径（渠道 / 子代理 / 评测）仍然可以绕过队列并发执行。**这与 2026-10-15 那次的失败是同一个形状：只建一半。**

### 0.7 排队语义的前端契约（**破坏性变更，必须有契约与开关**）

「并发消息从『拒绝 409』改为『排队』」是**前端可见的行为变更**：

| | 现状 | 改后 |
|---|---|---|
| 用户连发两条 | 第二条收到 409 `SESSION_BUSY`，前端提示「上一轮还在跑」 | 第二条**排队**，等第一轮完成后自动执行 |
| 前端表现 | 错误提示 | **需要展示「排队中」** |

**需要新增的 chunk**：当前 **17** 种 `TurnChunk` 里**没有 `queued` 类型**（`libs/schema/src/qzdap_schema/dtos/turn.py`，实测 17 个 `*Chunk` 类）→ 需新增 `QueuedChunk`（含 `position` / `waited_ms` / `estimated_wait_seconds`），否则前端只能一直转圈到首 chunk 到达。

**灰度开关**：排队语义是**破坏性契约变更**，需要一个开关：

| 项 | 决定 |
|---|---|
| 开关 | `QZDAP_ROUTER_QUEUE_ENABLED`（默认 **off**，先按现状「拒绝」跑，观察后再开） |
| 位置 | Router 层（L2），读环境变量 |
| 前端 | `QueuedChunk` 与 409 两种表现**都要支持**（前端先上线兼容，再开开关） |
| 灰度顺序 | 前端兼容 → 后端开关上线（默认 off）→ 观察 → 开 |

> **回滚**：开关关掉即回到「拒绝」语义 —— 这是本层唯一的、**成本最低的回滚手段**，比「回退需重新上线旧版本」好得多。

---

## 1. 现状盘点

### 1.1 现状的路由策略：几乎不存在

| 场景 | 现状 | 证据 |
|---|---|---|
| **Web Copilot** | 前端建会话时直接传 `agentId`，后端不判断 | `modules/agent_runtime/adapter/http/session_router.py:162`（`if not agent_id: 400`） |
| **IM 渠道** | **硬编码** `SYSTEM_AGENT_ID = 00000000-...-c0c1` | `modules/channel/adapter/dispatch/dispatch_subscriber.py:43` |
| **模型策略链** | 存在（`route_id` → `select_chain_for_strategy`），但只由前端 body 传入，且在 graph 内部生效 | `modules/agent_runtime/adapter/graph/chat_model.py:90` → `modules/model/src/qzdap/modules/model/application/services.py:980` |
| **task_kind 分类** | 旧路径**零实现**；只有新 runtime 有启发式 | `runtimes/agent_runtime/src/qzdap_agent_runtime/graph/routing.py:91` |
| **业务线 / 用户标签** | **无**。`catalog.py:274-281` 的 `category` 映射只是**前端展示文案**（「销售」→「销售支持」），不参与任何路由 | `modules/agent_runtime/src/qzdap/modules/agent_runtime/domain/catalog.py:274` |

> **结论**：现状的「路由」= 前端指定 agentId + 渠道硬编码 agentId。Strategy 是**从零新建**，不是改造。

### 1.2 现状的会话路由与有序性

| 场景 | 现状 | 证据 |
|---|---|---|
| **Web** | 会话 id 由前端持有 → 指向正确；但并发消息被**拒绝**（`try_claim` CAS → `SESSION_BUSY`），不是排队 | `modules/agent_runtime/adapter/persistence/repositories.py:85`（`try_claim`）；`application/copilot.py:229`（`code="SESSION_BUSY"`） |
| **IM 渠道** | **每条消息新建一个 session** → 完全无会话、无连续性、无顺序 | `modules/channel/adapter/dispatch/dispatch_subscriber.py:175-186` |
| **外部会话 → 会话实例映射** | `agent_sessions.channel_session_key` 列**已存在且有索引**，但**全仓无任何读写** | `adapter/persistence/models.py:80` |
| **跨 worker 顺序保证** | 无。无队列、无会话内序号、无 FIFO | `modules/` 里 `ingress_seq` / `next_ingress_seq` / `last_completed_seq` **零命中** —— 旧路径**从来没有过任何序号机制** |
| **审批中断时的后续消息** | 无定义（旧路径 `try_claim` 会直接拒绝） | — |

### 1.3 现状的两个会话/turn 实现（Session Routing 的下游）

| 实现 | claim | 幂等 | 取消 | 审批 | 谁在用 |
|---|---|---|---|---|---|
| ① Copilot（`application/copilot.py` + `adapter/graph/runner.py`） | ✅ | ⚠️ | ✅ | ⚠️ 决策不落库 | 前端 Copilot 页 |
| ② use_cases（`application/use_cases/run_turn.py` + `run_turn_to_completion.py`） | ❌ | ❌ | ❌ | ❌ | 渠道入站、子代理、catalog 评测 |

**Router 的 Session Routing 必须建立在「只有一套 turn 实现」之上**——否则「有序处理」只对其中一条路径成立。这是本方案与 Session 层方案的强耦合点（**§0.5 前置依赖**）。

### 1.4 已有可复用资产

| 资产 | 位置 | 状态 |
|---|---|---|
| `agent_sessions.channel_session_key`（String 512，**已建索引**） | `adapter/persistence/models.py:80` | ✅ 表已建，**无人用** → 正是「外部会话 → 会话实例」的落点 |
| `admin_agents.visible_scope`（JSONB，默认 `["部门"]`） | `adapter/persistence/catalog_models.py` | ✅ 语义就是「哪些部门可见这个 agent」→ **用户标签路由的直接依据** |
| `admin_agents.category`（业务线） | 同上 | ✅ 业务线策略的依据 |
| `admin_agents.tags` / `profile` | 同上 | ✅ 标签与扩展策略配置 |
| `ActorContext.roles`（来自 JWT claims） | `libs/auth/src/qzdap_auth/dependencies.py:49` | ✅ 角色维度策略依据 |
| `build_session_key` | `runtimes/.../channels/gateway.py` | ✅ 可用 |
| `select_chain_for_strategy`（模型策略链） | `modules/model/src/qzdap/modules/model/application/services.py:980` | ✅ 真实现 → 归 Agent 层 Execution 的**模型解析**调用（查表，不是运行时决策） |
| `classify_task_kind_heuristic` | `runtimes/.../graph/routing.py:91` | ✅ 可用 → 归 Agent 层 |
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
   ├─▶ ② Session Routing · 第一步：定位既有会话
   │      2a. 会话 key 派生（tenant+workspace+channel+chat+user → sha256）
   │      2b. 调 Session 的 lookup(session_key) → SessionRef | None
   │          · 命中 → 拿到既有会话的 agent 绑定 → ① 走「粘性」规则
   │          · 未命中 → 无绑定 → ① 走完整规则链
   │
   ├─▶ ① Strategy ──────────────── 选 agent（处理单元的 agent 维度）
   │      输入：actor / channel_type / text / **2b 给出的既有会话绑定（可空）**
   │      依据：会话粘性（2b 命中时直接生效）· 显式指定 · 业务线(category) · 用户标签(visible_scope ∩ roles) · 兜底
   │      输出：AgentTarget{agent_id, agent_version, strategy_id, rule_version,
   │                       confidence, reason, candidates[]}
   │
   └─▶ ② Session Routing · 第二步：落地
          2c. 调 Session 的 resolve_or_create(session_key, agent_binding) → SessionRef
          2d. 分配会话内单调序号 ingress_seq（原子）
          2e. 入队（status=queued）
          输出：SessionAssignment{session_ref, agent_id, agent_version,
                                ingress_seq, predecessor_seq, queue_position}
   │
   ▼
Session（执行）
```

**⚠️ 为什么 Strategy 不能完全排在 Session Routing 之前**（2026-10-29 审查修正）：

决策链的**规则 1「会话粘性」需要「目标会话已存在」这个事实**，而 Gateway 的 `InboundMessage` **不含会话绑定字段**（Gateway 方案 §3.3 的 16 个字段里没有）。若 Strategy 完全先执行，它**拿不到既有绑定** —— 规则 1 无法实现。

**正确的流程是两步**：

| 步骤 | 动作 | 归属 | 为什么必须在这一步 |
|---|---|---|---|
| 1 | 派生 `session_key` | Router | key 只依赖入站字段，不需要会话 |
| 2 | `lookup(session_key)` → `SessionRef`（None 表示不存在） | **Session**（只读） | 拿到「会话是否已存在」与「既有 agent 绑定」 |
| 3 | Strategy：命中则走粘性；未命中则走完整规则链 | Router | 粘性与规则链共用同一个 `RouteDecision` 出口 |
| 4 | `resolve_or_create(session_key, agent_binding)` | **Session** | 决策 #10：会话创建只有一处 |

> **决策 #10 的边界澄清**：「Router 不直接写会话表」**约束的是写，不是读**。Router 读 `agent_sessions` 是允许的 —— 架构测试规则 1 禁的是**写生命周期字段**（见 §10.2）。
>
> **⚠️ 但读路径只有一条**：**既有会话绑定的读取一律经 Session 的 `lookup` 端口**（§9）—— Router 直接读 `agent_sessions` **仅限**两件事：`next_ingress_seq` 的分配与 `last_completed_seq` 的读取。**不得另开一条直接读绑定的路径**（否则粘性规则与 §10.2 规则 1 的扫描口径都判不清）。
>
> **Session 必须提供 `lookup` 端口** —— 原方案只定义了 `resolve_or_create`，而它需要 `agent_binding` 作为**入参**，用粘性去喂它就成了鸡生蛋。`lookup` 是只读的、可单独实现的、不创建任何东西。已同步登记到 [`session-refactor-plan.md`](session-refactor-plan.md)。

---

## 3. Strategy 设计

### 3.1 决策链（优先级从高到低）

| 优先级 | 规则 | 依据 | 备注 |
|---|---|---|---|
| 1 | **会话粘性** | 目标会话已存在 → 沿用其 `agent_id` / `agent_version` | 只在会话已存在时生效。会话中途换 agent 会让历史上下文的解释方式突变。**前提**：`lookup(session_key)` 必须先返回既有绑定（见 §2 的两步流程） |
| 2 | **显式指定** | `InboundMessage.explicit_agent_id`（非 None 时生效） | Web / API 场景前端显式指定 agent |
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
| 扩展配置（策略偏好、场景） | `admin_agents.profile`（JSONB） | 已存在，无需 DDL。⚠️ **不含模型偏好** —— 模型由 agent 配置绑定（D1）|
| 默认 agent / 业务线→agent 映射 | `profile` 或工作区级配置 | 见 §6.4 的决策点 |

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
- **需要唯一约束** `(tenant_id, channel_session_key)`（否则并发首条消息会建出两个会话）——**该索引由 Session 的迁移 0046 建**（会话创建归 Session，决策 #10）；本方案只负责**派生 key**；
- 查不到 → **交给 Session 创建**（见下）。

> **决策 #10（已定稿）：Router 不直接写会话表。**
>
> | 方案 | 做法 | 问题 |
> |---|---|---|
> | **R1（推荐）** Router 只算 `session_key` + 分配 `ingress_seq`；`resolve_or_create` 由 **Session** 执行，Router 收 `SessionRef` | 会话创建逻辑只有一处（Session 的 `SessionManager`），Router 不碰 `agent_sessions` | Router 需要等 Session 的端口就绪（Stage 依赖，见下） |
> | R2 Router 自己查 `agent_sessions` 并创建 | Router 直接改会话表 | **两处都能建会话** → 第二套真相；且 Router 会退化成第二个持久化模块 |
>
> **取 R1。** Router 的职责是「决定这条消息属于哪个 agent、哪个外部会话、排第几」，**不是**「维护会话记录」。
>
> **落地**：`session_key` 的**派生**归 Router（它需要 agent 与业务线上下文）；`channel_session_key` 的**存储与查回**归 Session（表归会话域）。因此 Router 0045 的唯一索引是**为 Session 的写入服务的约束**，不是 Router 自己的读路径。
>
> **依赖顺序**：Router Stage 2（会话映射）**依赖 Session Stage 1（`SessionManager.resolve_or_create` 端口可用）**。这与 `README.md` §3.3 的 DAG 一致（Session Stage 0–2 与 Gateway Stage 0–3 可并行，Router Stage 2 在其后）。

> **web 场景**：前端先 `POST /api/sessions` 建会话再发消息，web 的 `external_chat_id` = session_id。因此 web 走「**会话已存在 → 粘性**」路径，不走 channel_session_key 映射。

### 4.2 有序处理：三个机制

#### (a) 序号分配（会话内单调、原子）

> **决策 #5（已定稿）**：用**会话行原子自增**（`agent_sessions.next_ingress_seq` 列）。不用全局序列（跨会话无意义）、不用分布式锁（多一次往返且不解决并发正确性）。

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

「没有正在执行的 turn」用会话级互斥保证。

> **⚠️ 快照可能落后 —— 必须有兜底，否则队列会卡死**（2026-10-29 审查修正）
>
> `session.last_completed_seq` 是**冗余快照**（§6.2），权威值在 `session_turns`。若两者不一致（例如轮次终态更新会话行失败、或 sweeper 尚未对账），**放行条件 `ingress_seq == last_completed_seq + 1` 永远不成立** → **整个会话的队列卡死**，且现象是「无报错、只是不跑」，极难排查。
>
> **两级判定**：
>
> | 级 | 条件 | 用途 |
> |---|---|---|
> | **快路径** | `turn.ingress_seq == session.last_completed_seq + 1` | O(1)，命中即放行（**正常路径，快照与权威一致**） |
> | **兜底路径** | 快路径不成立，但 `session_turns` 里有 `status='succeeded' AND ingress_seq >= :turn.ingress_seq` 的行 | **快照落后** → **以权威值为准放行**，同时：① 修复 `last_completed_seq`（`SET last_completed_seq = (SELECT MAX(ingress_seq) FROM session_turns WHERE session_id = ... AND status = 'succeeded')`）；② 计数 `qzdap_router_seq_snapshot_drift_total` 并告警 |
>
> **一致性由设计保证，快照只在异常时落后**：轮次进入终态（`succeeded` / `failed` / `cancelled`）时，**在同一个事务内**更新 `session_turns` 与 `session_sessions.last_completed_seq` → **正常路径上不一致窗口 = 0**。兜底路径处理的是「事务部分失败 / 人工改库 / sweeper 修复前的窗口」这类异常。
>
> **检测指标**：`qzdap_router_seq_snapshot_drift_total`（兜底路径命中次数）—— **正常应恒为 0**；持续 > 0 说明有系统性问题。

> 🔴 **锁语义必须先论证清楚**（`pg_try_advisory_xact_lock` 直接搬过来是错的）：
>
> | 问题 | 说明 |
> |---|---|
> | **事务提交即释放** | `_xact_lock` 在事务结束时释放；而 turn 是**长流式执行**（可能几十秒到几分钟），若锁随某个短事务提交而释放，**互斥形同虚设** |
> | **`hashtext()` 碰撞** | 32 位哈希，不同 session 可能碰撞 → 误互斥（不致命，但会造成莫名排队） |
> | **长事务** | 持有 `xact` 锁意味着整个 turn 期间都开着事务 → 连接池被占满 |
>
> **决议（决策 #9，新增）**：**互斥的唯一权威是 `session_turns` 行的状态 CAS**，advisory lock 只作为「避免重复扫同一会话」的优化：
>
> ```sql
> -- 唯一权威：轮次表 CAS
> UPDATE session_turns
>    SET status = 'running', started_at = now()
>  WHERE id = :turn_id AND status = 'queued'
> RETURNING id;
> ```
>
> 只有 `status` 从 `queued` 原子地变成 `running` 的那个 worker 才能执行该 turn —— **不需要任何跨事务锁**，也不会因事务提交而失效。
>
> advisory lock（若保留）改用**会话级** `pg_try_advisory_lock`（非 `_xact_`），并**显式 `pg_advisory_unlock`**；哈希改用 `('x' || substr(md5(:session_id::text), 1, 16))::bit(64)::bigint`（64 位，降低碰撞）。
>
> **Stage 3 的前置**：Session 层的 `session_turns` 必须已启用（含 `status='queued'`），否则 CAS 无从谈起。
>
> **现状核实**：`pg_advisory` 在 `modules/` 与 `composition/` 中**零命中**（只出现在从未接线的 `runtimes/agent_runtime/.../execution/lock.py`）→ **这是新增机制，不是复用**。
>
> **跨会话并行**：互斥按 session_id 粒度，不同会话互不阻塞。

### 4.3 「有序」的准确边界

> **决策 #6（已定稿）**：审批中断**不占用 FIFO 执行位**（等待审批不阻塞新消息）。占用会造成「等审批 → 后续消息全部堵死」的死锁。代价是「审批恢复的那一轮」与「新消息」之间不保证全局有序 —— 靠会话级互斥保证不并发即可。

必须说清楚，否则会实现出错误的语义：

| 情形 | 是否受 FIFO 约束 | 说明 |
|---|---|---|
| 同一会话的连续消息 | ✅ 严格按 `ingress_seq` | 本节的核心保证 |
| 不同会话的消息 | ❌ 不约束 | 并行处理 |
| 同一用户、不同会话 | ❌ 不约束 | 用户可以同时开多个会话 |
| **审批中断中的 turn** | ⚠️ **不占用执行位** | 见下 |
| 被幂等判重的重复消息 | — | 在 Gateway 就短路了，不进队列 |

**审批中断的处理**（重要）：

审批等待中的 turn 状态是 **`waiting`**（`session_turns.status` 的既有取值），**不是 `running`**。（`waiting_approval` 是 `agent_sessions.status` 的**会话级**取值，两者不是一回事。）它**不持有 advisory lock**（lock 在 turn 完成时释放）。因此：

- 用户在等待审批时发的**新消息**可以立即入队并执行（不会被审批卡住）；
- 但**审批恢复的那一轮**必须与同一会话的其他执行互斥；
- 审批恢复的 turn **不参与 `ingress_seq` 的 FIFO 排队**——它是「挂起轮的延续」，不是新消息。

> **这是「有序」的一个例外，必须在方案里显式承认**，否则会出现「等审批 → 后续消息全部堵死」的死锁。

### 4.4 与 Gateway 幂等的分工

| 关注点 | 归属 | 机制 |
|---|---|---|
| 同一条消息投递两次 | **Gateway** | `session_inbox` 原子 claim（幂等键） |
| 同一会话的多条**不同**消息的先后 | **Router** | `ingress_seq` + FIFO |
| 同一会话同时只能跑一轮 | **Session** | **`session_turns.status` 的状态 CAS**（唯一权威，决策 #9）；advisory lock 仅作「避免重复扫同一会话」的优化 |

三者是**互补**的，不是重复：幂等防「同一条」，有序防「不同条的乱序」，互斥防「同时跑」。

### 4.5 并发消息的语义：排队 vs 拒绝（决策点）

现状是**拒绝**（`try_claim` 失败 → `SESSION_BUSY` → HTTP 409）。需求是「保证有序处理」→ 应为**排队**。但语义变化会影响前端契约：

| 方案 | 行为 | 代价 |
|---|---|---|
| **S1 严格排队**（推荐） | 第二条等第一条完成后再跑 | 需要新增「排队中」的前端信号；队列积压需超时/丢弃策略 |
| S2 拒绝（现状） | 返回 409 `SESSION_BUSY` | 用户连发两条要手动重试；与「有序处理」需求不符 |
| S3 合并 | 短窗口内多条消息合并成一轮 | 语义复杂，用户预期难对齐 |

**S1 的配套要求**：

1. **前端需要知道「在排队」**。当前 **17** 种 `TurnChunk` 里**没有 `queued` 类型** → 需要新增 `QueuedChunk`（含 `position` / `waited_ms`），否则前端只能转圈直到首 chunk 到达。
2. **队列上限与超时**：单会话排队上限（N 条）与最长等待时间（T 秒），超限返回明确错误码，**不得静默丢弃**。

   > **决策 #7（已定稿）**：N 与 T 的取值，以及错误码。
   > - **定稿**：N = 5 条 / T = 60 秒；错误码 `QUEUE_FULL`（超上限）与 `QUEUE_TIMEOUT`（超等待时间），HTTP 409 / 504。
   > - **Stage 0 落点**：`ErrorCode` 枚举增这两个码 + `_HTTP_STATUS` 映射（`libs/schema/src/qzdap_schema/dtos/errors.py`）。
   > - **验收**：排队超限时返回 `QUEUE_FULL` / `QUEUE_TIMEOUT`，**不静默丢弃**；超限的 turn 落 `cancelled`（可从 `session_turns` 查到）。
   > - **前端契约**：排队中的消息需要前端可见 → 见下方「排队语义的前端契约」。

> 这两条是 S1 相对 S2 的**额外成本**，也是决策 #1 的连带义务。

---

## 5. 四个必须澄清的边界

### 5.1 Router 选 agent ≠ Agent Router 选专家

> **Router 决策 #4**：**深度任务判定与模型链解析不在本层**，归 **Agent 层**。理由：本层在**会话入口**执行，那时还没有上下文（消息数、工具数、意图都拿不到），无法判定深度任务。

| | **⑤ Router.Strategy** | **⑧ Agent Router** |
|---|---|---|
| 轴 | 执行轴 · **会话入口一次** | 执行轴 · **每步一次** |
| 选什么 | **会话绑定的 agent**（处理单元） | **本步的专家 Agent** |
| 结果 | **会话绑定**（冻结到 agent 版本，会话内不变） | **本步的专家**（每步可变） |
| 依据 | 会话粘性 > 显式指定 > 业务线(category) > 用户标签 > 兜底 | 推理意图 + 专家目录 |
| 上下文依赖 | **不需要**完整上下文 | 需要（每步的上下文） |
| 模型 / 工具 | **不涉及** —— 配置轴，管理员在 agent 配置里绑定 | **不涉及** —— 随选中专家的配置取值（Agent 方案 §5.2.1 / §5.3.1） |

> **⚠️ 模型 / 工具不在这两列里** —— Agent 决策 #4 已定：模型与工具由**管理员在 agent 配置里绑定**，运行时**查表取值**（Agent 层 Execution），**不是运行时挑**。所以本层的对照只到「选专家」为止。
>
> **两者不冲突的原因**：Router 选的是**整个会话跟谁聊**（一次决定，全程有效）；Agent Router 选的是**这一步交给哪个专家**（每步可变）。专家切换**不改变会话绑定**（Agent 方案 §4.1 规则 4）。

> **推论**：v3.1 里放在 `route` 节点的「模型策略链选择」与「深度任务判定」**不属于本层**，应归 Agent 层。
>
> **⚠️ 本层不产出任何模型 / 工具信号** —— D1 之后「给下游一个模型偏好」在语义上不存在（模型在配置轴上由管理员绑定，运行时只查表）。所以 `RouteDecision` **没有 `model_hint` 字段**。

### 5.2 `deep_task` 判定不在 Strategy

v3.1 §5.5 的启用规则依赖「消息数 > 20」「工具数 > 5」等**完整上下文信息**——入站时拿不到。→ 归 Agent 层。

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

> **⚠️ 重要更正（2026-10-29 审查）**：旧路径的 `try_claim` **只管执行权，不管顺序**。
>
> 实测 `repositories.py:85-108` 全文：
> ```python
> .where(SessionORM.id == session_id,
>        or_(SessionORM.wait_status != "running",
>            SessionORM.updated_at < stale_before))   # 僵尸兜底
> .values(wait_status="running", updated_at=func.now())
> ```
> 它是**一个布尔 CAS，只保证「同一会话同时只有一轮在跑」**——**没有任何序号、没有顺序语义**。且 `modules/` 里 `ingress_seq` / `next_ingress_seq` / `last_completed_seq` **零命中**，旧路径**从来没有过顺序机制**。
>
> **所以**：
> - **Router 的 FIFO 是从零新建**，不是「从 `try_claim` 里拆出来」；
> - **`try_claim` 整体归 Session**（唯一职责 = 互斥；替代者是 `session_turns.status` 的状态 CAS，`wait_status` 的停写/DROP 已在 Session Stage 0/6）；
> - **Router 不删除 `try_claim` 的任何东西**。台账 **R3 的描述据此修正为「`try_claim` 的会话互斥职责」，owner 改为 Session**。

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

> **决策 #2（已定稿）**：启用新表 `session_turns` / `session_messages` / `session_events`，旧表 `agent_turns` / `agent_session_messages` 在切换时**迁数据后废弃**。理由：新表是 Gateway 方案 §8 已定的目标形态，两层用同一套表才不产生第二套真相。
>
> 影响：`agent_sessions` 是否也换成新表？Gateway 方案 §8 已定「`agent_sessions` 保留」。本方案沿用 `agent_sessions` 作为会话主表，只在其上加列。

### 6.2 Router 需要的状态落点

| 状态 | 落点 | 动作 |
|---|---|---|
| 外部会话 → 会话实例映射 | `agent_sessions.channel_session_key`（**已存在**） | 启用；唯一约束 `(tenant_id, channel_session_key)` 由 **Session 迁移 0046** 建（会话创建归 Session，决策 #10） |
| 会话内入站序号 | `agent_sessions.next_ingress_seq`（**新增列**） | `Integer NOT NULL DEFAULT 0` |
| 最后完成轮次的序号 | `agent_sessions.last_completed_seq`（**新增列**） | `Integer NOT NULL DEFAULT 0`；权威值在 `session_turns`，本列是冗余快照。**一致性由同事务更新保证**；万一落后，放行判定走 §4.2(c) 的兜底路径（以权威值为准 + 修复 + 告警） |
| 排队中的消息 | `session_turns`（`status='queued'` + `ingress_seq`） | 启用新表；**DDL 归 Session（0046）**，本方案只引用 |
| 路由决策留痕 | `session_turns` 的 `route_decision`（JSONB） | 记录 `RouteDecision`；**DDL 归 Session（0046）**；⚠️ **本层是这一列的唯一写者** —— Agent 层的专家选择写**另一列** `agent_decision`（见 Agent 方案 §4.1），两者语义不同、不可共用一列 |
| 用户属性 | `identity` 的 `User.metadata` + 新增 `UserDirectoryPort` | 结构化字段待补（§1.5） |

### 6.3 迁移草案（0045）

```sql
-- migrations/versions/0045_router_session_routing.py
--
-- ⚠️ 本迁移只改 agent_sessions。session_turns 的 DDL **归 Session（0046）**，
--    Router 只引用列、不另建迁移（表归属唯一原则，见 README.md §3.3）。

-- 1) agent_sessions：入站序号（Router 自己的排序状态）
ALTER TABLE agent_sessions
    ADD COLUMN next_ingress_seq    Integer NOT NULL DEFAULT 0,   -- 下一个待分配的入站序号
    ADD COLUMN last_completed_seq  Integer NOT NULL DEFAULT 0;   -- 最后一个已完成轮次的 ingress_seq
--
-- ⚠️ (tenant_id, channel_session_key) 的唯一索引**不在本迁移**：
--    它保护的是**会话创建**的唯一性，而会话创建由 Session 执行（决策 #10），
--    因此该索引归 Session 的迁移 0046。
```

> **`last_completed_seq` 为什么必须新增**：FIFO 放行判定是 `turn.ingress_seq == session.last_completed_seq + 1`（§4.2c）。该列此前**没有任何方案定义**。它与 `next_ingress_seq` 同表、同生命周期，一并放在 0045。
>
> **与 `session_turns` 的关系**：`last_completed_seq` 是**会话行的冗余快照**，权威值在 `session_turns`（该会话已完成轮次的最大 `ingress_seq`）。轮次终态时**在同一事务内**更新两者 → 正常路径不一致窗口 = 0。
>
> **不一致时的处理**：以 `session_turns` 为准 —— 放行判定走 §4.2(c) 的**兜底路径**（修复快照 + 计数告警），sweeper 定期对账作为第二重保险。**不能只靠 sweeper 对账**：两次调度之间队列是卡住的。
>
#### 6.3.1 0045 的回滚

0045 是**纯新增两列**，回滚代价极低：

```sql
ALTER TABLE agent_sessions
    DROP COLUMN IF EXISTS last_completed_seq,
    DROP COLUMN IF EXISTS next_ingress_seq;
```

> **⚠️ 回滚会丢失入站序号**：`next_ingress_seq` / `last_completed_seq` 是**运行中状态**（不是业务数据），回滚后 FIFO 判定失效 —— 但**回滚意味着新实现也不再用**，所以无影响。
>
> **真正的不可逆点在别处**：`session_turns.ingress_seq`（0046，Session 所有）**不回滚** —— 它是有业务含义的入站顺序，回滚会破坏重放与对账。**两列必须同进同退**：若 0045 回滚而 0046 不回滚，FIFO 判定会缺依据。
>
> **⚠️ 因此 0045 与 0046 必须一起回滚**（虽然 DDL 层面互不冲突）：
> - **DDL 层面可独立回滚** —— 0045 只加 `agent_sessions` 的两列，0046 加索引 + 改 `wait_status` + 加 `session_turns` 的列，**不同列 / 不同约束**，技术上一个回滚另一个不受影响；
> - **但语义上不可独立回滚** —— 0045 回滚后 `next_ingress_seq` / `last_completed_seq` 消失，而 0046 的 `session_turns.ingress_seq` 还在 → **FIFO 判定失去依据**（Router 方案 §4.2c）。
>
> **结论：两者的 DDL 可独立回滚，语义上必须同进同退。** 排期上 0045 与 0046 相邻（Router Stage 0 与 Session Stage 0），**回滚时一起处理**。

> **Session 0046 需要一并提供的 `session_turns` 列**（本迁移不建）：
>
> ```sql
> -- migrations/versions/0046_session_runtime.py（Session 方案拥有）
> ALTER TABLE session_turns
>     ADD COLUMN ingress_seq      Integer,
>     ADD COLUMN route_decision   JSONB,
>     ADD COLUMN pending_approval JSONB,
>     ADD COLUMN cancel_requested Boolean NOT NULL DEFAULT false;
>
> CREATE UNIQUE INDEX uq_session_turns_session_ingress
>     ON session_turns (session_id, ingress_seq)
>     WHERE ingress_seq IS NOT NULL;
>
> -- 轮次状态枚举：0035 建的是 session_turns_status_enum
> --   ('running','waiting','succeeded','failed','cancelled')
> -- 0046 需要加 'queued'，必须先 DROP 再重建（Postgres 不能直接改 check 约束）
> ALTER TABLE session_turns DROP CONSTRAINT session_turns_status_enum;
> ALTER TABLE session_turns
>     ADD CONSTRAINT session_turns_status_enum
>     CHECK (status IN ('queued','running','waiting','succeeded','failed','cancelled'));
> ```
>
> ⚠️ **取值统一**：审批挂起态沿用 0035 已有的 **`waiting`**，**不引入 `waiting_approval`**（`agent_sessions` 的会话级状态才用 `waiting_approval`，两者不是一回事）。

### 6.4 默认 agent 与业务线映射的配置落点

两个候选：

- `admin_agents.profile`（JSONB，已存在）里放「默认 agent 标记」与「业务线→agent 优先级」；
- 工作区级配置（`admin_ops` 的 collection 机制）。

> **决策 #3（已定稿）**：放 `admin_agents.profile`——策略是 agent 的属性，与 §3.3 的「不新建策略表」一致。

---

## 7. 逐文件改造与删除清单

### 7.1 新增（`backend/runtimes/agent_runtime/src/qzdap_agent_runtime/router/`）

| 文件 | 内容 |
|---|---|
| `types.py` | `RouteDecision`（§3.2 给了完整定义）/ `AgentTarget` / `AgentCandidate` / `SessionAssignment`（形状以 §9 的边界表为准）|
| `strategy.py` | `Strategy` Protocol + 规则链实现 + `RouteDecision` 留痕 |
| `session_key.py`（⚠️ **不叫 `session_router.py`** —— 那个名字已被既有的 `modules/agent_runtime/adapter/http/session_router.py` 占用，它是 **HTTP 路由**不是会话路由，同名必然混淆） | 会话 key 派生 · 映射与创建 · `ingress_seq` 分配 · 入队 |
| `sequencer.py` | `SessionSequencer` Protocol + FIFO 放行判定 + advisory lock 端口 |

### 7.2 迁移

| 旧位置 | 迁到 | 动作 |
|---|---|---|
| `modules/channel/adapter/dispatch/dispatch_subscriber.py:43,175-186` 硬编码 agent + 每消息建 session | `router/strategy.py` + `router/session_key.py` | **删除**，改走 Strategy + 会话映射 |
| `modules/agent_runtime/adapter/http/session_router.py:162` `agentId` 直取 | `router/strategy.py` | 改为「显式指定」规则，优先级 2 |
| `modules/agent_runtime/adapter/persistence/repositories.py:85-108` `try_claim` | 拆成 Router（FIFO）+ Session（执行权） | 改造 |
| `runtimes/.../channels/gateway.py` `build_session_key` | `router/session_key.py` | 改为哈希版 |
| `runtimes/.../graph/routing.py:91` `classify_task_kind_heuristic` | `agent_router`（**不属本层**） | ⚠️ **该文件从未接线**（`runtimes/agent_runtime/` 全仓零生产引用）→ **「迁出」是伪动作**。它是 **Agent 层**的删除范围（台账 X1），本层**不碰** |

### 7.3 保留但改造

| 文件 | 改造点 |
|---|---|
| `modules/agent_runtime/adapter/persistence/models.py` | `agent_sessions` 加 `next_ingress_seq` / `last_completed_seq`（唯一索引由 Session 0046 建） |
| `modules/agent_runtime/adapter/persistence/catalog_models.py` | `admin_agents` 无需 DDL（策略走已有字段） |
| `modules/model/src/qzdap/modules/model/application/services.py:980` `select_chain_for_strategy` | **保留**，但调用方从 graph 移到 Agent 层 Execution 的模型解析 |

### 7.4 删除清单（Stage 4 停用 + 打点 → Stage 5 删除）

| 类别 | 具体 | owner |
|---|---|---|
| 硬编码路由 | `dispatch_subscriber.py` 的 `SYSTEM_AGENT_ID` / `SYSTEM_USER_ID` | **Gateway（G3）** —— 本层只保证不再有调用方 |
| 每消息建会话 | `dispatch_subscriber.py:175-186` 的临时 session 创建 | **本层（R1）** —— 行为替换；**文件删除归 Gateway（G9）** |
| 进程内去重 | `dispatch_subscriber.py` 的 `OrderedDict` LRU | **Gateway（G6）** |
| 旧的会话互斥 | `try_claim` 的 CAS（**它只有这一个职责** —— 无顺序语义，见 §5.4 的更正） | ⚠️ **Session（R3，owner 已改）** —— 本层**不删**，只确认互斥已迁到 `session_turns` 的状态 CAS |
| 旧的会话 key | `build_session_key`（冒号拼接版） | **本层（R4）** |
| 展示用 category 映射 | `catalog.py:274-281`（若策略改用 `category` 原值，需同步改展示层） | **本层** |

> **唯一 owner 规则**（台账 §3.4）：同一个旧实现只能由**一个方案**负责删除。
> - **`dispatch_subscriber.py` 的文件删除 → Gateway（G9）**。本层只保证「不再有调用方」。
> - **第二套 turn 实现 → Session（X2）**。本层**不删**，也不另起删除 PR —— 否则会与 Session 的删除 PR 互相冲突。
> - 本层 Stage 5 真正删除的只有：`build_session_key`（R4）、`try_claim` 的顺序职责（R3）、`catalog.py` 的展示映射。

---

## 8. 实施阶段

> 每阶段验收都含「**旧代码减少了什么**」。

### Stage 0：契约与配置（不改行为）

| 动作 | 细节 |
|---|---|
| 建 `router/` 骨架 + `types.py` | 4 个类型定稿 |
| 迁移 0045 | `agent_sessions` 加 `next_ingress_seq` / `last_completed_seq` |
| 策略配置规范 | `admin_agents.profile` 的路由配置 schema（文档化，不强制） |
| `UserDirectoryPort` 契约 | 定义在 router 侧，实现在 identity 侧 |
| **`ErrorCode` 增 `QUEUE_FULL` / `QUEUE_TIMEOUT`** | `libs/schema/src/qzdap_schema/dtos/errors.py` + `_HTTP_STATUS` 映射（决策 #7） |
| **收敛基础设施** | 建 `qzdap_legacy_calls_total` 指标（若尚未建立），并给本层台账条目的旧入口打点（`record_legacy_call("<编号>")`）。**没有打点就没有清理判据** —— 见 `cleanup-ledger.md` §3.2 |

**旧代码减少**：无（纯新增）。
**验收**：类型有单测；迁移在 dev 库跑通。
**验收补充**：本层每个台账条目的旧入口都有打点；`/metrics` 能查到 `qzdap_legacy_calls_total`。

### Stage 1：Strategy 落地（web 路径先行）

| 动作 | 细节 |
|---|---|
| 规则链实现 | 粘性 > 显式 > 业务线 > 用户标签 > 兜底 |
| `RouteDecision` 留痕 | 写入 `session_turns.route_decision`（**本层唯一写者**；Agent 写 `agent_decision`，不共用本列） |
| web 建会话改走 Strategy | `session_router.py:162` → Strategy |

**旧代码减少**：`agentId` 直取逻辑收进 Strategy 规则。
**验收**：兜底命中率可查；显式指定与策略冲突时按粘性规则并留痕。

### Stage 2：Session Routing 落地（IM 路径）

> **开工前置（硬）**：**Session 层的 `SessionManager.resolve_or_create` 端口已可用**（Session Stage 1）。Router 只**派生 `session_key`**，会话的创建/查回由 Session 执行（决策 #10）—— 没有这个端口，Router 就得自己建会话（第二套真相）。
>
> **✅ 已执行（2026-10-31）** —— 实施结果见 **§13.6** ✓。

| 动作 | 细节 |
|---|---|
| 会话 key 派生 | 本层职责：tenant+workspace+channel+chat+user → sha256 |
| **只读 `lookup(session_key)`** | **调 Session 的 `lookup` 端口**（不是直接查表）→ `SessionRef` 或 `None`。⚠️ **这是粘性规则的唯一依据来源**（§3.1 规则 1）—— 没有它，「命中 → 走粘性」无法实现 |
| 会话创建/复用 | **调 Session 的 `resolve_or_create`**（不再自建）；绑定 Strategy 选出的 agent |
| `ingress_seq` 分配 + 入队 | 新增列 + `session_turns.status='queued'` |
| **删除** IM 临时 session 创建 | `dispatch_subscriber.py:175-186` |

**旧代码减少**：每消息建会话的行为消失。
**验收**：同一飞书群连续 3 条消息 → **同一个 session_id**；跨 worker 一致。

### Stage 3：有序处理落地

> **开工前置（硬）**：**Session 层的唯一 turn 实现已落地**（Session Stage 3）。未落地则「有序」只对一条路径成立 —— 渠道 / 子代理 / 评测仍可绕过队列并发执行。详见 §0.5。
>
> **✅ 已执行（2026-10-31）** —— 实施结果见 **§13.6** ✓（⚠️ **排队开关默认关** ✓ —— 见 13.6-D8 ✓）。

| 动作 | 细节 |
|---|---|
| FIFO 放行判定 | `ingress_seq == last_completed_seq + 1` |
| **FIFO 兜底路径** | ⚠️ `last_completed_seq` 是 `agent_sessions` 上的**冗余快照**，可能落后于权威值（`session_turns`）→ **以权威值为准放行**，并修复快照 + 计数告警（§6.2 的兜底口径）|
| 会话级互斥 | **轮次表 CAS 为主**（`session_turns.status`）；advisory lock 仅作优化（决策 #9） |
| 审批中断不占执行位 | 轮次状态机区分 `waiting` 与 `running`（`waiting_approval` 是**会话级**状态，见 §4.3） |
| 并发语义切换 | 从「拒绝 SESSION_BUSY」改为「排队」 |

**旧代码减少**：**无删除**。⚠️ 旧路径**本来就没有顺序机制**（§5.4 的更正）—— 本 Stage 是**从零新建** FIFO，不是「移除 `try_claim` 的顺序职责」。
**验收**：并发 5 条同会话消息 → **按入站顺序执行**，不丢不乱；不同会话并行不互相阻塞；审批等待期间新消息可执行。

### Stage 4：新实现接管与弃用

> **本阶段只上新，不删旧**。旧实现打 `@deprecated` + 调用打点（`qzdap_legacy_calls_total{entry="..."}`），进入清理窗口。清理机制见 [`cleanup-ledger.md`](cleanup-ledger.md) R1–R4。

| 动作 | 细节 |
|---|---|
| 渠道入站改走 Strategy + Session Routing | IM 消息不再硬编码 agent、不再建临时 session |
| `dispatch_subscriber.py` | **停用**（打弃用标记 + 打点），不立即删 |
| 第二套 turn 实现 | **停用**（打弃用标记 + 打点）；合并是 Session 层的主战场，Router 侧只配合 |
| 更新 [`cleanup-ledger.md`](cleanup-ledger.md) R1–R4 状态 | → 已弃用 |

**旧代码减少**：无删除，但 R1–R4 全部进入弃用与观测状态。
**验收**：§10 全部检查项通过；**旧路径已被打点覆盖 100%**（每个待清理的旧入口都有 `record_legacy_call("R<N>")`）、新路径流量占比 **≥95%**。
>
> **归零判据属于 Stage 5 的进入条件，不在这里要求** —— Stage 4 刚接管时旧路径必然还有残留流量（长连接、缓存、灰度中的客户端）。与 Gateway Stage 4a 的口径一致。

### Stage 5：旧实现清理

> **进入条件（硬性）**：连续运行 **≥ 7 天** + 新路径流量占比 **≥ 95%** + `qzdap_legacy_calls_total{entry="…"}` 窗口内**累计为 0** + 窗口内无相关生产事故。指标未归零 → 不许进入本阶段，先查为什么还有人在调。

| 动作 | 细节 |
|---|---|
| 删 `build_session_key` 冒号拼接版 | 台账 **R4**（本层 owner） |
| **确认** `try_claim` 的互斥职责已由 Session 迁走 | ⚠️ **本层不删** —— 台账 **R3 的 owner 是 Session**（互斥归 Session 的执行权，见 §5.4 的更正） |
| 删 `catalog.py:274-281` 的展示映射 | 若策略改用 `category` 原值 |
| **确认** `dispatch_subscriber.py` 无残留调用方 | ⚠️ **文件删除归 Gateway（G9）**，本层不删 |
| **确认**第二套 turn 实现无残留调用方 | ⚠️ **删除归 Session（X2）**，本层不删 |
| 启用扫描脚本的 Router 段 | 进 CI（脚本唯一来源：台账 §3.1） |
| 更新台账状态 | R1–R4 → 已清理 |
| 更新 `docs/copilot-chat-module-architecture.md` | 现状文档同步 |

**旧代码减少**：§7.4 删除清单**归零**。
**验收**：§10 全部检查项通过；台账 Router 域条目全部「已清理」。

### 阶段与「旧代码减少」对照

| 阶段 | 删除/替换 | 量级 | 旧路径状态 |
|---|---|---|---|
| Stage 0 | 无（纯新增：契约 + 迁移 0045） | 0 | — |
| Stage 1 | `agentId` 直取 | ~10 行 | 直接替换（无残留调用方） |
| Stage 2 | IM 临时 session 创建 + 硬编码 agent | ~40 行 | 直接替换 |
| Stage 3 | **无**（旧路径无顺序机制，FIFO 全新建） | 0 | — |
| Stage 4 | — | 0 | **停用 + 打点**（进入清理窗口） |
| Stage 5 | `build_session_key` + `catalog.py` 展示映射 | **~60 行** | 删除（台账清零）。`dispatch_subscriber.py`、第二套 turn 实现、**`try_claim`（R3）** 均**不在本层删除** |

> **全层合计约 110 行**（10 + 40 + 60）。⚠️ **不含 `try_claim`** —— 旧路径**从来没有顺序机制**（§5.4 的更正），`try_claim` 的互斥职责归 **Session（R3）**，本层不删。

---

## 9. 与相邻层的接口

| 方向 | 契约 |
|---|---|
| Gateway → Router | `InboundMessage`（含 `actor` / `channel_type` / `external_chat_id` / `external_user_id` / `explicit_agent_id` / `text` / `idempotency` / 附件） |
| Router → Session | **两步**：① 先调 **只读**的 `lookup(session_key) → SessionRef`（None 表示不存在；拿既有绑定，供粘性规则用）；② 再调 `resolve_or_create(session_key, agent_binding) → SessionRef`（创建/复用）。随后在 `SessionRef` 上分配 `ingress_seq`，最终产出 `SessionAssignment{session_ref, agent_id, agent_version, ingress_seq, predecessor_seq, queue_position}` + `RouteDecision`（留痕用）。见决策 #10 与 §2 的两步流程 |
| Router ← Agent Catalog | `AgentCatalogService`（已有）→ 提供 `category` / `visible_scope` / `tags` / `profile` / `version` |
| Router ← Identity | `UserDirectoryPort`（新增）→ 用户属性 |
| Router ← Model | **不调用**；模型策略链归 Agent 层 Execution |

---

## 10. 验收标准

> **本层在系统级验收中的责任**：
> 本层负责系统级验收的 **#4（同会话严格有序）**（完整清单见 [`README.md`](README.md) §7）。

### 10.1 功能验收

1. **路由正确性**：5 类入口 × 3 类策略来源 → 命中的 agent 符合规则链，且 `RouteDecision` 完整留痕；
2. **粘性**：同一会话内 Strategy 始终返回同一 agent，即使策略配置在会话中途变化；
3. **会话稳定性**：同一 IM 群连续 3 条消息 → 同一个 `session_id`；
4. **严格有序**：并发 5 条同会话消息 → 执行顺序 == 入站顺序，无丢失、无乱序；
5. **跨会话并行**：N 个会话并发 → 互不阻塞；
6. **审批不阻塞**：审批等待期间发新消息 → 新消息正常执行；
7. **跨 worker 一致**：两个 worker 分别处理同一会话的不同消息 → 顺序仍然正确；
8. **兜底安全**：无任何策略命中 → 走默认 agent，**消息不丢**；
9. **可解释**：`route_decision` 可查询，能回答「为什么是这个 agent」；
10. **架构测试**：Router 层不得 import FastAPI / SQLAlchemy（与 Gateway 方案同一条规则）；
11. **排队超限不静默**：排队超过 N 条 → 返回 `QUEUE_FULL`；等待超过 T 秒 → 返回 `QUEUE_TIMEOUT`；两种情况下 turn 落 `cancelled` 且**可从 `session_turns` 查到**（不静默丢弃）；
12. **开关可回滚**：`QZDAP_ROUTER_QUEUE_ENABLED=off` 时行为回到现状（409 拒绝），前端行为不需改动。


---

### 10.2 架构测试

```python
# tests/architecture/test_router_boundary.py
FORBIDDEN = ("fastapi", "starlette", "sqlalchemy", "asyncpg", "psycopg")

def test_router_layer_has_no_framework_imports():
    """Router 层不得依赖框架 —— 由 README §3.2 的边界判据派生。"""
    for path in _py_files(("backend/runtimes/agent_runtime/src/qzdap_agent_runtime/router",)):
        for mod in FORBIDDEN:
            assert mod not in _imports_of(path), f"{path} 引入了 {mod}"
```

另加三条本层特有的规则：

| # | 规则 | 检查方式 |
|---|---|---|
| 1 | **Router 不写会话的生命周期字段**（决策 #10）—— `agent_sessions` 里除**自己的排序列**外，一律只读 | 关键字扫描：router 包内对 `agent_sessions` 的 `UPDATE` **只允许出现在 `next_ingress_seq` 上**；`INSERT INTO agent_sessions` 零命中；`UPDATE agent_sessions SET status` / `agent_id` / `owner_id` / `current_revision` / `wait_status` 零命中 |
| 2 | **Router 不算 token、不装上下文** | import 扫描（不得 import `context` 包） |
| 3 | **Router 不调用 LLM** | import 扫描（不得 import `qzdap_llm`） |

### 10.3 「没有第二套实现」的扫描

**扫描脚本的唯一来源是 [`cleanup-ledger.md`](cleanup-ledger.md) §3.1**，本层不另写一份。Router 域对应的规则：

| 旧符号 | 台账条目 | 判据类型 |
|---|---|---|
| `build_session_key` | **R4** | 指标 + 扫描 |
| **IM 每消息新建 session**（`dispatch_subscriber.py` 里的临时 session 创建） | **R1** | **扫描**（行为替换：文件删除归 Gateway G9，本层只保证那段代码不再被调用） |
| **`agentId` 直取**（`session_router.py` 里 `body.get("agentId")` 直传） | **R2** | 扫描 |
| **`try_claim`**（`repositories.py`） | **R3** | **扫描** —— ⚠️ **owner 是 Session**，本层只「确认无残留调用方」，**不删** |
| `compile_loop_graph` | X5（与 Agent 层共用） | 扫描 |

> 启用时点：**Router Stage 5 合并时**，与旧实现删除在同一个提交里完成。

---

## 11. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| **并发语义从「拒绝」改为「排队」** | 前端契约变化（需 `queued` 事件）；用户预期变化 | 决策 #1 明确取舍；新增 `QueuedChunk`；队列上限与超时显式化 |
| **「唯一 turn 实现」未先落地** | Router 的有序性只对一条路径成立 | §0.5 前置依赖：Session 层方案先落地；否则 Stage 3 不得开启 |
| ~~表选择未定~~ | — | **已消解**：决策 #2 已定稿（启用新表 `session_turns`），与 Session 决策 #5 同值；两表并存即第二套真相 |
| 用户标签无结构化数据源 | 「按用户标签路由」只能近似 | §1.5；`UserDirectoryPort` 契约先行；不做大范围 identity 改造 |
| `channel_session_key` 唯一约束加不上 | 并发首条消息可能建两个会话 | 部分唯一索引（Session 0046）+ 冲突后重查 |
| advisory lock 依赖 Postgres | 多副本部署需共享 DB | 现状已是共享 Postgres；不引入 Redis |

### 11.1 回退

| 时点 | 回退方式 | 代价 |
|---|---|---|
| Stage 1–3（未切换） | `git revert` 对应提交即可 | 无（旧实现一直在场） |
| Stage 4（已接管，未清理） | `git revert` 切换提交 → 流量回落旧实现 | 无。**这正是保留清理窗口的收益** |
| Stage 5（已清理） | 需**重新上线旧版本** | 旧表已 DROP，**数据不可恢复** → 依赖迁移前的备份 |

> **本层特有的不可逆点**：`agent_turns` / `agent_session_messages` 的 DROP（Session Stage 6 执行）。Router 只引用新表，自身不删表 —— 回退时数据在 `session_turns` 里，**不受影响**。
>
> **排队开关是本层的天然回退阀**：`QZDAP_ROUTER_QUEUE_ENABLED` 默认 off（决策 #8）。新路径出问题时把它关掉，即退回「拒绝 SESSION_BUSY」的旧语义，**不需要回滚代码**。
---

## 12. 治理与可观测性落点

### 12.1 治理落点（Governance）

| 本层步骤 | 闸门 | 拒绝 / 降级时的行为 |
|---|---|---|
| Strategy 匹配 | 业务线 / 用户标签的路由策略 | 未命中 → 走 fallback 规则；fallback 也未命中 → **按 §3.1「兜底必须安全」走工作区默认 agent**；连默认 agent 都没有 → `AGENT_NOT_AVAILABLE`（既有 `ErrorCode` 成员） |
| 策略优先级 | 规则链固定顺序（sticky > explicit > business_line > user_tag > fallback） | 冲突时**高位规则胜出**，不进入低位规则 |
| 会话配额 | 每会话的并发轮次上限、租户级会话数上限 | 超限 → **排队超时按 `QUEUE_TIMEOUT`（既有于本方案 Stage 0 新增）**；租户级会话数超限 → **`FORBIDDEN`**（既有 `ErrorCode` 成员，403）。⚠️ **本方案不新增 `SESSION_LIMIT` / `NO_ROUTE` 这类码** —— `ErrorCode` 枚举（`libs/schema/.../errors.py`）只有 20 个成员，不含它们 |
| 租户隔离 | `session_key` 必须含 `tenant_id` + `workspace_id` | 跨租户 key 一律拒绝，防止会话串租户 |

> **本层不拥有的治理**：消息内容级配额（Gateway）、模型与工具白名单（Agent 层 Execution）、记忆检索范围（Memory）。

### 12.2 可观测性指标（Observability）

指标名进 `qzdap_*` 命名空间，实现落在 `backend/libs/observability/src/qzdap_observability/metrics.py`。

| 指标名 | 类型 | 标签 | 说明 |
|---|---|---|---|
| `qzdap_router_route_total` | Counter | `strategy`, `outcome` | 路由决策数（`strategy`：命中的规则名；`outcome`：`matched` / `fallback` / `rejected`） |
| `qzdap_router_route_duration_seconds` | Histogram | `strategy` | 路由决策耗时 |
| `qzdap_router_queue_depth` | Gauge | `tenant_id` | 当前排队消息数（仅 `QZDAP_ROUTER_QUEUE_ENABLED=true` 时上报） |
| `qzdap_router_queue_wait_seconds` | Histogram | `tenant_id` | 排队等待时长 |
| `qzdap_router_concurrency_rejected_total` | Counter | `reason` | 因会话并发上限被拒的消息数 |
| `qzdap_router_session_key_hash_total` | Counter | — | 会话 key 归一化次数（**不记录 key 本身**，避免泄漏身份） |
| `qzdap_legacy_calls_total` | Counter | `entry` | 旧实现调用计数（标签 `entry` 为台账编号） |

**Span 划分**：

| Span | 父子关系 | 属性 |
|---|---|---|
| `router.route` | 根 | `strategy`, `outcome`, `session_key_hash`（**哈希，不落原文**） |
| `router.dispatch` | `router.route` | `target`, `ingress_seq` |

> **观测约束**：会话 key 与用户身份在日志 / span 中**一律哈希或脱敏**。trace 属性禁止出现 `external_user_id`、消息正文、附件内容。

### 12.3 审计

| 事件 | 何时写 | 内容 |
|---|---|---|
| `router.route.fallback` | 落到 fallback 规则 | 会话 key 哈希、可用策略集（排查「为什么没按业务线路由」） |
| `router.route.rejected` | 路由失败 | 原因、trace_id |

> 审计写入走 Governance 模块，Router 只投递事件。
---

## 13. Stage 0 + Stage 1 实施结果（2026-10-29）

> **本节记录已落地的部分与偏差** —— 方案是「打算做什么」，本节是「实际做了什么、
> 哪里没做到」。**偏差不藏**：做不到的写清楚做不到，以及它归谁。

### 13.1 落地了什么

| 动作 | 落点 | 状态 |
|---|---|---|
| `router/` 骨架 + `types.py`（4 个类型定稿 + 2 个端口） | `backend/runtimes/agent_runtime/src/qzdap_agent_runtime/router/types.py` | ✅ |
| 规则链实现（五条规则） | 同目录 `strategy.py` | ✅（**粘性规则缺输入**，见 13.2-D1） |
| `UserDirectoryPort` 契约（router 侧） | `router/types.py` | ✅ |
| `UserDirectoryPort` 实现（identity 侧） | `modules/identity/src/qzdap/modules/identity/adapter/user_directory.py` | ✅（identity 模块新增依赖 `qzdap-agent-runtime-runtime`） |
| 候选池适配（复用既有 `AgentCatalogService`，**不另起查询**） | `modules/agent_runtime/.../adapter/routing/catalog_port.py` | ✅ |
| `ErrorCode` 增 `QUEUE_FULL` / `QUEUE_TIMEOUT` | `libs/schema/src/qzdap_schema/dtos/errors.py` | ✅（**消费方归 Stage 3**） |
| 策略配置规范（`admin_agents.profile["routing"]`） | `router/types.py` 的模块 docstring | ✅ |
| 打点收敛（R2 的旧打点撤除，改打 `record_new_call("R2")`） | `session_router.py` | ✅ |
| 路由指标（§12.2） | `libs/observability/.../metrics.py`：`qzdap_router_route_total{strategy,outcome}` + `qzdap_router_route_duration_seconds` | ✅（排队的三个指标归 Stage 3） |
| **web 建会话改走 Strategy**（台账 **R2 已清理**） | `session_router.py` 的 `create_session` | ✅ |
| `RouteDecision` 留痕 → `session_turns.route_decision` | 决策挂会话 metadata，随轮次写进轮次行 | ✅（**代填**，见 13.2-D2） |
| 架构测试（§10.2 的 4 条 + 「契约层不得反向依赖模块」） | `backend/tests/architecture/test_router_boundary.py` | ✅ |
| 扫描规则（台账 §3.1 唯一来源） | `backend/scripts/check_no_legacy_impl.sh`：`record_legacy_call\("R2"\)` **同 PR 启用** | ✅ |

**旧代码减少**：`session_router.py` 的 `agentId` 直取（含 `record_legacy_call("R2")`
打点）**删除**，收进策略链的「显式指定」规则；台账 R2 状态 → **已清理**。

### 13.2 偏差与未接管（**不假装做到**）

| # | 偏差 | 事实 | 归属 |
|---|---|---|---|
| **D1** | ~~**粘性规则（规则 1）拿不到输入**~~ → **已消解**（2026-10-31 ✓ 13.6） | Session 的只读 `lookup(session_key)` 端口已落地 ✓（Session Stage 5b ✓）→ **IM 路径把既有会话的绑定喂给规则 1** ✓；web 路径的粘性是**结构性的** ✓（会话行自带绑定 ✓，见 13.6-D10 ✓） | ✅ 已消解 |
| **D2** | **`route_decision` 的「唯一写者」在字面上不成立** | 决策的**产出者唯一是 Router**（策略链）；但写列的是 **Session 的行写者**（copilot 的 journal）—— Router 不直接写 `session_turns`（那会越权写会话表，违反 §10.2 规则 1）。实际保证是「**只有 Router 产出这一列的值**」 | 措辞修正见 §6.2 / §10.2 |
| **D3** | **业务线规则（规则 3）在 web 路径恒不命中** | 规则 3 需要「本次请求的业务线」这个输入 —— **web 路径没有这个概念**（业务线是渠道 / 工作区的属性）。⚠️ **2026-10-31 仍未消解** ✓（IM 侧也还没派生 ✓ —— 见 13.6-D9 ✓） | 渠道 / 工作区属性落地后接 |
| **D4** | **用户标签规则（规则 4）只是近似** | §1.5 的缺口没消失：部门**没有结构化字段**。实现取 `visible_scope` ∩（部门 ∪ 标签 ∪ roles）；`visible_scope` 写的是**范围类型**（默认的 `["部门"]`）时，按「用户有部门归属即命中」处理。⚠️ **IM 侧的输入已接上** ✓（服务账号的 `roles` ✓ —— 13.6 ✓） | identity 补结构化字段（之后只改适配器） |
| **D5** | ~~**`QUEUE_FULL` / `QUEUE_TIMEOUT` 暂无消费方**~~ → **已消解**（2026-10-31 ✓ 13.6） | 排队语义（Stage 3）已落地 ✓ → 两个错误码**有消费方了** ✓（`QueueFullError` / `QueueTimeoutError` ✓ + `ErrorCopy` 文案 ✓） | ✅ 已消解 |
| **D6** | ~~**`sequencer.py` 仍然没建**~~ → **已消解**（2026-10-31 ✓ 13.6） | 「没有调用方的类型就是建而不切」—— **有调用方了** ✓：`session/sequence.py`（序号分配 ✓）+ `session/queue.py`（FIFO 放行 ✓）+ `PostgresTurnQueue`（实现 ✓） | ✅ 已消解 |
| **D7** | **兜底默认 agent 需要配置才有意义** | 兜底规则读 `admin_agents.profile.routing.default`。**存量 agent 都没打这个标** → 不带 `agentId` 的建会话请求仍是 400（与改造前同形，只是文案说明「缺什么」） | 运维打标（不改代码） |


### 13.3 Stage 2 的**可做部分**：会话 key 派生（2026-10-29）

> Stage 2 的主体（Session Routing / IM 路径切换）**被 Session Stage 1 硬阻塞** ✗
> （§13.5）。但 Stage 2 有一项**不依赖 Session** 的工作 —— **会话 key 派生**
> （§4.1 的 `session_key = sha256(tenant|workspace|channel_type|channel|chat|user)`）。

| 动作 | 落点 | 状态 |
|---|---|---|
| 会话 key 派生（哈希版） | `runtimes/agent_runtime/src/qzdap_agent_runtime/router/session_key.py` —— `derive_session_key()` | ✅ |
| **删除旧的冒号拼接版**（台账 **R4 已清理**） | `runtimes/.../channels/gateway.py` 的 `build_session_key` | ✅ |
| 引用点同步 | 从未接线的 `engine.py` / `scripts/verify_e2e.py` / 两个单测 | ✅ |
| 扫描规则 | 台账 §3.1 的 R4 规则**改正目录并启用** ⚠️（原本扫 `modules/`，而旧实现在 `runtimes/` —— **这条规则从来没生效过** ✗） | ✅ |

**为什么旧实现非删不可**：冒号拼接有两个治不了的老问题 —— **分隔符注入**
（`("a:b","c")` 与 `("a","b:c")` 撞车）与**清洗歧义**（把冒号换成下划线，
`"a:b"` 与真的 `"a_b"` 又撞上）。哈希版用**长度前缀**编码，两者都不可能撞 ✓。
而且旧 key **可读**（会进日志 / 审计 / 数据库）→ 哈希版不可逆 ✓
（§12.2 的观测约束 ✓）。

**新增维度**：旧实现只有 5 维 —— 漏了 `channel_type` ✗（同一个 `channel_id`
在飞书与钉钉下不是一回事 ✓）。新实现 6 维 ✓。

**为什么现在就能删**：旧实现**无生产调用方** ✓（引用关系可证：只有从未接线的
`engine.py` / 一个开发脚本 / 两个单测）→ 按 Gateway 附录 C.8 的 **G-38 口径**
（「能证明无人调用的当场删」）执行 ✓。⚠️ 台账 §3.2 要求的「停用 + 打点」
**做不了** —— 无调用方的旧实现打点会得到恒为 0 的指标，那是**比没有指标更危险**
的状态 ✓（台账自己的警告）。


### 13.4 验收对照（§10.1）

| # | 验收项 | 状态 |
|---|---|---|
| 1 | 路由正确性 + `RouteDecision` 完整留痕 | ✅（**web + IM 都走规则链** ✓ —— 见 13.6） |
| 2 | 粘性 | ✅（**IM**：既有会话的绑定作为规则 1 的输入 ✓ —— `SessionManager.lookup` ✓；**web**：粘性是**结构性的** —— 会话行自带 agent 绑定 ✓ —— 规则链不参与 ✓） |
| 3 | 会话稳定性（同一 IM 群同一 session） | ✅（台账 R1 ✓ —— Session Stage 5b ✓） |
| 4 | 严格有序 | ✅（**开关打开时** ✓ —— `QZDAP_ROUTER_QUEUE_ENABLED` ✓；⚠️ **默认关** ✓ —— 见 13.6-D8） |
| 5 | 跨会话并行 | ✅（Router 不介入执行，天然互不阻塞） |
| 6 | 审批不阻塞 | ✅（审批挂起落 `waiting` ✓ —— **不占 FIFO 位** ✓ —— 决策 #6 ✓） |
| 7 | 跨 worker 一致 | ✅（`ingress_seq` 由**会话行原子自增**分配 ✓ + 放行靠**轮次行 CAS** ✓ —— 不依赖进程内状态 ✓） |
| 8 | 兜底安全（无命中 → 默认 agent，**消息不丢**） | ✅（规则 5 + 无默认 agent 时 400 且说明缺什么；**IM 侧退回渠道登记的 agent** ✓ —— 不丢消息 ✓） |
| 9 | 可解释（`route_decision` 可查） | ✅（会话 metadata + `session_turns.route_decision` ✓） |
| 10 | 架构测试（Router 不引框架） | ✅ `tests/architecture/test_router_boundary.py` |
| 11 | 排队超限不静默 | ✅（`QUEUE_FULL` / `QUEUE_TIMEOUT` ✓ —— **有消费方了** ✓ —— D5 消解 ✓） |
| 12 | 开关可回滚（`QZDAP_ROUTER_QUEUE_ENABLED=off`） | ✅（**默认关** ✓ —— 关掉即旧语义 ✓ —— 「拒绝 `SESSION_BUSY`」✓） |


### 13.5 Stage 2 / Stage 3 曾被 Session 阻塞（**历史** —— 已解锁 ✓）

| 本层阶段 | 硬前置 | 归属 | 现状 |
|---|---|---|---|
| **Stage 2**（Session Routing / IM 路径） | Session 的 **`resolve_or_create` + 只读 `lookup(session_key)`** 端口 | Session Stage 1 | ✅ **已解锁**（2026-10-30，Session Stage 5b ✓）→ **Stage 2 已执行** ✓（13.6） |
| **Stage 3**（FIFO 有序） | Session 的**唯一 turn 实现** | Session Stage 3 | ✅ **已解锁**（2026-10-30，Session Stage 3/5b ✓）→ **Stage 3 已执行** ✓（13.6） |

> **本层现在能做的都做完了**：Stage 0 ✓ · Stage 1 ✓ · Stage 2 ✓ · Stage 3 ✓ —— **台账 R1–R4 全「已清理」** ✓。


### 13.6 Stage 2 + Stage 3 实施结果（2026-10-31）

> **Session 层的两道门开了** ✓（§13.5）→ 本层的**主体**终于能落地 ✓。
> 本节记录**实际做了什么**与**仍然没做到的** ✓。

#### 13.6.1 Stage 2（Session Routing / IM 路径）

| 动作 | 落点 | 状态 |
|---|---|---|
| **IM 走规则链**（台账 **R19** ✓） | `modules/agent_runtime/.../application/channel_turn.py` 的 `_route()` ✓ —— **渠道登记的 agent 只是「显式指定」这一条规则的输入** ✓ | ✅ |
| 粘性输入（规则 1） | `SessionManager.lookup(session_key)` → `AgentTarget` ✓（**Router 不自己查会话表** ✓） | ✅ |
| 用户标签输入（规则 4） | 服务账号的 `roles` 随 `metadata` 带到规则链 ✓（`channel_turn_dispatcher.py` ✓） | ✅ |
| **路由不命中 → 不丢消息** | `RoutingUnavailable` → **退回渠道登记的 agent** ✓（记 warning ✓） | ✅ |
| 路由决策留痕 | 会话 metadata → `session_turns.route_decision` ✓（与 web 侧**同口径** ✓） | ✅ |
| **会话 key 接上哈希版**（台账 **R4** 的**最后一块** ✓） | `channel_turn_dispatcher.py` → `derive_session_key()` ✓ —— ⚠️ **此前哈希版只有测试在调** ✓（**建而不切** ✗✗ —— IM 路径还在用**冒号拼接的原始 key** ✓ → 渠道 ID / 群 ID **原文进了数据库** ✗） | ✅ |
| IM 会话粘性（台账 R1 ✓） | Session Stage 5b ✓（本层不动 ✓） | ✅（前一轮已达成） |

#### 13.6.2 Stage 3（同会话 FIFO 排队）

| 动作 | 落点 | 状态 |
|---|---|---|
| **排队契约**（端口 + 上限 + 超时） | `runtimes/agent_runtime/src/qzdap_agent_runtime/session/queue.py` ✓ —— `TurnQueuePort` ✓ / `wait_for_turn_slot()` ✓ | ✅ |
| **序号分配**（原子） | `session/sequence.py` ✓ —— 会话行自增 ✓（跨 worker 有效 ✓） | ✅ |
| **入队** | `session_turns.status='queued'` ✓（`journal.start_turn(ingress_seq=...)` ✓） | ✅ |
| **FIFO 放行** | `modules/agent_runtime/.../adapter/persistence/session_queue.py` 的 `PostgresTurnQueue` ✓ —— **单语句 CAS** ✓（`status: queued → running` ✓） | ✅ |
| **兜底路径** | 快照落后 → **以 `session_turns` 权威值为准放行** ✓ + **修快照** ✓ + **计数告警** ✓（`qzdap_router_seq_snapshot_drift_total` ✓） | ✅ |
| **审批不占执行位** | 审批挂起落 `waiting` ✓（**不是 `running`** ✓） | ✅ |
| **排队期间的可见性** | `QueuedChunk` ✓（`position` / `waited_ms` / `estimated_wait_seconds` ✓）→ 前端能显示「排队中」✓ | ✅ |
| **超限不静默** | `QUEUE_FULL`（429 ✓）/ `QUEUE_TIMEOUT`（503 ✓）✓ + `ErrorCopy` 文案 ✓ | ✅ |
| **开关可回滚** | `QZDAP_ROUTER_QUEUE_ENABLED` ✓（**默认关** ✓ —— 关掉即旧语义 ✓） | ✅ |
| 观测 | `qzdap_router_route_total` ✓（沿用）+ **快照漂移计数** ✓ + **队列深度 / 等待时长 / 被拒计数 / 会话 key 派生次数** ✓（§12.2 的四个指标 ✓ —— **本轮补齐** ✓） | ✅ |

**旧代码减少**：**无删除** ✓ —— ⚠️ 旧路径**本来就没有顺序机制**（§5.4 的更正）✓
—— 本 Stage 是**从零新建** FIFO ✓（不是「移除 `try_claim` 的顺序职责」✓ —— 它的
互斥职责归 **Session（R3）** ✓）。

#### 13.6.3 偏差与未接管（**不假装做到**）

| # | 偏差 | 事实 | 归属 |
|---|---|---|---|
| **D8** | **排队默认关** | `QZDAP_ROUTER_QUEUE_ENABLED` **默认 false** ✓ —— 「同会话严格有序」**只有开关打开后才成立** ✓。关掉 = 旧语义（claim 失败即 `SESSION_BUSY` ✓） | 运维开开关（**不急着开** ✓ —— 打开前先在预发验证 ✓） |
| **D9** | **业务线规则（规则 3）仍无输入** | D3 未消解 ✓ —— `RoutingRequest.business_line` **两边都没人填** ✓（web 没有「业务线」概念 ✓；IM 侧的渠道配置里也还没派生 ✓）。规则本身已实现 ✓ | 渠道 / 工作区属性落地后接（**只改适配器** ✓） |
| **D10** | **web 的粘性不经过规则链** | web 建会话时**本来就没有既有会话** ✓ —— 粘性由**会话行的 agent 绑定**承担 ✓（结构性 ✓）。因此 web 路径**不需要**规则 1 ✓ | 无（设计如此 ✓） |
| **D12** | **换哈希 key 后旧的原始 key 行成为孤儿** | IM 的 `channel_session_key` 从「`channel_id:chat_id`」换成 sha256 ✓ → **旧行再也查不到** ✓（会话会新建 ✓ —— 上下文不续 ✗）。**dev 库与 demo 库各有 0 行** ✓（已核对 ✓）→ **无影响** ✓ | 无（存量 0 行 ✓） |
| **D11** | **兜底默认 agent 仍需打标** | D7 未消解 ✓ —— 存量 agent 都没打 `profile.routing.default` ✓ → IM 侧「一条规则都没命中」时**退回渠道登记的 agent** ✓（不是 400 ✓ —— **不丢消息** ✓） | 运维打标（不改代码） |

#### 13.6.4 验收对照

见 §13.4 ✓（第 4 / 7 / 11 / 12 项本轮转正 ✓）。

---

## 附录 A：已定稿的决策（2026-10-29 逐条确认）

> 以下 **10 条**决策（#1–#10）已逐条确认并定稿。**改动其中任何一条，都必须同步修改正文对应章节，并在 §8 补记受影响的阶段。**

| # | 决策 | 定稿结果 | 备选 | 影响 |
|---|---|---|---|---|
| 1 | 并发消息语义 | **S1 严格排队**（FIFO） | S2 拒绝（现状）/ S3 合并 | 前端契约、用户体验、工作量 |
| 2 | 表选择 | **启用新表** `session_turns` / `session_messages`，旧 `agent_turns` / `agent_session_messages` 迁数据后废弃 | 沿用旧表（缺幂等键/revision/版本冻结字段） | **与 Session 决策 #5 同值**（两者是同一决策的两面，已同日定稿）；与 Gateway 方案 §8 一致 |
| 3 | 默认 agent / 业务线映射的配置落点 | **`admin_agents.profile`**（不新建策略表） | 工作区级配置 / 新建 `routing_rules` 表 | 配置模型 |
| 4 | 深度任务判定与模型链解析 | **不在本层**，归 Agent 层 | 放 Strategy（但入站拿不到上下文） | 与基线图的一致性 |
| 5 | `ingress_seq` 分配方式 | **会话行原子自增**（`next_ingress_seq` 列） | 全局序列 / 分布式锁 | 跨 worker 正确性 |
| 6 | 审批中断是否占用 FIFO 执行位 | **不占用**（等待审批不阻塞新消息） | 占用（严格全局有序，但会堵死） | 死锁风险 |
| 7 | 排队上限 N / 等待超时 T / 超限错误码 | **N=5 条、T=60 秒**；`QUEUE_FULL`（409）/ `QUEUE_TIMEOUT`（504） | 无上限（无限排队）；拒绝而非排队 | 前端契约 + 资源保护 |
| 8 | 排队语义的开关 | **`QZDAP_ROUTER_QUEUE_ENABLED` 默认 off**，前端先兼容再开 | 无开关直接切（不可回滚） | 回滚成本 |
| 9 | 会话级互斥的原语 | **轮次表 CAS 为唯一权威**（`session_turns.status`）；advisory lock 仅作优化，**不用 `_xact_` 变体** | 纯 advisory lock（事务提交即失效） | 并发正确性 |
| 10 | 会话实例由谁创建 | **Router 只派生 `session_key` + 分配 `ingress_seq`；`resolve_or_create` 由 Session 执行**（R1） | R2 Router 自己查建会话（两处都能建 → 第二套真相） | 会话创建逻辑的唯一性、层间依赖顺序 |

---

## 附录 C：2026-10-29 审查修正记录

> 本方案 v1.2 → **v1.3** 的全部修正。**每条都对着 `backend/` 的代码与迁移核实过**。
>
> **决策定稿（2026-10-29）**：附录 A 的 **10 条**决策已由用户拍板，取值为本方案的建议值；正文中所有开放问句同步改为定稿表述。

| # | 级别 | 问题 | 修正 | 落点 |
|---|---|---|---|---|
| **D1** | 设计 | **骨架与 Agent 决策 #4 不自洽**：D1 取消了 Model Router / Tool Router 之后，本方案 §5.1 的对照表仍按「Strategy 选 agent ≠ Agent Router 选模型 / 工具」建立 —— 而**模型 / 工具已不是任何一层的「选择」** | **按两条轴重排**：新增 **§0.2 本层的前提**（入口一次 / 每步一次 / 配置轴不归本层）作为全篇前提；**§5.1 改为「⑤ Router.Strategy vs ⑧ Agent Router」两轴对照**（模型 / 工具两行均标「不涉及」）；§0.4 补一行「本层不产出模型 / 工具信号」；**删除 `RouteDecision.model_hint` 字段**（D1 后无消费方）| §0.2 / §0.3 / §0.4 / §3.2 / §3.3 / §5.1 / §7.3 / 附录 A |
| **D2** | 严重 | **`route_decision` 一列两写者**：Router 写 `RouteDecision`（会话入口策略决策），Agent 层也写同一列（每步专家选择）→ **后写覆盖先写**，Router 的可解释性留痕被冲掉 | **拆成两列**：0046 建 `route_decision`（**Router 唯一写者**）与 `agent_decision`（**Agent 写**）；同步 §6.2 / Stage 1 / 边界表 | §6.2 / §8 Stage 1 / Session §7.2 / Agent §4.1 / README §3.3.2 |
| **D3** | 严重 | **§8 Stage 2 缺 `lookup` 工作项**：§3.1 规则 1（会话粘性）与 §2 的两步流程都以「拿到既有会话绑定」为前提，但 Stage 2 表里只有 key 派生 / `resolve_or_create` / 入队 —— **照此施工，粘性规则无法实现** | Stage 2 补「只读 `lookup(session_key)`」行，并标注它是粘性规则的**唯一依据来源** | §8 Stage 2 |
| **D4** | 严重 | **§8 Stage 3 缺 FIFO 兜底路径**：§6.2 明确 `last_completed_seq` 是**冗余快照**，可能落后于 `session_turns` 的权威值，但 Stage 3 表里没有兜底动作 | Stage 3 补「FIFO 兜底路径」行（以权威值为准放行 + 修复快照 + 计数告警）| §8 Stage 3 / §6.2 |
| **D5** | 中 | **读路径两条并存**：§2 写「Router 读 `agent_sessions`（lookup…）是允许的」，而 §3.1 / §9 又规定 lookup 经 **Session 端口** → 两条读路径并存，§10.2 规则 1 的扫描口径判不清 | §2 明确「**既有会话绑定的读取一律经 Session 的 `lookup` 端口**；直接读表仅限 `next_ingress_seq` 分配与 `last_completed_seq` 读取」| §2 / §9 / §10.2 |
| **D6** | 中 | **旧代码减少三处对不上**：§8 对照表 Stage 5 写 ~90 行；实施方案 R-22 ~30 + R-24 ~30 = 60；实施方案汇总又写「约 130 行」并把 **`try_claim` 顺序职责 20 行**算进来 —— 但 §5.4 已更正「旧路径从来没有顺序机制」，`try_claim` 归 Session | 对照表 Stage 5 改 **~60 行**；全层合计 **~110 行**；实施方案汇总去掉 `try_claim` 20 行 | §8 对照表 / 实施方案 §3.2 |
| **D7** | 中 | **`SessionAssignment` 形状三处不一致**：§2 图写 `session_id`（缺 `agent_version`），§9 写 `session_ref` + `agent_version` | 统一为 §9 的形状（`session_ref` / `agent_id` / `agent_version` / `ingress_seq` / `predecessor_seq` / `queue_position`）；§2 图同步 | §2 / §9 / 基线 §4 |
| **D8** | 中 | **悬空引用**：§3.3 写「见 §6.3 的决策点」，但 §6.3 是「迁移草案（0045）」，配置落点在 **§6.4** | 改指 §6.4 | §3.3 |
| **D9** | 中 | **决策 #4 同号不同义**：§5.1 的「决策 #4」指本方案附录 A 的 #4，而同节又提到「Agent 决策 #4」—— 同号两义 | 本方案内的指称一律写「**Router 决策 #4**」 | §5.1 / §6.1 |

> **同步改动**：`session-refactor-plan.md`（0046 建 `agent_decision` 列 / §7.1 表终态 / §7.2 回滚）、`agent-refactor-plan.md`（§4.1 规则 3 / §7.1 / §9 Stage 4 改写 `agent_decision`）、`session-lifecycle-sequence.md`（§4 契约表补两列的写者）、`implementation-plan.md`（A-24 / R-08 / S-02 / 依赖表）、`README.md`（§3.3.2 表归属）。

---

## 附录 B：与 Gateway 方案的分工（避免重复）

| 关注点 | Gateway | Router |
|---|---|---|
| 协议解析、鉴权、归一化 | ✅ | — |
| 重复消息识别 | ✅（`session_inbox` 幂等键） | — |
| 选 agent | — | ✅ **Strategy** |
| 选会话实例 | — | ✅ **Session Routing** |
| 同一会话的先后顺序 | — | ✅ **`ingress_seq` + FIFO** |
| 同一会话同时只能跑一轮 | — | **执行权归 Session**（`session_turns.status` 的状态 CAS，唯一权威）。Router 只在**分配 `ingress_seq`** 时写 `agent_sessions.next_ingress_seq`（自己的排序列），**不碰执行权** |
| 渠道回包 | ✅ | — |
