# 会话架构重构方案集

> 版本：1.1（2026-10-29：文档集入口建立，含决策状态汇总、术语约定、上位方案关系表）
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
| 3 | [`gateway-refactor-plan.md`](gateway-refactor-plan.md) | Gateway 泳道：Channel Gateway / Auth Identity / Message Normalizer / Idempotency Guard | **已定稿** |
| 4 | [`router-refactor-plan.md`](router-refactor-plan.md) | Router 泳道：Strategy（选 agent）+ Session Routing（选会话 + 有序保证） | 待评审 |
| 5 | Session 层方案 | 唯一 turn 实现 · 轮次状态机 · 事件落库与重放 · 并发控制 | 待写 |
| 6 | Context 层方案 | 上下文装配 · token 预算 · 压缩与摘要 · context manifest | 待写 |
| 7 | Memory 层方案 | L1/L2/L3 召回与写入 · 排序去重 · provenance · degraded | 待写 |
| 8 | Agent Loop / Agent Router / Execution 层方案 | 推理循环 · 模型与工具选择 · 实际执行与副作用幂等 | 待写 |

**为什么是这个顺序**：基线定契约 → 台账定收敛规则 → 从最外层（Gateway）往里推进。Gateway 是最外层、边界最清晰、最容易独立验收的一层；Router 次之；Session 层同时是 Gateway 的上游依赖（`session_events` 落库是「无感重放」的前提），是所有层的枢纽，因此**建议在 Gateway 与 Router 定稿后立刻写 Session 层**。

---

## 2. 决策状态汇总

> 每份层方案的附录 A 列了该层的待定决策。**任一决策改动，都要同步修改该方案正文对应章节**，并在这里更新状态。

| 方案 | 决策数 | 已定稿 | 待确认 | 未定稿的关键项 |
|---|---|---|---|---|
| Gateway | 8 | 8 | 0 | — |
| Router | 6 | 0 | 6 | #1 并发语义（排队 / 拒绝）；#2 表选择（新表 `session_*` vs 旧表 `agent_*`） |
| Session | — | — | — | 待写 |
| Context | — | — | — | 待写 |
| Memory | — | — | — | 待写 |
| Agent Loop / Router / Execution | — | — | — | 待写 |

**Router 的 #1 与 #2 会直接决定 Session 层方案的形态**，建议优先。

---

## 3. 全局规则

### 3.1 实现收敛：最终态只有一个实现

**先上新、后清旧**。新实现接管并稳定运行后，删除旧实现。

```
未开始 →（新实现接管 + @deprecated + 调用打点）→ 已弃用
       →（调用指标归零 + 稳定运行 ≥1 发布周期）→ 待清理 →（删除）→ 已清理
```

| 规则 | 说明 |
|---|---|
| **弃用标记 + 观测** | 旧实现被接管时打 `@deprecated` + `qzdap_legacy_calls_total{path="..."}`，让「旧路径还在被调用」成为可观测事实 |
| **删除条件客观化** | 指标归零 **且** 新实现稳定运行 ≥ 1 个发布周期；不接受「感觉没人用了」 |
| **台账化** | 全部旧实现登记在 [`cleanup-ledger.md`](cleanup-ledger.md) |
| **不可结转** | 某层台账未清零，该层不得进入下一层的「切换」阶段；未完成项不允许滚到下个迭代 |

**为什么不在同一次提交里一起删**：并存期可以用真实流量对照新旧行为（唯一可靠的验证方式），且旧实现留在场可作回退兜底。**代价**：清理完成后回退需重新上线旧版本。

> 2026-10-15 那次重构建了完整的新 runtime 却**从未接线**，同期旧路径继续长功能，两套并存至今。根因是验收标准是「单测通过」而非「旧实现减少」——上面四条规则就是针对这个根因的。

### 3.2 边界判据

> **把某一层整个摘掉，剩下的层应该完全不知道 HTTP、SSE、飞书这些词存在。**

落成一条架构测试：runtime 层不得 import `fastapi` / `starlette` / `sqlalchemy` / `asyncpg` / `psycopg`。

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

---

## 5. 写新层方案的要求

1. 明确标出自己在基线图上的位置，并说明与相邻层的**接口数据形状**；
2. **不得引入与基线冲突的层次**；
3. **不得在同一层内并存两套实现**；
4. 每个阶段验收必须包含「**旧代码减少了什么**」；
5. 旧实现登记进 [`cleanup-ledger.md`](cleanup-ledger.md)，删除时同步更新状态；
6. 附录 A 列出该层的待定决策，决策改动要回改正文；
7. 引用上位方案时明确说明**哪些部分仍有效**（当前：§4 状态模型、§5.7 治理语义、§13.3–13.5 契约、§14 迁移细节）。

---

## 6. 文档集与上位方案的关系

| 上位方案（v3.1）的部分 | 处置 |
|---|---|
| §4 状态与持久化模型（`SessionState`、`session_turns` / `session_messages` / `session_events` / `session_inbox` / `tool_executions`、outbox 投递状态机） | **沿用**，新层方案直接引用，不重新设计 |
| §5.7 治理语义（PolicyGuard、审批 TTL、同 hash 幂等） | **沿用** |
| §13.3–13.5 工具 / 记忆 / 结果契约 | **沿用** |
| §14 迁移细节 | **沿用**，按本目录的迁移编号继续（0040 / 0041 …） |
| §3.1 / §3.2 分层与 19 节点平图 | **被取代** → 改为按泳道分层，LangGraph 只圈住 Agent Loop 内循环 |
| §8 / §16 Stage 划分 | **被取代** → 改为按层推进，每层自带旧实现清理阶段 |
| §5.1–5.10 十项能力域 | **被取代** → 泳道 + 子件（Strategy / Session Routing / Idempotency Guard 等） |

上位方案 §8 的 8 个 Stage 已于 2026-10-15 执行完毕，产出 `backend/runtimes/agent_runtime/`——**但从未被 composition 根接线**，全部依赖为 InMemory 假实现。那批代码**不是**本方案集的实施基础，而是台账条目 **X1（待替换对象）**。处置原则见 [`cleanup-ledger.md`](cleanup-ledger.md) §5.3：**按需取用部件，不整体接线**。
