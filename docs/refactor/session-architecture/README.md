# 会话架构重构方案集

> 版本：1.3（2026-10-31：外部前置项与台账状态按已落地的事实回填 ✓）
> 目录：`docs/refactor/session-architecture/`
> 建立日期：2026-10-29
> 状态：**生效中**
> 上位文档：[`../session-module-refactor-plan.md`](../session-module-refactor-plan.md)（v3.1，19 节点 LangGraph 方案）——它定义的状态模型与持久化设计仍然有效，但**分层视角已被本目录的基线取代**

本目录是**会话链路重构**的全部方案。每份文档对应[生命周期基线](session-lifecycle-sequence.md)里的一条泳道，共享同一套收敛规则与清理台账。

---

## 1. 阅读顺序

| # | 文档 | 是什么 | 状态 |
|---|---|---|---|
| 1 | [`session-lifecycle-sequence.md`](session-lifecycle-sequence.md) | **权威基线**：会话完整生命周期的泳道划分与时序。所有层方案的共同上游契约 | **已定稿** |
| 2 | [`cleanup-ledger.md`](cleanup-ledger.md) | **全局收敛机制**：旧实现台账（弃用标记 → 调用打点 → 指标归零 → 删除 → CI 扫描脚本 → 阶段门禁） | **生效中** |
| 3 | [`gateway-refactor-plan.md`](gateway-refactor-plan.md) | Gateway 泳道：Channel Gateway / Auth Identity / Message Normalizer / Idempotency Guard ＋ 入口级限流 | **已定稿（v1.12）· Stage 0–3 + Stage 4a 两段 + Stage 4b + Stage 5 已实施**（幂等守卫 / 鉴权收口 / 归一化收口 / 门面接管 + 出站 sink + web 入口接管 / 无感重放 / **旧 `/v1/sessions*` 整段删除 + 扫描脚本进 CI + 架构测试**；**Stage 0 的 G-02/G-02b 补齐** —— 错误码收敛进 `ErrorCode` 枚举 + `ERROR_PROJECTION` 投影表，台账 **G12 已清理**；**G9 与 X2 已随 Session Stage 5b 的原子切换完成 ✓（2026-10-30）✓** —— 台账 Gateway 域 **G1–G12 全「已清理」** ✓） |
| 4 | [`router-refactor-plan.md`](router-refactor-plan.md) | Router 泳道：Strategy（选 agent）+ Session Routing（选会话 + 有序保证） | **已定稿（v1.6）· Stage 0–3 已实施**（契约层 `router/` + 五条规则链 + `RouteDecision` 留痕 + **web 建会话改走 Strategy → 台账 R2 已清理** + **哈希版会话 key 派生 → 台账 R4 已清理** + **IM 也走规则链 ✓** + **同会话 FIFO 排队 ✓**（`session/queue.py` + `PostgresTurnQueue` ✓ —— 序号分配 / 入队 / 放行 / 兜底 / 上限 / 超时 ✓）—— 台账 **R1–R4 全「已清理」** ✓） |
| 5 | [`session-refactor-plan.md`](session-refactor-plan.md) | Session 泳道：Manager（生命周期）+ State（状态机）+ Thread（多轮线程）+ 唯一 turn 实现 | **已定稿（v1.3）· Stage 0–3b + 5a + 5b + 6a/6b/6c/6d 已实施**（唯一 turn 实现 + **IM 切入口 + 删第二套 turn 实现**（台账 **X2 / G9 / R1 已清理** ✓）+ `wait_status` 整列退役（**X6** ✓）+ `graph_state` 整列退役（**X3** ✓）+ **旧表迁数据 + 切读 + 停旧写** ✓（**X4 已清理** ✓（迁移 0062 DROP ✓ —— 用户已提前结束只读窗口 ✓））） |
| 6 | [`context-refactor-plan.md`](context-refactor-plan.md) | Context 泳道：Builder（拼装）+ Compressor（压缩）+ Persistence（manifest 落库） | **已定稿（v1.2）** |
| 7 | [`memory-refactor-plan.md`](memory-refactor-plan.md) | Memory 泳道：Retrieval（检索）+ Writer（沉淀）+ STM/LTM 分层 | **已定稿（v1.4）** |
| 8 | [`agent-refactor-plan.md`](agent-refactor-plan.md) | ⑦ Agent Loop（大脑）· ⑧ Agent Router（**只选专家**：模型 / 工具 / 知识都来自 agent 配置，**不做 Model Router**）· ⑨ Execution Runtime（Agent / Model Runtime / Tool Runtime）。技术栈：LangGraph 1.x + LangChain + Deep Agents | **已定稿（v1.2）** |
| 9 | [`oncall-runbook.md`](oncall-runbook.md) | **值班手册**：告警响了怎么办（阈值 / 排查 / **回退步骤** ✓）—— 规则在 [`deploy/prometheus/alerts.yml`](../../../deploy/prometheus/alerts.yml) ✓ | **生效中** |
| 10 | [`implementation-plan.md`](implementation-plan.md) | **实施方案**（**按层组织**）：六层各自的 Stage 表、工作项、删除项、退出判据、回退点 + 跨层编排（依赖 / 并行 / 排期 / 里程碑）+ 守卫规则 + 风险预案 | **已定稿（v3.6）** |

**为什么是这个顺序**：基线定契约 → 台账定收敛规则 → 从最外层（Gateway）往里推进。Gateway 是最外层、边界最清晰、最容易独立验收的一层；Router 次之；Session 层同时是 Gateway 的上游依赖（`session_events` 落库是「无感重放」的前提），是所有层的枢纽，因此**建议在 Gateway 与 Router 定稿后立刻写 Session 层**。

---

## 2. 决策状态汇总

> 每份层方案的附录 A 列了该层的决策。**任一决策改动，都要同步修改该方案正文对应章节**，并在这里更新状态。

| 方案 | 决策数 | 已定稿 | 待确认 | 定稿要点 |
|---|---|---|---|---|
| Gateway | 9（+ #2b） | **10** | 0 | #1 出站归 ①；#2 `modules/channel` 保持独立模块；#2b `session_inbox` 表归 Session；#3 改造成 **strong 部分唯一索引**；#4 无感重放（**Stage 4b 已落地**：重复命中 → 重放事件流；202 降级路径删除）；#5 weak **不抑制** + 标 `unprotected` + 禁用副作用工具；#6 不迁对象存储；#7 `/v1/sessions*` 只留兼容别名；#8 先上新后清旧；#9 限流硬编码 + 环境变量 |
| Router | 10 | **10** | 0 | **#1 S1 严格排队（FIFO）**；**#2 启用新表 `session_*`**；#3 配置落点 `admin_agents.profile`；#4 深度任务判定归 Agent 层；#5 `ingress_seq` 会话行原子自增；#6 审批**不占** FIFO 位；#7 N=5 / T=60 秒；#8 排队开关默认 off；#9 轮次表 CAS 为唯一权威；**#10 Router 只派生 key + 分配 `ingress_seq`，`resolve_or_create` 归 Session**（**边界是「不写会话表」，不禁止读**；粘性规则另需 Session 提供**只读的 `lookup(session_key)` 端口**） |
| Session | 7 | **7** | 0 | #1 `DELETE /api/sessions/{id}` = **关闭**（删除走治理域）；#2 空闲超时后**复活为新会话**；**#3 废弃 `wait_status`**（用 `current_turn_id` + `session_turns.status` 推导）；#4 审批恢复失败**对用户可见**；**#5 与 Router #2 同值**（启用新表 + 旧表迁数据后 DROP，Stage 6）；#6 审批挂起落 `session_turns.pending_approval`；#7 空闲阈值 30 天可配 |
| Context | 7 | **7** | 0 | #1 agent prompts **放在 Builder 内**；**#2 统一用 `budget.py:42` 的按语种估算**，旧路径也用它；#3 上下文快照**先不做**；#4 摘要阈值 `window × 0.70`；#5 仍超限抛 `CONTEXT_TOO_LARGE`；#6 manifest **每次模型调用一条**；**#7 给 `ContextCompactedChunk` 补可选 `degraded` 字段**（前端目前不读 chunk 字段 → 补字段向后兼容） |
| Memory | 12 | **12** | 0 | **#1 L3 退役**，知识统一归 `modules/knowledge`（最大架构分叉）；#2 向量过滤**下沉到 pgvector**（安全，落在 `admin_memory_vec`）；#3 规则起步 + 预留 LLM 接口；#4 每轮结束写一次；**#5 L1 退役**（STM 换带 `session_id` 的新表）；#6 embedding 统一走独立 `embedding_runtime`；#7 召回**更新**统计；#8 记忆模块实现 `data_subject` 的一个 scope；#9 沿用 `admin_memory_*` 补列；#10 管理面乐观并发（版本号）；**#11 写入侧持久化 `owner_id`，存量自动记忆不回填**；**#12 放开 `admin_memory_policies` 唯一约束到 `(tenant_id, workspace_id, layer, label)`** |
| Agent Loop / Agent Router / Execution | 8 | **8** | 0 | **#4 模型来源（早已拍板）**：模型由管理员在 agent 配置里绑定，运行时**查表**，**不做 Model Router**；#1 **自建 6 节点 StateGraph**（不用 `create_react_agent`）；**#2 `QZDAPChatModel(BaseChatModel)` 薄适配器**；#3 **复用 `agent_versions` + role 标签**，不建专家表；#5 绑定集 ∩ 风险 ∩ 作用域，`unprotected` **剔除**副作用工具；#6 **`tool_executions` 为唯一权威**；#7 成本闸门**两级**；#8 Deep Agents **先隔离分支验证再接 Stage 6** |

**跨层一致性约束**（每一对都必须同时定、取值相同 —— ✅ 下列各对已于 2026-10-29 同批定稿）：

| 耦合对 | 内容 |
|---|---|
| **Router #2 ↔ Session #5** | 表选择（同一个决策的两面） |
| **Router #1 ↔ Session #3** | Router 采纳 S1 排队 → `session_turns` 需有 `queued` 态 → Session 决策 #3（废弃 `wait_status`，改用轮次表 CAS）的解法才成立 |
| **Router #10 ↔ Session §3.1** | Router 不**写**会话表（**读是允许的**）；`resolve_or_create` 由 Session 执行；**粘性规则另需只读的 `lookup(session_key)` 端口** |
| **Memory #1 ↔ Context §6** | L3 退役 → 知识召回走 `KnowledgePort.search`，不经过 Memory |
| **Gateway #5 ↔ Agent 方案 #5 / §5.3.1** | `unprotected` 轮次禁用副作用工具 —— 兑现点在**工具绑定的治理过滤**（剔除，不是执行时拦截） |
| **Session #6 ↔ Agent 方案 §3.5** | 审批挂起落点：`session_turns.pending_approval`（Session 拥有），Agent Loop 只调策略闸门并 `interrupt()` |
| **Router 层（选 agent）↔ Agent Router（选专家）** | **会话入口**选 agent（一次决定、会话绑定）vs **每步推理**选专家 Agent（每步可变、会话绑定不变） |
| **执行轴 ↔ 配置轴**（Agent 层） | 执行轴 = 每步推理（循环 → 选专家 → 执行）；配置轴 = 管理员配置 → agent 绑定 → 运行时取值。**模型 / 工具在配置轴上**，运行时只能取、不能挑（Agent 方案 §0.2） |

---

## 3. 全局规则

### 3.1 实现收敛：最终态只有一个实现

**先上新、后清旧**。新实现接管并稳定运行后，删除旧实现。

```
未开始 →（新实现接管 + @deprecated + 调用打点）→ 已弃用
       →（连续运行 **≥ 7 天** + 新路径流量占比 **≥ 95%** + `qzdap_legacy_calls_total{entry="…"}` 窗口内**累计为 0** + 窗口内无相关生产事故）→ 待清理 →（删除）→ 已清理
```

| 规则 | 说明 |
|---|---|
| **弃用标记 + 观测** | 旧实现被接管时打 `@deprecated` + `qzdap_legacy_calls_total{entry="..."}`，让「旧路径还在被调用」成为可观测事实。✅ 指标已落地 ✓（2026-10-30）—— ⚠️ **打点已随旧实现全部撤除** ✓（生产代码 `record_legacy_call` 调用点 = **0** ✓ —— 2026-10-31 核对 ✓）→ 判据统一走 CI 扫描脚本 ✓（47 条规则全开 ✓） |
| **删除条件客观化** | 连续运行 **≥ 7 天** + 新路径流量占比 **≥ 95%** + `qzdap_legacy_calls_total{entry="…"}` 窗口内**累计为 0** + 窗口内无相关生产事故。**不使用「发布周期」概念** —— 本项目无 tag / CHANGELOG / release 目标，该周期不可定义，等于「随时」（见台账 §3.3 的论证） |
| **台账化** | 全部旧实现登记在 [`cleanup-ledger.md`](cleanup-ledger.md) |
| **单实现不变量** | **对每个关注点，任一时刻只有一个实现活着。**「弃用」不是终态 —— 每个旧实现的删除都落在**某一层的某个具体 Stage** 的具体 PR，见 [`implementation-plan.md`](implementation-plan.md) §1.2 的「关注点 → 唯一实现 → 删除时点 → 归属层 · Stage → **允许并存窗口**」表，并由 §6.2 的守卫规则在 CI 里强制 |
| **守卫分批启用** | 守卫规则**不是一开始就全开** —— 每条关注点的规则在**它的「允许并存窗口」关闭的那个 Stage** 才启用（与台账「扫描脚本在删除 PR 里同步启用对应规则」同一条原则）。**否则 CI 从第一天起就是红的**（`MemoryService` 拆了但单类还在、`wait_status` 停写了但列还在……） |
| **不可结转** | 某层台账未清零，**依赖该层的下游层不得进入「切换」阶段**；未完成项不允许滚到下个 Stage。**唯一豁免**：跨层硬依赖中「下游的切换**先于**上游的清理」的那一段（见 §3.3 豁免表） |

**为什么不在同一次提交里一起删**：并存期可以用真实流量对照新旧行为（唯一可靠的验证方式），且旧实现留在场可作回退兜底。**代价**：清理完成后回退需重新上线旧版本。

### 3.1.1 回退约定（全局）

每一层都按同一套节奏走，因此**回退方式也是同一套**：

| 时点 | 回退方式 | 代价 | 判定 |
|---|---|---|---|
| 切换前 | 什么都不用做 | 无 | — |
| **已接管、未清理** | `git revert` 切换提交 → 流量回落旧实现 | **无**。这就是保留清理窗口的收益 | 旧实现仍在场 |
| **已清理** | 需**重新上线旧版本** | 旧表已 DROP、状态列已废弃 → **数据不可恢复** | 依赖迁移前的备份 |

> **每份层方案的「风险」章节后都有一节「回退」**，列出**本层特有的不可逆点**（哪些 DROP、哪些列被废弃、哪些数据会丢）。

**三条回退纪律**：

| # | 纪律 | 为什么 |
|---|---|---|
| 1 | **安全修复不回退** | 作用域过滤（Memory X14）、`unprotected` 剔除（Gateway 决策 #5）、审批校验（Session X7）—— 这些是**修缺陷**，回退等于重新打开漏洞 |
| 2 | **清理阶段的执行条件是「指标归零 + 备份已验证」** | 「测试环境验证过」**不算**；备份必须**恢复演练过** |
| 3 | **回退到有已知安全缺陷的状态，需要安全负责人确认** | Memory 层尤其：旧实现 = 恢复跨用户泄漏 |

> 2026-10-15 那次重构建了完整的新 runtime 却**从未接线**，同期旧路径继续长功能，两套并存至今。根因是验收标准是「单测通过」而非「旧实现减少」——上面四条规则就是针对这个根因的。

### 3.2 边界判据

> **把某一层整个摘掉，剩下的层应该完全不知道 HTTP、SSE、飞书这些词存在。**

落成一条架构测试：runtime 层不得 import `fastapi` / `starlette` / `sqlalchemy` / `asyncpg` / `psycopg`。

### 3.3 跨方案依赖表（**Stage 的真实顺序**）

六份方案的 Stage 0 **不能并行**——它们共享表、共享迁移序号、共享调用点。下表是唯一权威的顺序来源。

```
Session Stage 0(迁移 0046 / saver / 表 DDL 唯一 owner)  →  Session Stage 1(resolve_or_create + lookup 端口)
   →  Session Stage 2(启用新表写入)  →  Session Stage 3(唯一 turn 实现)
        ├─→  Session Stage 4(session_events 落库)  →  Gateway Stage 4b(无感重放 ✅ 已实施)
        │      ↑ ⚠️ 4b 的硬依赖开工时不满足 → **连带落地了 Session 侧的最小必要**
        │        （轮次双写 + 事件落库 + 按 seq 读取端口）—— 见 Gateway 附录 C.6 的 G-31 / G-32
        │      →  Gateway Stage 5 / Router Stage 5
        ├─→  Router Stage 3(FIFO 有序处理)
        ├─→  Context Stage 1/2（组装与压缩）
        └─→  Memory  Stage 3（Writer 重写）

Session Stage 1(resolve_or_create + lookup)  →  Router Stage 2(会话映射 + 粘性查找)
Router Stage 0(迁移 0045 ✅)  →  Router Stage 1(策略链 ✅)  →  Router Stage 2(会话映射 + 粘性查找 ✅)  →  Router Stage 3(FIFO ✅)
                              ↑ ⚠️ Stage 2 曾被 Session Stage 1 的 `lookup` 端口阻塞 —— **已解锁 ✓**（2026-10-31，Router §13.6 ✓）
Gateway Stage 0(迁移 0044)  →  Gateway Stage 1/2/3  →  Gateway Stage 4a(接管)  →  Gateway Stage 4b(无感重放 ✅)  →  Gateway Stage 5(清理 ✅)
                              ↑ Stage 5 的「删 dispatch_subscriber + 删第二套 turn 实现」**已达成 ✓**（2026-10-30，Session Stage 5b 同 PR ✓ —— 台账 G9 / X2 ✓）
                              ↑ Stage 4a 是豁免 E1：不等 Session 台账清零
Context Stage 0(迁移 0047，依赖 0046)  →  Context Stage 1/2
Memory  Stage 0(迁移 0048)  →  Memory  Stage 1(作用域过滤，安全修复，可独立先行)
Agent  Stage 0(端口 + 依赖核对)  →  Agent Stage 1/2/3/4(模型·路由·执行)
Agent  Stage 5(循环)  ←  Session Stage 3(唯一 turn 实现)
```

| 前置 | 被阻塞 | 阻塞类型 | 写在谁的文档里 |
|---|---|---|---|
| Session Stage 3（唯一 turn 实现） | **Router Stage 3**（FIFO 有序） | 语义 | Router §0.1 + 风险表；**Stage 表缺前置行 → 已补** |
| Session Stage 1（`resolve_or_create` + **`lookup`** 端口） | **Router Stage 2**（会话映射 + 粘性查找） | 契约 | Router 决策 #10 + Stage 2 前置行 ✅ |
| Session Stage 4（`session_events` 落库） | **Gateway Stage 4b**（无感重放） | 硬依赖 | ✅ **已随 Stage 4b 连带落地最小必要**（轮次双写 + 事件落库 + 按 seq 读取端口）；Session 的 outbox 调度 / 死信仍在 Session Stage 4 |
| Session 迁移 0046（`agent_sessions` / `session_turns` DDL） | Context 迁移 0047 | 物理顺序 | Context §7.2 依赖声明 ✅ |
| Session Stage 2（新表写入） | Context / Memory 的写入切换 | 数据 | 各自 Stage 表 ✅ |
| Session Stage 3 | Context Stage 1、Memory Stage 3 | 语义（停用的是旧调用点） | 各自方案 ✅ |
| Gateway Stage 1（`InboundMessage` 定稿） | Router Stage 1 | 契约 | Router §9 ✅ |
| Router Stage 1（`SessionAssignment` 定稿） | Session Stage 3 | 契约 | Session §6 ✅ |
| Session Stage 3（唯一 turn 实现） | **Agent Stage 5**（循环本体） | 语义 | Agent §9 Stage 5 前置行 ✅ |
| Session Stage 3（唯一 turn 实现） | **Memory Stage 3**（Writer 重写） | 语义 | Memory §11 Stage 3 前置行 ✅ |
| Session Stage 3（唯一 turn 实现） | **Memory Stage 3**（Writer 重写） | 语义 | Memory §11 Stage 3 ✅ |
| Agent Stage 1（`QZDAPChatModel`） | Agent Stage 6（Deep Agents） | 依赖 | Agent §2.2 ✅ |
| **Agent Stage 5 的 A-26**（`_run_turn_inner` 改接新 Builder / Writer） | **Context Stage 4**（停用 `_load_messages` / 四套模板 / `compact.py`）、**Memory Stage 7**（删 `_remember`） | **语义（删除顺序自底向上）** | 实施方案 §3.6 A-26 ✅ **（2026-10-30 已达成 ✓ —— 门禁已开 ✓）** |
| **Session Stage 5b**（删 `use_cases/run_turn.py`） | **Context Stage 5**（删 `adapter/llm/prompts.py` —— `run_turn.py` import 那四个函数） | **语义** | 实施方案 §3.3 S-33 ✅ |
| **`ErrorCode` 码收敛**（跨模块） | **Gateway Stage 0**（`ERROR_PROJECTION` 投影表建在枚举之上） | 契约 | 实施方案 §3.1 G-02b ✅ |
| **`modules/channel` 新增 `qzdap-agent-runtime` 依赖** | **Gateway Stage 2**（验签迁出后，channel 的 webhook 端点调 `Gateway.accept`） | 依赖 | Gateway 方案 §9.2.1 ✅ |
| **Session 的 sweeper 第四类清扫**（`session_inbox` 过期行） | **Gateway Stage 1**（幂等 TTL 依赖它 —— 不清理则 TTL 之后持续误杀） | 数据 | Gateway 方案 §4.3.1 ✅ |

### 3.3.1 豁免表（唯一的例外）

「不可结转」规则按依赖方向读：**上游层台账未清零 → 下游层不得切换**。但存在一类依赖是**反向**的——下游层的某个能力依赖上游层的「新实现」，而上游层的台账要等下游切换完才能清零。这构成死锁，只允许以下豁免：

| 豁免 | 范围 | 条件 | 为什么必须豁免 |
|---|---|---|---|
| **E1** | **Gateway Stage 4a（接管，重放降级）** 可先于 Session 台账清零 | Gateway Stage 0–3 已完成；`session_events` 表已存在（迁移 0035 已建） | Gateway 的接管本身**不依赖** Session 的台账清零，只依赖「重复分支可降级」这一降级路径可用 |
| **E2** | **Gateway Stage 4b（启用无感重放）** | Session Stage 4 已完成（`session_events` 真写真读） | ✅ **已实施（2026-10-29）** —— 硬依赖**未被豁免**，而是**连带落地了 Session 侧的最小必要**（表在、**一行没有** → 补上轮次双写 + 事件落库 + 读取端口）；Gateway 附录 C.6 的 **G-31 / G-32** 记录了这次偏差 |

> **豁免不等于可以先删后补**。E1 只允许「**先接管、重放走降级**」，不允许在 Session 未就绪时宣称「支持无感重放」。Gateway 的对外文档必须写明当前处于 4a 还是 4b 状态。

### 3.3.2 迁移序号与表归属

**迁移序号是唯一的物理顺序**：0044（Gateway）→ 0045（Router）→ 0046（Session）→ 0047（Context）→ 0048（Memory）。既有迁移已占用 0040–0043，**新方案从 0044 起，不得撞号**。

| 迁移 | owner | 内容 |
|---|---|---|
| 0044 | Gateway | `session_inbox` 加列改约束 |
| 0045 | Router | `agent_sessions` 加 `next_ingress_seq` / `last_completed_seq` |
| 0046 | Session | `agent_sessions` 唯一索引；`session_turns` / `session_messages` 加列与状态枚举；checkpoint 四表（`checkpoints` / `checkpoint_blobs` / `checkpoint_writes` / `checkpoint_migrations`）—— ⚠️ **已由迁移 0063 删除** ✓（2026-10-31 ✓ —— saver 退役后全仓零引用 ✓）|
| 0047 | Context | `agent_sessions.rolling_summary` 列 + `session_context_manifests` 表（**依赖 0046 的物理顺序**；回填按 `graph_state` 优先 → `metadata` 兜底 → 清 `metadata`） |
| 0048 | Memory | `admin_memory_l2` 补列 + `session_memory_buffer` 表 + **DROP 死表 `memory_l2_embeddings`**（X19）+ 放开 `admin_memory_policies` 唯一约束 |
| **（无）** | **Agent / Execution** | **不需要新迁移** —— `tool_executions` 的列与唯一约束已在 0035 建齐、`cost_usd` 在 0043、`route_decision` 在 0046、checkpoint 表在 0046 |

> **0049 及之后**留给 Agent / Execution 层的后续演进（Deep Agents 依赖落 `pyproject.toml`，不占迁移号）。
>
> ⚠️ **实际已经用到 0060** ✓（2026-10-31 核对 ✓）—— 这段话**已过期** ✓：
>
> | 迁移 | owner | 内容 |
> |---|---|---|
> | 0049 | Gateway | **服务账号物化** ✓（`channels.service_account` ✓ —— 取代硬编码的 `SYSTEM_USER_ID` ✓） |
> | 0050 | Gateway | **无感重放的最小必要** ✓（轮次双写 ✓ + 事件落库 ✓ + 按 seq 读取端口 ✓） |
> | 0051 | Gateway | Stage 5 的清理 ✓（`recent_request_ids` 残留 ✓ + 孤儿索引 ✓） |
> | 0052 | Session | 消息序号 ✓（`session_messages.session_seq` ✓） |
> | 0053 | Session | **DROP `agent_sessions.wait_status`** ✓（X6 ✓） |
> | 0054 | Session | 旧表 → 新表**迁数据** ✓ + 对账脚本 ✓（X4 的第一步 ✓） |
> | 0055 | Session | `session_turns.user_input` 补列 ✓ |
> | 0056 | Session | **DROP `agent_sessions.graph_state`** ✓（X3 ✓） |
> | 0057 | Memory | **DROP `admin_memory_l1`** ✓（X13 ✓） |
> | 0058 | Memory → Knowledge | L3 **逐行搬进** knowledge ✓（X15 的第一步 ✓） |
> | 0059 | Memory | **DROP `admin_memory_l3`** ✓（X15 ✓） |
> | 0060 | Platform | **DROP `subscriptions.workspace_id`** ✓（P-13 扫出来的真缺陷 ✓ —— 订阅是租户级的 ✓） |
>
> **dev 库 / demo 库都在 0060** ✓（upgrade → downgrade → upgrade 实测通过 ✓）。
>
> ✅ **0044–0048 已实现（2026-10-29）**：五个迁移脚本已落在 `backend/migrations/versions/`，**dev 库实测 upgrade → downgrade → upgrade 全程通过**（可回滚，M0 判据达成）。其中两处与本表原描述不同，已回写方案：
> - **0046 的 checkpoint 表名**：按已安装的 `langgraph-checkpoint-postgres` **3.1.3** 的实际 DDL → `checkpoints` / `checkpoint_blobs` / `checkpoint_writes` / `checkpoint_migrations`（**无 `langgraph_` 前缀、无 `_v2` 变体**，那是 2.x 的命名）。迁移把 `checkpoint_migrations` 的版本行写成 `9`，saver 的 `setup()` 跑完仍是单行 → **不会重复建表**。
> - **0047 的 `metadata` 清理**：**不在 0047 里做** —— 旧路径仍是 `rolling_summary` 的唯一写者，提前清空会丢摘要且旧路径会立刻写回来。清理落在 **Context Stage 4（旧循环停用）之后**。
> - **0046 的 `session_messages` 回填 join 键**：`session_turns` 的主键列名是 **`id`**（不是 `turn_id`）—— 方案原文的 SQL 有误，已改。

**表归属唯一**：每张表只有一个 owner 方案负责 DDL。

| 表 | DDL owner | 其他方案 |
|---|---|---|
| `agent_sessions` | **Session（0046）**：唯一索引 + `wait_status` 处置 | Router（0045）加 `next_ingress_seq` / `last_completed_seq`（排序状态，归 Router） |
| `session_turns` | **Session（0046）**：`ingress_seq` / `route_decision` / `agent_decision` / `pending_approval` / `cancel_requested` / 状态枚举 | **Router 写 `route_decision`**（会话入口的策略决策）；**Agent 写 `agent_decision`**（每步的专家选择 + 模型/工具取值）—— ⚠️ **两列两写者，不共用** |
| `session_messages` | **Session（0046）**：`session_seq` / `session_id` | Context 只读 |
| `session_events` | **Session（0046）** | Gateway **读写**（Stage 4b 连带落地：Session 侧写、Gateway 侧按 seq 读回重放） |
| `session_inbox` | **Session（会话域）** | Gateway 0044 改约束（幂等语义来自 Gateway） |
| `session_context_manifests` | **Context（0047）** | 无 |
| `admin_memory_*` / `session_memory_buffer` | **Memory（0048）** | 无 |
| `tool_executions` | **既有（0035）** | Agent 层**开始写入**（幂等唯一权威） |
| `tool_calls` | **`modules/tool`** | Agent 层只读关联（`tool_call_id`） |

### 3.4 前置决策：**表选择**（其余决策的前置）

Router 决策 #2（表选择）与 Session 决策 #5（表选择）**是同一个决策的两面**。它曾是所有迁移的前置：

- 五个 Stage 0 的迁移设计无法定稿；
- Context / Memory 的写入切换路径无法确定；
- 「数据回填 vs 双写」的工作量无法估算。

> **定稿（2026-10-29 用户拍板）：启用新表 `session_turns` / `session_messages` / `session_events`**（迁移 0035 已建、零生产数据），旧表 `agent_turns` / `agent_session_messages` 双写 → 对账 → 切读 → 停旧写 → DROP。废弃动作在 **Session Stage 6**，迁移归 **Session（0046）**，Gateway 方案 §8 已同步为「迁数据后废弃」。
>
> **状态：✅ 已定稿** —— Router 决策 #2 与 Session 决策 #5 均已标记为定稿（README §2 的决策状态汇总同步反映）。**迁移 0045–0048 的 DDL 现在可以定稿**，六个 Stage 0 中的四个不再被此项阻塞。

### 3.5 横切关注点的落点约定

基线定义了两条横切（Governance / Observability）。**每份层方案必须显式写出本层的落点**，不得只散落在正文：

| 横切 | 本层要回答的问题 | 落点示例 |
|---|---|---|
| **Governance** | 本层的哪一步会触发权限 / 策略 / 审批 / 预算闸门？ | Gateway：鉴权；Router：策略与配额；Session：审批挂起；Agent Loop：工具执行前审批 + 成本闸门 |
| **Observability** | 本层产出哪些 span / 指标？指标名是什么？ | 每份方案的「可观测性指标」小节，指标名进 `qzdap_*` 命名空间 |

> 2026-10-29 核对发现：初版六份方案中**只有 Gateway 显式写了横切落点**，其余五份为零散提及。**已逐份补齐**（每份方案末尾的「治理与可观测性落点」小节）。
>
> **指标命名约定**：全局唯一的 `qzdap_legacy_calls_total`（台账编号为标签）是**收敛机制的基础设施**，六份方案共用同一个定义，不得各层自定义同义指标。

---

## 4. 术语约定

| 词 | 含义 | 不要混用 |
|---|---|---|
| **泳道** | 生命周期基线图上的一个参与者（Gateway / Router / Session / Context / Memory / Agent Loop / Agent Router / Execution） | — |
| **层** | 一份方案文档的粒度，**与泳道一一对应** | 不要用「层」指代子模块（如「Auth 层」应说「Gateway 的 Auth Identity 子件」） |
| **处理单元** | 一条消息最终要去的地方 = (目标 agent, 目标会话实例, 入站序号) | 见 Router 方案 §0.2 |
| **标准消息** | Gateway 产出的 `InboundMessage` | 与「原始消息」（入站原始字节）区分 |
| **旧实现 / 旧路径** | 台账登记的、等待清理的代码 | 统一用「旧实现」；「旧路径」特指 HTTP 入口路径 |
| **弃用** | 旧实现被新实现接管、进入清理窗口 | 与「删除」区分：弃用 ≠ 已删 |
| **会话绑定 agent** | Router 层在**会话入口**选定的 agent，整个会话内不变 | 与「专家 Agent」区分 |
| **专家 Agent** | Agent Router 在**每步推理**选定的执行者（客服 / 销售 / 订单…），**每步可变**，不改变会话绑定 | 不要与「子代理（sub-agent）」混用 —— 子代理是 Deep Agents 的执行单元 |
| **配置绑定链** | 管理员配置 model / tool / skill → 配置 agent 时绑定（`agent_versions.model_id` / `route_id` / `allowed_tools` / `allowed_skills`）→ 运行时**取值** | **取值不是决策** —— 运行时没有「挑模型 / 挑工具」这一步（Agent 决策 #4） |
| ~~**Model Router**~~ | ❌ **已取消**（Agent 决策 #4）：模型由管理员在 agent 配置里绑定，运行时是**查表**不是决策 | 与「Router 层」区分 —— 那是选 agent |
| ~~**Tool Router**~~ → **工具绑定 + 治理过滤** | 工具集来自 agent 配置（`allowed_tools` / `allowed_skills`）；本层只做**治理过滤**（unprotected / risk / scope） | 与「Tool Runtime」区分 —— 那是「怎么执行」 |
| **Tool Runtime** | Execution Runtime 的一路：工具的实际执行环境（超时 / 重试 / 熔断 / 幂等） | 与 `modules/tool` 的**协议派发**区分 —— 后者只管 custom / openapi / mcp 怎么调 |
| **`unprotected`** | Gateway 判定该消息的幂等键强度不足，**禁止副作用工具** | 兑现点在 Agent 方案的**工具绑定治理过滤**（**剔除**，不是执行时拦截） |
| **`QZDAPChatModel`** | 平台模型对 LangChain `BaseChatModel` 的**薄适配器** | 只做类型翻译，不碰供应商 / 路由 / 成本 |

---

## 5. 层方案的编写规范

> 这七条是**硬规范**。六份层方案已全部按此写就；后续新增层（如需要）必须同样满足。

1. 明确标出自己在基线图上的位置，并说明与相邻层的**接口数据形状**；
2. **不得引入与基线冲突的层次**；
3. **不得在同一层内并存两套实现**；
4. 每个阶段验收必须包含「**旧代码减少了什么**」；
5. 旧实现登记进 [`cleanup-ledger.md`](cleanup-ledger.md)，删除时同步更新状态；
6. 附录 A 列出该层的**已定稿决策**，决策改动要回改正文；
7. 引用上位方案时明确说明**哪些部分仍有效**（当前：§4 状态模型、§5.7 治理语义、§13.3–13.5 契约、§14 迁移细节）。

### 5.1 六份方案的结构自检

所有层方案采用**同一套章节骨架**，便于横向对照：

| 章节 | 内容 | 六份是否齐备 |
|---|---|---|
| §0 | 定位与范围（基线位置 / 子件 / 明确不做 / 收敛规则 / 前置依赖） | ✅ |
| §1 | 现状盘点（逐条标注文件与行号） | ✅ |
| §2 | 目标架构 | ✅ |
| §3–§5 | 各子件设计 | ✅ |
| §6 | 与相邻层的边界 | ✅ |
| §7 | 数据与表（含迁移草案与回滚） | ✅ |
| §8 | 逐文件改造与删除清单 | ✅ |
| §9 | 实施阶段（Stage 0…N，每阶段含「旧代码减少」） | ✅ |
| §10 | 验收标准（功能 + 架构测试 + 扫描） | ✅ |
| §11 | 风险 | ✅ |
| §12（Gateway 为 §13） | 治理与可观测性落点 | ✅ |
| 附录 A | 已定稿的决策（决策名 / 定稿结果 / 备选 / 影响） | ✅ |
| 附录 B | 现状 → 目标 文件对照速查 | ✅ |
| 附录 C | 本轮重排 / 审查修正记录（问题 → 修正 → 落点） | ✅（**六份都有**） |

> **Gateway 的章节偏移（v1.4 重排后）**：Gateway 的子件设计是 **§3–§6**（统一标准数据 / 幂等与去重 / 限流 / 出站），因此它从 §7 起整体后移一位 —— **§7 边界 · §8 数据与表 · §9 逐文件与删除清单 · §10 实施阶段 · §11 验收 · §12 风险 · §13 治理**。引用 Gateway 的章节时按这张偏移表换算。

> **两条可机械校验的性质**（2026-10-29 全量核对通过）：
> 1. **每条决策在正文都有锚点** —— 附录 A 的每一行，正文里都有对应的「决策 #N」引用（否则改了决策不知道该改哪一节）。六份方案合计 **54 条**（53 条编号决策 + Gateway 的补充条目 #2b），锚点覆盖率 100%。
> 2. **每个 Stage 都有「旧代码减少」栏** —— 六份方案的全部 Stage 均已包含。

> **Gateway 的 §1.6「外部依赖的现状核实」**是唯一的额外章节（记录对 `qzdap_llm` / `qzdap_schema` / `qzdap_persistence` 等外部包的依赖核实结果）—— 它归在「现状盘点」下，因为它核的是**现状**而不是验收项。

---

## 6. 落地路线与里程碑

> **这是「从哪开始、怎么并行、什么时候算一段做完」的全局视图。** 逐层、逐 Stage 的执行计划见 [`implementation-plan.md`](implementation-plan.md) §3（六层各一节）与 §4（跨层编排）；各方案的 Stage 细节见各自文档。

### 6.1 三条推进主线

```
主线 ①（安全与地基，可立即并行开工）
  Memory Stage 1  作用域过滤修复（工作区内跨用户泄漏）      ← 最高优先级，完全独立
  Gateway Stage 0–3  契约 / 幂等 / 鉴权 / 归一化            ← 不依赖任何下游
  Router Stage 0    契约 / 配置                            ← Router Stage 1 依赖 Gateway Stage 1
  Agent Stage 0–3  端口 / 模型适配 / 工具绑定 / 执行落库      ← Agent Stage 2 需要 Gateway 决策 #5 的 `unprotected` 语义
  Session Stage 0  迁移 0046                              ← 关键路径的起点
  Context Stage 0  迁移 0047                              ← 物理上必须等 0046 落地

主线 ②（Session 枢纽 —— 全局关键路径）
  Session Stage 0 (0046) → 1 (resolve_or_create + lookup) → 2 (新表写入 / 双写 / 切读 / 停旧写)
     → 3 (唯一 turn 实现) ← 全局最关键的一个 Stage
     → 4 (session_events 落库) → 5 (审批加固) → 5b (删第二套 turn 实现，与 Gateway 4a 同 PR) → 6 (清理)

主线 ③（Session 之后的收敛）
  Router Stage 2/3/4/5   （依赖 Session 1 / 3）
  Agent Stage 4          专家选择 + 配置取值接线（模型/工具取自 agent 配置；依赖 Session 0 的 `agent_decision` 列）
  Agent Stage 5          循环 + **A-26：旧循环改接新 Builder / Writer**（依赖 Session 3）
  Context Stage 1–3      组装 / 压缩 / 持久化（**只新建，不动调用点**）
  Context Stage 4–5      停用 + 删（依赖 **Agent A-26** 与 **Session 5b**）
  Memory Stage 2–6b      检索 / 写入 / 绑定 / 向量化 / 统计 / 管理面（依赖 Session 3）
  Memory Stage 7         清理（依赖 **Agent A-26**）
  Gateway Stage 4b/5     （依赖 Session 4）
```

### 6.2 里程碑判据

每个里程碑都有**可客观判定**的完成标志 —— 达不到就不算完成（这是 2026-10-15 那次失败的直接防线）。

| 里程碑 | 覆盖的 Stage | 完成判据 |
|---|---|---|
| **M0 地基就位** | Gateway 0–3 · Router 0–1 · Memory 0–1 · Agent 0 · Context 0 · Session 0 | 五个迁移（0044–0048）全部在 dev 库可跑且可回滚；`qzdap_legacy_calls_total` 已上线且各层旧入口已打点；**Memory 的跨用户泄漏已修复**（有测试） |
| **M1 唯一 turn 实现** | Session 1–3 | 全仓只剩**一套**「跑一轮」的语义；`use_cases/run_turn.py` 与 `run_turn_to_completion.py` 已停用并打点；旧表双写期已开始对账 |
| **M2 事件可重放** | Session 4/5 · Gateway 4a/4b · **Session 5b（删第二套 turn 实现）** | `session_events` 真写真读；SSE 断线带 `Last-Event-ID` 重连内容完整；重复请求**无感重放**（Gateway 4b 完成）；**IM 渠道上只剩一套 turn 实现**（Session 5b 与 Gateway 的 IM 切换同 PR 删除） |
| **M3 上下文与记忆上线** | Context 1–3 · Memory 2–3 | 上下文可喂模型（`[{role, content}]`）；超预算走真压缩而非标记；记忆召回按用户隔离；manifest 落库 |
| **M4 路由与执行成型** | Router 2–4 · Agent 1–5 | 同会话消息严格有序；工具幂等**跨 worker** 生效；`tool_executions` 有真实行；**专家选择有留痕**、模型 / 工具**取自 agent 配置**；**存在一条跑完整个循环的端到端测试** |
| **M5 全部清零** | 全部 Stage N（清理） | 台账 37 条**全部「已清理」**；CI 扫描脚本零命中；`qzdap_legacy_calls_total` 全指标归零 |

### 6.3 关键路径与并行度

- **全局关键路径**：Session Stage 0 → 1 → 2 → 3 → 4 → Gateway Stage 4b → 5。**Session Stage 3（唯一 turn 实现）是整条链的咽喉** —— 它之前，四条下游支线全部堵住。
- **可并行度**：M0 阶段有**六条线**，其中 **五条可同时开工**（Gateway 0–3、Router 0、Agent 0–3、Memory 0–1、Session 0）。只有 **Context Stage 0 被 0046 的物理顺序卡住**（0047 依赖 0046 的 `agent_sessions` 变更）。
- **注意 Agent Stage 4 的位置**：它虽然**不需要** Session 的 turn 实现，但需要 Session 迁移 0046 建出的 `session_turns.agent_decision` 列 —— 所以它卡在**迁移**上，不是卡在**语义**上。
- **最容易被低估的**：Session Stage 3 的工作量（旧路径 647 行 `copilot.py` + 915 行 `runner.py` 的语义合并 + 审批加固）。它不是「写代码」，是**在两套漂移的语义里挑出对的那套并统一**。
- **⚠️ 删除顺序是自底向上的，拆开就会断**：旧路径的调用链是
  `copilot.py (X18) → runner._run_turn_inner (X17) → _load_messages (X8) / _remember (X11)`，以及 `use_cases/run_turn.py (X2) → adapter/llm/prompts.py (X10)`。
  **下层被上层调用，必须先停上层、再删下层** —— 这条约束由 **Agent Stage 5 的 A-26（旧循环改接新实现）** 兜住。

---

## 7. 跨方案系统级验收

> 各方案有各自的验收清单；这一节是**系统级**的 —— 一条消息走完 8 条泳道后的端到端判据。**这一节不过，任何一层的验收都不算数。**

| # | 系统级判据 | 涉及层 |
|---|---|---|
| 1 | **一条消息走完全链路**：入站 → 鉴权 → 归一化 → 去重 → 路由 → 建会话 → 组装上下文 → 召回记忆 → 推理 → 调工具 → 回灌 → 收尾 → 事件落库 → 渠道回包，**每一跳都有 trace_id 且可串联** | 全部 |
| 2 | **五种入口行为一致**：web / api / 飞书 / 企微 / 钉钉经 `Gateway.accept` 后，除 `channel_type` / `raw_metadata` 外字段完全一致 | Gateway |
| 3 | **重复消息只跑一次**：同一 `clientRequestId` 并发 10 次 → 只起 1 轮，其余 9 次**无感重放**（内容完整，不是 202） | Gateway + Session |
| 4 | **同会话严格有序**：并发 5 条同会话消息 → 执行顺序 == 入站顺序，无丢失无乱序；不同会话互不阻塞 | Router + Session |
| 5 | **审批中断可恢复**：工具挂起 → 客户端审批 → 恢复执行 → **执行的是被审批的那次调用**（`request_hash` 一致）；审批过期 → 明确错误，**不执行** | Session + Agent + Governance |
| 6 | **副作用不重复**：同一 `idempotency_key` 在两个 worker 上并发 → **只执行一次**；`tool_executions` 有真实行 | Agent |
| 7 | **`unprotected` 不碰副作用**：幂等键强度不足的消息 → **不产生任何副作用工具调用** | Gateway + Agent |
| 8 | **上下文不超限**：长会话压缩后 token 在预算内；仍超限 → 明确 `CONTEXT_TOO_LARGE`，**不是**继续超限喂模型 | Context |
| 9 | **记忆不串用户**：用户 A 的会话召回结果里不含用户 B 的记忆（租户 / 工作区 / 用户三层隔离各有测试） | Memory |
| 10 | **manifest 可查**：任一轮都能查出它每次模型调用的上下文组成与**淘汰原因** | Context |
| 11 | **成本归属正确**：`session_turns.cost_usd` 与实际调用一致；专家路由 / 模型降级都计入 | Agent |
| 12 | **旧实现真的少了**：台账 37 条全部「已清理」（**修复类条目 X14 / G10 走「已修复」**）；CI 扫描脚本零命中；`qzdap_legacy_calls_total` 全指标归零 | 全部（台账） |
| 13 | **架构边界不被绕过**：runtime 层零框架 import；摘掉任一层，其余层**不知道 HTTP / SSE / 飞书存在** | 全部 |

---

## 8. 外部前置依赖

> 这些改动**不在本方案集的代码范围内**，但方案里的某些 Stage 依赖它们。**不在本目录跟踪，但必须有人在别的目录推进** —— 否则对应的 Stage 会卡住。

| # | 依赖 | 归属模块 | 被哪个 Stage 卡住 | 备注 |
|---|---|---|---|---|
| 1 | ~~**`route_strategy` 新取值**~~ | ~~`modules/model` + `modules/agent_factory`~~ | ~~Agent Stage 4~~ | ❌ **已取消**（Agent 决策 #4）：不做运行时策略路由 → **这条跨模块前置不再存在**，`route_strategy` 保持 0042 的现有取值集合 |
| 2 | **专家 Agent 的 role 标签** | `modules/agent_factory`（`agent_versions`） | **Agent Stage 4** | 建议**复用 `agent_versions` + role 标签**，不新建专家表 —— 若决定新建，需在本目录补一份表归属登记 | ✅ **已消解**（2026-10-31，A-22 / A-23 ✓）—— 决策 #3 = **复用 `agent_versions`** ✓（专家 = 模型 + 指令 + 工具集 ✓）→ **未新建专家表** ✓ |
| 3 | **工具幂等 / 重试 / 熔断** | `modules/tool`（`InvokeToolUseCase`） | **Agent Stage 3** | 本方案给 Execution 层补幂等，但**执行器在 `modules/tool`**。落地要么在 `modules/tool` 里改，要么由 Execution 层包一层 —— **需先定归属**（倾向：改 `modules/tool`，因为它已经在写 `tool_calls`） | ✅ **已消解**（2026-10-31，A-14 / A-16 / A-20b ✓）—— 归属拍板 = **改 `modules/tool`** ✓（`tool_executions` 开始写 ✓ + 指数退避 + 熔断 ✓ + `turn_id` / `idempotency_key` ✓） |
| 4 | ~~**`tools` 表的 spec 生成真实 schema**~~ | ~~`modules/tool`~~ | — | ✅ **已消解**（2026-10-31，A-11 ✓）—— `modules/tool/.../application/tool_schema.py` ✓（**spec → JSON Schema 的单一真相** ✓）→ 模型看得到参数 ✓ |
| 5 | **工具白名单与 `unprotected` 语义** | `modules/agent_runtime`（agent 配置） | **Agent Stage 2** | 白名单在 agent 配置里（`allowed_tools` / `allowed_skills`）；`unprotected` 是 Gateway 判定的事实，需沿链路传到工具绑定的治理过滤 | ✅ **已消解**（2026-10-31，A-10 ✓）—— 治理过滤在 runtime 侧 `execution/tool_binding.py` ✓（`unprotected` 轮次的副作用工具**已剔除** ✓）→ 链路已通 ✓ |
| 6 | ~~**`deepagents` 依赖**~~ | ~~`runtimes/agent_runtime/pyproject.toml`~~ | — | ✅ **不再需要**（2026-10-31）—— Agent Stage 6 **已关闭** ✓（A-28b · 决策 #8 未采纳 ✓ —— 不接 `deepagents` = 不造第三套循环 ✓）→ `InMemoryDeepAgentFactory` 已随 Agent Stage 7 删除 ✓（全仓零命中 ✓）→ **这条前置不存在了** ✓ |
| 7 | ~~**`qzdap_legacy_calls_total` 指标**~~ | ~~`libs/observability`~~ | — | ✅ **已落地（2026-10-29）**：`LEGACY_CALLS_TOTAL` + `record_legacy_call(entry)` + `NEW_CALLS_TOTAL` + `record_new_call(entry)`（有单测）；**16/36 条台账条目已在旧入口打点**，其余 7 条走替代判据（从未接线 / 数据类）。**这一条不再是外部前置依赖** |
| 8b | ~~**`ErrorCode` 码收敛**~~ | ~~`libs/schema` + `modules/channel` + `modules/agent_runtime`~~ | — | ✅ **已消解**（2026-10-31，G-02b / G-02c ✓）—— 7 个码**全在 `ErrorCode` 枚举里** ✓（枚举 160 个成员 ✓）+ 守卫扩到**全量生产目录** ✓ → 生产代码里**不再有任何错误码字面量** ✓ |
| 8c | ~~**`modules/channel` 依赖 `qzdap-agent-runtime`**~~ | ~~`modules/channel` + `uv.lock`~~ | — | ✅ **已消解**（2026-10-31）—— `modules/channel/pyproject.toml` **已显式声明** `qzdap-agent-runtime-runtime` ✓ → 装得上 ✓ |
| 8 | ~~**LangGraph checkpoint 表**~~ | ~~`backend/migrations`（Session 迁移 0046）~~ | — | ✅ **已消解**（2026-10-31）—— ⚠️ **原文写「checkpoint 系列表不在任何迁移里」是错的** ✓ —— 0046 恰恰建了它们 ✓；但 **saver 已退役** ✓（S-14 ✓ —— 唯一消费者那张 19 节点图已随 Agent Stage 7 删除 ✓）→ **全仓零引用** ✓ → **迁移 0063 把四张表删了** ✓（`checkpoint_thread_id` 死函数一起删 ✓）|

---

## 9. 文档集与上位方案的关系

| 上位方案（v3.1）的部分 | 处置 |
|---|---|
| §4 状态与持久化模型（`SessionState`、`session_turns` / `session_messages` / `session_events` / `session_inbox` / `tool_executions`、outbox 投递状态机） | **沿用**，新层方案直接引用，不重新设计 |
| §5.7 治理语义（PolicyGuard、审批 TTL、同 hash 幂等） | **沿用** |
| §13.3–13.5 工具 / 记忆 / 结果契约 | **沿用** |
| §14 迁移细节 | **沿用**，按本目录的迁移编号继续（**0044 起**，注意与既有 0040–0043 避让） |
| §3.1 / §3.2 分层与 19 节点平图 | **被取代** → 改为按泳道分层，LangGraph 只圈住 Agent Loop 内循环 |
| §8 / §16 Stage 划分 | **被取代** → 改为按层推进，每层自带旧实现清理阶段 |
| §5.1–5.10 十项能力域 | **被取代** → 泳道 + 子件（Strategy / Session Routing / Idempotency Guard 等） |

上位方案 §8 的 8 个 Stage 已于 2026-10-15 执行完毕，产出 `backend/runtimes/agent_runtime/`——**但从未被 composition 根接线**，全部依赖为 InMemory 假实现。那批代码**不是**本方案集的实施基础，而是台账条目 **X1（待替换对象）**。处置原则见 [`cleanup-ledger.md`](cleanup-ledger.md) §5.3：**按需取用部件，不整体接线**。
