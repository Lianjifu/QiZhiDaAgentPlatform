# 会话架构重构 · 实施方案

> 版本：3.6（2026-10-29 · **按层组织** + 独立审查后的 16 项修正 + **Session 层审查同步**（X18 → Stage 3b）+ **Context 层审查同步**（关注点 #9–#11 停用阶段统一为 Stage 4 / 决策 #2 改写为「口径对齐」/ 新增决策 #7）+ **Memory 层审查同步**（新增台账 **X19** / 关注点 #12–#13 停用阶段修正 / 决策 #11 #12 / 台账条目数 32 → 33（2026-10-30 起 36））+ **Agent 层审查同步**：**决策 #4 取消 Model Router**（模型与工具只从 agent 配置取）/ X5 归属统一为 Agent Stage 7 / A-09 删除时机修正 / 空壳数 6 → 5 / `cost_usd` 迁移号改正）+ **Agent 层骨架重排**（配置轴 / 执行轴分离；模型解析与工具绑定归 ⑨ Execution；`ToolRouterPort` → `ToolBindingPort`）
> 上一版：3.4（2026-10-29 · Memory 层审查同步）· 3.3（Context 层审查同步）· 3.2（Session 层审查同步）· 3.1（按层组织 + 16 项修正）· 3.0（按层组织重写）· 2.0（按迭代组织，已废止）
> 状态：**已定稿**（§2 的全局前置于 2026-10-29 全部完成；六层方案的 53 条决策亦已同日定稿）
> 方案集入口：[`README.md`](README.md)
> 上位基线：[`session-lifecycle-sequence.md`](session-lifecycle-sequence.md)
> 收敛台账：[`cleanup-ledger.md`](cleanup-ledger.md)
> 适用项目：`QiZhiDaAgentPlatform`
> **核心约束：最终态只有一个实现 —— 每个关注点在任一时刻只有一个实现活着，旧的或不正确的必须删掉**

---

## 0. 这份计划是什么

**六份层方案回答「每层怎么做」，这份计划回答「每层按什么顺序做、什么时候算做完、做砸了怎么退」。**

### 0.1 粒度：**按层**，不按迭代

> **v2.0 按「迭代」组织（I0–I7 跨层交织），执行时不好用** —— 一个迭代里同时改 4 层，任何一层延期都会拖住整个迭代，而且「这一层做到哪了」在迭代表里看不出来。**v3.0 改为按层组织**：主体 §3 是六层各自的完整执行计划，跨层的顺序与并行只出现在 §4。

| | 层方案 | 本计划 §3（每层一节） | 本计划 §4（跨层编排） |
|---|---|---|---|
| 粒度 | 一层（一个泳道） | **一层** | 全局 |
| 内容 | 目标架构、数据表、接口契约、验收标准 | **该层的 Stage 表、工作项、删除项、退出判据、回退点** | **层间依赖、并行窗口、排期、里程碑** |
| 问题 | 「怎么设计」 | 「**这一层怎么落地**」 | 「**六层怎么拼起来**」 |

**本计划不重新设计任何东西** —— 所有架构决策、接口形状、表结构、验收标准都在层方案里，这里只做**执行编排**。两者冲突时以**层方案**为准。

### 0.2 每层的标准模板

§3 的六节**结构完全相同**，便于横向对照与分工：

| 段 | 内容 | 回答的问题 |
|---|---|---|
| **本层目标** | 一句话 + 边界 | 这一层做完，系统多了什么能力 |
| **前置** | 本层开工前**必须**已完成的外部条件（硬依赖） | 我现在能不能开工 |
| **Stage 表** | Stage / 工作项 / 产出 / **删除的旧实现** / **旧代码减少** / 依赖 | 具体做什么、做完旧代码少多少 |
| **退出判据** | 本层完成的客观标志 | 什么算做完（**「旧的已删除」是必填项**） |
| **本层删除的旧实现汇总** | 清单 + 量级 | 这层一共要删多少东西 |
| **回退点** | 本层特有的不可逆点 | 做砸了怎么退、能不能退 |
| **本层负责的台账条目** | G/R/X 编号 | 哪些条目归我删 |
| **本层特有风险** | 只属于本层的 | 这层最容易坏在哪 |

> **「删除的旧实现」与「旧代码减少」两栏是必填的** —— 填不出来，说明这一层留下了两套实现。**这正是 2026-10-15 那次失败的防线**：当时的验收标准是「单测通过」，而不是「旧代码减少」。

### 0.3 里程碑在哪

§4.4 给出里程碑到层的映射。**本计划不重新定义里程碑** —— 判据在 [`README.md`](README.md) §6.2。

---

## 1. 全局不变量（**六层共享**）

> 这一节的内容**不属于任何一层**，但对每一层都成立。

### 1.1 不变量陈述

> **对每一个「关注点」，在任一时刻，生产环境里只允许有一个实现活着。**
>
> 「旧的或不正确的」不是「标记弃用就完事」—— **必须删除**。弃用标记与调用打点只是**删除前的观测手段**，不是终点。

### 1.2 关注点 → 唯一实现 → **归属层 · 删除时点**

**这张表是全计划的骨架。** 它把 30 个关注点映射到唯一实现、旧实现、以及**哪一层的哪个 Stage 负责删**。

> **「允许并存窗口」这一列是守卫规则的输入 —— 缺了它，CI 从第一天起就是红的。**
>
> 一个关注点从「新实现接管」到「旧实现删除」之间，**新旧必然同时存在**（这正是「先上新、后清旧」的含义）。所以守卫规则 **不能** 一上来就要求「新旧符号不得同时存在」—— 它必须**分批启用**：每条关注点的扫描规则，在**它的允许并存窗口关闭的那个 Stage** 合入时才启用（与台账 §3.1「扫描脚本在删除 PR 里同步启用对应规则」同一条原则）。
>
> **窗口为「无」的关注点**（#20 / #24–#29）：它们的旧实现**从未被生产调用过**，所以从第一天起就**不应该**出现在生产包里 —— 它们的守卫规则**立即启用**。

| # | 关注点 | **唯一实现（终态）** | 旧实现 | 旧实现删除时点 | **归属层 · Stage** | **允许并存窗口** |
|---|---|---|---|---|---|---|
| 1 | 跑一轮对话（web/api） | `session/turn_runner.py` + 模块侧 `application/turn_entry.py` | `copilot.py` 的 turn 编排（~600 行，**语义是对的**，X18） | ✅ **已清理**（2026-10-31 · S-21b ✓）—— 语义迁入即删，不是重写；**薄壳已删** ✓（`copilot.py` 只剩会话生命周期 + 审批 + 取消 ✓） | **Session · Stage 3**（切换）→ **Stage 3b**（删除）✓ | Session S3 → **S-21b 关闭** ✓ |
| 2 | 跑一轮对话（IM 入口） | 同上（**同一套**） | `use_cases/run_turn.py` + `run_turn_to_completion.py`（X2） | Gateway 切完 IM 入口后（**必须原子**，见 §1.4） | **Session · Stage 5b**（与 Gateway Stage 4a 同 PR） | Session S3–S5b |
| 3 | 入站归一化 | `gateway/normalizer.py` | `ParsedMessage` + `ChannelMessageReceived`（G4 / G5） | 直接替换 | **Gateway · Stage 3** | Gateway S3 |
| 4 | 入站去重 | `gateway/idempotency.py` + `session_inbox` | `record_request_id` + `recent_request_ids`（G1）+ IM 进程内 LRU（G6） | 直接替换 | **Gateway · Stage 1 / Stage 3** | Gateway S1–S3 |
| 5 | 身份与鉴权 | `gateway/identity.py` | `_verify_signature`（G2）+ 硬编码 `SYSTEM_USER_ID`/`SYSTEM_AGENT_ID`（G3） | 直接替换 | **Gateway · Stage 2** | Gateway S2 |
| 6 | 会话路由 | `router/strategy.py` | `session_router.py` 的 `agentId` 直取（R2） | 直接替换 | **Router · Stage 1** | Router S1 |
| 7 | 会话 key 派生 | `router/session_router.py`（哈希版） | `build_session_key`（冒号拼接版，R4） | 停用 → 删 | **Router · Stage 2 停用 → Stage 5 删** | Router S2–S5 |
| 8 | 消息有序 | `ingress_seq` + 轮次表 CAS | **无 —— 旧路径从未有过顺序机制**（`try_claim` 只做互斥；`modules/` 里 `ingress_seq` 零命中） | **全新建**，无删除项 | **Router · Stage 3** | **无** |
| 9 | 上下文组装 | `context/builder.py` | `runner._load_messages`（X8） | 停用 → 删 | **Context · Stage 4 停用 → Stage 5 删** | Context S4–S5 |
| 10 | 上下文压缩 | `context/compressor.py` | `adapter/graph/compact.py`（X9） | 停用 → 删 | **Context · Stage 4 停用 → Stage 5 删** | Context S4–S5 |
| 11 | system prompt 渲染 | `context/prompts.py`（单段式） | `adapter/llm/prompts.py` 四套模板（X10） | 停用 → 删 | **Context · Stage 4 停用 → Stage 5 删** | Context S4–S5 |
| 12 | 记忆写入 | `memory/writer.py` | `runner._remember`（X11） | 停用 → 删 | **Memory · Stage 7 删**（**停用 = Agent Stage 5 的 A-26** —— 旧写入点在此之前一直被旧循环调用，Memory Stage 3 不能停用它） | Memory S7 |
| 13 | 记忆检索 | `memory/retrieval.py` | `layered.py`（317 行，逻辑反转，X12） | 停用 → 删 | **Memory · Stage 7 删**（**从未接线 → 无停用阶段**） | Memory S7 |
| 14 | 记忆数据面 | `admin_memory_l2` + `session_memory_buffer` | `admin_memory_l1`（X13，退役）+ `admin_memory_l3`（X15，退役） | 退役 | **Memory · Stage 7** | Memory S7 |
| 15 | 记忆服务分层 | 平面 A `MemoryRuntimeService` + 平面 B `MemoryAdminService` | 原 `MemoryService` 单类（X16） | 拆分 → 删单类 | **Memory · Stage 0 拆分 → Stage 7 删** | Memory S0–S7 |
| 16 | 工具执行 | **`modules/tool` 的 `InvokeToolUseCase`**（唯一权威；`execution/tool_runtime.py` 只是端口与编排层，不是第二个执行器） | `InMemoryToolExecutor`（进程内 dict，#16） | 语义落地（幂等/重试/熔断补在 `modules/tool` 侧）→ 文件删 | **Agent · Stage 3 语义 → Stage 7 删文件** | Agent S3–S7 |
| 17 | 工具注册 | `tools/registry.py` + 真实工具服务 | `ToolServiceAdapter.list_tools` 的空 schema | 修复（补真实 schema） | **Agent · Stage 2** | Agent S2 |
| 18 | 推理循环 | `agent_loop/runner.py`（6 节点图） | `runner._run_turn_inner` 的手写 `while True`（X17，~250 行） | 停用 → 删 | **Agent · Stage 5 停用 → Stage 7 删** | Agent S5–S7 |
| 19 | Agent 图骨架 | `agent_loop/graph.py`（6 节点） | `graph/nodes.py` 的 13 节点 + `graph/builder.py` 19 节点装配 | 停用 → 删 | **Agent · Stage 7** | Agent S7 |
| 20 | 残留占位图 | ——（**它不该存在**） | `compile_loop_graph`（passthrough，从未被走过，X5） | 直接删 | **Agent · Stage 7** | **无**（从未被走过） |
| 21 | 轮次/消息存储 | `session_turns` / `session_messages` | `agent_turns` / `agent_session_messages`（X4） | 迁数据 + 对账 + 只读窗口后 DROP | **Session · Stage 6** | Session S2–S6 |
| 22 | 续传状态 | LangGraph checkpoint + `session_events` | `agent_sessions.graph_state`（X3） | 停写 → 废弃 | **Session · Stage 6** | Session S6 |
| 23 | 会话状态字段 | `session_turns.status` + `current_turn_id` | `agent_sessions.wait_status`（X6） | 停写 → DROP | ⚠️ **停写推到 Session Stage 3**（第二套 turn 实现 X2 仍靠它做互斥 —— 提前停写会让 IM 侧失去互斥）→ **Stage 6 DROP** | Session S3–S6 |
| 24 | **事件类型（前端契约）** | **`libs/schema/src/qzdap_schema/dtos/turn.py` 的 `TurnChunk`（17 种）** —— 生产在用，前端 SSE 契约在这 | `runtimes/.../result/events.py` 的 16 种 `*Event` —— ⚠️ **平行实现，生产零引用**（只有它自己的单测用）；且**少了 `InteractiveActionEvent`**（旧有 `InteractiveActionChunk`，前端 `POST /api/sessions/{id}/interactive/answer` 在用） | 从未接线 → 直接删 | **Agent · Stage 7** | **无**（从未接线） |
| 25 | **审批存储** | **`modules/governance` 的 `approvals` 表** —— 生产在用，`approve`/`deny` 校验正确 | `runtimes/.../governance/approval.py` 的 `InMemoryApprovalStore` —— 平行实现，零生产引用 | 从未接线 → 直接删 | **Agent · Stage 7** | **无**（从未接线） |
| 26 | **策略闸门** | **`modules/governance` 的 `PolicyGuard`** | `runtimes/.../governance/policy.py` 的 `InMemoryPolicyGuard` | 从未接线 → 直接删 | **Agent · Stage 7** | **无**（从未接线） |
| 27 | **审计** | **`modules/governance` 的审计器** | `runtimes/.../governance/audit.py` 的 `InMemoryAuditLogger` | 从未接线 → 直接删 | **Agent · Stage 7** | **无**（从未接线） |
| 28 | **数据主体 / 导出** | **`modules/governance` 的 `data_subject`** | `runtimes/.../governance/data_subject.py` 的 `InMemoryDataSubjectService` / `InMemoryUserDataExportService` | 从未接线 → 直接删 | **Agent · Stage 7** | **无**（从未接线） |
| 29 | **未接线包的 16 个 `InMemory*` 假实现** | **真实实现**（DB / 真实服务） | 16 个 `InMemory*`（逐条见 §1.5） | 从未接线 → 语义落地后删文件 | **Agent · Stage 7** | Agent S3–S7 |
| 30 | **审批恢复路径的幂等键** | **Gateway 生成的幂等键随轮次上下文传递**，恢复时复用同一个键 | `record_request_id("")` 的空键短路（`copilot.py:474-482` 的 `decide_approval` 不传 `clientRequestId` → 幂等被跳过 → 连点两次「同意」工具再执行一次） | 修复类（不是删除类）：键传到位即达成 | **Gateway · Stage 1**（G-09b）+ **Session · Stage 5**（X7 侧） | Gateway S1 |

### 1.3 「删除」的定义（**避免自我欺骗**）

一个旧实现算「已删除」，必须**同时**满足三条：

| # | 条件 | 怎么验 |
|---|---|---|
| 1 | **生产路径零调用** | `qzdap_legacy_calls_total{entry="X<N>"}` 累计为 0，且窗口 ≥7 天、**新路径流量占比 ≥95%**（占比 = `qzdap_new_calls_total{entry}` / (新 + 旧)，见 §2.3 C1） |
| 2 | **代码里零残留** | 台账 §3.1 的扫描规则命中数**只剩 `tests/`** |
| 3 | **数据零残留** | 旧表/旧列已 DROP（不是「保留并启用」也不是「保留不用」） |

> **只满足 1 = 弃用；只满足 1+2 = 删了代码留了数据；三条全满足 = 真的清掉了。**
>
> 台账状态机因此是：`未开始 →（接管 + 打点）→ 已弃用 →（1+2+3）→ 已清理`。
> **「已弃用」不是终态** —— **每一层**的退出判据里，「旧的已删除」是**必填项**。

### 1.4 必须原子切换的五处（**拆两步就会坏**）

台账 §3.4 列了必须原子切换的动作。落到本计划：

| 原子单元 | 为什么不能拆 | 涉及层 | 怎么保证 |
|---|---|---|---|
| **IM 渠道入口切换 + use_cases turn 删除** | 停用 turn 实现与停用渠道入口必须同 PR，否则 IM 断 | **Gateway Stage 4a + Session Stage 5b** | **同一个 PR**（§3.1 G-20 / §3.3 S-30） |
| **`ChannelMessageReceived` 发布端 + 消费端** | `services.py` 发布、`dispatch_subscriber.py` 消费 | Gateway | Stage 3 同一个 PR |
| **`graph_state` 停写 + 切读** | 同一份续传状态的读写两端 | Session | Stage 6 同一个 PR |
| **`wait_status` 停写 + 列 DROP** | 列被 repositories 写、copilot 读 | Session | **停写在 Stage 0**（旧代码还在读），**DROP 在 Stage 6**（读端已删）—— 这是唯一允许跨 Stage 的 |
| **`session_turns` 切读 + 旧表 DROP** | 物理不可逆 | Session | Stage 6 同一个 PR，且前置是备份恢复**演练过** |

> **唯一 owner 规则**：同一个旧实现只能由**一个方案**负责删除。Gateway / Router 遇到 X2（第二套 turn 实现）时**只做「确认无残留调用方」，不删**（台账 §2.0）。

### 1.5 未接线包的处置规则（**「从未接线」的第二实现**）

> **2026-10-29 核对发现**：`backend/runtimes/agent_runtime/` 里有 **16 个 `InMemory*` 假实现** + **一套平行的 `*Event` 事件类型**，**全部零生产引用**（只在它们自己的单测里出现）。
>
> 这类东西**最危险** —— 它长得像「已经建好的新实现」，而下一个人看到「`InMemoryToolExecutor` 已经写好了」就可能直接接线，接出一个「能启动但不干活」的运行时（这正是 2026-10-15 那次失败的形态）。

| 规则 | 内容 |
|---|---|
| **R1** | **`InMemory*` 只允许存在于测试**。生产路径必须用真实实现（DB / 真实服务） |
| **R2** | **终态不允许任何 `InMemory*` 留在生产包里** —— 要么被真实实现取代，要么删掉 |
| **R3** | **平行的事件类型必须收敛到前端契约那一套**：`libs/schema/dtos/turn.py` 的 `TurnChunk`。新 runtime 的 `result/events.py` 的 `*Event` 要么删、要么降级为「构造 `TurnChunk` 的工厂」，**不得两套并存** |
| **R4** | 每次**新写一个 `InMemory*`**，就要在同一 PR 里登记它将来被谁取代（台账 + 本表）—— 否则它会变成新的孤儿 |
| **R5** | **取用 ≠ 保留**。台账 §5.3 说「按需取用部件」时，取的是**语义**（如 `result/sink.py` 的重放语义），不是**那份平行类型定义** |

**16 个 `InMemory*` 的处置归属**（全部落在 **Agent · Stage 7** 删除；**语义**在更早的 Stage 落地）：

| 假实现 | 生产里的唯一实现 | 语义落地于 | 文件删除于 |
|---|---|---|---|
| `InMemoryToolExecutor` | `modules/tool` 的 `InvokeToolUseCase` | Agent Stage 3（幂等/重试/熔断补在 `modules/tool` 侧） | Agent Stage 7 |
| `InMemoryToolRegistry` | `modules/tool` 的 `tools` 表 | Agent Stage 2（**适配逻辑保留**，只删 `InMemory*` 实现） | Agent Stage 7 |
| `InMemoryLayeredMemory` | `modules/memory` 的 `MemoryService`（拆平面后） | Memory Stage 2（新 `memory/retrieval.py` 取代） | Agent Stage 7 |
| `InMemoryPolicyGuard` | `modules/governance` 的 `PolicyGuard` | Agent Stage 2（治理接线） | Agent Stage 7 |
| `InMemoryAuditLogger` | `modules/governance` 的审计器 | Agent Stage 2 | Agent Stage 7 |
| `InMemoryApprovalStore` | `modules/governance` 的 `approvals` 表 | Session Stage 5（审批挂起落库） | Agent Stage 7 |
| `InMemoryDataSubjectService` | `modules/governance` 的 `data_subject` | —（治理域，本方案集不重写） | Agent Stage 7 |
| `InMemoryUserDataExportService` | `modules/governance` 的导出 provider | —（治理域，本方案集不重写） | Agent Stage 7 |
| `InMemoryCostAttribution` | `copilot._price_of` → 新 `execution/llm_client.py` | Agent Stage 1 / Stage 3（成本结算） | Agent Stage 7 |
| `InMemoryResultSink` | Gateway 出站（`ResultSink`） | Gateway Stage 4a | Agent Stage 7 |
| `InMemoryOutboxRepository` | `outbox_dead_letters` 表 | Session Stage 4（outbox worker 接线） | Agent Stage 7 |
| `InMemoryLockManager` | 轮次表 CAS（Session 层） | Session Stage 1 | Agent Stage 7 |
| `InMemorySummaryModel` | 真实摘要模型（`qzdap_llm`） | Context Stage 2（结构化摘要） | **Context Stage 5**（随 `budget.py` 一起删） |
| `InMemoryDeepAgentFactory` / `InMemoryDeepAgent` | `deepagents.create_deep_agent`（决策 #8） | Agent Stage 6（决策 #8 采纳时） | Agent Stage 7；未采纳 → Stage 7 直接删 |
| `InMemoryOnlineEvaluator` | `modules/evaluation` | Agent Stage 5（`Evaluator` 单一判定点） | Agent Stage 7 |

> **守卫规则**：§6.2 的 `test_single_implementation.py` 增加一条 —— **生产包里不得存在 `InMemory*` 类**（测试包除外）。这条规则**在全局前置阶段就进 CI**，作为「不许新增长孤儿」的闸门。

### 1.6 「两套并存」的最短窗口有多大

每个旧实现的并存窗口 = **接管完成 → 指标归零 → 删除**，量化条件是：

```
≥ 7 天  +  新路径流量占比 ≥ 95%  +  旧路径调用累计为 0  +  窗口内无相关生产事故
```

> **「新路径流量占比」需要两个计数器，不是估算**：`qzdap_legacy_calls_total{entry}`（旧）与 `qzdap_new_calls_total{entry}`（新）**用同一套 `entry` 标签**，占比 = 新 / (新 + 旧)。**只有一个旧计数器是不够的** —— 旧路径归零但新路径也没有流量的入口，会被误判成「占比 100%」。§2.3 C1 因此要求两个计数器一起建。

**按层看，每个层内部就完成「接管 → 清理 → 删除」**，因此：

| 层 | 该层引入的并存窗口 | 何时关闭 |
|---|---|---|
| Gateway | 无（Gateway 是**替换**，不是新增 —— 旧入站逻辑在同一 PR 内删）；Stage 4a 的旧路径停用是唯一的窗口 | Gateway Stage 5 |
| Router | 无（Stage 1–3 是直接替换）；Stage 4 的停用是唯一的窗口 | Router Stage 5 |
| Session | Stage 3 停用两套 turn 实现 | Session Stage 5b（X2）/ **Stage 3b（X18）** / Stage 6 |
| Context | **Stage 4** 停用旧组装/压缩/模板（Stage 1–3 只新建，不动调用点） | Context Stage 5 |
| Memory | Stage 2–3 停用旧检索/旧写入 | Memory Stage 7 |
| Agent | Stage 1–5 逐个停用旧节点 / 旧循环 | Agent Stage 7 |

> **关键**：窗口**不叠加**。因为每层内部就完成「接管 → 清理 → 删除」，所以**全局同一时刻最多只有一层的少数关注点处于并存窗口**。
>
> **⚠️ 关注点 #24–#29 是「从未接线」型的**：它们的旧实现（`InMemory*` 与新 runtime 的 `*Event`）**从未在生产跑过**，所以**没有「接管 → 窗口 → 删除」的过程** —— 它们要么被真实实现取代，要么**直接删掉**。这类最容易漏，因为「它没在生产跑，删了应该没影响？」—— 恰恰相反：**留着它就是留了一套第二实现**，而且它长得像「现成的新实现」，会被下一个人直接接线。
>
> 如果把清理攒到最后做，就会变成 **6 个窗口同时开着** —— 那才是真正的「两套实现」。**v3.0 的分层结构就是为了避免这一点。**

---

## 2. 开工前的全局前置（**不做完不许开任何一层**）

> 这三项**不属于任何一层**，但每一层的 Stage 0 都依赖它们。

### 2.1 前置 A：拍板 51 条决策 —— 其中**一条是硬 gate**

| 决策 | 位置 | 为什么是 gate |
|---|---|---|
| **表选择**（Router 决策 #2 ↔ Session 决策 #5） | `router-refactor-plan.md` 附录 A #2 · `session-refactor-plan.md` 附录 A #5 | **五个迁移（0044–0048）的设计都依赖它**。表没定，迁移没法写；迁移没写，所有层的 Stage 0 都悬空。 |

> **状态**：✅ **已定稿（2026-10-29 用户拍板）** —— 启用新表 `session_turns` / `session_messages` / `session_events`，旧表迁数据后废弃，废弃在 **Session Stage 6**，迁移归 **Session（0046）**。**五个迁移（0044–0048）的设计不再被此项阻塞。**

**全部 53 条决策已于 2026-10-29 按各方案的建议值定稿**（Gateway 9+#2b、Router 10、Session 7、Context 7、Memory 12、Agent 8）——
上表列的是其中的**前置 gate**；下表是各层决策的定稿要点与状态：

| 层 | 条数 | 状态 | 定稿要点 |
|---|---|---|---|
| Gateway | 9（+ #2b） | ✅ 已全部定稿 | 出站归 ①；`modules/channel` 保持独立模块；#2b `session_inbox` 表归 Session；#3 改造成 strong 部分唯一索引；#4 无感重放；#5 weak 不抑制 + 标 `unprotected`；#6 不迁对象存储；#7 `/v1/sessions*` 只留兼容别名；#8 先上新后清旧；#9 限流硬编码 + 环境变量 |
| Router | 10 | ✅ 已全部定稿 | **#1 S1 严格排队（FIFO）**；#2 启用新表；#3 `admin_agents.profile`；#4 深度任务归 Agent 层；#5 会话行原子自增；#6 审批不占 FIFO 位；#7 N=5 / T=60 秒；#8 排队开关默认 off；#9 轮次表 CAS；#10 Router 只派生 key |
| Session | 7 | ✅ 已全部定稿 | #1 DELETE = 关闭；#2 复活为新会话；#3 废弃 `wait_status`；#4 审批恢复失败对用户可见；#5 启用新表（= 前置 A）；#6 审批挂起落 `session_turns.pending_approval`；#7 空闲 30 天 |
| Context | 7 | ✅ 已全部定稿 | #1 prompts 放 Builder；#2 统一按语种估算；#3 快照先不做；#4 阈值 0.70；#5 抛 `CONTEXT_TOO_LARGE`；#6 manifest 每次调用一条；#7 补 `degraded` 字段 |
| Memory | 12 | ✅ 已全部定稿 | #1 **L3 退役**；#2 向量过滤下沉 pgvector；#3 规则起步；#4 每轮写一次；#5 L1 退役；#6 走 `embedding_runtime`；#7 召回更新统计；#8 实现 `data_subject` scope；#9 沿用 `admin_memory_*`；#10 乐观并发；#11 **存量不回填**；#12 放开唯一约束 |
| Agent | 8 | ✅ 已全部定稿 | #1 自建 6 节点 StateGraph；#2 `QZDAPChatModel` 适配器；#3 复用 `agent_versions`；#4 **模型来源（早已拍板）**；#5 `unprotected` 剔除副作用工具；#6 **`tool_executions` 唯一权威**；#7 成本闸门两级；#8 Deep Agents 先验证再接 |

### 2.2 前置 B：修一个真实的打包缺陷（**5 分钟的事，但不做会埋雷**）

> **发现**：2026-10-29 核对。`modules/agent_runtime` 在 **5 个文件**里 `from qzdap_vault.actor import ActorContext`：
>
> ```
> adapter/llm/__init__.py:12 · adapter/graph/chat_model.py:13 · adapter/graph/runner.py:34
> application/use_cases/run_turn.py:47 · application/ports/__init__.py:19
> ```
>
> 但它的 `pyproject.toml` 只声明了 `qzdap-auth / kernel / llm / messaging / persistence / schema` —— **没有一个声明 `qzdap-vault`**，而 `qzdap-vault` 也**不在**这六者的传递依赖里（只有 `qzdap-channel` / `qzdap-model` / `qzdap-app` / `qzdap-embedding-runtime` 声明它，而这四个 `modules/agent_runtime` 都不依赖）。
>
> **后果**：今天能跑，是因为 `uv sync` 把整个 workspace 都装了。**任何只装 `qzdap-agent-runtime` 声明依赖的环境**（CI 的 isolated install、PyPI 包、外部部署）都会 `ModuleNotFoundError: qzdap_vault`。
>
> **这个问题在 2026-10-15 就被记录过**（[`../langgraph-1x-migration-notes.md`](../langgraph-1x-migration-notes.md) §4.1，当时列为「合并到 Stage 1 PR」），**但一直没做**。
>
> **修法**（一个 PR）：
> ```toml
> # backend/modules/agent_runtime/pyproject.toml
> dependencies = [
>     "qzdap-vault",   # ← 新增：ActorContext 来源，当前只靠 workspace 全量安装才能跑
>     ...
> ]
> ```
> **验收**：只装 `qzdap-agent-runtime` 的声明依赖后，`import qzdap.modules.agent_runtime.application.ports` 不报错。

> **状态**：✅ **已修（2026-10-31）** —— `modules/agent_runtime/pyproject.toml` 已加 `qzdap-vault` ✓ + `uv.lock` 离线重锁 ✓（**无版本变动** ✓）。
> ✅ **守门人也已到位** ✓（**P-12 / C10 已做** ✓ —— `backend/scripts/check_isolated_deps.py` ✓ + CI 的 `isolated-install` job ✓ —— 它当场又抓到 7 个包漏声明 ✗✗ → 已补 ✓）→ 同类问题**不会再犯** ✓。

### 2.3 前置 C：把收敛基础设施建起来（**不做则后面全部删不掉**）

> **`qzdap_legacy_calls_total` 这个指标在代码里不存在**（`grep` 零命中）。台账 36 条条目的「指标归零」判据**目前全部无从判定** —— 收敛机制是空的。
>
> 这与 2026-10-15 那次失败是同一个形状：**机制写在了文档里，但没有落地成代码**。

| # | 工作项 | 落点 |
|---|---|---|
| C1 | 建**两个**计数器：`LEGACY_CALLS_TOTAL` + `record_legacy_call(entry)`、**`NEW_CALLS_TOTAL` + `record_new_call(entry)`**（同一套 `entry` 标签，供「新路径流量占比 ≥95%」判定） | `libs/observability/src/qzdap_observability/metrics.py` |
| C2 | 把 `record_legacy_call` / `record_new_call` 接到**可打点的台账条目**的旧/新入口 | 各旧实现文件 |
| C3 | 建 CI 扫描脚本骨架（**先不启用**） | `backend/scripts/check_no_legacy_impl.sh`（唯一来源 = 台账 §3.1） |
| C4 | 建架构测试骨架（runtime 层 import 禁令 + **单实现扫描** + **`InMemory*` 禁令**） | `backend/tests/architecture/` |
| C5 | 指标看板：`/metrics` 暴露 + 按 `entry` 分组的查询片段 | 端点已存在，无需改 |
| C6 | **逐条登记 16 个 `InMemory*` + 平行 `*Event` 的处置归属** | 本计划 §1.5 |
| C7 | **建验收环境与脱敏样本** | 横切 H1（§5） |
| C8 | **建告警规则** | 横切 H2（§5） |
| C9 | **确认 `/v1/sessions*` 是否有仓外消费者**（前端实测只用 `/api/sessions*`） | 横切 H5（§5）；**需 API owner 拍板，非纯技术项** |
| C10 | **CI 加 isolated install 检查** | 横切 H6（§5）—— 这就是 `qzdap-vault` 那类问题的守门人 |

> **C4 要加两条规则**：
> ① 扫描「同一关注点是否存在两个实现」—— 例如 `class MemoryService` 与两个新服务类同时存在、`_run_turn_inner` 与 `AgentLoopRunner` 同时存在。**这条规则是「单实现不变量」的自动化守卫**（§6.2）。
> ② 扫描「生产包里是否存在 `InMemory*` 类」—— **这条规则的价值在拦住新增**，所以必须现在就进 CI，而不是等 Agent Stage 7 清理时才建。
>
> **C2 是最容易漏的一步**，而且**不能是「33 个全部打点」** —— 台账里有 **16 条**根本没有可打点的旧入口（14 条扫描 + G10 / X14 两条修复类）：
>
> | 类型 | 条目 | 判据类型 |
> |---|---|---|
> | **可打点**（有旧调用入口） | G1 · G2 · G3 · G6 · G7 / G8 · G9 · R1 · R2 · R4 · X2 · X8 · X9 · X10 · X11 · X17 · X18 | **指标归零** |
> | **数据类 / 旧表 / 旧列 / 从未接线**（无调用入口） | G4 / G5（数据类型）· R3（职责被 Session 接管）· X1 · X1-a · X1-b · X5 · X3（旧列）· X6（旧列）· X4（旧表）· X13 · X15（旧表）· X16 · X7（吞异常的代码模式）· X12（从未接线） | **grep 扫描 + 数据迁移/DROP** |
> | **修复类** | G10（审批恢复路径的幂等键）· X14（跨用户泄漏） | **测试判定，不进指标** |
>
> **C2 的产出是一张 38 行的「条目 → 打点位置 / 判据类型」对照表**（附录 D，覆盖台账 36 条 + X1 的两个子项 X1-a / X1-b），**逐条与台账核对**。验收标准是「**每个可打点条目都有打点，且对照表与台账逐条一致**」—— **不是「33 个 entry 标签全部有值」**（后者对无入口条目既不可达也无意义：一个从未被调用的代码，打点永远不会 inc，Prometheus 的 label 在首次 inc 前根本不出现）。
>
> **漏一个可打点的入口，那条台账就永远清不掉**（指标永远不为 0）。

---

## 3. 分层实施计划

> 每一节的结构相同（§0.2）。**Stage 编号与各层方案 §9/§11 的 Stage 编号一致** —— 本表是层方案 Stage 的**可执行展开**，不是另起一套编号。

---

### 3.1 Gateway 层

> 层方案：[`gateway-refactor-plan.md`](gateway-refactor-plan.md) · 迁移：**0044** · 台账域：**G1–G9**

**本层目标**：把**入站**收敛成一个入口 —— 五种渠道归一化成 `InboundMessage`，去重靠数据库原子 claim 而不是进程内 LRU，身份来自渠道配置而不是硬编码常量。**本层不产生新能力，只消灭分歧。**

**前置**：
- 全局前置 A/B/C 完成；
- Gateway 决策已全部定稿（✅ 已完成）。

| Stage | 工作项 | 产出 / 落点 | **删除的旧实现**（台账 / 关注点） | **旧代码减少** | 依赖 |
|---|---|---|---|---|---|
| Stage 0 · 契约与地基 | G-01 建 `gateway/` 骨架 + `types.py` | ✅ **已达成** —— `gateway/` 骨架 ✓（`types.py` ✓ / `normalizer.py` ✓ / `identity.py` ✓ / `idempotency.py` ✓ / `facade.py` ✓ / `replay.py` ✓ / `web.py` ✓ / `outbound.py` ✓ / `channels.py` ✓） 4 个类型定稿 | — | 0（纯新增） | — |
| | G-02 扩 `ErrorCode` 投影表 | ✅ **已实施**（2026-10-29）：`libs/schema/.../errors.py` 的 `ERROR_PROJECTION`（http/im/web 三套文案）+ `project_error` / `try_project_error` / `project_error_message`；**三处投放面接线**（http 错误信封 / im 出站编码器 / web 的 SSE 错误 chunk）。⚠️ **落点与 §9.1 的 `gateway/errors.py` 不同** —— 唯一一份放 `libs/schema`（Gateway 方案附录 C.8 的 G-46）| — | 0 | G-01 |
| | **G-02b 错误码收敛（跨模块）** | ✅ **已实施**（2026-10-29）：**15 个**码提升为 `ErrorCode` 枚举成员（方案 §9.0 列了 7 个 —— 实施时发现 Gateway Stage 2/4a **自己又造了 8 个**，按实况补齐），各模块 `domain/errors.py` 的 `code=` 改为 `ErrorCode.X.value`；台账 **G12 已清理**（扫描规则 + 架构测试双重守门）。✅ **2026-10-31 跨模块全量接管** ✓ —— 其余模块的 **121 个**码也进了 `ErrorCode` 枚举 ✓（枚举 40 → **160** 个成员 ✓ —— 见 G-02c 行 ✓）+ 守卫扩到**全量生产目录** ✓（`tests/architecture/test_error_code_vocabulary.py` ✓）→ 生产代码里**不再有任何错误码字面量** ✓ | — | 0 | **横切 H8**（跨模块前置） |
| | **G-02c 错误码收敛的跨模块扩展**（2026-10-31） | ✅ **已达成** —— ① **121 个码**提升为枚举成员 ✓（**扫出来的** ✓ —— AST 扫 `code=` / `"code":` / `"error_code":` 三种位置 ✓ —— 不是拍脑袋数的 ✓）→ 枚举 **40 → 160 个** ✓；② **229 处字面量**改成 `ErrorCode.X.value` ✓（15 个模块 + 5 个 lib + 契约层 + composition ✓）；③ **投影表补齐** ✓（**每个成员都有 http/im/web 三套文案** ✓ —— 此前有 **12 个成员没文案** ✓ → 漏的码用户只看到兜底 ✓）；④ **`_HTTP_STATUS` 补齐** ✓（**每个成员都有状态** ✓ —— `http_status` 是查表 ✓ → 漏一项 = 运行期 KeyError ✗✗）；⑤ **守门人从「Gateway 的 15 个」扩到「全部」** ✓（`tests/architecture/test_error_code_vocabulary.py` ✓ —— **生产代码里不许再有任何错误码字面量** ✓）；⑥ ⚠️ **词汇表从 `qzdap_schema` 搬进 `qzdap_kernel`** ✓（`libs/kernel/.../error_codes.py` ✓）—— **错误码与错误层级是同一件事** ✓ → 词汇表与错误层级住在一起 ✓ → **base 层不必反过来依赖上层** ✗✗（`kernel` 保持零依赖 ✓）；⑦ ⚠️ **唯一的线上码变更** ✓：`E_WORKSPACE_NOT_FOUND` → `WORKSPACE_NOT_FOUND` ✓（auth 自造的 `E_` 前缀 ✓ —— 只有前端 mock 用过 ✓）；⑧ ⚠️ **这批也不单独进 PR** ✓ —— **与 S-36 / S-21b / P-13 同一批走** ✓（2026-10-31 决定 ✓ —— **用户随后决定提前结束窗口** ✓ → **同批一起提交** ✓ —— 提交已在本地 main ✓ —— `35380f3d` ✓）| **G12 → 全量已清理** ✓ | **~800 行**（枚举 + 投影表 ✓ —— **旧代码减少 0 行** ✓ —— 这一批是**收敛**不是删除 ✓） | **G-02b** |
| | G-03 **迁移 0044** | ✅ **已执行**（2026-10-29）—— `session_inbox` 的 **strong 部分唯一索引** ✓ + `expires_at` ✓ `session_inbox` 加列 + 换约束：**部分唯一索引**（`WHERE key_strength='strong'`，让 weak 键不参与判重）+ `expires_at` + NOT NULL 列的**合成值/哨兵**约定 | — | 0 | G-01 |
| | G-04 建架构测试 | ✅ **已执行** —— `backend/tests/architecture/test_gateway_boundary.py` ✓（import 禁令 ✓） import 禁令 | — | 0 | — |
| | G-05 打点本层旧入口 | ✅ **已达成** —— 打点**随旧实现删除逐条撤除** ✓（台账 G1–G9 全部「已清理」✓ —— 旧实现不在场时打点必须撤 ✓ 否则指标永远非零 ✗✗） `record_legacy_call("G1".."G10")` ×10 | — | 0 | 前置 C2 |
| Stage 1 · Idempotency Guard | G-06 `IdempotencyStore` 端口 + SQL 实现 | ✅ **已达成** —— `gateway/idempotency.py` ✓（strong 走 `ON CONFLICT ... WHERE key_strength='strong' DO NOTHING RETURNING` ✓；weak 走**不带 arbiter 的普通 INSERT** ✓ —— 永不判重 ✓） **strong / weak 两条 INSERT 路径**：strong 走 `ON CONFLICT (...) WHERE key_strength='strong' DO NOTHING RETURNING`；weak 走**不带 arbiter 的普通 INSERT**（永不判重，决策 #5） | — | 0 | Stage 0 |
| | G-07 `Gateway.accept` 编排 | ✅ **已达成** —— `gateway/facade.py` ✓（①→②→③→④ 四步 ✓） ①→②→③→④ 四步 | — | 0 | G-06 |
| | G-08 web 入站切过来 | ✅ **已达成** —— `session_router.py:351` 取 `app.state.web_gateway` → `gateway.accept(...)` ✓ `session_router.py` 的 `stream_turn` 先过 `Gateway.accept` | — | 0 | G-07 |
| | **G-09 删 `record_request_id` + `recent_request_ids`** | ✅ **已清理**（台账 **G1** ✓）—— 协议方法、实现与 `recent_request_ids` 的全部读写**已删** ✓ — | **G1**（关注点 #4） | **~25 行** | G-08 |
| | **G-09b 审批恢复路径传幂等键** | ✅ **已修复**（台账 **G10** ✓）—— `decide_approval` 生成 `approval\|{approval_id}\|{decision}` 强键 ✓（连点两次「同意」只执行一次 ✓） `decide_approval` 触发的续跑请求**携带原轮次的 `clientRequestId`** → 连点两次「同意」只执行一次工具 | — | 0 | G-08 · **Session Stage 5**（X7 侧） |
| | **G-09c 过期行不当成重复** | ✅ **已达成** —— `gateway/idempotency.py` 的 `expires_at` 过期行处理 ✓ claim 命中冲突行但 `expires_at < now()` → 同事务内 `DELETE` + 重新 `INSERT`（第二道保险） | — | 0 | G-06 |
| Stage 2 · Auth Identity | G-10 `IdentityVerifier` 端口 | ✅ **已达成** —— `gateway/identity.py` ✓（web JWT / IM HMAC / internal ✓） web(JWT) / IM(HMAC) / internal 三种实现 | — | 0 | Stage 0 |
| | G-11 服务账号物化 | ✅ **已达成** —— 迁移 **0049** ✓（`channels.service_account` ✓ + 存量回填 ✓）；渠道没登记服务账号就**不跑这一轮** ✓ IM 的 actor 从渠道配置读 | — | 0 | G-10 |
| | G-12 验签迁出 | ✅ **已清理**（台账 **G2** ✓）—— `_verify_signature` 已删 ✓ `channel/application/services.py` → `gateway/identity.py` | — | 0 | G-10 |
| | G-13 补 `/v1/sessions` 租户校验 | ✅ **不适用** —— 该路由**整体已删**（Stage 5 ✓ —— 台账 G7 / G8 ✓） 或随 Stage 4a 直接删该路由 | — | 0 | G-10 |
| | **G-13b `modules/channel` 加 `qzdap-agent-runtime` 依赖** | ✅ **已执行** —— `modules/channel/pyproject.toml` 声明 `qzdap-agent-runtime-runtime` ✓ Gateway 方案 §9.2.1 的依赖方向变更 —— webhook 端点要调 `Gateway.accept`。**必须同步更新 `uv.lock`** | — | 0 | **横切 H6**（锁文件） |
| | **G-14 删验签分支 + 硬编码身份常量** | ✅ **已清理**（台账 **G2 / G3** ✓） —— — | **G2 / G3**（关注点 #5） | **~60 行** | G-12 |
| Stage 3 · Message Normalizer | G-15 4 个 inbound adapter 改产 `InboundMessage` | ✅ **已达成** —— `gateway/normalizer.py` ✓（台账 G4 / G5 / G6 ✓） 补 tenant / workspace / channel / trace / attachments | — | 0 | Stage 0 |
| | G-16 附件统一 | ✅ **已达成** —— `gateway/types.py` 的 `AttachmentRef` ✓ + `AttachmentStoragePort` ✓ `AttachmentRef` + `AttachmentStoragePort` | — | 0 | G-15 |
| | **G-17 删 `ParsedMessage` + `ChannelMessageReceived` + IM 进程内 LRU** | ✅ **已清理**（台账 **G4 / G5 / G6** ✓） —— — | **G4 / G5 / G6**（关注点 #3、#4） | **~120 行** | G-15 |
| Stage 4a · 接管（重放降级） | G-18 `ResultSink` 落地 | ✅ **已达成** —— `gateway/outbound.py` ✓ 出站编码 + 卡片 + 降级规则 | — | 0 | Stage 0–3 |
| | **G-18a `Gateway.accept` 门面**（①②③）+ ④ 的三个动作 | ✅ **已达成** —— `gateway/facade.py` ✓（claim / complete / release 拆给「开始轮次的一方」✓） 编排收进一处：查渠道 → 验签 → 归一化；claim / complete / release 拆给「开始轮次的一方」 | **渠道服务内联的 ②③ 删除**（`_verify_identity` + 归一化段落） | **~70 行** | G-15 |
| | **G-18b web 入口走门面** | ✅ **已达成** —— `gateway/web.py` ✓ + `session_router.py` 的 SSE 端点改走 `Gateway.accept` ✓ `gateway/web.py`（② principal/租户头、③ 请求体 → 标准消息）+ `container.web_gateway()`；`session_router` 的 SSE 端点改走 `Gateway.accept` | **身份与幂等键各只有一个来源**（原先：端点自取租户头 + copilot 自选键） | **~40 行** | G-18a |
| | G-19 渠道入站切过来 | ✅ **已达成** —— 渠道入站 → `Gateway.accept` ✓（与 G-20 一起 ✓） `receive_webhook` → `Gateway.accept` → Router | — | 0 | G-18 |
| | **G-20 切 IM 入口（原子）** | ✅ **已达成**（2026-10-30，Session Stage 5b 同 PR）—— `dispatch_subscriber.py` → `channel_turn_dispatcher.py`（渠道侧驱动）→ Session 层 `ChannelTurnService`（**会话按 `channel_session_key` 粘住** ✓）→ **唯一 turn 实现** ✓ | 与 **Session S-32 同 PR** ✅（关注点 #2） | 0（只切不删） | — |
| | G-21 `/v1/sessions*` turn 部分停用 + 打点 | ✅ **已清理** —— `/v1/sessions*` **整体删除**（Stage 5 ✓ —— 台账 G7 / G8 ✓） — | **G7 / G8** | 0 | G-19 |
| | G-22 `dispatch_subscriber.py` 停用 + 打点 | ✅ **已达成** —— 文件**已删**（Stage 5b ✓ —— 台账 **G9** ✓） — | **G9** | 0 | G-19 |
| | G-23 重复请求降级路径 | ✅ **已被 G-25 取代** —— 重复命中改走**重放** ✓（202 分支删除 ✓ —— 台账 **G11** ✓） 命中重复但 `session_events` 未就绪 → 202 + `replay_unavailable`（**不静默丢弃**） | — | 0 | G-19 |
| Stage 4b · 无感重放 | **G-24 `Last-Event-ID` 重放** | ✅ **已达成** —— `gateway/replay.py` ✓（`StoredEvent` ✓ / `EventStore` ✓ / `event_digest` ✓）；SSE 每帧带 `id: <seq>` ✓ 从 `session_events` 按 seq 重放 —— `gateway/replay.py`（`StoredEvent` / `EventStore` 读端口 / `event_digest`）+ `Gateway.replay()`；SSE 每帧带 `id: <seq>`（live 与 replay **共用一个编码器**） | — | 0 | **Session Stage 4 完成（硬依赖，不豁免）** |
| | **G-25 降级路径移除** | ✅ **已执行** —— 202 分支与 `replay_unavailable` 删除 ✓（台账 **G11** ✓） 重复命中 → **重放上一轮的事件流**（200 + SSE）；**202 分支与 `replay_unavailable` 字段删除**（台账 **G11 已清理**）；重放不了（这一轮还在跑）→ **409** | **202 降级路径整条删除**（同一语义的两套实现 → 只留重放） | ~15 行 | G-24 |
| | **G-26 重放一致性校验** | ✅ **已达成** —— `test_copilot_duplicate_response.py::test_the_replayed_events_have_the_same_digest_as_the_original` ✓ `event_digest`（规范化摘要 —— JSONB 不保序，比的不是字节相等）+ seq 连续；真库集成测试断言「copilot 跑一轮 → 事件落库 → 门面重放 → 摘要与原流一致」 | — | 0 | G-24 |
| | **G-24b Session 侧最小交付（连带落地）** | ✅ **已达成** —— 轮次双写 ✓ + `session_events` 事件落库 ✓ + 按 seq 的读取端口 ✓ + 迁移 0050 ✓ ⚠️ **方案偏差**（Gateway 附录 C.6 的 **G-31 / G-32**）：Stage 4b 的硬依赖（Session Stage 4「`session_events` 真写真读」）**开工时不满足** —— 表在、**一行没有**。本轮**连带落地**三件事：① `session_turns` **轮次双写**（它是 `session_events.turn_id` 的外键父行）② `session_events` **事件落库**（每 chunk 一行，**先落库再投递**）③ **按 seq 的读取端口**（JOIN 轮次表按租户过滤）+ 迁移 0050 | — | ~250 行 | **Session Stage 0/2/4 的最小部分**（outbox 调度 / 死信 / 保留期仍在 Session Stage 4） |
| Stage 5 · 清理 | **G-27 删 `/v1/sessions*`（turn 部分 + 列表别名）** | ✅ **已执行**（2026-10-29）：**整个 `adapter/http/router.py` + `mappers.py` 删除**、4 个 DTO 删除、`GET /v1/sessions` 别名删除、`composition/main.py` 挂载删除；仓内调用方（perf 脚本 / 集成测试）同步迁到 `/api` | **G7 / G8** | **~280 行** | ⚠️ 依据是**引用关系**（P-11 确认无仓外消费者），不是指标（偏差 G-38 / G-39） |
| | **G-28 删 `dispatch_subscriber.py`** | ✅ **已达成**（2026-10-30，Session Stage 5b 同 PR）—— 文件**删除** ✓（取代它的是 `channel_turn_dispatcher.py` ✓） | **G9 已清理** ✅ | **~290 行** | — |
| | G-29 删 `recent_request_ids` 残留列 / 孤儿索引 / 废弃常量 | ✅ **已执行**（2026-10-29）：迁移 **0051**（`metadata - 'recent_request_ids'` + DROP `session_events` 的 `turn_id` 单列索引）—— ⚠️ 它是 **JSONB 里的键**不是列（G-43） | — | 少量 | G-09 |
| | G-30 启用扫描脚本 Gateway 段 | ✅ **已执行**（2026-10-29）：`backend/scripts/check_no_legacy_impl.sh`（规则表唯一来源 = 台账 §3.1 ✓）+ `.github/workflows/backend.yml` 的 `legacy-scan` job；**8 条 Gateway 规则启用**（⚠️ **2026-10-31 核对**：G9 的规则**也已启用** ✓ —— 旧实现已删 ✓；扫描脚本现共 **32 条启用 / 12 条待启用** ✓） | — | 0 | G-27 |
| | G-31 更新台账 + 现状文档 | ✅ **已执行**（2026-10-29）：台账（G7 / G8 → 已清理 ✓）+ `docs/copilot-chat-module-architecture.md`（API 表 + 缺陷 #9 ✓）+ 根 `README.md`（API 列表 ✓） | — | 0 | G-30 |
| | **G-31b 架构测试（§11.2）** | ✅ **已执行**（2026-10-29）：`backend/tests/architecture/test_gateway_boundary.py`（import 禁令 + Gateway 不反向依赖 ✓）+ `test_single_implementation.py`（单实现守卫 + `InMemory*` 基线 ✓）。⚠️ 方案的 `SCAN_DIRS` 含整个 `backend/runtimes`（那里有**独立的 FastAPI 服务** ✓）→ 收窄（G-40） | — | 0 | G-27 |

**退出判据**（本层完成 = 里程碑 **M0** 的一部分 + 本层清零）：
1. 五种入口经 `Gateway.accept` 后，除 `channel_type` / `raw_metadata` 外字段完全一致（参数化测试）；
2. 同一 `clientRequestId` 并发 10 次 → 只起 1 轮；**跨 worker** 有效；
3. 伪造签名 / 过期时间戳 / 跨租户重放全部拒绝**且有审计事件**；鉴权失败有 `trace_id`；
4. **台账 G1–G9 全部「已清理」**，`qzdap_legacy_calls_total{entry="G1".."G9"}` 全归零；
5. 扫描脚本 Gateway 段**零命中**；
6. **无感重放可判定**：SSE 断开带 `Last-Event-ID` 重连 → **重放拼接结果与原流 chunk 序列的 hash 相同**、seq 连续（这是 Stage 4b 的验收，机械可断言）。

**本层删除的旧实现汇总**：**G1–G9 共 9 条**，约 **735 行**（`record_request_id` 25 + 验签与硬编码身份 60 + 归一化类型与 LRU 120 + `/v1/sessions*` 280 + `dispatch_subscriber.py` 250）。

**回退点**：每个替换 PR 独立可 revert。Stage 4a–5 期间旧实现在场，回退 = `git revert` 切换提交。**Stage 5 之后不可逆**（`/v1/sessions*` 与 `dispatch_subscriber.py` 删除后，IM 渠道只有一条路）。

**本层负责的台账条目**：**G1 · G2 · G3 · G4 · G5 · G6 · G7 · G8 · G9**（唯一 owner）。

**本层特有风险**：

| 风险 | 触发信号 | 预案 |
|---|---|---|
| **IM 入口切换与 Session Stage 5b 不同 PR** | 两个 PR 都已合但只有一个生效 | **CI 校验**：G9 的删除 PR 必须引用 Session Stage 5b 的 PR 号，否则不合 |
| 鉴权收紧导致合法请求被拒 | 401/403 突增 | 回退**只回退鉴权**（安全修复不回退的是**新增**的更严规则，不是**旧的不安全实现**）—— 保留 `_verify_signature` 分支可回退 |
| `/v1/sessions*` 有仓外消费者 | 删除后 404 突增 | 前置 C9 先确认；确认不了就**保留别名并加 deprecation 头**（兼容期），但**必须写进台账的保留期限** |

---

### 3.2 Router 层

> 层方案：[`router-refactor-plan.md`](router-refactor-plan.md) · 迁移：**0045** · 台账域：**R1–R4**

**本层目标**：把**选 agent** 与**选会话**变成两个有留痕、有规则的决策 —— 策略链替代 `agentId` 直取，哈希 key 替代冒号拼接，队列保证同会话严格有序。

**前置**：
- **Router Stage 2 开工前**：**Session Stage 1 的 `SessionManager.resolve_or_create` 端口必须可用**（决策 #10）—— 没有它 Router 只能自己建会话（第二套真相）；
- **Router Stage 3 开工前**：**Session Stage 3（唯一 turn 实现）必须落地** —— 否则「有序」只对一条路径成立；
- Router 决策 #1（并发语义：排队 vs 拒绝）必须先拍板。

| Stage | 工作项 | 产出 / 落点 | **删除的旧实现**（台账 / 关注点） | **旧代码减少** | 依赖 |
|---|---|---|---|---|---|
| Stage 0 · 契约与配置 | R-01 建 `router/` 骨架 + `types.py` | ✅ **已达成** —— `router/types.py` ✓（`RouteDecision` ✓ / `UserDirectoryPort` ✓） 4 个类型定稿 | — | 0 | — |
| | R-02 **迁移 0045** | ✅ **已执行** —— `agent_sessions.next_ingress_seq` / `last_completed_seq` ✓ `agent_sessions` 加 `next_ingress_seq` / `last_completed_seq` | — | 0 | R-01 |
| | R-03 策略配置规范 | ✅ **已达成** —— `admin_agents.profile` 的路由配置 ✓（文档化 ✓ 不强制 ✓） `admin_agents.profile` 的路由配置 schema（文档化，不强制） | — | 0 | R-01 |
| | R-04 `UserDirectoryPort` 契约 | ✅ **已达成** —— `router/types.py:295` ✓（实现在 identity 侧 ✓） 定义在 router 侧，实现在 identity 侧 | — | 0 | R-01 |
| | R-05 `ErrorCode` 加 `QUEUE_FULL` / `QUEUE_TIMEOUT` | ✅ **已达成** —— `libs/schema/.../errors.py` ✓ 两个码 + `_HTTP_STATUS`（429 / 503）✓ + **文案**（`ErrorCopy` ✓） `libs/schema/.../errors.py` + `_HTTP_STATUS` 映射 | — | 0 | 决策 #7 |
| | R-06 打点本层旧入口 | ✅ **已达成** —— 打点**随旧实现删除逐条撤除** ✓（台账 R1 / R2 / R4 全「已清理」✓） `record_legacy_call("R1".."R4")` ×4 | — | 0 | 前置 C2 |
| Stage 1 · Strategy | R-07 规则链实现 | ✅ **已达成** —— `router/strategy.py` ✓（粘性 > 显式 > 业务线 > 用户标签 > 兜底 ✓） 粘性 > 显式 > 业务线 > 用户标签 > 兜底 | — | 0 | Stage 0 |
| | R-08 `RouteDecision` 留痕 | ✅ **已达成** —— `session_router.py:216` 的 `strategy.decide(...)` → `session_turns.route_decision` ✓（`adapter/turn/lifecycle.py:71` 写入 ✓） 写入 `session_turns.route_decision`（**本层唯一写者**） | — | 0 | R-07 |
| | **R-09 web 建会话改走 Strategy** | ✅ **已达成** —— `agentId` 直取**删除** ✓（台账 **R2** ✓ —— 改为「显式指定」这一条规则的输入 ✓） `session_router.py:162` → Strategy | **R2**（关注点 #6） | **~10 行** | R-08 |
| Stage 2 · Session Routing | R-10 会话 key 派生 | ✅ **已达成** —— `router/session_key.py` ✓（长度前缀 + sha256 ✓ 6 维 ✓）· ⚠️ **2026-10-31 才真正接上** ✓（此前哈希版**只有测试在调** ✓ —— **建而不切** ✗✗；IM 路径改调 `derive_session_key()` ✓ —— **原文不再进库** ✓） tenant+workspace+channel+chat+user → sha256 | — | 0 | — |
| | **R-10b 查既有会话（只读）** | ✅ **已达成** —— Session 侧 `SessionManager.lookup` ✓（Session S-08b ✓ —— 只读 ✓ 不建表 ✓） 调 Session 的 `lookup(session_key)` → 既有绑定 → **粘性规则的依据**（Gateway 的 `InboundMessage` 不含会话绑定，粘性必须先查） | — | 0 | **Session Stage 1（硬）** |
| | R-11 会话创建/复用改调 Session | ✅ **已达成** —— `channel_turn.py:58` 与 web 侧都调 `resolve_or_create` ✓（不再自建 ✓） 调 `resolve_or_create`（不再自建）；绑定 Strategy 选出的 agent | — | 0 | R-10b |
| | R-12 `ingress_seq` 分配 + 入队 | ✅ **已达成** —— **分配** ✓（`session/sequence.py` ✓ 原子自增 ✓）；**入队** ✓（`session_turns.status='queued'` ✓ —— `journal.start_turn(ingress_seq=...)` ✓） 新增列 + `session_turns.status='queued'` | — | 0 | R-11 · 迁移 0046 已落 |
| | R-13 IM 路径切换 + 旧 key 停用 | ✅ **已达成** —— IM 会话按 `channel_session_key` 粘住 ✓（台账 **R1** ✓ —— Session Stage 5b ✓） `dispatch_subscriber.py:175-186` | **R1**（行为替换）· **R4**（停用 + 打点） | **~40 行（行为）** | R-11 |
| Stage 3 · 有序处理 | R-14 FIFO 放行判定 | ✅ **已达成** —— `runtimes/agent_runtime/.../session/queue.py` ✓（契约）+ `modules/agent_runtime/.../adapter/persistence/session_queue.py` ✓（`PostgresTurnQueue` ✓ —— **单语句 CAS** ✓） `ingress_seq == last_completed_seq + 1` | — | 0 | **Session Stage 3（硬）** ✅ |
| | R-15 会话级互斥 | ✅ **已达成** —— **轮次行状态 CAS 是唯一权威** ✓（决策 #9 ✓ —— `status: queued → running` 原子改 ✓ —— 只有改成的那个 worker 能执行 ✓）；**advisory lock 不需要** ✓（事务提交即释放会让互斥形同虚设 ✗✗） 轮次表 CAS 为主；advisory lock 仅作优化（决策 #9） | — | 0 | R-14 |
| | R-16 审批中断不占执行位 | ✅ **已达成** —— 审批挂起落 `waiting` ✓（**不是 `running`** ✓ —— 不阻塞新消息 ✓，决策 #6 ✓） `waiting_approval` 是**会话级**状态 | — | 0 | R-15 |
| | R-17 并发语义切换 | ✅ **已达成** —— **排队** ✓（`TurnRunner._wait_for_slot()` ✓ —— 排队期间发 `queued` chunk ✓ —— 不再是「claim 失败即 `SESSION_BUSY`」✓；⚠️ **开关关掉时仍是旧语义** ✓） 从「拒绝 `SESSION_BUSY`」改为「排队」 | — | 0 | R-14 · 决策 #1 |
| | **R-18 FIFO 兜底路径** | ✅ **已达成** —— 快路径（快照）不成立时**以 `session_turns` 权威值为准放行** ✓ + **修 `last_completed_seq`** ✓ + **计数告警** ✓（`qzdap_router_seq_snapshot_drift_total` ✓） 快路径（快照）不成立时，以 `session_turns` 权威值为准放行 + 修复 `last_completed_seq` + 计数告警（防「快照落后 → 队列卡死」） | — | 0 | R-14 |
| Stage 4 · 接管与弃用 | R-19 渠道入站改走 Strategy + Session Routing | ✅ **已达成** —— **web 走 Strategy** ✓；**IM 也走 Strategy** ✓（`channel_turn.py` 的 `_route()` ✓ —— 渠道登记的 agent 只是「**显式指定**」这一条规则的输入 ✓；**粘性**由 `SessionManager.lookup` 提供 ✓；**路由不命中 → 退回渠道 agent** ✓ —— **不丢消息** ✓） — | — | 0 | Stage 1–3 |
| | R-20 `dispatch_subscriber.py` 停用 + 打点 | ✅ **已达成** —— 文件**已删** ✓（台账 **G9** ✓ —— 归 Gateway 删除 ✓） ⚠️ **只停用，不删**（G9 归 Gateway） | — | 0 | R-19 |
| | R-21 第二套 turn 实现停用 + 打点 | ✅ **已达成** —— 两个用例**已删** ✓（台账 **X2** ✓） ⚠️ **只停用，不删**（X2 归 Session） | — | 0 | R-19 |
| Stage 5 · 清理 | **R-22 删 `build_session_key` 冒号拼接版** | ✅ **已清理**（台账 **R4** ✓） —— — | **R4**（关注点 #7） | **~30 行** | 归零判据满足 |
| | **R-23 确认 `try_claim` 的互斥职责已由 Session 迁走** | ✅ **已清理**（台账 **R3** ✓ —— owner 是 Session ✓） ⚠️ **本层不删** —— 台账 **R3 的 owner 是 Session**（互斥归 Session 的执行权；旧路径本无顺序职责，Router 的 FIFO 是全新建） | — | 0 | — |
| | R-24 删 `catalog.py:274-281` 的展示映射 | ⚠️ **待核对** —— 现状 `catalog.py:274-281` 是 `set_favorite` ✓（旧的展示映射已不在那里 ✓）—— 未逐行比对历史版本 ✗ 若策略改用 `category` 原值 | — | **~30 行** | R-09 |
| | R-25 **确认** `dispatch_subscriber.py` 无残留调用方 | ✅ **已确认** —— 文件已删 ✓ 扫描规则已启用 ✓ ⚠️ **不删**（归 Gateway） | — | 0 | — |
| | R-26 **确认**第二套 turn 实现无残留调用方 | ✅ **已确认** —— 两个用例已删 ✓ 扫描规则已启用 ✓ ⚠️ **不删**（归 Session） | — | 0 | — |
| | R-27 启用扫描脚本 Router 段 | ✅ **已达成** —— `build_session_key` ✓ / `try_claim` ✓ 两条规则**已启用** ✓ 进 CI | — | 0 | R-22 |
| | R-28 更新台账 + 现状文档 | ✅ **已达成**（2026-10-31）—— **现状文档已更新** ✓（`docs/copilot-chat-module-architecture.md` ✓ —— §3.2 加了「路由 / 排队」两行 ✓ + §12.2 ✓ —— 与 Session S-38 / Context C-32 / Memory M-51 **同一份** ✓） | — | 0 | R-27 |

**退出判据**：
1. 同一飞书群连续 3 条消息 → **同一个 `session_id`**，跨 worker 一致；
2. 并发 5 条同会话消息 → **按入站顺序执行**，不丢不乱；不同会话并行不互阻；审批等待期间新消息可执行；
3. 兜底命中率可查；显式指定与策略冲突时按粘性规则并留痕；
4. **台账 R1–R4 全部「已清理」**，指标归零，扫描脚本 Router 段零命中。

**本层删除的旧实现汇总**：**R1–R4 共 4 条**，约 **130 行**（`agentId` 直取 10 + IM 临时会话 40 + `try_claim` 顺序职责 20 + `build_session_key` 30 + `catalog.py` 映射 30）。

**回退点**：Stage 1–3 是直接替换（每个 PR 可 revert）。Stage 4–5 期间旧实现在场，回退 = revert 切换提交。**Stage 5 之后不可逆**（`build_session_key` 冒号版删除后，新旧 key 不兼容）。

**本层负责的台账条目**：**R1 · R2 · R3 · R4**（唯一 owner）。**不删** G9 与 X2。

**本层特有风险**：

| 风险 | 触发信号 | 预案 |
|---|---|---|
| **排队语义改了前端契约** | 前端收到 `202 queued` 不知道怎么办 | 决策 #1 必须带**契约文档 + 开关**（Router 方案 §0.6）；先前端后端切 |
| **`resolve_or_create` 端口没按时可用** | Router Stage 2 开工时 Session Stage 1 未完成 | Router Stage 2 **硬依赖**，不提前；宁可延后也不自建会话 |
| **`try_claim` 的顺序职责与执行权 CAS 拆错** | 并发下出现重复执行 | 顺序与执行权**必须同时**从 `try_claim` 移走，拆一半会产生既无序又无锁的状态 |

---

### 3.3 Session 层

> 层方案：[`session-refactor-plan.md`](session-refactor-plan.md) · 迁移：**0046** · 台账：**X2 · X3 · X4 · X6 · X7 · X18**
> **本层是全局关键路径。** 它的 Stage 3（唯一 turn 实现）是四条下游支线的咽喉。

**本层目标**：把「跑一轮对话」收敛成**唯一一套语义** —— 一个会话状态机、一张轮次表、一个 turn 编排、一套事件落库。

**前置**：
- **表选择决策必须先拍板**（全局前置 A）—— 迁移 0046 的设计依赖它；
- Session 决策 #3 / #5 / #6 在 Stage 0 前拍完；
- `AsyncPostgresSaver` 接线必须在 **Stage 0**完成（不能用同步版 `PostgresSaver.from_conn_string`，会阻塞事件循环）。

| Stage | 工作项 | 产出 / 落点 | **删除的旧实现**（台账 / 关注点） | **旧代码减少** | 依赖 |
|---|---|---|---|---|---|
| Stage 0 · 契约与迁移 | S-01 建 `session/` 骨架 + `state.py` | ✅ **已实施**（2026-10-30）：`runtimes/agent_runtime/src/qzdap_agent_runtime/session/`（`state.py` / `manager.py` / `sweeper.py`）；状态机 **5 个会话状态 + 6 个轮次状态**，合法/非法转移全覆盖（`test_session_state.py`） | — | 0 | — |
| | S-02 **迁移 0046** | ✅ **已执行**（2026-10-29，早于本轮） | `pending_approval` / `cancel_requested` / `ingress_seq` / `route_decision`（**Router 写**）/ `agent_decision`（**Agent 写**）；`session_messages` 加 `session_seq`/`session_id`；`session_turns.status` 加 `queued`（先 DROP enum 再重建）；建 `langgraph_checkpoint_*` 表 | — | 0 | 决策 #5 |
| | S-03 `session_messages.session_id` 回填 | ✅ **已执行**（2026-10-29，迁移 0046 内：可空列 → 回填 → SET NOT NULL → 唯一索引；孤儿行直接报错不回填） | — | 0 | S-02 |
| | S-04 `ErrorCode` 加 `APPROVER_MUST_DIFFER` | ✅ **已实施**（2026-10-30）：`libs/schema/.../errors.py` 的枚举成员 + 投影条目；`modules/governance` 的 `ApproverMustDiffer.code` 对齐 | — | 0 | — |
| | S-05 **`AsyncPostgresSaver` 接线** | ✅ **已实施**（2026-10-30）：`langgraph.checkpoint.postgres.aio` 接进 **composition 的 lifespan**（建连接 → `setup()` → 关停时释放）；建表仍归**迁移 0046**（`setup()` 因此是幂等空跑）| **X20 已清理**（同步 saver 工厂 `graph/builder.py:from_url` **删除** —— 同步 saver 在全异步仓库里会阻塞事件循环，且无生产调用方；扫描规则 + 架构测试双重守门） | ~25 行 | S-01 |
| | S-06 停写 `wait_status` | ✅ **已达成**（2026-10-30，Stage 6）—— 三个依赖都摘掉了才停写：① 互斥迁到 `current_turn_id`（R3 ✅）② 审批挂起落进 `session_turns.pending_approval`（Stage 5a ✅）③ 读端（会话卡片 / 任务列表的「等你确认」）改成**从轮次表推导** ✓ | **X6 已清理**（关注点 #23） | 写入点归零（~20 行） | S-02 |
| | S-07 打点本层旧入口 | ✅ **已实施**（2026-10-30）：**X2**（`dispatch_subscriber`，早于本轮）· **X3 / X6**（`repositories`，早于本轮）· **X4**（`SqlTurnRepository.add` / `SqlSessionMessageRepository.append`，本轮补）· **R3**（`try_claim` + copilot 调用点，本轮补）· **X18**（`copilot.stream_turn`，早于本轮）。⚠️ **X7 的打点已撤除** —— 它的旧行为（吞异常）本轮就删了 | — | 0 | 前置 C2 |
| Stage 1 · Manager | S-08 `resolve_or_create` | ✅ **已实施**（2026-10-30）：`session/manager.py` 的 `SessionManager.resolve_or_create`（lookup → insert → **唯一约束冲突** → 有界重试 → 读回胜者）；`PostgresSessionStore` 的 `ON CONFLICT ... WHERE channel_session_key IS NOT NULL` **arbiter 带同一谓词**（否则 Postgres 认不出这个部分唯一索引） | — | 0 | Stage 0 |
| | **S-08b `lookup`（只读）** | ✅ **已实施**（2026-10-30）：`SessionManager.lookup` —— **只读**查既有会话 + 其 agent 绑定；**不创建、不写表**、查不到返回 `None`。Router 粘性规则（决策链规则 1）的依据 —— 没有它就是鸡生蛋（`resolve_or_create` 需要 `agent_binding` 入参） | — | 0 | Stage 0 |
| | S-09 `close` / `archive` | ✅ **已实施**（2026-10-30）：`SessionManager.close` / `archive`；`PostgresSessionStore` 的关闭是**终态 + 幂等**（已是终态不动），归档 = 关闭 + `metadata.archived` | — | 0 | S-08 |
| | S-10 sweeper 骨架 + 僵尸轮次接管 | ✅ **已实施**（2026-10-30）：`session/sweeper.py` + `PostgresSessionSweeper`；僵尸轮次阈值**复用同一个来源** `CLAIM_STALE_MINUTES`（两处各写一个数字迟早不一致）；转移 `running → failed` **由状态机判定**（`assert_turn_transition`） | — | 0 | S-08 |
| | **S-10b sweeper 第四类清扫** | ✅ **已实施**（2026-10-30）：删 `session_inbox` 中 `expires_at <= now()` 的行（单批 ≤1000）—— **Gateway 幂等 TTL 依赖它**（Gateway 方案 §4.3.1）；不清理则 Gateway 在 TTL 之后持续误杀。⚠️ **调度归 composition**：lifespan 里的周期任务（`QZDAP_SESSION_SWEEPER_INTERVAL`，默认 300s），**一次失败不杀任务**（下一轮继续） | — | 0 | S-10 · **Gateway Stage 0 的迁移 0044** |
| | **S-10c sweeper 第三类清扫（会话空闲）+ 复活路径** | ✅ **已实施**（2026-10-31）—— ① **复活路径** ✓（契约层 `SessionManager.resolve_or_create` ✓ —— 查到**终态**会话就**让出外部会话键** ✓（置 NULL ✓ —— 迁移 0046 的部分唯一索引 ✓）→ **新建一个接管** ✓（不是状态转移 ✓ —— `closed` 是终态 ✓）；② **空闲清扫** ✓（模块侧 `PostgresSessionSweeper._sweep_idle_sessions` ✓ —— 「最后活动」= **最后一轮的开始时间** ✓（不是会话行的 `updated_at` ✓）→ 关闭 + 记 `metadata["close_reason"]="idle_timeout"` ✓（**关闭原因之前被丢掉了** ✗✗ —— 顺手补上 ✓）；③ ⚠️ **只关「有外部会话键」的** ✓ —— 那些**有复活路径** ✓；**Web 会话不关** ✓（关了历史就从列表里消失 ✗✗ —— 方案 §3.4 点名的坑 ✓）；④ **阈值可配** ✓（`QZDAP_SESSION_IDLE_TIMEOUT_DAYS` ✓ —— 默认 30 天 ✓ —— 决策 #7 ✓）—— 测试：契约层单测（终态会话 → 复活成新会话 ✓）+ 真库集成测试（空闲的 IM 会话被关 ✓ / Web 会话不动 ✓）| — | 0 | S-10b |
| | **S-11 删 `try_claim` 的 `wait_status` 分支** | ✅ **已达成**（2026-10-31）—— **X2 已在 Stage 5b 删除** ✓ → 阻塞解除 ✓ → `try_claim` 及其 `wait_status` CAS **随台账 R3 一起删掉** ✓（`SessionRepository` 协议里的方法一并删 ✓）；旧打点 `record_legacy_call("R3")` 撤除 ✓ | **R3（关注点 #23）** | **~20 行** | S-08 ✓ |
| Stage 2 · Thread | S-12 轮次序列 `ingress_seq` | ✅ **已实施**（2026-10-30）：契约 `session/sequence.py`（`SessionSequencePort.next_ingress_seq`）+ `PostgresSessionSequence`（**原子自增** `UPDATE ... RETURNING`，跨 worker 有效）；DDL 是 0045 的 `next_ingress_seq` 列（Router 拥有）⚠️ **调用方是 Router**（入站顺序 = FIFO 顺序）—— 消费在 **Router Stage 3** | — | 0 | S-02 |
| | S-13 消息序列 `session_seq` | ✅ **已实施**（2026-10-30）：新表 `session_messages` 的 ORM（`SessionMessageORM`）+ **计数器列** `agent_sessions.next_message_seq`（**迁移 0052**，Session 层 DDL）；分配同样是原子自增 —— ⚠️ `MAX(session_seq)+1` 在两个写者之间会撞唯一索引 ✗✗ | — | 0 | S-02 |
| | S-14 checkpoint 接线 | ✅ **已达成（以「不适用」收口）**（2026-10-31）—— 它唯一的消费者是**那张 19 节点的 LangGraph 图** ✓（**已随 Agent Stage 7 删除** ✓）→ **新的循环用会话 `metadata["resume"]` + 轮次行续传** ✓（不需要 LangGraph 的 checkpoint ✓）→ **lifespan 不再起 saver** ✓（省一个连接池 ✓）；✅ **checkpoint 表已删** ✓（**迁移 0063** ✓ —— 2026-10-31 ✓ —— S-36 那批漏了它们 ✓ → 本次补上 ✓ —— **全仓零引用** ✓ —— `checkpoint_thread_id` 死函数一起删了 ✓） | — | 0 | S-05 |
| | S-15 **双写启用**：`session_turns` / `session_messages` 开始写 | ✅ **已实施**（2026-10-30）：`session_turns` 的轮次双写早于本轮（Gateway Stage 4b ✓）；`session_messages` 的**消息双写**本轮落地 —— `PostgresSessionMessageStore`（新表 + 旧表都写），**调用方（copilot）改为依赖 `SessionMessagePort` 契约**（不再直接依赖旧表 repo ✓） | — | 写入点切换 | S-12 |
| | S-15a **切读新表** | ✅ **已达成**（2026-10-30，Stage 6c）—— 读端改成**新表** ✓（`PostgresSessionMessageStore.list_for_session` JOIN 轮次表按租户过滤 ✓ + 按 `session_seq` 排 ✓）；**工具名**进 `metadata_` ✓（否则切读后工具消息丢工具名 ✗）；旧表的**读方法删除** ✓（不留第二条读路径 ✗）。⚠️ **顺带修掉一个真 bug**：旧表只能按**轮次内**的 `seq` 排 ✗ → 多轮会话的历史**交错** ✗✗；新表按 `session_seq` 排 = 真实先后 ✓。⚠️ **demo 种子改成写新表** ✓（旧种子只写旧表 ✗ → 演示会话会点不开 ✗）⚠️ **已种下的 demo 数据要重种** ✗（旧种子的消息 `turn_id` 为空 ✗ → 搬不动 ✗）| — | 0 | S-15 |
| | S-15b **停旧写（双写结束）** | ✅ **已达成**（2026-10-30，Stage 6d）—— ① `TurnLifecycle` **不再持旧表仓库** ✓（轮次只写 `session_turns` ✓）；② 消息**只写新表** ✓；③ 旧 ORM（`TurnORM` / `LegacySessionMessageORM` / `SqlSessionMessageRepository`）与旧读方法**已删** ✓（不留第二条路径 ✗）；④ 任务卡片的「用户说了什么」改从新表 `session_turns.user_input` 取 ✓（迁移 **0055** 补列 ✓ —— 不补就是**静默降级** ✗✗）；⑤ 真库对账差异 = 0 ✓（dev + demo 各一遍 ✓）。⚠️ **旧表还在**（只是没人写 ✗）—— DROP 归 S-36 ✓ | — | 旧表写入归零 ✅ | S-15a ✅ |
| Stage 3 · 唯一 turn 实现 | S-16 `turn_runner.py` 落地 | ✅ **已达成**（2026-10-30，Stage 3b）—— 编排（轮次行 / 消息 / 事件 / 终态 / 取消 / 审批挂起）迁到契约层 `session/turn_runner.py`；能力全部走**窄端口**（执行器 / 生命周期 / 消息 / 会话状态 / 取消）；模块侧适配器在 `adapter/turn/`。⚠️ **执行器仍是旧的 graph runner**（台账 X17，归 Agent 层 A-26）—— 本层只管编排 ✓ | **X18 编排已迁出**（旧编排的私有符号 `_fail_turn` / `_publish_chunk` 都已消失 ✓） | ~200 行（copilot 里的旧编排删除） | Stage 1–2 |
| | S-17 轮次幂等 | ✅ **已具备**（2026-10-30 核对）：`session_turns.idempotency_key` 的**部分唯一索引**（迁移 0050）+ Gateway 的 `IdempotencyGuard`（`session_inbox` strong 键原子 claim）—— 幂等**已在服役**，等 S-16 把编排迁过去时**沿用**它，不重写 | — | 0 | S-16 |
| | S-18 取消 | ✅ **已具备**（2026-10-30 核对）：`session_turns.cancel_requested` 列（迁移 0046）+ copilot 的取消轮询（`CANCEL_POLL_SECONDS`）—— 跨进程机制**已在服役**；⚠️ **「是否在飞」的判定**本轮从 `wait_status` 改成了 `current_turn_id`（互斥迁走后的必然调整 ✓） | — | 0 | S-16 |
| | S-19 成本归属 | ✅ **已具备**（2026-10-30 核对）：`journal.finish_turn(status, cost_usd=...)` 已在写 `session_turns.cost_usd` ✓ | — | 0 | S-16 |
| | S-20 **切换 web/api 入口** → 新 `turn_runner` | ✅ **已达成**（2026-10-30，Stage 3b）—— web/api 的入口（`session_router.py` → `copilot.stream_turn`）现在**委托**契约层的 `TurnRunner`；copilot 只剩「读 + 组装 + 转发」的薄壳 ✓ | — | 0 | S-16 |
| | S-21 停用 + 打点 `copilot.py` 的 turn 编排 | ✅ **已达成**（2026-10-30，Stage 3b）—— 旧编排**迁出**（`_fail_turn` / `_publish_chunk` / `_next_seq` / `_auto_title` 全部删除）；旧打点 `record_legacy_call("X18")` **撤除**（旧实现不在场 → 打点该撤 ✓）；**薄壳本身**（幂等 + claim + 转发）的删除落在 **Stage 3b · S-21b**（清理窗口 ≥7 天） | **X18 → 编排已迁出**（关注点 #1） | **~200 行** | S-20 |
| | S-22 停用 + 打点 `use_cases/run_turn*.py` | ✅ **已达成**（2026-10-30，Stage 5b）—— IM 入口切到唯一 turn 实现 ✓ → 两个用例**删除** ✓ → 打点随代码一起撤除 ✓ | **X2 已清理**（关注点 #2） | **~600 行** | S-20 |
| Stage 3b · 删 Copilot 侧旧 turn 编排 | **S-21b 删 `copilot.py` 的 turn 编排** | ✅ **已达成**（2026-10-31 ✓ —— **用户决定提前结束清理窗口** ✓（原定 2026-11-06 ✓））—— ① **幂等 + claim + 转发 → 契约层的 `session/turn_runner.py`** ✓（`TurnRunner` 加两个窄端口 ✓ —— `IdempotencyGuard` ✓ + `TurnClaimPort` ✓ —— **编排本就归它** ✓）；② **「读 + 组装 `TurnRequest`」→ 模块侧新服务** ✓（`application/turn_entry.py` ✓ —— 「契约层不认模块侧的领域对象 ✓ —— 让模块侧组装」✓ —— `copilot._run_turn` 的内容搬过去 ✓）；③ **调用方切过去** ✓（`session_router.py` ✓ / `one_shot_turn.py` ✓ / `channel_turn.py` ✓ / `copilot.decide_approval` 的恢复路径 ✓）；④ **删 `copilot.py` 的薄壳** ✓（`stream_turn` / `_run_turn` / `_select_key` ✓）→ `copilot.py` 降级为**纯 HTTP 薄壳** ✓（会话生命周期 + 审批 + 取消 ✓）；⑤ **错误类型归属明确** ✓ —— 契约层抛 `DuplicateTurnRequest` / `TurnBusy` ✓，模块侧翻译成 `DuplicateRequestError`（带 `turn_id` ✓）/ `SessionBusyError` ✓ —— **HTTP 契约不变** ✓（409 `SESSION_BUSY` ✓ + `DUPLICATE_REQUEST` 带 `turn_id` ✓）；⑥ ⚠️ **客户端断开要显式关内层生成器** ✓（`GeneratorExit` 落在**外层**的 `yield` 上 ✓ —— 不显式关的话轮次会停在 running ✗✗ —— 补了 `aclose()` ✓ —— `test_cancelled_stream_does_not_leave_a_running_turn` 守住 ✓） | **X18 → 已清理** ✓（关注点 #1） | **~225 行**（薄壳已删 ✓） | S-20 ✅ |
| Stage 4 · 事件落库与 outbox | S-23 chunk 写 `session_events` | ✅ **已达成**（2026-10-29，Gateway Stage 4b 连带落地）—— 每个 chunk 一行 ✓，**落库先于投递** ✓ | — | 0 | Stage 3 |
| | S-24 dispatcher 接线 | ✅ **已达成**（2026-10-30，Stage 4b）—— `ChannelOutboxDispatcher`（渠道侧）+ 契约层的 `OutboxWorker`（**重试 / 退避 / 死信只有一份** ✓） | — | 0 | S-23 |
| | S-25 `Last-Event-ID` 重放 | ✅ **已达成**（2026-10-29，Gateway Stage 4b）—— 从 `session_events` 按 seq 重放 ✓ | — | 0 | S-23 |
| | S-26 outbox worker 接线 | ✅ **已达成**（2026-10-30，Stage 4b）—— `PostgresOutboxRepository`（`session_events` 上的队列 ✓）+ worker **进 lifespan** ✓（与清扫器同生命周期 ✓，可注入以便离线测 ✓） | — | 0 | S-24 |
| Stage 5 · 审批加固 | S-27 审批挂起落库 | ✅ **已实施**（2026-10-30，Stage 5a）—— 挂起时把 `approval_id` / `tool_name` / **`arguments_digest`** / `session_id` / `turn_id` / `created_at` 落进 `session_turns.pending_approval`，同时轮次状态转 `waiting` ✓（契约 `session/approval.py`；落库在 `journal.write_pending_approval` ✓） | — | 0 | Stage 3 |
| | S-28 恢复校验清单 | ✅ **已实施**（2026-10-30，Stage 5a）—— 恢复前逐项校验（层方案 §8）：挂起记录存在且是**这个**审批 / 属于**这个会话**（`APPROVAL_NOT_MATCH`）· 审批未过期（`APPROVAL_EXPIRED`）· **审批记录里的参数摘要**与挂起时一致（`TOOL_ARGUMENT_INVALID`）；自审批与「已决策」由 governance 的 `approve()` 把关 ✓。⚠️ **比对的是审批记录里的参数**（权威 ✓），不是前端传回来的参数 | — | 0 | S-27 |
| | **S-29 删 `except Exception: pass`** | ✅ **已提前完成**（2026-10-30，Session Stage 1 —— 台账 **X7 已清理**：改成「记日志 + 再抛」） | **X7 已清理** | **~5 行** | S-28 |
| | S-30 审批自动过期 | ✅ **已达成**（2026-10-31）—— **判定在治理域** ✓（`expire_if_due()` ✓ —— 只有一份判断 ✓）；清扫器**接上回调** ✓（组合根接线 ✓ —— 清扫器不引治理模块 ✓）；跨租户扫「到期未决策」✓（维护任务 ✓）；**一类失败不影响另一类** ✓ | — | 0 | S-27 ✓ |
| | S-31 审批幂等 | ✅ **已达成**（2026-10-31）—— 同 `(session_id, tool_call_id, request_hash)` → **同一个 approval ID** ✓（`uuid5` ✓ —— 确定性 ✓ —— 摘要用**全仓那一份算法** ✓）；治理侧按 `correlation_id`（**有索引** ✓）复用 ✓ → **重试不多出一条待办** ✓ | — | 0 | S-27 ✓ |
| Stage 5b · 删第二套 turn 实现 | **S-32 切 IM 入口** | ✅ **已达成**（2026-10-30）—— `dispatch_subscriber.py` → `channel_turn_dispatcher.py`（渠道侧驱动）→ Session 层的 `ChannelTurnService`（**会话按 `channel_session_key` 粘住** ✓）→ `copilot.stream_turn` → 契约层 `TurnRunner`（**唯一 turn 实现** ✓） | **与 Gateway G-20 / G-28 同 PR** ✅（IM 未断 ✓） | 0（只切不删） | — |
| | **S-33 删 `use_cases/run_turn.py` + `run_turn_to_completion.py`** | ✅ **已达成**（2026-10-30）—— 两个用例**删除** ✓；随之空掉的门面 `AgentRuntimeService` + `close_session` / `get_session` 用例**一起删** ✓；「drain 到完成」收敛到契约层 `session/completion.py` ✓（子代理 / 评估 / 委派共用同一份 ✓）；**孤儿的** `adapter/llm/prompts.py` 一并删 ✓（X10 的旧模板） | **X2（IM 侧）已清理** ✅（关注点 #2） | **~800 行**（含门面与用例） | 与 **Gateway G-20 同 PR** ✅ |
| Stage 6 · 清理与封口 | **S-34 DROP `agent_sessions.wait_status` 列** | ✅ **已达成**（2026-10-30）—— **迁移 0053**（单独迁移 ✓，不与 0046 合并）；ORM 不再映射 ✓ → **代码不再依赖这一列**（DROP 与否都不影响运行 ✓）。⚠️ dev 库待连接释放后 `make db-upgrade`（迁移 0052 / 0053） | **X6 已清理**（关注点 #23） | **1 列** | 读端已改成从轮次表推导 ✓ |
| | **S-35 停写并废弃 `agent_sessions.graph_state`** | ✅ **已达成**（2026-10-31）—— ① **续传状态改归 `metadata["resume"]`** ✓（契约层 `resume_state` ✓）；② **待审批从轮次行读** ✓（权威 ✓）；③ **plan 决策改归 metadata** ✓；④ ORM 不再映射 ✓ + **迁移 0056 DROP 列** ✓；⑤ 扫描规则 **X3 启用** ✓。⚠️ **前提的说明**：方案要求「≥95% 流量后 ≥7 天只读期」✓ —— 那是**有生产流量时**的判据 ✓；当前是**开发期** ✓（无生产流量 ✓）→ 改为「**代码里不再有读写点** + **ORM 不映射** + **扫描规则启用**」✓（等价且更强 ✓） | **X3 → 已清理**（关注点 #22） | **1 列** | 与 S-34 同 PR ✓ |
| | **S-36 迁数据 + DROP `agent_turns` / `agent_session_messages`** | ✅ **已达成**（2026-10-31 ✓ —— **用户决定提前结束只读窗口** ✓（原定 2026-11-06 ✓））—— ① **迁数据** ✓（迁移 **0054** ✓ + 对账脚本 `scripts/verify_session_tables.py` ✓）；② **切读** ✓（S-15a ✓）；③ **停旧写** ✓（S-15b ✓）；④ **全量对账差异 = 0** ✓（dev + demo 各一遍 ✓ —— **DROP 前又跑了一遍** ✓）；⑤ **备份恢复演练过** ✓（2026-10-31 ✓ —— 脚本 `scripts/backup_restore_drill.py` ✓ —— demo / dev / 测试库各一遍 ✓ + CI 加了演练步骤 ✓）；⑥ **迁移 0062 DROP 两张表** ✓（`0062_retire_legacy_tables` ✓ —— **downgrade 可重建原表** ✓ —— 含 `cost_usd` / `ck_agent_turns_status_enum` / 全部索引 ✓）；⑦ **对账脚本改为「无旧表即无事可对」** ✓（旧表已退役 ✓） | **X4 → 已清理** ✓（关注点 #21） | **2 张表** | **独占（删表）**。前置四条全满足：① 切读 ✓；② 对账差异 = 0 ✓；③ **只读窗口** ✓ —— **2026-10-30 起算 ✓ —— 原本要到 2026-11-06 ✓ —— 用户判定实质已满足 ✓ 决定提前结束 ✓**；④ 备份恢复演练 ✓。⚠️ **P-13（mypy 闸门）+ 错误码收敛那批一起走** ✓（**2026-10-31 决定** ✓ —— 错误码那批的提交已在本地 main ✓（`35380f3d` ✓ + `f37ad52b` ✓）—— **只是没开 PR** ✓） |
| | S-37 启用扫描脚本 Session 段 | ✅ **已达成**（2026-10-31 ✓）—— **X2 / X3 / X4 / X6 / X18 段全部启用** ✓（**X4 段随 S-36 一起启用** ✓ —— 旧表已 DROP ✓ —— 生产代码里不再有任何旧表名字面量 ✓ —— 连注释都改了 ✓ —— **47 条规则全部启用** ✓） | X4 已清理 ✓（关注点 #21） | 0 | S-33 · S-21b ✅ |
| | S-38 更新台账 + 现状文档 | ✅ **已达成**（2026-10-31）—— **现状文档已更新** ✓（`docs/copilot-chat-module-architecture.md` ✓ —— 版本 1.4 ✓ + §3 分层图 ✓ + §6.1/§6.2/§6.4 ✓ + §7 缺口表 ✓ + **新增 §12「重构落地后的现状」** ✓） | — | 0 | S-37 |
| | **S-39 §13.2 的架构规则 1 / 2 落地** | ✅ **已达成**（2026-10-31）—— ① **规则 1「只有一个 turn 实现」** ✓：模块侧的 `SessionGraphRunner.run_turn` **改名 `run_graph`** ✓（它跑的是**图**✓ —— 不是那一轮 ✓）→ 生产代码里 `run_turn` / `_run_turn` 的**定义只剩契约层 `turn_runner.py`** ✓；架构测试 `test_there_is_exactly_one_turn_implementation` ✓（别处只许**转调** ✓ —— 碰了 `AgentLoopRunner` / `SessionGraphRunner` / 执行器就是「第二套实现」✗✗ → 判红 ✓）+ `test_the_old_turn_use_cases_are_gone` ✓；② **规则 2「状态机是唯一的状态写入点」** ✓：契约层 `state.py` 增 `plan_turn_transition` ✓（**先读当前状态 → 状态机决定「写不写、写什么」** ✓ —— 同态不写 ✓ · 已在终态不覆盖 ✓ · 非法转移报错 ✓）；三个写入点全部改走它 ✓（`session_journal` 的终态 / 挂起 / 僵尸接管 ✓ + `session_sweeper` 的僵尸清扫 ✓ + `session_queue` 的放行 CAS ✓ —— **放行的状态值由状态机给** ✓ —— SQL 绑参 ✓ 不再写死字符串 ✓）；⚠️ **判据与方案原文有偏差（已记录）** ✓ —— 方案写的是「裸赋值只允许出现在 `state.py`」✓ 但 `state.py` 是**纯契约层**（不引 SQLAlchemy ✓ —— §13.2 的第一条禁令 ✓）→ 落成「**写点必须用状态机的词表与判定**」✓（架构测试按 AST 扫三种写法 ✓：建行 / 改行 / 裸 SQL ✓）| — | ~120 行 | S-21b · S-33 |

**退出判据**（本层完成 = 里程碑 **M1 + M2**）：
1. 状态机全部合法转移可用、全部非法转移报错；
2. **全仓只有一套「跑一轮」的语义**（CI 扫描脚本把关）；
3. 审批：过期 / 自审批 / 参数被改 / 重复点击 → **四种情况都不执行工具**，返回明确错误码；
4. 审批可恢复：进程重启后仍能恢复；
5. 事件可重放：SSE 断开带 `Last-Event-ID` 重连 → **重放拼接结果与原流 chunk 序列的 hash 相同**、seq 连续；投递失败进死信；
6. 幂等跨 worker 有效；取消跨 worker 生效；
7. 并发：不同会话并行不互阻，同会话严格按 `ingress_seq`；
8. **双写对账**：切读后**连续 ≥7 天**逐轮比对新旧表的行数与关键字段（`session_id` / `ingress_seq` / `status` / `cost_usd` / `agent_version`），**差异数 = 0**；
9. **台账 X2 / X3 / X4 / X6 / X7 / X18 全部「已清理」**；旧表已 DROP、旧列已 DROP。

**本层删除的旧实现汇总**：**X2 · X3 · X4 · X6 · X7 · X18 共 6 条**，约 **1600 行 + 2 张表 + 2 列**（第二套 turn 600（Stage 5b）+ `copilot.py` turn 编排 ~600（**Stage 3b**）+ `wait_status` 分支 20 + 审批吞噬 5 + 旧表迁移 ~300 + 2 列）。

> **⚠️ X18 不在 Stage 3 删**：Stage 3 只「停用 + 打点」，**删除落在 Stage 3b**（清理窗口 ≥7 天且指标归零后）—— 否则 647 行会永远停在「已弃用」，违反「停用 ≠ 删除」。

> **⚠️ 删除顺序是自底向上的，拆开就会断**：旧路径的真实调用链是
> ```
> copilot.py (X18) ──▶ runner.py._run_turn_inner (X17，**归 Agent 层**)
>                        ├─▶ _load_messages (X8，归 Context 层)
>                        └─▶ _remember (X11，归 Memory 层)
> use_cases/run_turn.py (X2) ──▶ adapter/llm/prompts.py (X10，归 Context 层)
> ```
> **下层被上层调用，所以必须先停上层、再删下层。** 这条顺序在 §4.1 的依赖表里是**硬约束，不是建议** —— 违反它就会出现「删完 `_load_messages`，还在服役的 `_run_turn_inner` 当场崩」。

**回退点**：
- Stage 0–5b：旧实现仍在场，回退 = revert；
- **Stage 3b 之后**：X18 的旧编排已删 → **Stage 3 的切换不再可 revert**（只能从 git 历史恢复代码 + 重新上线）；
- **Stage 6 之后不可逆**：4 张表的数据只能从备份恢复。**备份恢复演练是 Stage 6 的准入条件**（「测试环境验证过」不算）。

**本层负责的台账条目**：**X2 · X3 · X4 · X6 · X7 · X18**（唯一 owner）。

**本层特有风险**：

| 风险 | 触发信号 | 预案 |
|---|---|---|
| **Stage 3 拖期** | 延期 > 1 周 | 拆成「`turn_runner` 骨架」+「语义合并」两个 PR；骨架可先跑通简单问答。**这是全局咽喉**（§4.5） |
| **语义合并出错** | 双写期对账有差异 | 双写期**不做切读**；有差异就停，双写继续跑直到一致 |
| **删表后数据无法恢复** | 备份不存在 / 未演练 | **恢复演练是 Stage 6 的准入条件** |
| **Stage 5b 与 Gateway G-20 拆开** | 两个 PR 都合但只有一个生效 | **CI 校验**：G9 的删除 PR 必须引用 Session Stage 5b 的 PR 号 |

---

### 3.4 Context 层

> 层方案：[`context-refactor-plan.md`](context-refactor-plan.md) · 迁移：**0047**（依赖 0046） · 台账：**X8 · X9 · X10**

**本层目标**：把「拼上下文」变成**一件有清单的事** —— 每次模型调用都能查出它喂了什么、来自哪、为什么被淘汰。

**前置**：
- **迁移 0047 物理上必须等 0046 落地**（`agent_sessions.rolling_summary` 列依赖 0046 的 `agent_sessions` 变更）；
- Context 决策 #1 / #2 在 Stage 0 前拍完。

| Stage | 工作项 | 产出 / 落点 | **删除的旧实现**（台账 / 关注点） | **旧代码减少** | 依赖 |
|---|---|---|---|---|---|
| Stage 0 · 契约与迁移 | C-01 建 `context/` 骨架 + `types.py` | ✅ **已达成**（2026-10-30，Context Stage 0）—— `context/types.py` ✓（`AssembledContext` / `ContextManifest` / `ManifestEntry` ✓，补齐 `ref_id` / `score` / `degraded` ✓）；`budget.py` 改为**导入**它 ✓（不再自己定义 ✗✗） | — | 0 | — |
| | C-02 **迁移 0047** | ✅ **已达成** —— `rolling_summary` 列 + `session_context_manifests` 表 + **三步回填** ✓（dev 库已确认存在 ✓）。⚠️ **不清 `metadata['rolling_summary']`** ✓（旧路径仍是当前唯一写者 ✗ → 清理归 Stage 4 之后 ✓） | — | 0 | **0046 已落 ✓** |
| | C-03 `tokens.py` | ✅ **已达成**（2026-10-30）—— `context/tokens.py` **按语种估算的唯一实现** ✓；**旧路径 `adapter/graph/state.py` 改调它** ✓（不再 `len//4` 一刀切 ✗✗ —— 中文不再被低估 4 倍 ✓）；单元测试 ✓（中/英/混合 ✓ + 对 `tiktoken` 偏差 <15% ✓ + **新旧差异 <10%** ✓ 实测 0% ✓）。⚠️ **压缩触发点因此前移** ✓（中文会话更早压缩 ✓） | — | 0 | — |
| | C-04 打点本层旧入口 | ✅ **已达成** —— X8 / X9 打点已有 ✓（`runner.py:569` / `runner.py:212` ✓）；X10 的旧入口**已随 Session Stage 5b 删除** ✓ → 打点自然归零 ✓ | — | 0 | 前置 C2 ✓ |
| Stage 1 · Builder | C-05 `ContextBuilder` | ✅ **已达成**（2026-10-30，Context Stage 1）—— `context/builder.py` ✓ 固定优先级拼装 → `[{role, content}]` ✓；**消息与清单成对** ✓（降级时成对丢 ✓） | — | 0 | Stage 0 ✓ |
| | C-06 agent prompts 完整接入 | ✅ **已达成** —— 五段配置（soul / prompt / agents / tools / user）按**原顺序**进 system ✓（修「agent 身份不生效」✓）；agent 没配 prompt 时**不追加** ✓（兜底句不重复 ✓） | — | 0 | C-05 ✓ |
| | C-07 单段式 prompt 渲染 | ✅ **已达成** —— `context/prompts.py` **单段式渲染** ✓（一个模板 + 可选片段 ✓）；⚠️ 四套模板**已随 Session Stage 5b 删除** ✓（台账 X10 ✓，扫描规则已启用 ✓）→ 「合并」退化为「不再需要合并」✓ | — | 0 | C-05 ✓ |
| | C-08 召回发起 | ✅ **已达成** —— Builder 主动调 `recall` / `search` ✓（契约层定义协议 ✓，模块侧适配器结构上满足 ✓）；**复刻旧路径三个参数** ✓（`top_k=8/6` ✓、按 `score` 降序 ✓、每条截 400 字 ✓）；记忆**按当前用户过滤** ✓（跨用户泄漏 X14 ✓）；**失败可见** ✓（`recall_degraded` ✓ —— 旧路径静默吞掉 ✗） | — | 0 | C-05 ✓ |
| | C-09 manifest 生成 | ✅ **已达成** —— 每段一条 ✓：来源 / token / 版本 / **`ref_id`** / **`score`** / **`filtered_reason`** / `degraded` ✓；被超预算淘汰的片段**留记录** ✓（`filtered_reason='over_budget'` ✓） | — | 0 | C-05 ✓ |
| | C-10 **只新建，不动调用点** | ✅ **已达成**（2026-10-30）—— 旧路径 `_load_messages` **仍在服役** ✓（本 Stage 没碰调用点 ✓）；⚠️ Builder 因此**暂时没有生产调用方** ✓ —— 接线归 Stage 4 ✓，前置 = **Agent Stage 5 的 A-26** ✗（归「未接管」表 ✓） | — | — | C-05 ✓ |
| | **C-10b Builder 接上生产调用方** | ✅ **已达成**（2026-10-30，**Agent A-26**）—— `runner._run_turn_inner` 的上下文装配改调 `ContextBuilder.build` ✓；**C-10 的「只新建」约束到此解除** ✓ | — | 0 | C-10 · **Agent A-26** |
| Stage 2 · Compressor | C-11 async 压缩器 | ✅ **已达成**（2026-10-30，Context Stage 2）—— `context/compressor.py` ✓ **async** ✓（摘要模型走异步端口 ✓，旧 runtime 的 `run_async_from_sync` 绕行路径不再需要 ✓） |
| | C-12 结构化摘要 | ✅ **已达成** —— 提示词点名保留**决策 / 数字 / 承诺 / 未完成事项 / 来源 ID** ✓；输入**按 role 分组** ✓；系统提示不入摘要 ✓ |
| | C-13 压缩后复验预算 | ✅ **已达成** —— 压缩后复验 ✓ → 仍超限 → 二级确定性窗口 ✓ → 仍超限 → **抛 `CONTEXT_TOO_LARGE`** ✓（明确错误 ✓ 不静默截断 ✓） |
| | C-14 `removed_ids` 按 id 差集 | ✅ **已达成** —— 按**稳定序号**（`session_seq` ✓）报 ✓；⚠️ **不引用 `message_id`** ✓（`session_messages` 没这列 ✗✗） |
| | C-15 真正的降级序 | ✅ **已达成** —— 一级摘要 → 二级确定性窗口 → **明确错误** ✓；⚠️ 降级时**追加**而不是覆盖旧摘要 ✓；工具结果清洗（截 1500 字 ✓）复刻旧路径 ✓ |
| | C-16 `context_compacted` 事件 | ✅ **已达成** —— `ContextCompactedChunk` 补 `degraded: bool = False` ✓（决策 #7 ✓ 可选字段 ✓）；旧路径的 **`tokens_before=0` 修掉** ✓（改成压缩前的真实 token 数 ✓） |
| | C-17 **只新建，不动调用点** | ✅ **已达成**（2026-10-30）—— 旧路径 `compact.py` **仍在服役** ✓；Compressor 因此**暂时没有生产调用方** ✓ → 接线归 Stage 4 ✓（前置 = Agent A-26 ✗，归「未接管」表 ✓） |
| Stage 3 · Persistence | C-18 manifest 落库 | ✅ **已达成**（2026-10-30，Context Stage 3）—— `ContextManifestStore` 端口（契约层 ✓ 不引框架 ✓）+ `PostgresContextManifestStore`（模块侧 ✓）；按 `(turn_id, step)` ✓（一次模型调用一条 ✓）；**同 step 冲突即抛错** ✓（落库后立刻 flush ✓）；**不进 outbox** ✓ —— ⚠️ **2026-10-30（Context Stage 4）接上生产调用方** ✓（`runner` 每次模型调用前落一条 ✓，演示栈实测有行 ✓） |
| | C-19 `rolling_summary` 读写迁移 | ✅ **已达成**（2026-10-30，Context Stage 4）—— **新写入只走 `agent_sessions.rolling_summary`** ✓（`save_rolling_summary` ✓）；旧写入点（Session 层的 `metadata['rolling_summary']`）**不再写** ✓；读侧改读新列 ✓（旧副本**只作过渡回退** ✓ → 清理归 Stage 5 ✓） |
| | C-20 交付前落库 | ✅ **已达成**（2026-10-30，Context Stage 4）—— manifest **在模型调用之前**落库 ✓（实测：manifest 行先于模型响应存在 ✓）；⚠️ **落库失败就让这一轮失败** ✓ —— 「模型已回答却查不到上下文」比「这一轮失败」更糟 ✗✗ |
| Stage 4 · 接线与端到端 | C-21 Agent Loop 调 Context | ✅ **已达成**（2026-10-30，**Agent A-26**）—— 旧循环 `_run_turn_inner` 的上下文装配改调 `ContextBuilder.build` ✓（⚠️ **新的 `AgentLoopRunner` 那半还没做** ✗ —— 归 Agent Stage 5 ✓） 替换「自己拼 messages」 | — | 0 | **Agent Stage 5** |
| | C-22 召回失败的 degraded 标记 | ✅ **已达成**（2026-10-31）—— **契约落地** ✓：`ChunkEnvelope.flags` ✓（对外 chunk ✓ —— 挂在信封上 ✓ —— 前端读哪块都一样 ✓）+ `ResultEvent.flags` ✓（内部协议 ✓ —— 同一个词汇 ✓）；**Context → 运行时 → 事件流 → SSE 全链路通** ✓（召回失败 → 每一块都带 `recall_degraded` ✓） | — | 0 | C-08 |
| | C-23 端到端回归 | ✅ **已达成** —— `modules/agent_runtime/tests/unit/test_context_wiring.py` ✓（长会话 ✓ 混合中英文 ✓ 召回为空 ✓ 摘要模型故障 ✓） 长会话、混合中英文、召回为空、摘要模型故障 | — | 0 | C-21 |
| | **C-24 停用 + 打点 `_load_messages` / 四套模板 / `compact.py`** | ⚠️ **前置（硬）已满足**（Agent A-26 ✅ 2026-10-30）—— 旧循环 `_run_turn_inner` 已改接 `context/builder.py` + `memory/writer.py` ✓；**X8 的调用点已归零** ✓（演示栈实测 ✓）—— 剩下的「停用 + 打点 + 删除」归 **Context Stage 4 / Stage 5** ✓ | **X8 / X9 / X10 → 已弃用**（关注点 #9、#10、#11） | — | C-21 · **Agent A-26 ✓** |
| | C-25 Agent Loop 内自拼 messages 分支停用 + 打点 | ✅ **旧循环那一半已停用** ✓（2026-10-30：随 A-26 改调 Builder ✓）—— ⚠️ `nodes.py` 的 `agent` 节点那半是**死代码** ✓（19 节点图没有生产调用方 ✓）→ 删除归 Agent Stage 7（X17）✓ | — | — | C-21 ✓ |
| Stage 5 · 清理 | **C-26 删 `adapter/graph/compact.py`** | ✅ **已达成**（2026-10-30，Context Stage 5）—— 文件已删 ✓；调用点随 Stage 4 换掉 ✓ | **X9 → 已清理**（关注点 #10） | **~53 行** | 归零判据满足 + **C-24 已停用打点** ✓ |
| | **C-27 删 `adapter/llm/prompts.py` 四函数** | ✅ **已达成** —— 旧模板随 **Session Stage 5b** 删除 ✓；新渲染（`context/prompts.py` 单段式 ✓）随 Context Stage 4 接上生产 ✓ | **X10 → 已清理**（关注点 #11） | **~60 行** | 同上 + **Session S-33** ✓ |
| | **C-28 删 `runner.py` 的 `_load_messages`** | ✅ **已达成**（2026-10-30，Context Stage 5）—— 函数已删 ✓；调用点随 A-26 换掉 ✓ | **X8 → 已清理**（关注点 #9） | **~70 行** | 同上 + **Agent A-26** ✓ |
| | **C-29 删 `runtimes/.../context/budget.py`** | ✅ **已达成**（2026-10-31，Agent Stage 7 ✓）—— 那两个旧类只被**死代码** import ✓ → **随那批整包删掉** ✓ | — | 少量 | Stage 7 ✓ |
| | C-30 删 `metadata['rolling_summary']` 残留读写 | ✅ **已达成**（2026-10-30，Context Stage 5）—— Session 层不再写 ✓、`copilot.py` 不再读 ✓（只读新列 ✓） | — | 少量 | C-19 ✓ |
- [x] C-31 启用扫描脚本 Context 段 ✓（28 → 30 条 ✓）· [x] **C-32 更新台账 + 现状文档** ✓（2026-10-31 ✓ —— 同一份现状文档 ✓）
| | C-32 更新台账 + 现状文档 | ✅ **已达成**（2026-10-31）—— **现状文档已更新** ✓（`docs/copilot-chat-module-architecture.md` ✓ —— 与 Session S-38 / Router R-28 / Memory M-51 **同一份** ✓） | — | 0 | C-31 |

**退出判据**：
1. 上下文可喂模型（`[{role, content}]`）；agent 身份正确（不再是「企业助手」通用语）；
2. 超长会话压缩后 token 在预算内；仍超限 → 明确 `CONTEXT_TOO_LARGE`，**不是**继续超限喂模型；
3. 摘要保留决策与数字；摘要模型故障 → 确定性降级不崩；
4. **任一轮都能查出它每次模型调用的上下文组成与淘汰原因**；
5. **台账 X8 / X9 / X10 全部「已清理」**，扫描脚本 Context 段零命中；
6. **旧调用点归零**：`_load_messages` / `build_system_prompt*` / `compact_messages` 在 `modules/` 与 `runtimes/` 的**生产代码里零调用方**（`grep` 命中数 = 0，仅 `tests/` 可命中）；
7. **召回失败可见**：召回异常 → `recall_degraded = true`（旧路径是静默吞掉的）；
8. **降级不丢摘要**：确定性降级后 `rolling_summary` 仍含此前轮次的结论；
9. **口径一致**：新旧两条路径的 token 估算差异 < 10%。

**本层删除的旧实现汇总**：**X8 · X9 · X10 共 3 条**，约 **570 行**（`compact.py` **53** + 四套模板 60 + `_load_messages` 70 + `budget.py` 384）。

**回退点**：Stage 0–4 旧实现仍在场，回退 = revert。**Stage 5 之后不可逆**（旧组装/压缩/模板删除后，没有第二条路径能拼上下文）。

**本层负责的台账条目**：**X8 · X9 · X10**（唯一 owner）。**不删** X5（归 Agent）。

**本层特有风险**：

| 风险 | 触发信号 | 预案 |
|---|---|---|
| **两条路径的 token 口径不一致** | 同一会话在新旧路径上的「超预算」判定不同 | 决策 #2 **统一用按语种估算**（`budget.py:42` 已是此口径），旧路径改用它；新旧差异 < 10% 作为验收 |
| **`budget.py` 拆出去后行为变了** | 压缩后 token 仍超限 | 拆分是纯搬运，**必须先有覆盖旧行为的测试**再拆 |
| **manifest 写入量最大** | `session_context_manifests` 涨超预期 | 保留期策略（层方案 §11）；只存摘要指纹而非全文 |

---

### 3.5 Memory 层

> 层方案：[`memory-refactor-plan.md`](memory-refactor-plan.md) · 迁移：**0048** · 台账：**X11–X16**

**本层目标**：把「记忆」从「每轮无条件往表里塞点东西」变成**有作用域、有置信度、有去重、有淘汰、能被后台配置改变行为**的两平面体系。

**前置**：
- **Memory Stage 1（作用域过滤）是全局最高优先级** —— 它修的是一个**正在发生的数据泄漏**，完全独立、无任何依赖，**第一天就该开工**；
- **Memory Stage 3 开工前**：**Session Stage 3（唯一 turn 实现）已落地** —— 旧写入点 `runner._remember` 属于旧 turn 实现的一部分；
- Memory 决策 #1（L3 与 knowledge 的边界）必须先拍板。

| Stage | 工作项 | 产出 / 落点 | **删除的旧实现**（台账 / 关注点） | **旧代码减少** | 依赖 |
|---|---|---|---|---|---|
| Stage 0 · 契约与迁移 | M-01 **拆分 `MemoryService`** | ✅ **已达成**（2026-10-30，Memory Stage 0）—— 运行面 `MemoryRuntimeService` ✓ + 管理面 `MemoryAdminService` ✓（新文件 `admin_service.py` ✓）；向量写入抽成**共享实现** ✓（`embedding.py` ✓）；composition **两个工厂** ✓（对话路径看不到平面 B ✓）；**X16 打点撤除** ✓ + 扫描规则启用 ✓ | **X16 → 已弃用** ✓（关注点 #15；绕过脱敏那半归 M-42 ⏳） | 0（拆分） | — |
| | M-02 建 `memory/` 骨架 + 端口 | ✅ **已达成** —— 契约层新建 `extraction.py` / `redaction.py` / `policy.py` / `retrieval.py` / `writer.py` / `scope.py` ✓（**只建契约** ✓ —— 实现归 Stage 2 / Stage 3 ✓） |
| | M-03 **迁移 0048** | ✅ **早已落地** ✓（M0 地基 ✓）—— L2 补列 + 回填 ✓ + 索引 ✓ + `session_memory_buffer` ✓ + **DROP 死表 `memory_l2_embeddings`** ✓（X19 ✓）+ 放开策略唯一约束 ✓ |
| | **M-03b 写入侧持久化 `owner_id`** | ✅ **早已落地** ✓ —— `write()` 把 `owner_id` 写进 `L2Fact.user_id` ✓（`user_id` 唯一可靠的来源 ✓） |
| | M-04 `RecallHit` 扩字段 | ✅ **已达成** —— 契约的 `RecallHit` 补 `scope` / `used_count` / **`ref_id`** / **`version`** ✓（后两个是 Context manifest 依赖的 ✓）；**生产返回改用 `RecallHit`** ✓（不再返回 5 键 dict ✓），dict 转换只在 agent_runtime 的适配器一处 ✓ |
| | M-05 打点本层旧入口 | ✅ **已达成** —— 打点**随旧实现删除逐条撤除** ✓（X11 打点随 `_remember` 删除撤除 ✓ —— 演示栈实测 `qzdap_legacy_calls_total{entry="X11"}` = 0 ✓） `record_legacy_call("X11".."X16")` ×6 | — | 0 | 前置 C2 |
| Stage 1 · 作用域过滤 | M-06 L2 召回加 `user_id` 过滤 | ✅ **早已落地** ✓（X14 修复 ✓，2026-10-29 ✓）—— 下推到 SQL 的 WHERE ✓；**归属不明的行不召回** ✓ |
| | M-07 向量检索加 `user_id` payload 过滤 | ✅ **早已落地** ✓ —— 下沉到 pgvector ✓（决策 #2 ✓），落在 `admin_memory_vec` ✓ |
| | M-08 历史向量回填 | ✅ **早已落地** ✓（迁移 **0048** ✓）—— 按 id 关联回填 `payload.user_id` ✓；关联不上的行**保持无 user_id** ✓（按用户过滤时不可见 ✓）|
| | M-09 L3 的 `visible_scope` ACL（若保留 L3） | ⚠️ **跳过** ✓ —— 决策 #1：L3 **退役** ✓（知识归 `modules/knowledge` ✓）→ 不加 ACL ✓ |
| | **X14 修复完成即「已弃用」** | — | **X14**（**修复类条目，不是删除类**） | — | M-06 |
| Stage 2 · C2 Retrieval 重写 | M-10 向量优先 + 词法兜底 | ✅ **已达成**（2026-10-30，Memory Stage 2）—— **向量分为主 + 词法分补权重** ✓（0.7 / 0.3 ✓ —— 与旧路径同口径 ✓）；词法候选**始终**取 ✓ 替代全量扫描 | — | 0 | Stage 1 |
| | M-11 候选集 `top_k × 4` | ✅ **已达成** —— 端口的 `limit` = `top_k × 4` ✓（与 Context 的降级序一致 ✓） 替代全量 | — | 0 | M-10 |
| | M-12 去重 + 阈值 + abstain | ✅ **已达成** —— 去重按 `ref_id` + **`content_hash`** ✓（两道 ✓）；阈值 0.15 ✓；**abstained** ✓（「没召回」≠「没有相关知识」✓）|
| | M-13 provenance 补全 | ✅ **已达成** —— 每条命中带 `scope` / `used_count` / `version` / `created_at` / `content_hash` ✓；⚠️ **ORM 补上迁移 0048 已建但没映射的七列** ✓（领域实体同步 ✓）|
| | M-14 **C10 读取侧降级** | ✅ **已达成** —— 向量库 / embedding 不可用 → **纯词法** ✓ + `degraded=True` ✓（降级可见 ✓）；没配向量**不算降级** ✓|
| | M-15 **确认 `layered.py` 从未被接线** | ✅ **已核实** ✓（零生产引用 ✓）→ **没有停用阶段** ✓，删除在 Stage 7（M-44 ✓） | **X12**（关注点 #13） | 0 | M-10 ✓ |
| Stage 3 · C1 Writer 重写 | M-16 `FactExtractor`（规则起步） | ✅ **已达成**（2026-10-30，Memory Stage 3）—— `RuleFactExtractor` ✓（显式 0.95 ✓ / 陈述句 0.7 ✓ / 闲聊不记 ✓）| — | 0 | Stage 0 ✓ |
| | M-17 敏感信息闸门 `Redactor` | ✅ **已达成** —— `RuleRedactor` ✓（身份证 / 手机号 / 银行卡 / 密码 / 密钥 ✓）；命中 → **整条拒绝** ✓ + **留审计** ✓；⚠️ 手机号用前后瞻（`\b` 在中文里会漏 ✗✗）| — | 0 | M-16 ✓ |
| | M-18 幂等（`content_hash`） | ✅ **已达成** —— 规范化（NFKC + 折叠空白 + 小写 ✓，版本 1 ✓）+ 唯一约束 ✓；命中已有 hash → **更新用量而非插入** ✓ | — | 0 | M-17 ✓ |
| | M-19 置信度分级 | ✅ **已达成** —— 用户显式 0.95 ✓ / 规则 0.7 ✓（LLM 一档**预留** ✓ —— 决策 #3 ✓）| — | 0 | M-16 ✓ |
| | M-20 来源追溯 | ✅ **已达成** —— 每条记忆带 `user_id` ✓ + `source_turn_id` ✓ + `source_session` ✓ | — | 0 | M-16 ✓ |
| | M-21 **实现新 Writer，写新表** | ✅ **已达成** —— `MemoryRuntimeService.write_turn()` ✓（写 **L2** ✓，不再写 L1 ✓）；⚠️ **`runner._remember` 未停用** ✓（仍被旧循环调用 ✓ → 停用归 Agent A-26 ✓）| — | — | Stage 0 ✓ |
| Stage 4 · C6 策略绑定接线 | M-22 `enabled` | ✅ **已达成**（2026-10-31，Memory Stage 4 ✓）—— false → **一条不写** ✓（`skipped="policy_disabled"` ✓ —— 原因可见 ✓）；**解析走契约层** ✓（`PolicyBinding.to_policy()` ✓ —— 不再各处散着读 dict ✓） | — | 0 | Stage 3 |
| | M-23 `scope` | ✅ **已达成** —— **会话级 → 只召回本会话** ✓（过滤**下推到 SQL** ✓ + 向量 payload 带 session ✓）；**用户级 → 跨会话可见** ✓（默认 ✓）；**工作区级 → 明确不支持** ✓（不静默降级 ✓ —— 团队知识已迁 **knowledge** ✓ —— M-47 ✓） | — | 0 | M-22 |
| | M-24 `policyLabel` | ✅ **已达成** —— 标签**解析成保留策略** ✓（模块侧只读端口 ✓ —— `get_policy_by_label` ✓）→ 写在写入结果里 ✓（`retention_label` ✓ —— **绑定看得见** ✓）；⚠️ **执行者是淘汰器** ✓ → 归 **Stage 6（M-35）** ✓ | — | 0 | M-22 |
| | M-25 `l3EntryIds` / `knowledge_refs` | ✅ **已达成** —— 召回时**额外纳入** ✓（**绕过阈值** ✓ —— 绑定的不是搜出来的 ✓）；**按 id 取** ✓（`PinnedCandidateAdapter` ✓）；**别人的记忆看不见** ✓（不串号 ✓） | — | 0 | M-22 |
| Stage 5 · C5 向量化 + C3 提升 | M-26 向量写入统一走 embedding 服务 | ✅ **已达成**（2026-10-31，Memory Stage 5 ✓）—— embedding 调用集中在**模块侧适配器** ✓（`MemoryVectorizeAdapter` ✓）；契约层只编排 ✓ | — | 0 | Stage 2 |
| | M-27 异步补写 + 删除同步 | ✅ **已达成** —— **写路径不再内联 embedding** ✓（排进**应用级队列** ✓ —— 不阻塞对话 ✓）；**兜底补写** ✓（worker 定期扫「最近更新过的」✓ —— 丢掉的向量会被捡回来 ✓）；**删除同步删向量** ✓（端口就位 ✓ —— **调用方是 Stage 6 的淘汰器** ✓） | — | **~40 行** | M-26 |
| | M-28 `session_memory_buffer`（STM 缓冲） | ✅ **已达成** —— 表（迁移 0048 ✓）+ ORM ✓ + 仓储 ✓；**会话级策略写这里** ✓（不再写 L2 ✓ —— 决策 #5 ✓） | — | 0 | M-03 |
| | M-29 会话结束提炼 | ✅ **已达成** —— **由 sweeper 触发** ✓（与 Session 清扫器**同批调度** ✓）；**会话还在跑 → 不动** ✓（活跃度由 Session 层回答 ✓ —— Memory 不查会话表 ✓）；**过期 → 丢弃** ✓；提炼走**同一套闸门 / 去重** ✓ | — | 0 | M-28 · Session sweeper |
| | M-30 提升规则 + `PromotionEvent` 补字段 | ✅ **已达成** —— **终点是 knowledge 的候选** ✓（决策 #1 ✓ —— **不再写 L3 表** ✓ —— 台账 X15 ✓）；`PromotionEvent` 补 `from_layer` / `to_layer` / `reason` ✓（迁移 0048 建了列 ✓ —— ORM 当时没映射 ✗ → 现在映射 ✓） | — | 0 | M-29 |
| Stage 6 · C7 统计 + C4 淘汰 | M-31 统计更新 | ✅ **已达成**（2026-10-31，Memory Stage 6 ✓）—— **召回命中就更新** ✓（`used_count` / `last_used_at` / `usage_history` ✓（**真实时间戳** ✓ —— 旧的写死成「刚刚」✗）/ L3 的 `hits` ✓ —— 决策 #7 ✓） | — | 0 | Stage 5 |
| | M-32 淘汰器 | ✅ **已达成** —— 契约层 `memory/eviction.py` ✓（TTL → 条数 → 容量 ✓ 三条规则 ✓ + **LRU** ✓）；**淘汰 = 置 `retired`** ✓（**不物理删** ✓ —— 保留审计 ✓ —— §6 ✓） | — | 0 | M-31 |
| | M-33 `trend()` 改真实统计 | ✅ **已达成** —— **按天分组在 SQL 里做** ✓（`usage_by_day` ✓ —— 拉到 Python 再数 = 全量扫描 ✗✗）；旧的「拿条目数编序列」删掉 ✓ | — | 0 | M-31 |
| | M-34 接入 sweeper 调度 | ✅ **已达成** —— **与 Session 层清扫器同批调度** ✓（组合根的清扫循环里一并跑 ✓） | — | 0 | M-32 |
| | M-35 **淘汰执行器** | ✅ **已达成** —— `admin_memory_policies` 的 TTL / max_items / storage_mb **首次有执行者** ✓；**向量同步删** ✓（不留残留副本 ✓）；**按原因计数** ✓（`qzdap_memory_eviction_total{reason}` ✓） | — | 0 | M-34 |
| Stage 6b · 平面 B 落地 | M-36 B1 管理接口 | **18** 个管理端点收敛到 `MemoryAdminService` | — | 0 | Stage 0 |
| | M-37 B2 管理服务 | ✅ **已达成**（2026-10-31）—— 审核提升 ✓（→ knowledge 候选 ✓）/ 人工编辑 ✓（M-40 / M-41 ✓）/ **配置发布与生效** ✓（窄端口 `MemoryPolicyPublisherPort` ✓ → 写进 agent 行 ✓ → 运行时下一次就读到 ✓） | — | 0 | M-36 |
| | M-38 B3 管理策略 | ✅ **已达成**（2026-10-31）—— `application/admin_rules.py` ✓（平面 B 的规则单独成模块 ✓）：敏感闸门**与平面 A 共用同一实现** ✓ + **去重** ✓ + **版本化** ✓；人工编辑改走它 ✓（旧的内联逻辑删掉 ✓ —— 单一实现 ✓） | — | 0 | M-37 |
| | M-39 **C9 治理 provider** | ✅ **已达成**（2026-10-31）—— **先在治理域建 `data_subject` 接口** ✓（**契约放契约层** ✓ —— `qzdap_agent_runtime/governance/data_subject.py` ✓ —— 两边**不互相 import** ✓）+ 治理域的 `DataSubjectService` **按 scope 分发** ✓（各域自己实现一个 scope ✓ —— 决策 #8 ✓）+ **记忆域的 scope** ✓（`MemoryDataSubjectScope` ✓ —— 删 **L2 行 + 向量 + 会话缓冲** ✓ —— 「删干净」✓）+ 端点 `POST /v1/data-subject/{delete,export}` ✓（**管理员** ✓ —— 删数据不可逆 ✓）+ composition 接线 ✓（请求级 ✓ —— 各域的 scope 开着自己的会话 ✓） | — | 0 | M-36 |
| | M-40 乐观并发 | ✅ **已达成**（2026-10-31）—— 人工编辑带 `version` ✓ → 不一致 **409** ✓（**不静默后写覆盖** ✓）；管理端读回带 `version` ✓ | — | 0 | M-37 |
| | M-41 敏感闸门补齐 | ✅ **已达成**（2026-10-31）—— 管理端 `PATCH /l2/{id}` **走与平面 A 同一套闸门** ✓（命中敏感内容**整条拒绝** ✓ —— 被拒的**不入库** ✓） | — | 0 | M-37 |
| | M-42 管理端直写路径停用 + 打点 | ✅ **已达成**（2026-10-31）—— **没有直写路径可停** ✓（端点本来就走服务 ✓）→ **X16 转「已清理」** ✓ | — | 0 | M-36 ✓ |
| Stage 7 · 清理与封口 | **M-43 删 `runner._remember`** | ✅ **已达成**（2026-10-30，Memory Stage 7）—— 方法已删 ✓；**旧写入路径**（`MemoryRuntimeService.write` 87 行 ✓ + 适配器 ✓ + 端口 ✓）**一起删** ✓（它们唯一的生产调用方就是旧循环 ✓） | **X11 → 已清理**（关注点 #12） | **~117 行** | 归零判据满足 + **Agent A-26** ✓ |
| | **M-44 删 `runtimes/.../memory/layered.py`** | ✅ **已达成**（2026-10-31，Agent Stage 7 ✓）—— **已删** ✓（317 行 ✓）；**扫描规则同时覆盖 `modules/` 与 `runtimes/`** ✓ | **X12**（关注点 #13） | **317 行** | Agent Stage 7 ✓ |
| | **M-45 删 `graph/nodes.py` 的 `remember` 节点** | ✅ **已达成**（2026-10-31，Agent Stage 7 ✓）—— `nodes.py` **整体已删** ✓ | **X12** | **~30 行** | Agent Stage 7 ✓ |
| | **M-46 退役 `admin_memory_l1`** | ✅ **已达成**（2026-10-31）—— 管理端的 4 个 L1 端点**改读会话缓冲** ✓（`session_memory_buffer` ✓ —— 决策 #5 的落点 ✓ —— **契约没变** ✓）+ **迁移 0057 DROP 表** ✓（dev / demo / 测试库都跑过 upgrade ✓ —— downgrade 也能建回来 ✓）+ ORM / 仓储 / 实体 / 端口 / 演示种子里的 L1 **全删** ✓ | **X13**（✅ **已清理**） | **1 张表**（✅ 真删了） | 决策 #5 ✓ |
| | **M-47 退役 `admin_memory_l3`** | ✅ **已达成**（2026-10-31）—— **先上新** ✓：迁移 **0058** 把 L3 逐行搬进 knowledge（**team → KB** ✓ / **summary → chunk** ✓ / **doc id 沿用 L3 的 id** ✓）+ knowledge 加 **category / publish_state / contributor / origin** 四列 ✓；**再清旧** ✓：管理端 5 个 L3 端点删了 ✓、**召回路径不再查 L3** ✓（→ **运行时双份注入没了** ✓）、ORM / 实体 / 端口 / 仓储 / 候选 / 契约层（`l3EntryIds` / `MemoryRefKind.L3` / `extra_l3_entry_ids`）**全删** ✓、**迁移 0059 DROP 表** ✓（dev / demo / 测试库都跑过 ✓）+ **X15 打点撤除** ✓ + **扫描规则已启用** ✓ | **X15**（✅ **已清理**） | **1 张表**（✅ 真删了） | 决策 #1 ✓ |
| | M-48 清理 `memory_policy` 的无效语义 | ✅ **已达成**（2026-10-30）—— 旧 `autoSummarize` / `scope` 标签用法的**唯一消费者**（旧写入点）已删 ✓；**字段形状保留** ✓（前端表单按这四个字段读写 ✓）—— 「无效」指的是**运行时不再消费** ✓ | — | 少量 | Stage 4–5 ✓ |
| | **M-49 删原 `MemoryService` 单类** | ⚠️ 平面 A / B 两个服务类**必须保留** | **X16**（关注点 #15） | 少量 | M-01 |
- [x] **M-50 启用扫描脚本 Memory 段** —— ✅ **全段已启用** ✓ —— **X11 / X12 / X16** 于 2026-10-31 随 Agent Stage 7 的删除启用 ✓；**X13 / X15** 于 2026-10-31 随 **M-46 / M-47** 的 DROP 启用 ✓（表没了 ✓ → `modules/` 零命中 ✓）—— **45 条规则全跑** ✓（2026-10-31 补 X5 的两条 —— 旧模块路径 + 类名 ✓ —— 剩下的 2 条关着的是 **X4 的旧表** ✓ —— 表还在 ✓ 关着才是对的 ✓）· [x] **M-51 更新台账 + 现状文档** ✓（2026-10-31 ✓ —— 同一份现状文档 ✓）
| | M-51 更新台账 + 现状文档 | ✅ **已达成**（2026-10-31）—— **现状文档已更新** ✓（`docs/copilot-chat-module-architecture.md` ✓ —— §6.4 记忆与知识 ✓ + §12.4 ✓ —— 与 Session S-38 / Router R-28 / Context C-32 **同一份** ✓） | — | 0 | M-50 |

**退出判据**：
1. **用户 A 的会话召回结果里不含用户 B 的记忆**（租户 / 工作区 / 用户三层隔离各有测试）—— **X14 已修复**；
2. 1 万条 L2 下召回延迟不随 N 线性增长；`recall_degraded` 正确传递到 Context；
3. 重复内容不产生第二条；手机号类内容被拒绝写入并记审计；每条记忆可追溯到来源轮次；
4. **后台改绑定 → 下一轮对话行为可见地改变**，可机械断言为：**下一轮的召回结果集包含新绑定的 `scope` / `l3EntryIds`**，且 `route_decision` 与 `RecallHit.scope` 一致（对照测试）；
5. 会话结束后缓冲被提炼为 L2 候选；提升有事件记录；删除 L2 时向量同步删除；**embedding 不可用时写入不失败**；
6. 管理端：改一条 L2 → 敏感内容**被拒绝**；两人同时改 → 后者收到 **409**，**不静默覆盖**；治理删除一个用户 → 其 L1/L2/向量/缓冲**全部清除**；
7. **台账 X11 / X12 / X13 / X15 / X16 全部「已清理」**；**X14 标「已弃用」**（修复类）。

**本层删除的旧实现汇总**：**X11 · X12 · X13 · X15 · X16 共 5 条 + X14（修复类）**，约 **500 行 + 2 张表**（`_remember` 30 + `layered.py` 317 + `remember` 节点 30 + 管理端直写 150）。

**回退点**：Stage 0–6b 旧实现仍在场，回退 = revert。**Stage 7 之后不可逆**（L1 / L3 两张表退役后，旧数据只能从备份恢复）。

**本层负责的台账条目**：**X11 · X12 · X13 · X14（修复） · X15 · X16 · X19**（唯一 owner）。⚠️ **X19**（死表 `memory_l2_embeddings`）在 **Stage 0 的迁移 0048 内**就 DROP 掉了，不在 Stage 7。

**本层特有风险**：

| 风险 | 触发信号 | 预案 |
|---|---|---|
| **作用域过滤不完整** | 隔离测试只覆盖了 L2 | 三个隔离维度**各有测试**；向量检索的 payload 过滤单列测试（历史向量要回填） |
| **L3 退役影响知识召回** | 知识相关问题召回为空 | 决策 #1 必须先定边界；L3 退役前 `modules/knowledge` 的召回路径必须**已验证可用** |
| **「会话结束即提炼」没有触发者** | buffer 只涨不消 | **sweeper 是验收项**，不是实现备注；`qzdap_memory_policy_executor_missing` 指标必须归零 |
| **管理端乐观并发让管理员困惑** | 409 增多 | 管理界面必须显示「有人正在改」并提供重试；**不能自动后写覆盖** |

---

### 3.6 Agent 层（⑦ Agent Loop · ⑧ Agent Router（专家选择）· ⑨ Execution Runtime）

> 层方案：[`agent-refactor-plan.md`](agent-refactor-plan.md) · 迁移：**无**（`tool_executions` 的列已在 0035 建齐） · 台账：**X5 · X1（含 #24–#29）**
>
> **本层形态与其他层不同**：别的层是「旧实现完整、新实现未接线」，这一层是「**两套都不完整**」—— 旧路径的循环是真的但图是残留物，新 runtime 的图是真的但推理节点是空的。处置原则是「**取旧的真逻辑 + 用新骨架重写**」，而不是「把新 runtime 接上线」。

**本层目标**：把「推理循环」「**专家 Agent 选择**」「**模型 / 工具的取值与执行**」三件事各收敛成一个实现，并让**治理是默认路径而不是可选分支**。⚠️ **模型与工具不是运行时「挑」出来的** —— 它们由管理员在 agent 配置里绑定，运行时只负责**取出来并按治理规则过滤**（决策 #4）。

> **两条轴**（Agent 层方案 §0.2）：**执行轴**（每步推理：循环 → 选专家 → 执行）与**配置轴**（管理员配置 → agent 绑定 → 运行时取值）。**模型与工具在配置轴上，不在执行轴上** —— 所以 ⑧ 只剩「选专家」一路，模型 / 工具的**取值**落在 ⑨ Execution。

**前置**：
- **Agent Stage 4 开工前**：**Session 迁移 0046 已落地**（`session_turns.agent_decision` 列存在）—— 本阶段只依赖**表结构**，不依赖 Session 的 turn 实现；
- **Agent Stage 5 开工前**：**Session Stage 3（唯一 turn 实现）已完成**（硬依赖）—— Agent Loop 是跑在一轮之内的循环，没有唯一的 turn 编排，两边都会认为自己该管这件事；
- **Agent Stage 6 开工前**：**Stage 1 已完成**（`QZDAPChatModel` 可用）+ 决策 #8 已拍板；
- Agent 决策 #1 / #2 / #5 / #6 在 Stage 0 前拍完。

| Stage | 工作项 | 产出 / 落点 | **删除的旧实现**（台账 / 关注点） | **旧代码减少** | 依赖 |
| Stage 0 · 契约与依赖 | A-01 补五个端口 | ✅ **已达成**（2026-10-30，Agent Stage 0）—— `LLMPort` ✓ / `ModelResolverPort` ✓ / **`ToolBindingPort`** ✓ / `AgentRouterPort` ✓ / `ToolRuntimePort` ✓ 写进 runtime 的 `ports.py` ✓（**无 `ToolRouterPort`** ✓ —— 决策 #4 ✓）| — | 0 | — |
| | A-02 `QZDAPChatModel` 骨架 | ✅ **已达成** —— `execution/chat_model.py` ✓（`BaseChatModel` 子类 ✓；`_astream` 走 `LLMClient.stream()` ✓ → `AIMessageChunk` ✓；**只做类型翻译** ✓）；⚠️ 同步路径**明确报错** ✓（平台客户端只有异步 ✓ —— 基类的同步 `_agenerate` 默认实现被覆盖 ✓）| — | 0 | A-01 |
| | A-03 归一 `TaskKind` 与 `TaskClassifier` | ✅ **已达成** —— `graph/routing.py` **迁到** `agent_router/classifier.py` ✓（**不是新增一份** ✓）；返回值多了**置信度** ✓（`TaskClassification` ✓）；顺带把 `nodes.py` 里写死的 `confidence: 1.0` 换成**真实置信度** ✓ | — | 0（迁移 ✓） | A-01 |
| | A-04 依赖核对 | ✅ **已达成** —— 版本与方案 §2.1 一致 ✓：`langgraph` 1.2.12 ✓ / `langgraph-prebuilt` 1.1.0 ✓ / `langchain-core` 1.6.6 ✓；`deepagents` **未安装** ✓（决策 #8：Stage 6 可选 ✓ → 不加 ✓）；⚠️ runtime 的 pyproject **显式声明**了这三个依赖 ✓（之前只靠传递引入 ✗）+ `uv.lock` 离线重锁 ✓ | — | 0 | — |
| | A-05 打点 X5 旧入口 | ✅ **已有** ✓（`runner.py:104` 的 `record_legacy_call("X5")` ✓ —— 占位图 `compile_loop_graph` ✓）；扫描规则**仍关着** ✓（归 Agent Stage 7 与 X17 同批删 ✓） | — | 0 | 前置 C2 ✓ |
| Stage 1 · LLM / SLM | A-06 `QZDAPChatModel` 落地 | ✅ **已达成**（2026-10-30，Agent Stage 1）—— 内部持**端口** ✓（`LLMPort` ✓）；`_astream` → `AIMessageChunk` ✓；用量 → `usage_metadata` ✓；工具调用 delta → `tool_call_chunks` ✓（额外字段原样带走 ✓）| — | 0 | A-06 |
| | A-07 `LLMClient` 封装 | ✅ **已达成** —— `execution/llm_client.py` ✓（`LLMCaller` ✓）：**取值链**按 §5.2.1 走一遍 ✓（查表 ✓ 不决策 ✓）；**失败转移链**（primary → fallback ✓）交给端口 ✓ | — | 0 | A-06 |
| | A-08 `Reasoner` | ✅ **已达成** —— `agent_loop/reason.py` ✓；**`ToolCallAccumulator` 迁入** ✓（按 index 归并 ✓ / 参数表示不容混用 ✓ / `thought_signature` 透传 ✓）；文本增量实时到 ✓，**工具调用装配完整才交出去** ✓ | — | 0（迁移 ✓） | A-06 |
| | **A-09 迁移 `adapter/graph/chat_model.py` 的 `stream_chat` / `ToolCallAccumulator`** | ✅ **已达成**（2026-10-31 核对 ✓）—— `ToolCallAccumulator` 迁到 `agent_loop/reason.py` ✓；**文件也随 Agent Stage 7 删了** ✓（全仓 `stream_chat` **零命中** ✓ —— `adapter/llm/` 只剩 `__init__.py` ✓） | — | 0（代码迁出 ✓ + 文件删除 ✓） | A-08 |
| Stage 2 · 工具绑定与治理 | A-10 **工具绑定 + 治理过滤** | ✅ **已达成**（2026-10-30，Agent Stage 2）—— runtime 侧 `execution/tool_binding.py` ✓（`ToolBindingResolver` ✓）：tool / mcp / skill **统一成 `BaseTool`** ✓；∩ 风险 ✓；**`unprotected` 剔除副作用工具** ✓（**剔除，不是执行时拦截** ✓ —— §5.3.1 规则 3 ✓）；**绑定集为空不是错误** ✓（规则 1 ✓）。模块侧 `adapter/tools/tool_binding_adapter.py` ✓（`ToolBindingAdapter` ✓ 实现 runtime 的 `ToolBindingPort` ✓）+ `catalog_binding_reader.py` ✓（绑定集从 `admin_agents.tools` 读 ✓ —— agent_runtime 自己的表 ✓ 不跨模块读表 ✓） | — | 0（**新路径不接管旧路径** ✓ —— 接线归 Stage 4 ✓） | A-06 |
| | A-11 修 `list_tools` 的空 schema | ✅ **已达成** —— `modules/tool/.../application/tool_schema.py` ✓（**spec → JSON Schema 的单一真相** ✓）：**OpenAPI** 从文档的 paths 抽出 `__operation_id` / `path` / `query` / `body` ✓（**与 `openapi_runtime` 的参数路由同口径** ✓）；**MCP / 自定义** 取 spec 里声明的参数 ✓；`ToolServiceAdapter.list_tools` 改用它 ✓ —— admin 工具不再是空 `properties` ✓ | — | 0 | A-10 |
| | A-12 `governance` 接线 | ⚠️ **部分达成**（2026-10-30）—— **真实 actor** ✓：runtime 侧 `current_actor()` / `require_actor()` ✓（**取不到就拒绝执行工具** ✓ —— `ContextVar` ✓ 并发各挂各的 ✓）；模块侧 `adapter/tools/tool_runtime_adapter.py` ✓（`ToolRuntimeAdapter` ✓ 实现 `ToolRuntimePort` ✓）：**无 actor → `TOOL_ACTOR_MISSING`** ✓ + **跨租户 actor → `TOOL_ACTOR_TENANT_MISMATCH`** ✓。✅ **审批挂起的口径已改** ✓（2026-10-31 核对 ✓）—— **不再走 `interrupt()`** ✓：① 当时的理由是「`interrupt()` 要有 checkpointer + 图 ✓ —— 那时只有死代码那张 19 节点图 ✓」—— **前提已经不成立** ✓（新的 `AgentLoopRunner` 已落地 ✓ —— Stage 5 的 A-25 ✓ —— 19 节点图已整包删 ✓ —— Stage 7 ✓）；② **现在的实现走「事件 + 落库」** ✓（`session_turns.pending_approval` ✓ —— Session 方案 §8 · 决策 #6 ✓ —— 契约层 `TurnRunner` 的 `mark_waiting_approval` ✓ —— 恢复路径靠它校验「挂起的是哪个工具、参数有没有被改」✓）；③ **`interrupt()` 是 LangGraph 的特性** ✓ —— **新循环是手写循环** ✓（不是 LangGraph 图 ✓）→ **不适用** ✓ | — | 0 | A-10 |
| | A-13 **在新 AgentLoop 侧注入真实 actor** | ✅ **已达成**（2026-10-31 核对 ✓）—— `agent_loop/runner.py` 用 `set_current_actor` ✓ —— **取不到就拒绝执行工具** ✓（不拿假 actor 继续 ✓ —— §3.5 那个洞 ✓） | — | 0 | A-12 |
| Stage 3 · Tool Runtime 落库化 | A-14 `tool_executions` 开始写 | ✅ **已达成**（2026-10-31，Agent Stage 3）—— **唯一权威** ✓：`modules/agent_runtime/.../adapter/persistence/tool_executions.py` ✓（`ToolExecutionORM` ✓ —— **不用 `TenantScopedMixin`** ✓ —— 显式租户过滤 ✓）+ `PostgresToolExecutionStore` ✓（`ON CONFLICT (idempotency_key) DO NOTHING RETURNING` ✓ → **抢到 / 冲突读回** ✓）。⚠️ **列在 0035 已建齐** ✓ —— **不需要新迁移** ✓ —— **此前从未被写** ✓ → 幂等只在进程内 dict 里 ✗✗ | — | 0 | Stage 2 |
| | A-15 `request_hash` 冲突**拒绝** | ✅ **已达成** —— 指纹 = `sha256(canonical_json(arguments))` ✓（键排序 ✓）；**同键异参 → 拒绝** ✓（**`TOOL_IDEMPOTENCY_CONFLICT` 新增** ✓ —— `libs/schema` 的 `ErrorCode` ✓ + 投影文案 ✓ + 409 ✓；⚠️ 前端把错误码当不透明字符串 ✓ → **前端无需改** ✓）；**同键同参且已成功 → 复用既有结果** ✓；**同键执行中 → 拒绝** ✓（**`TOOL_IN_PROGRESS` 新增** ✓ + 409 ✓） | — | 0 | A-14 |
| | A-16 重试 / 熔断 | ✅ **已达成** —— `modules/tool/.../application/reliability.py` ✓：**指数退避 + jitter** ✓；**只重试「幂等工具的瞬时错误」** ✓；**按工具名熔断** ✓ → `TOOL_RATE_LIMITED` ✓（带 `retry_after_ms` ✓）；内置目录给 **20 个只读工具**标 `"idempotent": True` ✓ | — | 0 | A-14 |
| | A-17 **修复 async** | ✅ **随 Stage 7 达成** ✓ —— `run_async_from_sync` 当年只在**死代码**里 ✓（`context/budget.py` ✓ / `memory/__init__.py` ✓ / `graph/nodes.py` ✓）→ 那些文件**已随 Stage 7 删除** ✓ → **没有 async 可修** ✓ | — | 0 | A-14 |
| | A-18 沙箱接入 | ⚠️ **归 Stage 4/5** ✓ —— 沙箱作为**一类工具**走同一 `ToolRuntime` ✓ —— 需要新的 `AgentLoopRunner` 才有承载处 ✓ | — | 0 | A-14 |
| | A-19 成本结算 | ✅ **LLM 侧已在写** ✓ —— `journal.finish_turn(status, cost_usd=...)` ✓（Session S-19 ✓ —— `session_turns.cost_usd` ✓ —— ⚠️ **别写 `agent_turns.cost_usd`** ✗ 旧表会被 DROP ✓） | — | 0 | A-14 · **Session 0046 已落** |
| | A-20 进程内幂等降级为快速路径 | ✅ **达成** —— 权威已是 `tool_executions` ✓（跨 worker 有效 ✓）；⚠️ **`InMemoryToolExecutor` 本体仍在** ✗ → 删除归 **Stage 7（A-37）** ✓ | — | — | A-14 |
| | **A-20b `modules/tool` 的 `InvokeToolUseCase` 补幂等 / 重试 / 熔断** | ✅ **已达成**（2026-10-31，Agent Stage 3）—— 改 `modules/tool` ✓（归属已拍板 ✓）：`execute(...)` 新增 `turn_id` ✓ / `idempotency_key` ✓；**幂等流程** ✓（占权 → 同参复用 / 异参拒绝 / 进行中拒绝 ✓）+ **重试** ✓ + **熔断** ✓。⚠️ **端口在工具模块** ✓（`ToolExecutionPort` ✓ —— 只声明要什么 ✓），**实现在会话域** ✓（agent_runtime ✓ —— `turn_id` 外键 ✓） | — | 0 | A-14 |
| Stage 4 · 专家 Agent 选择 + 配置取值 | A-21 `AgentRouter` | ✅ **已达成**（2026-10-31，Agent Stage 4）—— 模块侧 `adapter/tools/agent_router_adapter.py` ✓（`CatalogAgentRouter` ✓ 实现 runtime 的 `AgentRouterPort` ✓）：**专家 = 目录里已发布的 agent** ✓（§4.2 规则 5 ✓）；匹配**确定性** ✓（显式 `profile.task_kinds` ✓ 优先 → category 关键词 ✓ → 低置信度不选 ✓ → **没命中落回会话绑定** ✓ 不报错 ✓） | — | 0 | **Session 0046 已落** |
| | A-22 **模型解析接线** | ✅ **已达成** —— runtime 侧 `agent_loop/expert.py` ✓（`ExpertAssembler` ✓ / `ExpertInstance` ✓ —— **专家 = 模型 + 指令 + 工具集** ✓ §4.2 规则 1 ✓）：模型走**取值链** ✓（`LLMCaller.resolve` ✓ —— §5.2.1 ✓ —— **查表，不是决策** ✓ —— 路由优先于 model_id ✓ —— 解析不出回退环境默认模型 ✓ 不是错误 ✓）→ 构造 `QZDAPChatModel` ✓（内部持**端口** ✓） | — | 0 | A-21 |
| | A-23 **工具绑定接线** | ✅ **已达成** —— 同一个 `ExpertAssembler` ✓：绑定集按**选中的专家**取 ✓（`ToolBindingPort.bindings(agent_id, agent_version)` ✓ —— §5.3.1 规则 6 ✓）→ **治理过滤** ✓（∩ 风险 ✓ ∩ 作用域 ✓ − unprotected 的副作用工具 ✓）→ **统一成 `BaseTool`** ✓ | — | 0 | A-21 |
| | A-24 路由留痕 | ✅ **已达成** —— 载荷**只记「用了什么」** ✓（专家 id ✓ / 版本 ✓ / 任务类型 ✓ / **解析出的模型** ✓ / **工具集** ✓）—— **不记「为什么」** ✓；⚠️ **不写 `route_decision`** ✓（那是 Router 层的列 ✓ —— **两列两写者** ✓）。落点两处 ✓：`session_turns.agent_decision` ✓（轮次级快照 ✓）+ `session_events` 的 `agent.expert.selected` ✓（追加式 ✓）→ 模块侧 `agent_decision_store.py` ✓ | — | 0 | A-21 · 0046 已落 |
| Stage 5 · 循环与终止 | A-25 `AgentLoopRunner` + `Evaluator` | ✅ **已达成**（2026-10-31，Agent Stage 5）—— runtime 侧 `agent_loop/` ✓：`runner.py`（`AgentLoopRunner` ✓）/ `evaluate.py`（`Evaluator` ✓ —— **六个终止条件的单一判定点** ✓）/ `observe.py`（`Observer` ✓ —— 失败也要回灌 ✓）/ `state.py`（`LoopState` ✓）/ `reason.py`（`Reasoner` ✓ —— Stage 1 迁入 ✓）。⚠️ **每步的旁路走钩子** ✓（`LoopHooks` ✓ —— 压缩 ✓ / manifest ✓ / 成本 ✓ / 旁路事件 ✓ —— 循环本体不碰业务 ✓）| — | 0（runtime 侧**新增** ✓） | **Session Stage 3（硬）** |
| | **A-26 把 `_run_turn_inner` 改接新 Builder / Writer** | ✅ **已达成**（2026-10-30）—— `runner.py:184` 的 `_load_messages` → `ContextBuilder.build` ✓；`runner.py:479` 的 `_remember` → `MemoryPort.write_turn`（走 `memory/writer.py` 五步流水线 ✓）。**X8 / X11 现在没有调用方** ✓（演示栈实测：`qzdap_legacy_calls_total{entry="X8"}` 与 `X11` 均为 0 ✓，X9 仍为 1 ✓）→ **Context Stage 4 与 Memory Stage 7 解锁** ✓ | — | 0（**旧代码减少 0 行** ✓ —— 函数体留着归各层的 Stage 5 / Stage 7 删 ✓） | A-25 · **Context Stage 1–3 + Memory Stage 3** |
| | A-27 端到端回归 | ✅ **已达成**（2026-10-31，Agent Stage 5）—— ① **整条循环跑完的测试** ✓（`runtimes/agent_runtime/tests/test_agent_loop.py` ✓ —— 13 条 ✓ —— 工具 → 回灌 → 收尾 ✓ / 失败回灌 ✓ / 没绑定回灌 ✓ / **没有 actor 不许执行工具** ✓ / 审批挂起 ✓ / 治理拒绝 ✓ / 治理放行 ✓ / 步数闸门 ✓ / 成本闸门 ✓ / 取消 ✓ / 空转护栏 ✓ / 观察者截断 ✓）；② **旧路径的既有测试全部保留** ✓（`modules/agent_runtime/tests/unit/` 118 条 ✓ —— 工具链 ✓ / 步数 ✓ / 空转 ✓ / 审批恢复 ✓ / 记忆写入 ✓ / 压缩 ✓ / 幂等重放 ✓ / 并发 ✓ / 取消 ✓ / 成本 ✓ / 埋点树 ✓ —— **回归网没被拆掉** ✓）| — | 0 | A-26 |
| | **A-28 停用 + 打点 `_run_turn_inner`** | ✅ **已达成**（2026-10-31，Agent Stage 5）—— ① **生产路径改跑新循环** ✓（`modules/agent_runtime/.../adapter/graph/runner.py` 的 `_drive_turn` ✓ —— 旧的 `while True` **删了** ✓ —— ~250 行 ✓）；② **每步的旁路** ✓（压缩 ✓ / manifest **先于模型落库** ✓ / 成本 ✓ / 旁路事件 ✓）走钩子 ✓；③ **专家实例** ✓（Agent Stage 4 的装配器**接上了** ✓ —— 选专家 ✓ 取模型 ✓ 取工具 ✓ —— `ExpertAssembler` ✓ —— **请求作用域** ✓ web ✓ + IM ✓ 同口径 ✓）；④ **旧打点撤除** ✓（`X17` ✓ / `X5` ✓ —— 占位图**不再构造** ✓）；⑤ **扫描规则 `_run_turn_inner` 已启用** ✓（零命中 ✓）| **X17 → 已弃用**（关注点 #18）· **X5 → 已弃用** | **~250 行**（手写循环已删 ✓ —— 文件级清理归 Stage 7 ⏳） | A-26 |
| Stage 6 · Deep Agents（可选） | **A-28b 加依赖** | 🚫 **Stage 关闭** ✓ —— **决策 #8 未采纳** ✓（「先隔离分支验证再接 Stage 6」✓ —— 验证**没做** ✓ → **不接** ✓）；⚠️ **接了就是第二套循环** ✗✗ —— 现在的唯一实现是 runtime 的 `AgentLoopRunner` ✓（六节点图已整包删 ✓ —— A-33 ✓ / A-34 ✓）→ **Deep Agents 会造出第三套** ✗ → **不做** ✓；⚠️ **不动 lockfile** ✓（不引入 `deepagents` 依赖 ✓ —— 一个**可选增强**不值得给生产依赖树加风险 ✓）| — | 0 | **决策 #8 未采纳** ✓ |
| | A-29 `deep/factory.py` | 🚫 **不做了** ✓（随 A-28b 一起关 ✓）| — | 0 | A-28b ✓ |
| | A-30 `deep/planner.py` | 🚫 **不做了** ✓ —— ⚠️ **「规划器 + 子代理派发」已经有实现** ✓ —— runtime 的 `ExpertAssembler` ✓（Agent Stage 4 ✓ —— 选专家 ✓ 取模型 ✓ 取工具 ✓）+ `delegate_subagent` 用例 ✓（**子代理走同一条循环** ✓ —— 不是另一套循环 ✓）→ **不重复造** ✓ | — | 0 | A-29 ✓ |
| | A-31 预算 | 🚫 **不做了** ✓ —— **预算闸门已有单一判定点** ✓：`agent_loop/evaluate.py` 的 `Evaluator` ✓（Agent Stage 5 ✓ —— 步数 ✓ / 成本 ✓ / 空转 ✓ / 取消 ✓ —— 六个终止条件 ✓）→ Deep Agents 的 `max_steps` / `max_cost_usd` 会是**第二套预算判定** ✗✗ | — | 0 | A-29 ✓ |
| | **A-32 删 `nodes.py` 的 `deep_agent_plan` / `subagent` 空壳** | ✅ **已达成**（2026-10-31，Agent Stage 7）—— `runtimes/agent_runtime/src/qzdap_agent_runtime/graph/` **整包删除** ✓（含 `deep_agent.py` ✓ —— 见 A-33 ✓ / A-40 ✓）→ **空壳已不在** ✓；⚠️ **仓内零引用** ✓（`deepagents` / `deep_agent` / `DeepAgent` **一处都没有** ✓ —— 扫过 `backend/` ✓） | — | **~130 行**（随 A-33 一起删 ✓） | A-29 → **不必做** ✓ |
| Stage 7 · 清理与封口 | **A-33 删 `graph/nodes.py` 的 13 个节点** | ✅ **已达成**（2026-10-31，Agent Stage 7）—— `runtimes/agent_runtime/src/qzdap_agent_runtime/graph/` **整包删除** ✓（`nodes.py` ✓ / `builder.py` ✓ / `state.py` ✓ / `deep_agent.py` ✓）| — | **~1000 行** | 归零判据满足 ✓ |
| | **A-34 改 `graph/builder.py` 为 6 节点版** | ⚠️ **不做了** ✓ —— **6 节点图没有承载者** ✓：新循环是 runtime 的**手写循环** ✓（`AgentLoopRunner` ✓ —— Reason → Observe → Evaluate ✓）+ **`LoopHooks`** ✓（每步旁路 ✓）—— 六个终止条件的**单一判定点** ✓ 已达成 ✓；⚠️ **再造一张图就是第三套** ✗✗（旧图 ✓ + 新图 ✗）→ **整包删掉** ✓ | — | **~177 行**（随 A-33 一起删 ✓） | A-33 ✓ |
| | **A-35 删 `adapter/graph/runner.py` 的 ReAct 循环** | ✅ **已达成**（2026-10-31，Agent Stage 5）—— 手写 `while True` **删掉** ✓（~250 行 ✓）—— 生产路径跑 runtime 的 `AgentLoopRunner` ✓ | — | **~250 行** | A-27 归零 ✓ |
| | **A-36 删 `adapter/graph/loop.py` 的 `compile_loop_graph`** | ✅ **已达成**（2026-10-31，Agent Stage 7）—— `adapter/graph/loop.py` **整文件删除** ✓（占位图 ✓ / 旧 `next_route` ✓ / 旧 `apply_stall_guard` ✓ —— 三个都有 runtime 侧的新实现 ✓）；`HARD_MAX_STEPS` **迁到契约层** ✓（`agent_loop/evaluate.py` ✓）| **X5 → 已清理**（关注点 #20）✓ | **~70 行** | A-35 ✓ |
| | **A-37 删 `executor.py` 的 `InMemoryToolExecutor`** | ✅ **已达成**（2026-10-31，Agent Stage 7）—— `execution/executor.py` **整文件删除** ✓ —— 工具执行的唯一权威是 `modules/tool` 的 `InvokeToolUseCase` ✓ | **关注点 #16** ✓ | **~305 行** | A-20 ✓ |
| | **A-38 删 `tools/registry.py` 的 `InMemoryToolRegistry`** | ✅ **已达成**（2026-10-31，Agent Stage 7）—— `tools/` **整包删除** ✓ —— 真实注册表是 `modules/tool` 的 `tools` 表 ✓（Stage 2 的 `tool_schema.py` ✓ 保留了适配逻辑 ✓）| **关注点 #29** ✓ | ~60 行 | A-10 ✓ |
| | **A-39 删 `result/events.py` 的 16 种 `*Event`** | ✅ **已达成**（2026-10-31）—— **16 种全删** ✓（文件整个没了 ✓）→ `result/` 只剩**一个工厂** ✓（`to_chunk` ✓ —— 「事件 → chunk」只有一处 ✓ —— 之前两份 ✗✗）；⚠️ **换之前先扩了 chunk 契约** ✓（usage 的 6 维 ✓ / error 的 `detailed` ✓ / `event_id` ✓ / `source_turn_id` ✓ / `query_hash` ✓ / `removed_ids` ✓ / `expires_at` ✓ / done 的状态与版本 ✓ —— **没丢字段** ✓）；出站编码器改吃 chunk ✓ | **X1-a**（✅ 已清理） | ~300 行（**真删了** ✓） | — |
| | **A-40 删其余 14 个 `InMemory*`** | ✅ **已达成**（2026-10-31，Agent Stage 7）—— `governance/` ✓（4 个 ✓）/ `evaluation/` ✓ / `observability/` ✓ / `execution/lock.py` ✓ / `context/budget.py` ✓ / `memory/layered.py` ✓ / `result/sink.py` ✓ / `graph/deep_agent.py` ✓ —— **全删** ✓；⚠️ **`InMemoryOutboxRepository` 保留** ✓（**Session Stage 4b 已取用** ✓ —— 出站重试与死信的**唯一实现** ✓ —— 不是孤儿 ✓）| **关注点 #25–#29** ✓ | ~700 行 | 各语义已落地 ✓ |
| | A-41 启用扫描脚本 Agent 段 + `InMemory*` 禁令 | ✅ **已达成**（2026-10-31，Agent Stage 7）—— 扫描脚本**启用 38 条** ✓（跳过 7 条 ✓）：`compile_loop_graph` ✓ / `_run_turn_inner` ✓ / `graph/nodes.py` ✓ / `build_session_graph` ✓ / `InMemoryToolExecutor` ✓ / `class InMemory(...)`（14 个名字 ✓）—— **零命中** ✓；⚠️ **架构守卫** ✓（`tests/architecture/test_single_implementation.py` ✓ —— 基线只剩 2 个 ✓ —— `InMemoryOutboxRepository` ✓ + `InMemoryDraftStore` ✓）| — | 0 | A-33 ✓ |
| | A-42 更新台账 + 现状文档 | ✅ **已达成**（2026-10-31，Agent Stage 7）—— 台账 ✓：**X1 / X5 / X12 / X17 → 已清理** ✓（统计已同步 ✓ —— 未开始 4 ✓ / 已弃用 2 ✓ / 已清理 28 ✓ / 已修复 2 ✓ = 36 ✓）；方案文档 ✓（Agent 方案 Stage 7 记录 ✓ + 实施计划 A-33…A-42 ✓）| — | 0 | A-41 ✓ |

**退出判据**：
1. **存在一条端到端测试跑完整个循环**（不是逐节点单测）—— 2026-10-15 那次失败的直接教训；六个终止条件各有一条测试；
2. 同一 `idempotency_key` 在**两个 worker** 上并发调用 → **只执行一次**；`tool_executions` 有真实行；同键不同参数 → 明确错误；
3. actor 是真实用户；取不到 actor → **拒绝执行工具**；`unprotected` 轮次**不产生任何副作用工具调用**；
4. **专家选择有独立测试**；模型与工具**取自 agent 配置**（代码里没有运行时「挑」的逻辑 —— 决策 #4）；`agent_decision` 完整留痕、**不碰 Router 的 `route_decision`**；**专家切换不改变会话绑定**；**专家切换后模型 / 工具随之换成新专家配置里的那些**（§4.2）；
5. 成本落到 `session_turns.cost_usd`（**0035 建的列**）；
6. **`QZDAPChatModel` 是 `langchain_core.BaseChatModel` 的实例**，能被 LangGraph 节点作为 `model` 接受（Deep Agents 的硬前置）；
7. **生产包里零 `InMemory*` 类**（CI 规则 6）；**平行 `*Event` 已删**，前端契约只剩 `TurnChunk` 一套；
7. **台账 X5 与 X1 的 Agent 部分「已清理」**，扫描脚本 Agent 段零命中。

**本层删除的旧实现汇总**：**X5 · X1（Agent 部分）** + 关注点 **#16 · #24 · #25–#29**，约 **2100 行**（`nodes.py` 13 节点 700 + `builder.py` 19 节点装配 177 + `_run_turn_inner` 250 + `compile_loop_graph` 70 + `InMemoryToolExecutor` 305 + 其余 15 个 `InMemory*` ~760 + 平行 `*Event` ~200 + `chat_model.py` 200 + `governance` 节点 120 + `deep` 空壳 130）。

**回退点**：Stage 0–6 旧实现仍在场，回退 = revert。**Stage 7 之后不可逆**（`runtimes/agent_runtime` 的未接线包被拆空后，没有第二份「现成的新实现」可退回 —— 这正是我们要的结果）。

**本层负责的台账条目**：**X5 · X1**（唯一 owner，含 #24–#29 的删除）。

**本层特有风险**：

| 风险 | 触发信号 | 预案 |
|---|---|---|
| **工具幂等上线后仍有重复执行** | `qzdap_tool_idempotent_hit_total` 为 0 但调用数高 | 立即**停用有副作用的工具**（不是回滚整个层） |
| **`deepagents` 与当前 lock 不兼容** | 探针失败 | 决策 #8 选「只保留类型定义」；本层不阻塞主线 |
| **`QZDAPChatModel` 适配错了语义** | 流式 tool call 装配失败 / Deep Agents 的 `model=` 报错 | Stage 1 的验收是「**是 `langchain_core.BaseChatModel` 的实例，能作为 LangGraph 节点的 `model` 被接受**」；失败则**不往下走**。⚠️ 别拿「能被 `ToolNode` 接受」当判据 —— `ToolNode` 接受的是**工具列表**，不是 chat model |
| **`InMemory*` 被下一个人当现成实现接线** | 生产包出现新的 `InMemory*` | **CI 规则 6 从全局前置起就在拦**（不是等 Stage 7） |

---

## 4. 跨层编排

> **本节只讲顺序与并行，不讲工作项。** 工作项全在 §3。

### 4.1 层间依赖（**唯一权威顺序来源**）

```
Global 前置(A/B/C)
   │
   ├─→ Gateway Stage 0–3 ────────────┬─→ Gateway Stage 4a ─┐
   │                                 │                      │ 同 PR
   ├─→ Router Stage 0–1              │                      │
   │                                 └─→ Gateway Stage 5 ←─┤
   ├─→ Session Stage 0 → 1 → 2 ──→ Session Stage 3 ─┬─→ Session Stage 4 ─→ Gateway Stage 4b ─→ Gateway Stage 5
   │                                              ├─→ Router Stage 3
   │                                              ├─→ Memory Stage 3
   │                                              ├─→ Agent Stage 5
   │                                              └─→ Context Stage 4
   ├─→ Context Stage 0（物理等 0046）
   ├─→ Memory Stage 0 → 1（独立，可最早开工）
   └─→ Agent Stage 0–3（Stage 4 等 0046）
```

**逐条硬依赖表**（改任何一条都要同步 README §3.3）：

| 前置 | 被阻塞 | 阻塞类型 | 写在谁的文档里 |
|---|---|---|---|
| Session Stage 1（`resolve_or_create` + **`lookup`**） | **Router Stage 2** | 契约 | §3.2 R-10 / R-10b |
| Session Stage 3（唯一 turn 实现） | **Router Stage 3**（FIFO 有序） | 语义 | §3.2 R-14 |
| Session Stage 3 | **Memory Stage 3**（Writer 重写） | 语义 | §3.5 M-21 |
| Session Stage 3 | **Agent Stage 5**（循环本体） | 语义 | §3.6 A-25 |
| Session Stage 3 | **Context Stage 4**（接线） | 语义 | §3.4 C-21 |
| Session Stage 4（`session_events` 落库） | **Gateway Stage 4b**（无感重放） | 硬依赖 | §3.1 G-24 |
| Session 迁移 0046 | **Context 迁移 0047** | 物理顺序 | §3.4 C-02 |
| Session 迁移 0046 | **Agent Stage 4**（`agent_decision` 列） | 物理顺序 | §3.6 A-21 |
| Gateway Stage 0–3 | **Gateway Stage 4a** | 顺序 | §3.1 G-18 |
| Gateway Stage 4a | **Session Stage 5b**（同 PR） | **原子** | §3.1 G-20 / §3.3 S-32 |
| Memory Stage 2（C2 Retrieval） | **Context Stage 1**（Builder 召回发起） | 语义 | §3.4 C-08 |
| **Agent Stage 5 的 A-26**（`_run_turn_inner` 改接新 Builder / Writer） | **Context Stage 4**（停用 `_load_messages` / 四套模板 / `compact.py`）、**Memory Stage 7**（删 `_remember`） | **语义（删除顺序自底向上）** | §3.6 A-26 |
| **Session Stage 5b**（删 `use_cases/run_turn.py`） | **Context Stage 5**（删 `adapter/llm/prompts.py` —— `run_turn.py` import 那四个函数） | **语义** | §3.3 S-33 → §3.4 C-27 |
| 「工具幂等落点」归属决策（README §8 依赖 3） | **Agent Stage 3**（A-14 / A-20b） | 契约 | §2.1 · §3.6 A-20b |
| Agent Stage 1（`QZDAPChatModel`） | ~~**Agent Stage 6**（Deep Agents）~~ | 🚫 **依赖解除** ✓ —— **Stage 6 已关闭** ✓（决策 #8 未采纳 ✓） | §3.6 A-28b |

### 4.2 可并行的独立支线

| 支线 | 可开工时点 | 约束 |
|---|---|---|
| **Memory Stage 1（作用域过滤）** | **立刻** | 完全独立、无迁移、无依赖 —— **且修的是正在发生的跨用户泄漏**，**优先级最高** |
| **Gateway Stage 0–3** | 全局前置完成后 | 不依赖任何下游 |
| **Router Stage 0–1** | Gateway Stage 1 之后 | Router Stage 1 依赖 Gateway Stage 1 |
| **Agent Stage 0–3** | Gateway 决策 #5 的 `unprotected` 语义确定后 | Agent Stage 2 需要它 |
| **Session Stage 0** | 表选择决策拍板后 | 关键路径起点 |
| **Context Stage 0** | **必须等 0046 落地**（物理顺序） | — |

### 4.3 排期（**相对周次** —— 3 人最小配置）

> 排期是**相对周次**，不是绝对日期 —— 关键路径（Session）的实际速度决定总时长。

| 层 | Stage 0 | Stage 1 | Stage 2 | Stage 3 | Stage 4/5 | 清理 Stage | 主责 | 主要阻塞者 |
|---|---|---|---|---|---|---|---|---|
| **Gateway** | W1 | W1–2 | W2 | W2–3 | W9–10（4a）/ W12（4b） | **W14（5）** | B | 4b 需 Session S4 |
| **Router** | W2 | W3 | W5 | W10 | W11（4）/ W13（5） | **W13** | B | S2 需 Session S1；S3 需 Session S3 |
| **Session** | W3 | W4 | W5 | **W6–8** | W9（S4）/ W10（S5）/ W11（S5b） | **W14（S6）** | A | **全局关键路径** |
| **Context** | W9 | W10 | W10–11 | W11 | W13（S4）/ W14（S5） | **W14（S5）** | A | S0 需 0046（W5 后）；**S4 需 Agent S5 的 A-26**；**S5 需 Session S5b** |
| **Memory** | W7 | **W2–3** | W10 | W10 | W11–13（S4–6b） | **W14（S7）** | C | S0 需 0047（W9 后）；**S7 需 Agent S5 的 A-26** |
| **Agent** | W3 | W4 | W5 | W6–7 | W8–9（S4）/ W10–12（S5） | **W15（S7）** | D | S4 需 0046；**S5 需 Session S3**；**S5 的 A-26 需 Context S1–3 + Memory S3** |

> **三条排期硬约束**（违反了就是「建而不切」的另一种形态）：
>
> | # | 约束 | 原因 |
> |---|---|---|
> | 1 | **迁移序号严格串行**：0044（W1）→ 0045（W2）→ 0046（W3）→ 0047（W9）→ 0048（W7 ❌ → **W10**） | 迁移号就是物理顺序。**注意 0048 必须晚于 0047** —— 所以 Memory Stage 0 排在 W10，不是 W2 |
> | 2 | **同一主责人名下的两个 Stage 不得并行** | 一个人做不了并行两段。A 名下 Session（W3–W14）与 Context（W9–W14）在 W9–W14 重叠 —— **Context 的 Stage 0–3 只能排在 Session S3 之后** |
> | 3 | **Context Stage 4 必须晚于 Agent Stage 5**（A-26 接线） | 否则删 `_load_messages` 会打断还在服役的旧循环 |

**全局关键路径**：`Session S0 → S1 → S2 → S3 → S4 → Gateway 4b → Gateway 5`。
**Session Stage 3 之前，四条下游支线全部堵住**（Router S3 / Memory S3 / Agent S5 / Context S4）。

> **⚠️ 最容易被低估的**：Session Stage 3 的工作量（旧 `copilot.py` 647 行 + `runner.py` 914 行的**语义合并** + 审批加固）。它不是「写代码」，是**在两套漂移的语义里挑出对的那套并统一**。

### 4.4 里程碑 → 层

| 里程碑 | 覆盖的层与 Stage | 完成判据（详见 [`README.md`](README.md) §6.2） |
|---|---|---|
| **M0 地基就位** | Gateway 0–3 · Router 0–1 · Memory 0–1 · Agent 0 · Context 0 · Session 0 | 五个迁移（0044–0048）可跑可回滚；`qzdap_legacy_calls_total` 已上线且各层旧入口已打点；**Memory 跨用户泄漏已修复** |
| **M1 唯一 turn 实现** | **Session 1–3** | 全仓只剩一套「跑一轮」的语义；两套旧 turn 实现已停用并打点；旧表双写期已开始对账 |
| **M2 事件可重放** | **Session 4/5/5b** · **Gateway 4a/4b** | `session_events` 真写真读；SSE 断线重连内容完整；重复请求**无感重放**；**IM 渠道上只剩一套 turn 实现**（S5b 与 G20 同 PR） |
| **M3 上下文与记忆上线** | **Context 1–3** · **Memory 2–3** | 上下文可喂模型；超预算走真压缩；记忆召回按用户隔离；manifest 落库 |
| **M4 路由与执行成型** | **Router 2–4** · **Agent 1–5** | 同会话消息严格有序；工具幂等**跨 worker** 生效；`tool_executions` 有真实行；**存在一条跑完整个循环的端到端测试** |
| **M5 全部清零** | **全部层的清理 Stage**（Gateway 5 · Router 5 · Session 6 · Context 5 · Memory 7 · Agent 7） | 台账 29 条**全部「已清理」**；CI 扫描脚本零命中；`qzdap_legacy_calls_total` 全指标归零；**生产包零 `InMemory*`** |

### 4.5 人力假设与角色（**排期的前提**）

| 角色 | 人数假设 | 负责 | 关键路径上的角色 |
|---|---|---|---|
| **后端 A（会话域 + 上下文域）** | 1–2 人 | **Session 全部 Stage**（§3.3）+ 迁移 0046 · **Context 全部 Stage**（§3.4）+ 迁移 0047 | ⭐ **咽喉角色** —— 缺人就全线延期。Context 归 A 是因为它重度依赖 Session 语义，且**排在 Session 之后**，不构成并行冲突 |
| **后端 B（接入域）** | 1 人 | **Gateway 全部 Stage**（§3.1）+ 迁移 0044 · **Router 全部 Stage**（§3.2）+ 迁移 0045 | |
| **后端 C（记忆域）** | 1 人 | **Memory 全部 Stage**（§3.5）+ 迁移 0048 | |
| **后端 D（Agent 域）** | 1 人 | **Agent 全部 Stage**（§3.6） | |
| **前端** | 0.5 人 | 契约核对（H5）、兼容别名下线、联调 | |
| **QA / 值班** | 0.5 人 | 验收环境（H1）、回归、演练（H3）、告警响应（H2） | |

> **最小可行配置：4 人**（A / B / C / D 各 1），总时长约 **15 周**。
>
> **3 人时的取舍**（必须承认代价）：
> - **Context 并入 A** —— 但 A 名下 Session 与 Context **只能串行**（Context 排在 Session 之后），总时长 **+2 周 ≈ 17 周**；
> - **或 Router 并入 A** —— Router 的 Stage 3 依赖 Session Stage 3，同理串行，**+1 周**；
> - **不能把 Context 与 Agent 合并给一个人** —— 它们的 Stage 在 W9–W12 高度重叠（Agent S4/S5 与 Context S0–S3），一个人必然做不出「两条并行支线」。
>
> **⚠️ 最需要提前安排的是「后端 A」** —— Session Stage 3 是全局咽喉（§4.3）。

---

## 5. 横切工作项（**每层都要做**）

> 下面这些**不属于任何一层**，但**每一层**都必须做。漏掉它们，是最常见的「Stage 打勾但东西没落地」。

| # | 横切项 | 什么时候做 | 怎么算完成 | 漏了会怎样 |
|---|---|---|---|---|
| **H1** | **测试数据与验收环境** | 全局前置建，每层开工前刷新 | dev 库有可复现的**脱敏生产样本**（含长会话、含工具调用、含审批、含多用户 —— 用来验隔离）；有一套「验收脚本」能一键跑完**本层**的判据 | 验收靠手工点，恢复演练无从谈起 |
| **H2** | **告警与值班** | 指标上线后**立即**建 | 每个新指标有阈值告警；`qzdap_legacy_calls_total` 有「某个 `entry` 归零前突然上涨」的告警；**值班人知道本层的回退步骤** | 出问题时没人知道要回退，回退变成「猜」 |
| **H3** | **数据迁移脚本 + 回滚恢复演练** | 迁移合入**前** | 每个迁移有**已合入的**回滚脚本；且在 dev 库**实际执行过恢复**（不只是「脚本能跑」） | 删表后数据找不回（Session Stage 6 不可逆） |
| **H4** | **文档更新** | 随 PR | 现状文档 `docs/copilot-chat-module-architecture.md` 与本目录 10 份文档同步；**新引入的 API 形状要有文档** | 半年后没人知道现状是什么 |
| **H5** | **契约变更通知** | 接口形状变更时 | **按前端真实调用穷举端点**（不是拍脑袋数）：`frontend/packages/api/src/pathMap.ts` + `web/src/features/user/copilot/copilotApi.ts` + `CopilotPage.tsx`，产出「端点 → 后端新路径 → 契约是否变 → 通知对象」对照表。当前 `/api/sessions*` **至少 12 个**（含 `feedback` / `cancel` / `attachments` / **`interactive/answer`** / `plans/{pid}/{approve,deny}`）—— **`interactive/answer` 正是关注点 #24 里「平行事件类型少了 `InteractiveActionEvent`」的那一类**；有仓外消费者时**提前一个发布周期公告** | 前端半夜被 breaking change 打挂 |
| **H6** | **锁文件与依赖** | 每次改 `pyproject.toml` | `uv.lock` 已更新且 `uv sync` 通过；CI 的 isolated install 通过 | 别人的环境装不上（`qzdap-vault` 就是这么埋的雷） |
| **H7** | **单机可跑通** | 每层结束 | 一台干净的机器 + `uv sync` 能起服务、跑通本层的验收脚本 | 靠「我本地能跑」交付，环境差异变成线上故障 |
| **H8** | **跨模块外部前置确认** | 每层 Stage 0 | 本层依赖的**其它模块**的改动已就位：① **`ErrorCode` 码收敛**（7 个散落在 `modules/channel` / `modules/agent_runtime` 异常里的码提升为枚举成员）→ Gateway Stage 0；② `route_strategy` 新取值（`modules/model` + `modules/agent_factory`）→ Agent Stage 4；③ 专家 Agent 的 role 标签（`agent_versions`）→ Agent Stage 4；④ **工具幂等落点归属**（`modules/tool`）→ Agent Stage 3；⑤ `tools` 表真实 schema → Agent Stage 2；⑥ **`modules/channel` 新增 `qzdap-agent-runtime` 依赖** → Gateway Stage 2。**每条都有明确的「谁改、何时改完」** | 跨模块前置没到位 → 该层 Stage 到点才发现停工，整层延期 |

> **H1–H8 不写进各层的 Stage 表，是因为它们贯穿全程** —— 但**每一层**的退出判据都要包含「H1–H8 在本层范围内的部分已完成」。
>
> **H8 特别容易被漏**：它是**别的模块**的活，不在本方案集的代码范围内，所以「本层做完了但外部前置没到位」这种情况**不会在本目录的任何 Stage 表里显形** —— 只能靠 H8 显式登记。

---

## 6. 单实现不变量的自动化守卫

### 6.1 守卫规则（**进 CI**）

| # | 规则 | 检查方式 |
|---|---|---|
| 1 | **同一关注点只有一个实现类** | 关键字扫描：每个关注点的「新类名」与「旧类名」**不得同时存在**（数据源 = §1.2 的 **30 行**）。⚠️ **分批启用**：每条关注点的规则在**它的「允许并存窗口」关闭的那个 Stage** 才启用 —— 见 §6.2 |
| 2 | **台账条目已清理 = 旧符号零命中** | 台账 §3.1 的扫描脚本（唯一来源） |
| 3 | **runtime 层零框架 import** | import 禁令 |
| 4 | **层边界不被绕过** | import 扫描（如 Router 不得写 `agent_sessions`） |
| 5 | **唯一 owner** | 同一旧实现只允许出现在一个层的删除清单里（可用 §1.2 表做数据源自动生成） |
| 6 | **生产包不得有 `InMemory*`** | 扫描 `backend/runtimes/**`（排除 `tests/`）：`class InMemory\w+` 命中数 **≤ 基线白名单**。**基线 = §1.5 表里的 16 个现存类名**，每删一个就从基线移除一个；**新增一个即红**。**全局前置就进 CI** —— 它的价值在**拦住新增**，不是清理存量 |

> **规则 1 是本计划的核心守卫**。它把「不能存在两套实现」从一句口号变成**每次 CI 都跑的红线**。

### 6.2 守卫的落地方式

```python
# backend/tests/architecture/test_single_implementation.py
"""同一关注点不得有两个实现并存。数据源 = 本计划 §1.2 的关注点表。"""

# 每条关注点：(关注点名, 新符号, 旧符号, 守卫启用时点)
# 启用时点 = 该关注点「允许并存窗口」关闭的那个 Stage（数据源 = 本计划 §1.2）
CONCERNS = [
    ("跑一轮对话",       "TurnRunner",           "copilot_turn_orchestration", "Session Stage 3b"),
    ("跑一轮对话(IM)",   "AgentLoopRunner",      "RunTurnCompletionUseCase", "Session Stage 5b"),
    ("上下文组装",       "ContextBuilder",       "_load_messages",        "Context Stage 5"),
    ("上下文压缩",       "ContextCompressor",    "compact_messages",      "Context Stage 5"),
    ("system prompt 渲染", "render_system_prompt", "build_system_prompt", "Context Stage 5"),
    ("记忆写入",         "MemoryWriter",         "_remember",             "Memory Stage 7"),
    ("记忆检索",         "MemoryRetrieval",      "LayeredMemory",         "Memory Stage 7"),
    ("会话 key 派生",    "build_session_key_hash", "build_session_key",    "Router Stage 5"),
    ("工具执行",         "ToolRuntime",          "InMemoryToolExecutor",  "Agent Stage 7"),
    ("推理循环",         "AgentLoopRunner",      "_run_turn_inner",       "Agent Stage 7"),
    ("Agent 图骨架",     "build_agent_loop_graph", "build_session_graph",  "Agent Stage 7"),
    ("轮次存储",         "SessionTurnORM",       "AgentTurnORM",          "Session Stage 6"),
    ("会话状态字段",     "SessionTurn.status",   "wait_status",           "Session Stage 6"),
    # …… 共 30 条，见本计划 §1.2（含「允许并存窗口」列）
]

# 已启用的规则（随 Stage 合入逐步增加；数据源 = 台账 §3.1 的扫描脚本）
ENABLED_RULES: set[str] = set()   # 例：{"Session Stage 3", "Gateway Stage 1"}


def test_no_dual_implementation():
    """只检查「允许并存窗口已关闭」的关注点 —— 窗口内的并存是设计，不是违规。"""
    for name, new_sym, old_sym, enable_at in CONCERNS:
        if enable_at not in ENABLED_RULES:
            continue                      # 窗口未关闭，规则还没启用
        new_hits = _grep_symbol(new_sym)
        old_hits = _grep_symbol(old_sym)
        assert not (new_hits and old_hits), (
            f"关注点『{name}』在并存窗口关闭后仍有两套实现："
            f"新 {new_sym} 与旧 {old_sym} 同时存在"
        )


# 基线白名单 = §1.5 表里的 16 个现存类名；每删一个就移除一个
INMEMORY_BASELINE = {
    "InMemoryOutboxRepository", "InMemoryResultSink", "InMemoryDeepAgentFactory",
    "InMemoryDeepAgent", "InMemoryToolRegistry", "InMemoryLayeredMemory",
    "InMemoryCostAttribution", "InMemorySummaryModel", "InMemoryLockManager",
    "InMemoryPolicyGuard", "InMemoryAuditLogger", "InMemoryApprovalStore",
    "InMemoryDataSubjectService", "InMemoryUserDataExportService",
    "InMemoryToolExecutor", "InMemoryOnlineEvaluator",
}


def test_no_inmemory_in_production():
    """生产包不得有【新的】InMemory* 假实现（本计划 §1.5 规则 R1/R2）。

    基线白名单里的 16 个是「已知存量」，随 Agent Stage 7 逐个删除；
    **白名单之外出现任何 InMemory* 即红** —— 这是「不许新增长孤儿」的闸门。
    """
    hits = _grep_class_def(r"^class InMemory\w+", "backend/runtimes/", exclude=["tests/"])
    new_ones = set(hits) - INMEMORY_BASELINE
    assert not new_ones, f"生产包里出现新的 InMemory* 假实现：{sorted(new_ones)}"
```

> **守卫 6 必须在全局前置阶段就进 CI**，而不是等 Agent Stage 7 清理时才建 —— 它的价值在**拦住新增**，不在于清理存量。
>
> **⚠️ 两条守卫都不能「一次性全开」**：
> - **规则 1 若一开始就全开，CI 从第一天起就是红的** —— 因为 §1.2 里有 25 条关注点按设计就要并存一段时间（`MemoryService` 拆了但单类还在、`wait_status` 停写了但列还在……）。**规则必须分批启用**：每条关注点的规则在**它的「允许并存窗口」关闭的那个 Stage** 合入时才生效。
> - **规则 6 若一开始就用「零命中」判定，同样是红的** —— 那 16 个 `InMemory*` 今天就在生产包里。所以规则 6 用**基线白名单 + 只查新增**。
>
> **这两张表（ENABLED_RULES 与 INMEMORY_BASELINE）应由本计划 §1.2 / §1.5 自动生成**，避免「文档改了、守卫没改」。

### 6.3 「两套实现」的三个隐蔽形态（**最容易漏**）

| 形态 | 例子 | 怎么发现 |
|---|---|---|
| **同名不同实现** | `MemoryService` 与 `MemoryRuntimeService` / `MemoryAdminService` | 守卫规则 1（同一关注点两个类名） |
| **旧表 + 新表** | `agent_turns` 与 `session_turns` | 表清单核对（README §3.3.2 的表归属表） |
| **旧列 + 新列** | `wait_status` 与 `session_turns.status` | 同上；且 `wait_status` **停写 ≠ 删除**（关注点 #23 的 DROP 在 Session Stage 6） |

> **「停用」不是「删除」**。本计划把每个旧实现的删除都落到**具体的层与具体的 Stage**（§1.2 表的「归属层 · Stage」列），就是为了防止「以为删了，其实只是打了个弃用标记」。

---

## 7. 日常执行规约

| # | 规约 | 为什么 |
|---|---|---|
| 1 | **接管与删除分开 PR**（除非是原子替换） | 中间要有「清理窗口」用于流量对照与回退兜底 |
| 2 | **每个 PR 只碰一个台账条目** | 避免「归零判据」无法定位到具体条目 |
| 3 | **指标未归零不许进删除 PR** | 唯一客观的判据 |
| 4 | **扫描脚本在删除 PR 里同步启用对应规则** | 规则与删除在同一个提交完成，否则脚本形同虚设 |
| 5 | **新代码不得引入第二套实现** | 守卫规则 1（§6.2）会在 CI 拦下 |
| 6 | **每一层的退出判据必须包含「旧的已删除」** | §1.3 的三条删除定义 |
| 7 | **改动跨层时，同步更新 README §3.3 的依赖表与本计划 §1.2 的关注点表** | 这两张表是唯一的顺序来源与守卫数据源 |
| 8 | **决策一改，正文锚点 + 附录 + README §2 三处同改** | 已验证 51 条决策的锚点覆盖率是 100%，别破坏它 |
| 9 | **跨层的原子删除必须互引 PR 号** | Gateway G-28 ↔ Session S-33 是同一个 PR；拆开就会 IM 断 |
| 10 | **跨层的回退粒度 = 层，不是 PR** | 旧代码会互相依赖：`use_cases/run_turn.py` import `adapter/llm/prompts.py` 四套模板（Context Stage 5 删）、`runner._run_turn_inner` 调 `_load_messages`（Context Stage 5 删）与 `_remember`（Memory Stage 7 删）。**回退 A 层的 PR 会恢复一个 import 已删模块的文件 → ImportError**。所以跨层回退必须**回到指定基线 commit 整体回退**，不能只 revert 单个 PR |
| 11 | **回退前先确认基线 commit 的依赖闭合** | 整体回退到基线时，该基线上的所有依赖（迁移、模块、配置）必须一起回来；跨迁移的回退必须先跑回滚脚本 |

### 7.1 每次合并前的检查清单

```bash
# 1. 收敛判据可查
curl -s localhost:8000/metrics | grep qzdap_legacy_calls_total

# 2. 旧实现零残留（扫描脚本，唯一来源 = 台账 §3.1）
bash backend/scripts/check_no_legacy_impl.sh

# 3. 单实现不变量没被破坏（没有两套并存）+ 生产包无 InMemory*
pytest backend/tests/architecture/test_single_implementation.py -q

# 4. 层边界没被绕过
pytest backend/tests/architecture/ -q

# 5. 端到端循环仍然跑通（不能只有节点单测）
pytest backend/tests/integration/test_agent_loop_e2e.py -q
```

---

## 8. 风险登记与预案

| # | 风险 | 触发信号 | 预案 | 归属层 |
|---|---|---|---|---|
| 1 | **Session Stage 3 拖期** | 延期 > 1 周 | 拆成「`turn_runner` 骨架」+「语义合并」两个 PR；骨架可先跑通简单问答 | Session |
| 2 | **语义合并出错** | 双写期对账有差异 | 双写期**不做切读**；有差异就停，双写继续跑直到一致 | Session |
| 3 | **两套实现并存被遗忘** | 台账有「已弃用」长期不变 | 守卫规则 1 + **每层的退出判据强制含「旧的已删除」**；「已弃用」超过一个 Stage 就升级为阻塞项 | 全部 |
| 4 | **工具幂等上线后仍有重复执行** | `qzdap_tool_idempotent_hit_total` 为 0 但调用数高 | 立即**停用有副作用的工具**（不是回滚整个层） | Agent |
| 5 | **审批恢复后执行了错误的调用** | `request_hash` 复核失败 | 复核失败**必须拒绝执行**（不是跳过） | Session / Agent |
| 6 | **迁移不可回滚** | dev 库回滚脚本失败 | 每个迁移的回滚脚本**在合入前跑一遍**（五个迁移的回滚 SQL 已在层方案里给出） | 各层 |
| 7 | **删表后数据无法恢复** | 备份不存在 / 未演练 | **恢复演练是 Session Stage 6 的准入条件**，不是可选项 | Session |
| 8 | **回滚引入安全缺陷** | 回滚后出现跨用户数据 | 纪律：**安全修复不回退**（§7 规约 1 的例外） | 各层 |
| 9 | **`deepagents` 与当前 lock 不兼容** | 探针失败 | 决策 #8 选「只保留类型定义」；本层不阻塞主线 | Agent |
| 10 | **并行 PR 互相冲突** | 同一文件被两个 PR 改 | 迁移**串行**（0044→0048）；同一张表的 DDL 只在一个迁移里 | 各层 |
| 11 | **「建而不切」重演** | Stage 打勾但旧代码没少 | **每层的判据是「台账归零 + 旧符号零命中」，不是「功能可用」** | 全部 |
| 12 | **原子切换被拆开** | IM 渠道 404 / 断流 | 规约 9：跨层原子删除必须互引 PR 号，CI 校验 | Gateway / Session |
| 13 | **`InMemory*` 被下一个人当现成实现接线** | 生产包出现基线白名单之外的 `InMemory*` | 守卫规则 6（基线白名单 + 只查新增）**从全局前置起就在拦**；§1.5 规则 R4 要求新写 `InMemory*` 必须同 PR 登记归属 | Agent |
| 14 | **删除顺序搞反（下层先删）** | 旧循环调用已删方法 → `AttributeError` / `ImportError` | §4.1 的「删除顺序自底向上」硬依赖；Agent A-26（接线旧循环）是 Context Stage 4 与 Memory Stage 7 的前置 | Session / Context / Memory / Agent |
| 15 | **Memory 决策 #1（L3 vs knowledge）迟迟不拍板** | Memory Stage 7 的 `admin_memory_l3` 退役无法开始 | **决策 #1 是 Memory Stage 0 的前置**，不拍板则该层整段停摆；拍板前不得开工 Stage 7 | Memory |
| 16 | **跨模块外部前置未就绪** | Agent Stage 3 / 4 到点才发现 `route_strategy` 新取值、工具幂等归属、role 标签都没人改 | 横切 **H8**（每层 Stage 0 显式登记外部前置 + 责任人与完成时间） | Agent |
| 17 | **仓外 API 消费者不知情** | 删 `/v1/sessions*` 后出现 404 突增 | 前置 C9 / P-11 先确认；确认不了就**保留兼容别名并标注 deprecation 期限**（但必须写进台账） | Gateway |
| 18 | **低流量入口永远达不到 95%** | 清理窗口无限延长 | 台账 §3.3 的「排除本来就没流量的入口」需要**兜底期限**（建议：该入口连续 14 天调用量为 0 即判「无流量」，直接进清理，不等占比） | 各层 |
| 19 | **回退到有安全缺陷的旧状态** | 回退后出现跨用户数据泄漏 | 纪律：**安全修复不回退**（规约 1 的例外）；Memory 的作用域过滤（X14）与审批校验（X7）**永不回退** | 各层 |

---

## 9. 与既有文档的关系

| 文档 | 在本计划里的角色 |
|---|---|
| [`README.md`](README.md) §6 / §7 | **里程碑判据**与**系统级验收**的来源 |
| 六份层方案 | **架构与验收标准的来源**；本计划不重新设计。**§3 的 Stage 编号与层方案一致** |
| [`cleanup-ledger.md`](cleanup-ledger.md) | **收敛判据的来源**（指标 + 扫描脚本 + 状态机 + 唯一 owner 规则） |
| [`../session-module-refactor-plan.md`](../session-module-refactor-plan.md) v3.1 | **状态模型与持久化设计的上游**（§4 / §5.7 / §13.3–13.5 / §14 仍有效） |
| [`../langgraph-1x-migration-notes.md`](../langgraph-1x-migration-notes.md) | LangGraph 1.x 升级结论；✅ **已补齐**（2026-10-31）—— `modules/agent_runtime/pyproject.toml` **已显式声明** `qzdap-vault` ✓ → 本计划 §2.2 前置 B **已消解** ✓ |
| [`../deepagents-probe-result.md`](../deepagents-probe-result.md) | Deep Agents 的 API 签名与三条实施约束 → Agent Stage 6 |

---

## 附录 A：工作项索引（**按层分组，全量可勾选**）

> **勾选规则**：完成一个工作项就勾上，并注明它让哪个台账条目前进了一格。**「删除」类工作项必须勾上才算该层完成。**

### 全局前置
> **2026-10-31 核对**（依据 = 代码 + 台账 + git 历史 ✓）。

- [x] P-01 拍板「表选择」决策 —— **gate**（前置 A）—— ✅ **2026-10-29 用户拍板** ✓（53 条决策全部定稿 ✓ —— §2.1 ✓）
- [x] **P-02 修 `qzdap-vault` 缺失声明**（前置 B）—— ✅ **2026-10-31 已修** —— `modules/agent_runtime` 有 **5 个文件** import `qzdap_vault` ✓（`adapter/llm/__init__.py` ✓ / `adapter/context/summary_adapter.py` ✓ / `adapter/graph/runner.py` ✓ / `adapter/graph/chat_model.py` ✓ / `application/ports/__init__.py` ✓）而 pyproject **没声明它** ✗ → **isolated install 环境直接 `ModuleNotFoundError`** ✗✗ —— 已加 `qzdap-vault` 到 `modules/agent_runtime/pyproject.toml` ✓ + `uv.lock` 离线重锁 ✓（**无版本变动** ✓）。✅ **同类问题已有守门人** ✓（= **P-12** ✓ —— `backend/scripts/check_isolated_deps.py` ✓ + CI 的 `isolated-install` job ✓ —— 它还当场抓到另外 7 个包漏声明 ✗✗ → 已补 ✓）
- [x] P-03 建 `qzdap_legacy_calls_total` + `record_legacy_call`（C1）—— ✅ `libs/observability/.../metrics.py` ✓（`NEW_CALLS_TOTAL` ✓ + `record_new_call` ✓ 同一套 `entry` 标签 ✓）
- [x] P-04 给台账条目的旧入口打点（C2，**逐条核对，不许漏**）—— ✅ **36 条中 16 条在旧实现的入口处打点** ✓（其余 20 条走替代判据 ✓ —— grep 扫描 / 数据迁移 / 回归测试 ✓） —— ⚠️ **打点随旧实现删除逐条撤除** ✓（旧实现不在场时打点必须撤 ✓ 否则指标永远非零 ✗✗）
- [x] P-05 建 CI 扫描脚本骨架（C3）—— ✅ `backend/scripts/check_no_legacy_impl.sh` ✓（**31 条启用** ✓ / 13 条待启用 ✓）+ CI 的 `legacy-scan` job ✓
- [x] P-06 建架构测试骨架 + 单实现扫描 + **`InMemory*` 禁令**（C4）—— ✅ `backend/tests/architecture/` ✓（5 个文件 ✓ —— `test_single_implementation.py` ✓ / `test_error_code_vocabulary.py` ✓ / 三层的 boundary ✓）
- [x] P-07 建指标看板查询片段（C5）—— ✅ `/metrics` 端点已有 ✓（按 `entry` 分组查询 ✓）
- [x] P-08 登记 16 个 `InMemory*` + 平行 `*Event` 的处置归属（C6）—— ✅ §1.5 ✓
- [x] **P-09 建验收环境与脱敏样本**（H1 / C7）—— ✅ **2026-10-31 已做** —— `composition/qzdap_app/.../acceptance_samples.py` ✓（**两个验收租户 × 每租户两个用户** ✓ —— 验隔离 ✓；**长会话** 6 轮 ✓；**含工具调用**的轮次 ✓；**含审批挂起**的轮次 ✓；**每用户一条记忆** ✓；**agent 上绑了记忆策略** ✓ —— C6 ✓）—— **id 用 uuid5 派生** ✓（**可复现** ✓ —— 脚本**幂等** ✓）—— **邮箱用 `.invalid`** ✓（脱敏 ✓ —— 保证不可投递 ✓）；脚本 `scripts/seed_acceptance_samples.py` ✓（**demo / 生产环境直接拒绝** ✓ —— demo 库要干净 ✓）+ `scripts/acceptance_check.py` ✓（**一键跑完 13 条判据** ✓ —— 样本在不在 ✓ / 孤儿消息 ✓ / 审批挂起 ✓ / 事件 seq 连续 ✓ / 策略绑定 ✓ / **跨租户越界** ✓ / 退役列 ✓）
- [x] **P-10 建告警规则**（H2 / C8）—— ✅ **2026-10-31 已做** —— `deploy/prometheus/alerts.yml` ✓（**11 条规则** ✓ —— 覆盖**每个新指标** ✓：收敛闸门 2 ✓ / Router 3 ✓ / Memory 2 ✓ / 通用 4 ✓）+ `docs/refactor/session-architecture/oncall-runbook.md` ✓（**每条告警的回退步骤** ✓ —— 「出了事怎么办」不用猜 ✓ —— H2 的验收 ✓）。⚠️ **阈值是起步值** ✓（按真实基线调 ✓ —— 调整要留痕 ✓）
- [x] P-11 **确认 `/v1/sessions*` 是否有仓外消费者**（H5 / C9，需 API owner 拍板）—— ✅ **已确认无仓外调用方** ✓（Gateway G-27 的删除依据 ✓ —— 兼容保留期因此归零 ✓）
- [x] **P-12 CI 加 isolated install 检查**（H6 / C10）—— ✅ **2026-10-31 已做** —— `backend/scripts/check_isolated_deps.py` ✓（**逐包**解析各自的 `pyproject.toml` ✓ → AST 扫 import ✓ → import 到的 **lib** 必须被**声明** ✓ —— 判据只有 pyproject 一个来源 ✓）+ CI 的 `isolated-install` job ✓。⚠️ **它当场抓到 7 个包漏声明** ✗✗ → 已补 ✓（`libs/auth` ✓ `libs/observability` ✓ `modules/agent_factory` ✓ `modules/evaluation` ✓ `modules/governance` ✓ `modules/self_evolution` ✓ `modules/tool` ✓ —— 各补 `qzdap-persistence` / `qzdap-auth` / `qzdap-vault` ✓）+ `uv.lock` 离线重锁 ✓（**无版本变动** ✓）。⚠️ **顺带修了 CI 的同步命令** ✗✗（`uv sync --all-extras` **只装根的依赖** ✓ → workspace 成员被**卸载** ✓ → smoke job import 不到 `qzdap.composition` ✗✗）→ 全部改成 `uv sync --all-extras --all-packages` ✓（与 Makefile 一致 ✓）

- [x] **P-13 CI 的 type-check 闸门（mypy）** —— ✅ **已达成**（**2026-10-31** ✓）—— ⚠️ **这批不进 PR** ✓（**2026-10-31 决定** ✓）—— **与 S-36 / S-21b 同一批走** ✓（**用户随后决定提前结束窗口** ✓ → **同批一起提交** ✓ —— **一次评审覆盖「类型收口 + 旧表 DROP + 薄壳删除」** ✓）—— **148 处错误清零** ✓（`mypy libs modules composition` ✓ —— **Success: no issues found** ✓）—— CI 的 `type-check` job **第一次是真的绿的** ✓（job 名字从「mypy strict」改成「mypy」✓ —— 配置**不是** strict ✓ —— 别写虚的 ✗）。⚠️ **2026-10-31 补记**：**这个绿灯后来被自己弄红过** ✓ —— 紧随其后的 `8621e0ef`（`eager_defaults` 一次性兜住 ✓）给 `DeclarativeBase` 加 `__mapper_args__: ClassVar[...]` ✓ → **mypy 报「不能用类变量覆盖实例变量」** ✓（SQLAlchemy 自己在 `decl_base.py` 里把它声明成**实例变量** ✓）→ **CI 的 type-check 会红** ✗✗（台账写「已达成」而代码已漂 ✓ —— **台账失真比没有台账更危险** ✓）。✅ **已修** ✓（2026-10-31 ✓ —— 改成 `Mapping[str, Any]` ✓ —— **不是**加 `# type: ignore` ✓ —— 那是把闸门关掉 ✗✗；**运行时行为逐字不变** ✓ —— `eager_defaults=True` ✓ 仍进到 mapper ✓）。**收口口径** ✓（**不是**逐处加 `# type: ignore` ✓ —— 那是把闸门关掉 ✗✗）：
  | 落点 | 做了什么 | 为什么 |
  |---|---|---|
  | **品牌 ID 搬家** ✓ | `qzdap_schema.ids` → **`qzdap_kernel.ids`** ✓（165 个文件的导入改掉 ✓） | 品牌 ID 是**最底层的值对象** ✓ → 住进**零依赖的 base 层** ✓ → **每一层**（libs ✓ / modules ✓ / composition ✓ / 契约层 ✓）共用同一套词汇 ✓；住 schema 的话 kernel 自己用不上 ✓ → 规则在 kernel 层就断了 ✗ |
  | **边界规则** ✓ | **裸 `UUID` 只允许出现在最外层** ✓ —— HTTP 头 / 查询参数 / JWT 解析 / DB 行 ✓；**进应用层前转品牌 ID** ✓；应用层往下（用例 / 端口 / 领域实体）**一律品牌 ID** ✓ | `NewType` 的转换**不校验** ✓ —— 逐处 `TenantId(x)` 那种糊法**等于没有类型保护** ✓ → 必须**在类型上贯通** ✓ |
  | **端口与适配器同步** ✓ | 事件发布端口（agent_runtime ✓ / tool ✓ / channel ✓ / identity ✓）、`EventBus.subscribe` ✓（协议写的是同步 ✓ 实现全是异步 ✓）、`Principal` ✓ / kernel 上下文 ✓ / `EventEnvelope` ✓、`TenantScopedMixin` 的时间列 ✓（`Mapped[object]` → `Mapped[datetime]` ✓ —— 一处修掉跨 5 个包的 14 处 ✓） | 端口是**应用层契约** ✓ —— 契约不收口 ✓ → 用例层再收也没用 ✗ |
  | **顺带修掉的真缺陷** ✓ | ① **写订阅必炸** ✓（领域实体没有 `workspace_id` ✓ ORM 却映射了 ✓ → 迁移 **0060** 删列 ✓）**且写了也不落库** ✓（请求依赖只开会话 ✓ 既不提交也不回滚 ✓ → 事务随请求结束回滚 ✓ → **平台域的写全部丢** ✓ → 依赖改成「开会话 / 成功提交 / 失败回滚」✓ 与 admin ops 那个依赖同口径 ✓ —— **评测域也是同一个病** ✓（那边一个显式提交都没有 ✓ → 一起改 ✓；agent_factory 不算丢 ✓ —— 用例层自己提交 ✓ —— 只是统一口径 ✓）；② **评测「列用例」端点必 500** ✓（服务上**没有** `list_cases` ✓ → 补用例 ✓）；③ **真跑评测那条路必炸** ✓（版本是**字典** ✓ 却按属性访问 ✓ + `AgentFactoryQueryPort` **没有任何实现** ✓ → 按键取值 ✓ + 组合根补实现 ✓）；④ **撤销 API Key 的端口缺 `update` 声明** ✓ | 这些是**潜伏的运行时错误** ✓ —— 表里一行数据都没有 ✓ / 那个端点没人调 ✓ → 一直没人撞上 ✓ → **类型检查把它们逼出来了** ✓ |
  | **回归测试** ✓ | 三个新测试文件 ✓（评测用例 ✓ / 订阅映射 ✓ / 模型 id 归一 ✓） | 缺陷要有**能被看见的测试** ✓ —— 不然下次还会破 ✓ |

### Gateway 层（§3.1）—— **删除 G1–G12**
> **台账 G1–G12 全部「已清理」** ✓ —— 本层**收口** ✓。剩余的只有「现状文档同步」（与 Session S-38 / Router R-28 / Context C-32 / Memory M-51 一起补 ✓）。

- [x] G-01 `gateway/` 骨架 + `types.py` ✓ · **G-02 `ErrorCode` 投影表** ✅ 2026-10-29 · **G-02b 错误码收敛（15 个 → `ErrorCode` 枚举 + 台账 G12）** ✅ 2026-10-29 · **G-02c 跨模块扩展（121 个码 → 枚举 160 个 + 词汇表搬进 kernel + 守门人扩到全量）** ✅ **2026-10-31** ✓ · G-03 **迁移 0044** ✓ · G-04 架构测试 ✓ · G-05 打点 G1–G11 ✓（随旧实现删除**已撤除** ✓）
- [x] G-06 `IdempotencyStore` ✓ · G-07 `Gateway.accept` ✓ · G-08 web 入站切过来 ✓
- [x] G-09 **删 `record_request_id` + `recent_request_ids`** → **G1** ✓ · **G-09b 审批恢复路径传幂等键** → **G10** ✓ · **G-09c 过期行不当成重复** ✓
- [x] G-10 `IdentityVerifier` ✓ · G-11 服务账号物化 ✓（迁移 0049 ✓）· G-12 验签迁出 ✓ · G-13 `/v1/sessions` 租户校验（**不适用** ✓ —— 该路由已随 Stage 5 删除 ✓）· **G-13b `modules/channel` 加 `qzdap-agent-runtime` 依赖** ✓
- [x] G-14 **删验签分支 + 硬编码身份常量** → **G2 / G3** ✓
- [x] G-15 4 个 inbound adapter ✓ · G-16 附件统一 ✓
- [x] G-17 **删 `ParsedMessage` + `ChannelMessageReceived` + IM LRU** → **G4 / G5 / G6** ✓
- [x] G-18 `ResultSink` ✓ · G-19 渠道入站切过来 ✓
- [x] **G-20 切 IM 入口**（与 **S-32 同 PR**）✅ 2026-10-30 ✓
- [x] G-21 `/v1/sessions*` 停用打点（随后随 Stage 5 删除 ✓）· G-22 `dispatch_subscriber.py` 停用打点 ✓ · G-23 重复请求降级路径（**Stage 4b 已删** ✓ 改重放 ✓）
- [x] G-24 `Last-Event-ID` 重放 ✓ · G-25 降级路径移除 ✓ · G-26 重放一致性校验 ✓
- [x] G-27 **删 `/v1/sessions*`** → **G7 / G8** ✓ · G-28 **删 `dispatch_subscriber.py`** → **G9** ✓（2026-10-30 ✓ 与 **S-33 同 PR** ✓）· G-29 残留列 / 孤儿索引 ✓（迁移 0051 ✓）
- [x] G-30 启用扫描脚本 Gateway 段 ✓ · G-31 更新台账 ✓ · **G-31b 架构测试** ✓ —— ⚠️ **现状文档**（`docs/copilot-chat-module-architecture.md` ✓ / 根 `README.md` ✓）在 G-31 已更新 ✓，但**后续几层的变更还没回灌** ✗（见 S-38 ✓）

### Router 层（§3.2）—— **删除 R1–R4**
> **台账 R1–R4 全部「已清理」** ✓ —— **Stage 3（排队语义）已落地** ✓（2026-10-31 ✓）。

- [x] R-01 `router/` 骨架 ✓ · R-02 **迁移 0045** ✓ · R-03 策略配置 schema ✓ · R-04 `UserDirectoryPort` ✓ · R-06 打点 R1–R4 ✓（随旧实现删除**已撤除** ✓）
- [x] **R-05 `QUEUE_FULL` / `QUEUE_TIMEOUT`** ✓ —— **随 Stage 3 一起加** ✓（两个码 + `_HTTP_STATUS` 429 / 503 ✓ + `ErrorCopy` 文案 ✓ —— **消费方已就位** ✓）
- [x] R-07 规则链 ✓ · R-08 `RouteDecision` 留痕 ✓（`session_turns.route_decision` ✓）
- [x] R-09 **web 建会话改走 Strategy** → **R2 已清理** ✓
- [x] R-10 会话 key 派生 ✓（哈希版 ✓ 6 维 ✓ —— **2026-10-31 真正接上** ✓：此前**只有测试在调** ✓ —— 建而不切 ✗✗）· **R-10b 调 Session 的 `lookup`** ✓（Session S-08b ✓ —— 粘性规则的输入有了 ✓）· R-11 改调 `resolve_or_create` ✓
- [x] **R-12 `ingress_seq` 分配 + 入队** ✓ —— **分配** ✓（`session/sequence.py` ✓ 原子自增 ✓）+ **入队** ✓（`status='queued'` ✓）
- [x] R-13 IM 路径切换 + 旧 key 停用 → **R1 / R4** ✓（2026-10-30 ✓ Session Stage 5b ✓）
- [x] **R-14 FIFO 放行** ✓（契约 `session/queue.py` ✓ + 实现 `PostgresTurnQueue` ✓）· **R-15 会话级互斥** ✓（轮次行 CAS ✓ —— 决策 #9 ✓）· **R-16 审批不占执行位** ✓（`waiting` ≠ `running` ✓）· **R-17 并发语义切排队** ✓（`TurnRunner._wait_for_slot()` ✓ —— 排队期间发 `queued` chunk ✓；⚠️ **开关关掉 = 旧语义** ✓）
- [x] **R-18 FIFO 兜底路径** ✓ —— **以权威值为准放行** ✓ + **修快照** ✓ + **计数告警** ✓（`qzdap_router_seq_snapshot_drift_total` ✓）
- [x] **R-19 渠道入站改走 Strategy** ✓ —— **IM 也走规则链** ✓（`channel_turn.py` 的 `_route()` ✓ —— 渠道登记的 agent 只是「显式指定」这一条规则的输入 ✓；粘性 ✓；**不命中 → 退回渠道 agent** ✓ —— 不丢消息 ✓）
- [x] R-20 `dispatch_subscriber` 停用打点 ✓（文件已删 ✓）· R-21 第二套 turn 停用打点 ✓（两个用例已删 ✓）
- [x] R-22 **删 `build_session_key`** → **R4 已清理** ✓（扫描规则的目录原本写错 ✓ 已改正并启用 ✓）· R-23 **确认 `try_claim` 的互斥已迁走** ✓（**不删** ✓ —— R3 归 Session ✓）· R-24 删 `catalog.py` 映射（⚠️ **待核对** ✓）
- [x] R-25 / R-26 **确认**无残留调用方 ✓ · R-27 启用扫描脚本 Router 段 ✓ · R-28 更新台账 + **现状文档** ✓（2026-10-31 ✓ —— `docs/copilot-chat-module-architecture.md` v1.4 ✓）

### Session 层（§3.3）—— **删除 X2 / X3 / X4 / X6 / X7 / X18**（**全局关键路径**）
- [x] S-01 `session/` 骨架 + `state.py` ✓ · S-02 **迁移 0046** ✓ · S-03 `session_messages.session_id` 回填 ✓ · S-04 `APPROVER_MUST_DIFFER` ✓ · S-05 **`AsyncPostgresSaver`** ✓（**X20 已清理** ✓）· S-06 停写 `wait_status` → **X6** ✓ · S-07 打点 X2–X7 ✓
- [x] S-08 `resolve_or_create` ✓ · **S-08b `lookup`（只读，Router 粘性依据）** ✓ · S-09 `close`/`archive` ✓ · S-10 sweeper 骨架 ✓ · **S-10b sweeper 第四类清扫** ✓
| | **S-11 删 `try_claim` 的 `wait_status` 分支** | ✅ **已达成**（2026-10-31）—— **X2 已在 Stage 5b 删除** ✓ → 阻塞解除 ✓ → `try_claim` 及其 `wait_status` CAS **随台账 R3 一起删掉** ✓（`SessionRepository` 协议里的方法一并删 ✓）；旧打点 `record_legacy_call("R3")` 撤除 ✓ | **R3（关注点 #23）** | **~20 行** | S-08 ✓ |
- [x] S-12 `ingress_seq` ✓ · S-13 `session_seq` ✓ · S-15 启用新表写入 ✓ · **S-15a 切读新表** ✓ · **S-15b 停旧写** ✓（双写期结束 ✓ 对账差异 = 0 ✓）
| | S-14 checkpoint 接线 | ✅ **已达成（以「不适用」收口）**（2026-10-31）—— 它唯一的消费者是**那张 19 节点的 LangGraph 图** ✓（**已随 Agent Stage 7 删除** ✓）→ **新的循环用会话 `metadata["resume"]` + 轮次行续传** ✓（不需要 LangGraph 的 checkpoint ✓）→ **lifespan 不再起 saver** ✓（省一个连接池 ✓）；✅ **checkpoint 表已删** ✓（**迁移 0063** ✓ —— 2026-10-31 ✓ —— S-36 那批漏了它们 ✓ → 本次补上 ✓ —— **全仓零引用** ✓ —— `checkpoint_thread_id` 死函数一起删了 ✓） | — | 0 | S-05 |
- [x] S-16 `turn_runner.py` 落地 ✓ · S-17 轮次幂等 ✓ · S-18 取消 ✓ · S-19 成本归属 ✓ · S-20 **切 web/api 入口** ✓
- [x] S-21 停用打点 `copilot.py` turn 编排 → **X18** ✓ · S-22 停用打点 `use_cases/run_turn*.py` → **X2（IM 侧）** ✓
- [x] **S-21b 删 `copilot.py` 的 turn 编排（薄壳）** —— ✅ **已达成**（**2026-10-31** ✓ —— **用户决定提前结束清理窗口** ✓（原定 2026-11-06 ✓））—— 目标形态**按 §3.3 的 S-21b 行照着做完了** ✓：幂等 + claim + 转发 → 契约层 `TurnRunner.run_turn` ✓ / 读 + 组装 → 模块侧 `application/turn_entry.py` ✓ / 调用方全切 ✓（`session_router` ✓ / `one_shot_turn` ✓ / `channel_turn` ✓ / `copilot.decide_approval` ✓）/ 删薄壳 ✓（`stream_turn` / `_run_turn` / `_select_key` 全删 ✓ ≈225 行 ✓）—— **HTTP 契约不变** ✓（409 `SESSION_BUSY` ✓ + `DUPLICATE_REQUEST` 带 `turn_id` ✓）—— **X18 → 已清理** ✓
- [x] S-23 chunk 写 `session_events` ✓ · S-24 dispatcher 接线 ✓ · S-25 `Last-Event-ID` 重放 ✓ · S-26 outbox worker 接线 ✓
- [x] S-27 审批挂起落库 ✓ · S-28 恢复校验清单 ✓ · S-29 **删 `except Exception: pass`** → **X7** ✓
| | S-30 审批自动过期 | ✅ **已达成**（2026-10-31）—— **判定在治理域** ✓（`expire_if_due()` ✓ —— 只有一份判断 ✓）；清扫器**接上回调** ✓（组合根接线 ✓ —— 清扫器不引治理模块 ✓）；跨租户扫「到期未决策」✓（维护任务 ✓）；**一类失败不影响另一类** ✓ | — | 0 | S-27 ✓ |
- [x] S-32 **切 IM 入口**（与 **G-20 同 PR**）✓ · S-33 **删 `use_cases/run_turn.py` + `run_turn_to_completion.py`** → **X2** ✓
- [x] S-34 **DROP `wait_status`** → **X6** ✓（迁移 0053 ✓）
| | **S-35 停写并废弃 `agent_sessions.graph_state`** | ✅ **已达成**（2026-10-31）—— ① **续传状态改归 `metadata["resume"]`** ✓（契约层 `resume_state` ✓）；② **待审批从轮次行读** ✓（权威 ✓）；③ **plan 决策改归 metadata** ✓；④ ORM 不再映射 ✓ + **迁移 0056 DROP 列** ✓；⑤ 扫描规则 **X3 启用** ✓。⚠️ **前提的说明**：方案要求「≥95% 流量后 ≥7 天只读期」✓ —— 那是**有生产流量时**的判据 ✓；当前是**开发期** ✓（无生产流量 ✓）→ 改为「**代码里不再有读写点** + **ORM 不映射** + **扫描规则启用**」✓（等价且更强 ✓） | **X3 → 已清理**（关注点 #22） | **1 列** | 与 S-34 同 PR ✓ |
| | S-37 启用扫描脚本 Session 段 | ✅ **已达成**（2026-10-31）—— **X2 / X3 / X4 / X6 / X18 段全部启用** ✓（**X4 段随 S-36 一起启用** ✓ —— 旧表已 DROP ✓ —— 生产代码里不再有任何旧表名字面量 ✓ —— **47 条规则全部启用** ✓） | X4 已清理 ✓（关注点 #21） | 0 | S-33 · S-21b ✅ |
| | **S-39 §13.2 的架构规则 1 / 2 落地** | ✅ **已达成**（2026-10-31）—— 规则 1（**只有一个 turn 实现** ✓）+ 规则 2（**状态机是唯一的状态写入点** ✓）—— 判据见上表 ✓ | — | ~120 行 | S-21b · S-33 |

### Context 层（§3.4）—— **删除 X8 / X9 / X10**
- [x] C-01 `context/` 骨架 ✓ · C-02 **迁移 0047** ✓ · C-03 `tokens.py` ✓ · C-04 打点 X8–X10 ✓（X10 的旧入口随 Session Stage 5b 删除 ✓ → 打点自然归零 ✓）
- [x] C-05 `ContextBuilder` ✓ · C-06 agent prompts 接入 ✓ · C-07 单段式渲染 ✓ · C-08 召回发起 ✓ · C-09 manifest 生成 ✓
- [x] C-10 **只新建，不动调用点** ✓ · **C-10b Builder 接上生产调用方** ✓（Agent A-26 ✓）· C-11 async 压缩器 ✓ · C-12 结构化摘要 ✓ · C-13 复验预算 ✓ · C-14 `removed_ids` 差集 ✓ · C-15 真正的降级序 ✓ · C-16 `context_compacted` 事件 ✓ · C-17 停用打点 `compact.py` → **X9** ✓
- [x] C-18 manifest 落库 ✓（**Context Stage 4 已接上生产** ✓）· C-19 `rolling_summary` 迁移 ✓ · C-20 交付前落库 ✓
- [x] C-21 Agent Loop 调 Context ✓（**旧循环那半** ✓ —— A-26 ✓；✅ **新 `AgentLoopRunner` 那半也已达成** ✓ —— A-25 / A-27 ✓ —— 生产路径跑的是新循环 ✓（`adapter/graph/runner.py` ✓）+ 上下文走 `ContextBuilder` ✓）· [x] **C-22 召回失败的 degraded 标记** ✓（2026-10-31 —— `flags` 契约落地 ✓ 全链路通 ✓）· C-23 端到端回归 ✓（`test_context_wiring.py` ✓）
- [x] C-24 停用打点 `_load_messages` / 四套模板 / `compact.py` → **X8 / X9 / X10** ✓（调用点已归零 ✓ —— 实测 legacy 计数 0 ✓）· C-25 自拼 messages 分支停用打点 ✓（旧循环那半 ✓ —— **删除归 Agent X17** ✓）
- [x] C-26 **删 `compact.py`** → **X9** ✓ · C-27 **删四套模板** → **X10** ✓ · C-28 **删 `_load_messages`** → **X8** ✓ · [x] **C-29 删 `budget.py`** ✓ —— **已随 Agent Stage 7 删除** ✓（2026-10-31 ✓ —— 那两个旧类只被死代码 import ✓）· C-30 删 `metadata['rolling_summary']` 残留 ✓
- [x] C-31 启用扫描脚本 Context 段 ✓（28 → 30 条 ✓）· [x] **C-32 更新台账 + 现状文档** ✓（2026-10-31 ✓ —— 同一份现状文档 ✓）

### Memory 层（§3.5）—— **删除 X11 / X12 / X13 / X15 / X16，修复 X14**
- [x] M-01 **拆分 `MemoryService`** → **X16 拆分** ✓ · M-02 `memory/` 骨架 + 端口 ✓ · M-03 **迁移 0048** ✓（含 **DROP 死表 X19** ✓）· **M-03b 写入侧持久化 `owner_id`** ✓ · M-04 `RecallHit` 扩字段 ✓ · M-05 打点 X11–X16 ✓（随旧实现删除**已撤除** ✓）
- [x] M-06 L2 `user_id` 过滤 ✓ · M-07 向量 payload 过滤 ✓ · M-08 历史向量回填 ✓ · M-09 L3 `visible_scope` ACL —— **跳过** ✓（决策 #1：L3 退役 ✓）→ **X14 修复完成即「已弃用」** ✓
- [x] M-10 向量优先 + 词法兜底 ✓ · M-11 候选集 `top_k×4` ✓ · M-12 去重/阈值/abstain ✓ · M-13 provenance ✓ · M-14 C10 降级 ✓ · M-15 **确认 `layered.py` 从未接线** ✓ → **X12**
- [x] M-16 `FactExtractor` ✓ · M-17 `Redactor` ✓ · M-18 幂等 ✓ · M-19 置信度 ✓ · M-20 来源追溯 ✓ · M-21 **实现新 Writer，写新表** ✓
- [x] **M-22 `enabled`** ✓ · [x] **M-23 `scope`** ✓ · [x] **M-24 `policyLabel`** ✓ · [x] **M-25 `l3EntryIds`/`knowledge_refs`** ✓ —— ✅ **Stage 4 已达成**（2026-10-31 ✓ —— 管理端绑的东西运行面**真的读到** ✓：关掉就一条不写 ✓ / 会话级只召回本会话 ✓ / 绑定的条目一定被召回 ✓ / 保留策略标签解析出来 ✓）
- [x] **M-26 向量统一走 embedding** ✓ · [x] **M-27 异步补写** ✓ · [x] **M-28 `session_memory_buffer`** ✓ · [x] **M-29 会话结束提炼（sweeper 触发）** ✓ · [x] **M-30 提升规则** ✓ —— ✅ **Stage 5 已达成**（2026-10-31 ✓）
- [x] **M-31 统计更新** ✓ · [x] **M-32 淘汰器** ✓ · [x] **M-33 `trend()` 真实统计** ✓ · [x] **M-34 接入 sweeper** ✓ · [x] **M-35 淘汰执行器** ✓ —— ✅ **Stage 6 已达成**（2026-10-31 ✓ —— 策略**第一次有执行者** ✓ ✓）
- [x] **M-36 B1 管理接口** ✓（18 个端点全走服务 ✓）· [x] **M-37 B2 管理服务** ✓（2026-10-31 —— 配置发布与生效 ✓）· [x] **M-38 B3 管理策略** ✓（2026-10-31 —— `admin_rules.py` ✓ 共用闸门 ✓ 去重 ✓ 版本化 ✓）· [x] **M-39 C9 治理 provider** ✓（2026-10-31 —— **治理域的 `data_subject` 接口已建** ✓ —— 契约在**契约层** ✓ —— 记忆域实现 `scope="memory"` ✓ —— 删 **L2 + 向量 + 会话缓冲** ✓ —— 端点 `/v1/data-subject/{delete,export}` ✓ —— demo 栈实测 ✓）· [x] **M-40 乐观并发 409** ✓ · [x] **M-41 敏感闸门补齐** ✓ · [x] **M-42 管理端直写停用打点** ✓（**没有直写路径可停** ✓ → X16 转「已清理」✓）
- [x] M-43 **删 `_remember`** → **X11** ✓ · [x] M-44 **删 `layered.py`** → **X12** ✓（**已随 Agent Stage 7 删除** ✓ —— 扫描规则同时覆盖 `modules/` 与 `runtimes/` ✓）· [x] M-45 **删 `remember` 节点** → **X12** ✓（同批 ✓）· [x] M-46 **退役 `admin_memory_l1`** ✓（2026-10-31 —— 端点改读**会话缓冲** ✓ + 迁移 0057 **DROP 表** ✓ —— 台账 **X13 已清理** ✓）· [x] M-47 **退役 `admin_memory_l3`** ✓（2026-10-31 —— **先上新** ✓ 迁移 0058 搬进 knowledge ✓ + **再清旧** ✓ 端点 / 召回 / 契约层全删 ✓ + 迁移 0059 **DROP 表** ✓ —— 台账 **X15 已清理** ✓）· M-48 清理 `memory_policy` 无效语义 ✓ · M-49 **删原 `MemoryService` 单类** → **X16** ✓（已拆 ✓ —— 两个服务类**必须保留** ✓）
- [x] **M-50 启用扫描脚本 Memory 段** —— ✅ **全段已启用** ✓ —— **X11 / X12 / X16** 于 2026-10-31 随 Agent Stage 7 的删除启用 ✓；**X13 / X15** 于 2026-10-31 随 **M-46 / M-47** 的 DROP 启用 ✓（表没了 ✓ → `modules/` 零命中 ✓）—— **45 条规则全跑** ✓（2026-10-31 补 X5 的两条 —— 旧模块路径 + 类名 ✓ —— 剩下的 2 条关着的是 **X4 的旧表** ✓ —— 表还在 ✓ 关着才是对的 ✓）· [x] **M-51 更新台账 + 现状文档** ✓（2026-10-31 ✓ —— 同一份现状文档 ✓）

### Agent 层（§3.6）—— **删除 X5 / X1 + 关注点 #16 / #24–#29**
- [x] A-01 补五个端口 ✓ · A-02 `QZDAPChatModel` 骨架 ✓ · A-03 归一 `TaskKind`/`TaskClassifier` ✓（`graph/routing.py` 迁到 `agent_router/classifier.py` ✓）· A-04 依赖核对 ✓ · A-05 打点 X5 旧入口 ✓
- [x] A-06 `QZDAPChatModel` 落地 ✓ · A-07 `LLMClient` 失败转移链 ✓ · A-08 `Reasoner` ✓（`ToolCallAccumulator` 迁入 ✓）
- [x] **A-09 删 `chat_model.py` 的 `stream_chat`** ✅ —— **已随 Agent Stage 7 删除** ✓（2026-10-31 核对 ✓ —— 全仓 `stream_chat` **零命中** ✓ —— `adapter/llm/` 只剩 `__init__.py` ✓）
- [x] A-10 **工具绑定 + 治理过滤** ✓ · A-11 修 `list_tools` 空 schema ✓ · A-12 `governance` 接线真实 actor（✅ 真实 actor ✓ —— `current_actor` ✓ / `require_actor` ✓ + `ToolRuntimeAdapter` ✓；✅ **审批挂起** ✓ —— **口径是「事件 + 落库」** ✓（`session_turns.pending_approval` ✓ —— 契约层 `TurnRunner` ✓ —— `interrupt()` **不适用** ✓ —— 2026-10-31 核对 ✓））
- [x] **A-13 在新 AgentLoop 侧注入真实 actor** ✅ —— **已达成** ✓（2026-10-31 核对 ✓ —— `agent_loop/runner.py` 用 `set_current_actor` ✓ —— **取不到就拒绝执行工具** ✓ —— 不拿假 actor 继续 ✓）
- [x] **A-14 `tool_executions` 开始写**（✅ 2026-10-31 —— `PostgresToolExecutionStore` ✓ 跨 worker 有效 ✓）· [x] **A-15 `request_hash` 冲突拒绝**（✅ —— `TOOL_IDEMPOTENCY_CONFLICT` ✓ + `TOOL_IN_PROGRESS` ✓ **新增** ✓）· [x] **A-16 重试/熔断**（✅ —— 退避 + jitter ✓ + 按工具名熔断 ✓）· [x] **A-17 修 async** ✅（⚠️ **随 Stage 7** ✓ —— 那些死代码**已经删了** ✓ —— 没有 async 可修 ✓）· [x] **A-18 沙箱接入** ✅（**已达成** ✓ —— 沙箱走**工具层** ✓ —— `HttpSandboxRuntimeClient` ✓ + `SandboxRuntimeAdapter` ✓ 装进 composition ✓ —— 沙箱容器在跑 ✓）· [x] **A-19 成本结算**（✅ LLM 侧已在写 ✓）· [x] **A-20 进程内幂等降级为快速路径**（✅ 权威已换 ✓ —— **类本体归 Stage 7** ✓）· [x] **A-20b `modules/tool` 的 `InvokeToolUseCase` 补幂等 / 重试 / 熔断**（✅ 2026-10-31 —— 改 `modules/tool` ✓）
- [x] **A-21 `AgentRouter`（选专家）**（✅ 2026-10-31 —— `CatalogAgentRouter` ✓ 确定性匹配 ✓ 落回不报错 ✓）· [x] **A-22 模型解析接线**（✅ —— `ExpertAssembler` ✓ 取值链 ✓ 查表不是决策 ✓）· [x] **A-23 工具绑定接线**（✅ —— 绑定集 + 治理过滤 ✓ → `BaseTool` ✓）· [x] **A-24 路由留痕 `agent_decision`**（✅ —— 快照 ✓ + `agent.expert.selected` 事件 ✓ —— **不写 `route_decision`** ✓）—— ⚠️ **装配器还没有生产调用方** ✓ → **接线落在 Stage 5** ✓
- [x] **A-25 `AgentLoopRunner` + `Evaluator`**（✅ 2026-10-31 —— runtime 侧 `agent_loop/` ✓ —— **六个终止条件的单一判定点** ✓）· [x] **A-26 把 `_run_turn_inner` 改接新 Builder / Writer** ✓ · [x] **A-27 端到端回归**（✅ —— 整条循环 13 条 ✓ + 旧回归网 118 条 ✓）· [x] **A-28 停用打点 `_run_turn_inner`**（✅ —— 手写循环删 ✓ —— **X17 → 已清理** ✓）
- [x] **A-28b 加 `deepagents` 依赖** 🚫 **不做了** ✓（**决策 #8 未采纳** ✓ —— 「先隔离分支验证再接」✓ —— 验证**没做** ✓ → **Stage 6 关闭** ✓；⚠️ **接了就是第二套循环** ✗✗ —— 唯一实现是 `AgentLoopRunner` ✓ → 不造第三套 ✓）· [x] **A-29 `deep/factory.py`** 🚫 不做 ✓ · [x] **A-30 `deep/planner.py`** 🚫 不做 ✓（**子代理已有实现** ✓ —— `ExpertAssembler` ✓ + `delegate_subagent` ✓）· [x] **A-31 预算** 🚫 不做 ✓（**预算单一判定点** ✓ —— `Evaluator` ✓）· [x] **A-32 删 deep 空壳** ✅（**2026-10-31 随 Agent Stage 7 达成** ✓ —— `graph/deep_agent.py` 随整包删 ✓ —— 仓内**零引用** ✓）—— 🚫 **Stage 6（可选）已关闭** ✓
- [x] **A-33 删 `nodes.py` 13 节点**（✅ 2026-10-31 —— `graph/` 整包删 ✓）· [x] **A-34 改 `builder.py` 为 6 节点版**（⚠️ **不做** ✓ —— 没有承载者 ✓ —— 随 A-33 一起删 ✓）· [x] **A-35 删 `runner.py` ReAct 循环**（✅）· [x] **A-36 删 `compile_loop_graph`** → **X5 → 已清理** ✓
- [x] **A-37 删 `InMemoryToolExecutor`** → **#16**（✅）· [x] **A-38 删 `InMemoryToolRegistry`** → **#29**（✅）—— 工具执行统一走 `modules/tool` ✓
- [x] **A-39 删平行 `*Event` 16 种** ✓（2026-10-31 —— **已删** ✓ —— `result/` 只剩一个工厂 ✓ —— 台账 **X1-a 已清理** ✓）· [x] **A-40 删其余 14 个 `InMemory*`** → **#25–#29**（✅ —— `InMemoryOutboxRepository` 保留 ✓ —— 已被 Session Stage 4b 取用 ✓）
- [x] **A-41 启用扫描脚本 Agent 段 + `InMemory*` 禁令**（✅ —— 38 条规则启用 ✓）· [x] **A-42 更新台账 + 现状文档**（✅ —— 台账 X1/X5/X12/X17 → 已清理 ✓）

## 附录 B：台账条目 → **层 · Stage** 推进表

| 台账条目 | 停用 | **删除** | **归属层 · Stage** | **守卫规则启用时点** |
|---|---|---|---|---|
| G1 `record_request_id` + `recent_request_ids` | —（直接替换） | **Gateway Stage 1** | Gateway · 1 | Gateway Stage 1 |
| G2 `_verify_signature` | — | **Gateway Stage 2** | Gateway · 2 | Gateway Stage 2 |
| G3 硬编码 `SYSTEM_USER_ID` / `SYSTEM_AGENT_ID` | — | **Gateway Stage 2** | Gateway · 2 | Gateway Stage 2 |
| G4 `ParsedMessage` | — | **Gateway Stage 3** | Gateway · 3 | Gateway Stage 3 |
| G5 `ChannelMessageReceived` | — | **Gateway Stage 3**（与发布端原子） | Gateway · 3 | Gateway Stage 3 |
| G6 IM 进程内 LRU | — | **Gateway Stage 3** | Gateway · 3 | Gateway Stage 3 |
| G7 `/v1/sessions*` 的 turn 部分 | Gateway Stage 4a | **Gateway Stage 5** | Gateway · 4a → 5 | Gateway Stage 5 |
| G8 `GET /v1/sessions` 列表别名 | Gateway Stage 4a | **Gateway Stage 5** | Gateway · 4a → 5 | Gateway Stage 5 |
| G9 `dispatch_subscriber.py` | Gateway Stage 4a | **Gateway Stage 5**（与 Session 5b 同 PR） | Gateway · 4a → 5 | Gateway Stage 5 |
| G10 审批恢复路径丢失幂等键 | —（**修复类**） | **Gateway Stage 1**（G-09b）+ **Session Stage 5**（X7 侧） | Gateway · 1 | **立即**（修复类） |
| R1 IM 每消息建会话 | Router Stage 2 | **Router Stage 5** | Router · 2 → 5 | Router Stage 5 |
| R2 `agentId` 直取 | —（直接替换） | **Router Stage 1** | Router · 1 | Router Stage 1 |
| R3 `try_claim` 的**会话互斥**职责（⚠️ 无顺序语义，旧路径从未有过顺序机制） | —（**从未有过待删项**） | **Session**（迁到 `session_turns.status` 的 CAS） | **Session** · 不属 Router | **立即**（修复类：Router 只需确认无残留调用方） |
| R4 `build_session_key` 冒号拼接版 | Router Stage 2 | **Router Stage 5** | Router · 2 → 5 | Router Stage 5 |
| X1 `runtimes/agent_runtime` 整包 | —（**从未接线**） | **Agent Stage 7**（**只取用部件，不整体接线**） | Agent · 7 | Agent Stage 7 |
| X1-a 平行事件类型 16 种 `*Event`（**#24**） | —（从未接线） | **Agent Stage 7** | Agent · 7 | **立即**（从未接线） |
| X1-b 16 个 `InMemory*`（**#25–#29**） | —（从未接线） | **Agent Stage 7**（语义在更早 Stage 落地，见 §1.5） | Agent · 7 | Agent Stage 7 |
| X2 第二套 turn 实现 | Session Stage 3（停用） | **Session Stage 5b**（与 Gateway 4a 原子） | Session · 3 → 5b | Session Stage 5b |
| X3 `graph_state` | Session Stage 6（停写） | **Session Stage 6**（废弃） | Session · 6 | Session Stage 6 |
| X4 旧表 `agent_turns` / `agent_session_messages` | Session Stage 6（迁数据） | **Session Stage 6**（DROP；前置：备份恢复演练） | Session · 6 | Session Stage 6 |
| X5 `compile_loop_graph` | —（**从未被走过，无停用阶段**） | **Agent Stage 7** | Agent · 7 | **立即**（从未被走过） |
| X6 `wait_status` | ⚠️ **Session Stage 0 停写未达成**（第二套 turn 实现 X2 仍靠它做互斥 —— 等 **Stage 3**） | **Session Stage 6**（DROP） | Session · **3** → 6 | Session Stage 6 |
| X7 审批吞异常 | —（直接修） | ✅ **Session Stage 1**（2026-10-30 提前完成） | Session · 1 | — |
| X8 `_load_messages` | Context Stage 4（停用，前置 = Agent A-26） | **Context Stage 5** | Context · 4 → 5 | Context Stage 5 |
| X9 `compact.py` | Context Stage 4（停用，前置 = Agent A-26） | **Context Stage 5** | Context · 4 → 5 | Context Stage 5 |
| X10 四套模板 | Context Stage 4（停用，前置 = Agent A-26） | **Context Stage 5** | Context · 4 → 5 | Context Stage 5 |
| X11 `_remember` | Memory Stage 7（停用，前置 = Agent A-26） | **Memory Stage 7** | Memory · 7 | Memory Stage 7 |
| X12 `layered.py` | Memory Stage 7 | **Memory Stage 7** | Memory · 7 | Memory Stage 7 |
| X13 `admin_memory_l1` | — | **Memory Stage 7**（退役） | Memory · 7 | Memory Stage 7 |
| X14 跨用户泄漏 | —（**修复类，不是删除类**） | **Memory Stage 1**（修复完成即「已弃用」） | Memory · 1 | **立即**（修复类） |
| X15 `admin_memory_l3` | — | **Memory Stage 7**（退役） | Memory · 7 | Memory Stage 7 |
| X16 `MemoryService` 单类 | Memory Stage 0（拆分） | **Memory Stage 7**（删单类） | Memory · 0 → 7 | Memory Stage 7 |
| X19 `memory_l2_embeddings` 死表 | —（**从未被代码引用**） | **Memory Stage 0**（迁移 0048 内 DROP） | Memory · 0 | Memory Stage 0 |
| X17 `runner._run_turn_inner` 的手写 `while True`（~250 行） | Agent Stage 5（**A-26 改接新 Builder / Writer**） | **Agent Stage 7** | Agent · 5 → 7 | Agent Stage 7 |
| X18 `copilot.py` 的 turn 编排（~600 行，**语义是对的**） | Session Stage 3（切 web/api 入口） | **Session Stage 3b**（清理窗口 ≥7 天且指标归零后删） | Session · 3 → 3b | Session Stage 3b |

> **每个条目的「删除」都落在某一层的某个具体 Stage，没有一个条目是「最后统一清」。**
>
> **「守卫规则启用时点」这一列**是 §6.2 守卫规则的分批启用清单 —— **它与「删除」时点同步**（删除发生的那次 PR 里同时启用对应规则，规约 4）。标「**立即**」的条目从未被生产调用，规则从第一天起就生效。

---

## 附录 C：开始动手的第一周

| 天 | 做什么 | 产出 |
|---|---|---|
| **D1 上午** | 拍板「表选择」决策（前置 A） | 决策有结论，README §3.4 与两个附录 A 同步 |
| **D1 下午** | 修 `qzdap-vault` 缺失声明（前置 B） | 一个 PR，独立可合 |
| **D2** | 建 `qzdap_legacy_calls_total` + `record_legacy_call`（C1） | 指标可查 |
| **D2 下午 – D3** | 给**可打点**的台账条目打点（C2）——**逐条核对台账** | **附录 D**：29 行「条目 → 打点位置 / 判据类型」对照表，**每个可打点条目都有打点**（不是「29 个标签全部有值」—— 9 条无调用入口的条目打点永远不会 inc） |
| **D4** | 建 CI 扫描脚本骨架 + 架构测试骨架 + **单实现守卫（分批启用）+ `InMemory*` 基线白名单**（C3 / C4） | 两个骨架进 CI（当前应全绿 —— 守卫按 §6.2 **分批启用**，第一天不会红） |
| **D5 上午** | 建指标看板查询片段 + 告警规则（C5 / H2） | 一张按 `entry` 分组的查询 + 阈值告警 |
| **D5 下午** | **启动 Memory Stage 1（作用域过滤）** —— 独立支线，最高优先级 | 第一处真实的安全修复开工 |

> **D5 下午为什么先做 Memory Stage 1**：它是**唯一一个完全独立**的工作项 —— 不依赖任何其他层、不依赖任何迁移、且修的是一个**正在发生的数据泄漏**。第一天就把它推上，等于立刻拿到一个可验证的安全收益，而不是在等依赖的空转。

---

## 附录 D：打点对照表（C2 的产出 —— **2026-10-29 已实施**）

> **这张表是 C2 的验收物**：36 行（覆盖台账 36 条 + X1 的两个子项 X1-a / X1-b），**逐条与台账核对**。判据类型决定这条目「怎么算清零」。
>
> **判据类型三分法**：
> - **指标** —— 有旧调用入口，用 `qzdap_legacy_calls_total{entry}` 归零判定；
> - **扫描** —— 无调用入口（数据类型 / 旧表 / 旧列 / 从未接线），用台账 §3.1 的 grep 规则判定；
> - **修复** —— 修复类条目（如 X14），用测试判定，**不进指标**。
>
> ✅ **实施状态（2026-10-29，Gateway Stage 3 后）**：指标与 `record_legacy_call` /
> `record_new_call` 已落地（`libs/observability/src/qzdap_observability/metrics.py`，有单测）。
> **16 条在旧实现的入口处打点**（下表「打点位置」列非空者；**2026-10-30 更新**：X7 随旧实现删除一并撤除、X4 新增旧表写入点打点、R3 补齐仓库层打点）—— 比原骨架多打了 10 条：
> 原判为「扫描 / 修复」但**确实有调用入口**的条目（G4 / G5 / G10 / R3 / X3 / X5 / X6 /
> X7 / X15 / X16）也一并打点，**打点只是额外观测，它们的清零判据不变**（扫描 / 测试）。
> ⚠️ 其中 **G4 / G5 / G6 随旧实现一起删除（2026-10-29 Gateway Stage 3）**，打点一并撤除。
> ⚠️ **17 行没有打点，且不是遗漏** —— 它们**打不了点**，必须改用替代判据：
> - **7 条「打不了点」**：**R4**（从未接线的 runtime）、**X1 / X1-a / X1-b**（从未接线）、
>   **X4 / X12 / X13 / X19**（数据类 / 旧表 / 死表）。
>   **这 7 条不得用「指标为 0」判清零** —— 从未被调用的代码，打点永远不会 inc，
>   指标恒为 0，**看起来已清零、实则从未被观测**。
> - **9 条「已不需要打点」**：**G1 / G2 / G3 / G4 / G5 / G6 / G11**（旧实现已删除 —— 打点随
>   代码一起撤除；G11 = 重复请求的 202 降级路径，2026-10-29 Gateway Stage 4b）、
>   **G10 / X14**（修复类 —— 判据是回归测试，不进指标）。
>   **修复完成后继续保留打点，会让指标永远非零、清理判据永远不成立**。

| 台账条目 | 判据类型 | 打点位置（实施后的真实位置） | 扫描规则 id | 备注 |
|---|---|---|---|---|
| G1 `record_request_id` | **已清理** | —（**2026-10-29 删除**：协议方法 + 两处实现 + `recent_request_ids` 读写 + 打点一并撤除） | — | 替代物 = `session_inbox` 原子 claim；Gateway Stage 1 |
| G2 `_verify_signature` | **已清理** | —（**2026-10-29 删除**：渠道服务里的验签迁到 `gateway/identity.py`，打点一并撤除） | `G2` | 替代物 = `HmacWebhookVerifier`；Gateway Stage 2 |
| G3 硬编码身份常量 | **已清理** | —（**2026-10-29 删除**：`SYSTEM_USER_ID` / `SYSTEM_AGENT_ID` 改为渠道登记的服务账号，打点一并撤除） | `G3` | 替代物 = `channels.service_account`（迁移 0049）；Gateway Stage 2 |
| G4 `ParsedMessage` | **已清理** | —（**2026-10-29 删除**：数据类 + 协议 `InboundAdapter` + 4 个适配器的 `parse_webhook`，打点一并撤除） | `G4` | 替代物 = `InboundMessage`；Gateway Stage 3 |
| G5 `ChannelMessageReceived` | **已清理** | —（**2026-10-29 删除**：事件类 + 发布端打点一并撤除；**入站消息本身就是总线事件**） | `G5` | 替代物 = `InboundMessage`；Gateway Stage 3 |
| G6 IM 进程内 LRU | **已清理** | —（**2026-10-29 删除**：`OrderedDict` LRU + `_message_key` + `_evict_dedup`，打点一并撤除） | `G6` | 替代物 = `session_inbox` 原子 claim；Gateway Stage 3 |
| G7 `/v1/sessions*` turn | **已清理** | —（**2026-10-29 删除**：整个 `adapter/http/router.py`；打点一并撤除） | — | Gateway Stage 5 |
| G8 `GET /v1/sessions` | **已清理** | —（**2026-10-29 删除**：别名路由；打点一并撤除） | — | Gateway Stage 5 |
| G9 `dispatch_subscriber.py` | 指标 | `dispatch_subscriber.py` `_handle_event` | — | 与 Session S-32 同 PR 删除 |
| G11 重复请求的 202 降级路径 | **已清理** | —（**2026-10-29 删除**：SSE 端点的 202 分支 + `DuplicateRequestError.replay_unavailable`；替代物 = 按 seq 的事件流重放） | — | Gateway Stage 4b |
| G10 审批恢复路径的幂等键 | **修复**（✅ 2026-10-29 已修） | —（**打点已撤除**：修复类不留在指标里） | — | **判据 = 回归测试**：`test_copilot_resilience.py::test_double_clicking_approve_executes_the_tool_only_once`（连点两次「同意」只执行一次工具） |
| G12 各模块的自由字符串错误码（Gateway 域 15 个） | **扫描**（+ 架构测试） | `modules/` / `libs/` / `runtimes/` 里的 `code="X"` 字面量 | `G12` | ✅ **已清理**（2026-10-29：15 个码提升为 `ErrorCode` 枚举成员；⚠️ 其余模块自己的 ~150 个码**未接管**） |
| R1 IM 每消息建会话 | 指标 | `dispatch_subscriber.py` `_run_turn`（建 session 前） | — | |
| R2 `agentId` 直取 | **已清理** | —（**2026-10-29 删除**：直取 + `record_legacy_call("R2")` 打点一并撤除） | — | Router Stage 1 —— 替代物 = `router/strategy.py` 的规则链（请求里的 agentId 降级为「显式指定」这一条规则） |
| R3 `try_claim` 的会话互斥职责 | **扫描**（+ 打点） | `copilot.py` `stream_turn`、`repositories.py` `try_claim` | `R3` | ⚠️ **owner 是 Session**；清零判据 = Session 的 CAS 接管后本层无残留调用方 |
| R4 `build_session_key` | **扫描** | —（无生产调用方） | `R4` | 在从未接线的 runtime 里 → **打点会得到恒为 0 的指标**，是危险状态 |
| X1 未接线包整包 | **扫描** | — | `X1` | 从未接线 → 无调用入口 |
| X1-a 平行 `*Event` 16 种 | **扫描** | — | `X1a` | 从未接线 |
| X1-b 16 个 `InMemory*` | **扫描** | — | `X1b` | 从未接线 |
| X2 第二套 turn 实现 | 指标 | `dispatch_subscriber.py` `_run_turn`（`run_turn_to_completion` 前） | `X2` | 与 Session S-32 同 PR 删除 |
| X3 `graph_state` | **指标**（原判扫描） | `repositories.py` `add` / `update` | `X3` | 旧列，清零判据 = 停写 + 废弃 |
| X4 旧表 | **指标**（+ 扫描） | `SqlTurnRepository.add` · `SqlSessionMessageRepository.append`（2026-10-30 补） | `X4` | 判据 = **指标归零（旧表不再被写）** + 迁数据 + DROP |
| X5 `compile_loop_graph` | **指标**（原判扫描） | `runner.py` `__init__` | `X5` | 从未被走过 |
| X6 `wait_status` | **指标**（原判扫描） | `repositories.py` `add` / `update` / `try_claim` | `X6` | 旧列，判据 = 停写 + DROP |
| X7 审批吞异常 | **已清理** | —（**2026-10-30 删除**：吞异常改成「记日志 + 再抛」；打点一并撤除） | `X7` | ✅ Session Stage 1（比原定的 Stage 5 提前） |
| X8 `_load_messages` | 指标 | `runner.py` `_load_messages` | `X8` | 停用点 = Context Stage 4；旧入口随 X17 一起归零 |
| X9 `compact.py` | 指标 | `runner.py`（`compact_messages` 的调用点） | `X9` | |
| X10 四套模板 | 指标 | `adapter/llm/prompts.py` 四个 `build_system_prompt_*` | `X10` | 原计划在 `run_turn.py` 打点；**实际在模板函数本体**（更贴近入口） |
| X11 `_remember` | 指标 | `runner.py` `_remember` | `X11` | |
| X12 `layered.py` | **扫描** | — | `X12` | 从未接线 |
| X13 `admin_memory_l1` | **扫描** | — | `X13` | 旧表，判据 = 退役 |
| X14 跨用户泄漏 | **修复** | —（**已修复**，不需打点） | — | 判据 = 隔离测试通过（`modules/memory/tests/unit/test_memory_scope_isolation.py`，5 条） |
| X15 `admin_memory_l3` | **指标**（原判扫描） | `runner.py` `_load_messages`（memories 非空时） | `X15` | 旧表，判据 = 退役 |
| X16 `MemoryService` 单类 | **指标**（原判扫描） | `memory/application/services.py` `write` / `recall` | `X16` | 判据 = 拆出两服务类且单类已删 |
| X17 `_run_turn_inner` | 指标 | `runner.py` `_run_turn_inner` | `X17` | 判据 = Agent A-26 接线后删 |
| X18 `copilot.py` turn 编排 | 指标 | `copilot.py` `stream_turn` | `X18` | 判据 = 语义迁入 `turn_runner.py` **且** 指标归零 ≥7 天 **且** 扫描零命中（Stage 3b） |
| X19 `memory_l2_embeddings` 死表 | **扫描** | — | `X19` | 判据 = 表已 DROP（Memory Stage 0，迁移 0048 内） |
| X20 同步 `PostgresSaver` 工厂 | **已清理** | —（**2026-10-30 删除**：`graph/builder.py` 的 `from_url`；同步 saver 在全异步仓库里会阻塞事件循环） | `X20` | ✅ Session Stage 0 —— 替代物 = lifespan 持有的 `AsyncPostgresSaver` |

> **34 行里 19 行有打点**（G7–G9 · R1 · R2 · R3 · X2 · X3 · X5 · X6 · X7 · X8 · X9 · X10 · X11 · X15 · X16 · X17 · X18），
> **15 行靠替代判据**（G1 / G2 / G3 / G4 / G5 / G6 已清理 · R4 · X1 · X1-a · X1-b · X4 / X12 / X13 / X19 —— 已删除 / 从未接线 / 数据类），
> **其中 8 行同时是修复类**（G1 / G2 / G3 / G4 / G5 / G6 已清理 · G10 / X14 —— 清零靠测试或删除）。
>
> **「指标」类条目既打点也扫描**：调用入口归零（`qzdap_legacy_calls_total{entry}` = 0 ≥7 天）**且** 残留符号 grep 零命中 —— 两者都满足才算清零。

---
