# 旧实现清理台账（全局）

> 版本：1.1
> 建立日期：2026-10-29
> 最后更新：2026-10-29（方案集迁入 `docs/refactor/session-architecture/`）
> 状态：**生效中**
> 适用范围：`docs/refactor/session-architecture/` 下全部重构方案（Gateway / Router / Session / Context / Memory / Agent Loop / Agent Router / Execution）

---

## 0. 这份台账为什么存在

2026-10-15 那次重构建了一套完整的新 runtime（8 个 Stage 全部打勾），却**从未接线**，同期旧路径继续长功能，两套并存至今。根因不是技术问题，是**流程问题**：

> 每个 Stage 的验收标准是「单测通过」，而不是「旧实现减少」。于是每一步都「完成」了，而旧实现从未退场。

本台账是针对这个根因的机制。**规则**：

1. **最终态只有一个实现**——任一职责在全仓只有一套实现承接；
2. **先上新、后清旧**——新实现接管并稳定运行后删除旧实现，清理窗口内允许短期并存；
3. **清理是必达项**——台账条目不允许滚到下个迭代；某层台账未清零，该层不得进入下一层的「切换」阶段。

---

## 1. 状态机

```
未开始 ──(新实现接管 + 打弃用标记 + 打点)──▶ 已弃用
                                              │
                                    (调用指标归零 + 稳定运行 ≥1 发布周期)
                                              ▼
                                          待清理 ──(删除)──▶ 已清理
```

| 状态 | 含义 | 允许合并？ |
|---|---|---|
| 未开始 | 旧实现仍是唯一生效路径 | — |
| 已弃用 | 新实现已接管；旧实现仍可被调用，但带弃用标记与调用打点 | ⚠️ 需在 PR 里说明 |
| 待清理 | 调用指标归零且已稳定运行 ≥ 1 个发布周期 | ✅ 应尽快删 |
| 已清理 | 代码已删除、扫描脚本无命中 | ✅ |

---

## 2. 台账

> 「观测指标」统一为 `qzdap_legacy_calls_total{path="<标识>"}`，在旧实现被调用的入口处打点。

### 2.1 Gateway 域

| # | 旧实现 | 位置 | 替代者 | 状态 | 所属方案 |
|---|---|---|---|---|---|
| G1 | `record_request_id` + `session.metadata.recent_request_ids` | `modules/agent_runtime/adapter/persistence/repositories.py:155-170` | `gateway/idempotency.py`（`session_inbox` 原子 claim） | 未开始 | Gateway Stage 1 |
| G2 | IM 验签分支 `_verify_signature` / `_reject` | `modules/channel/application/services.py:195-215` | `gateway/identity.py` | 未开始 | Gateway Stage 2 |
| G3 | 硬编码 `SYSTEM_USER_ID` / `SYSTEM_AGENT_ID` | `modules/channel/adapter/dispatch/dispatch_subscriber.py:42-46` | 渠道配置登记的服务账号 | 未开始 | Gateway Stage 2 / Router Stage 2 |
| G4 | `ParsedMessage` 数据类 | `modules/channel/application/ports.py:95-104` | `gateway/types.py` 的 `InboundMessage` | 未开始 | Gateway Stage 3 |
| G5 | `ChannelMessageReceived` 事件（缺 `external_message_id` / `trace_id`） | `modules/channel/domain/events.py:27-46` | `InboundMessage` + `session_inbox` | 未开始 | Gateway Stage 3 |
| G6 | IM 进程内 LRU 去重 | `modules/channel/adapter/dispatch/dispatch_subscriber.py:43-44,113-125,253-260` | `session_inbox` 原子 claim | 未开始 | Gateway Stage 3 |
| G7 | `/v1/sessions*` 的 turn 部分 | `modules/agent_runtime/adapter/http/router.py:209-280` | 统一会话 API（`/api/sessions*`） | 未开始 | Gateway Stage 4→5 |
| G8 | `GET /v1/sessions` 列表别名 | `modules/agent_runtime/adapter/http/session_router.py:541-547` | `GET /api/sessions` | 未开始 | Gateway Stage 4→5 |
| G9 | `dispatch_subscriber.py` 整体 | `modules/channel/adapter/dispatch/dispatch_subscriber.py` | `Gateway.accept` 直连 | 未开始 | Gateway Stage 4→5 |

### 2.2 Router 域

| # | 旧实现 | 位置 | 替代者 | 状态 | 所属方案 |
|---|---|---|---|---|---|
| R1 | IM 每条消息新建临时 session | `modules/channel/adapter/dispatch/dispatch_subscriber.py:175-186` | `channel_session_key` → `session_id` 映射 | 未开始 | Router Stage 2 |
| R2 | `agentId` 直取（无任何策略） | `modules/agent_runtime/adapter/http/session_router.py:162-171` | `router/strategy.py` 规则链 | 未开始 | Router Stage 1 |
| R3 | `try_claim` 中混在一起的「顺序」职责 | `modules/agent_runtime/adapter/persistence/repositories.py:85-108` | `ingress_seq` + FIFO（执行权部分留 Session） | 未开始 | Router Stage 3 |
| R4 | `build_session_key`（冒号拼接版） | `runtimes/agent_runtime/src/qzdap_agent_runtime/channels/gateway.py` | 哈希版 `session_key`（`router/session_router.py`） | 未开始 | Router Stage 2 |

### 2.3 跨层 / 历史遗留

| # | 旧实现 | 位置 | 替代者 | 状态 | 所属方案 |
|---|---|---|---|---|---|
| X1 | **未被接线的 `backend/runtimes/agent_runtime/` 整包**（19 节点图、InMemory 假实现、无任何 import） | `backend/runtimes/agent_runtime/src/qzdap_agent_runtime/` | 各层方案按泳道逐步替换；最终只保留被采用的部件 | **未开始（最高风险项）** | 全部层 |
| X2 | 第二套 turn 实现（无 claim / 幂等 / 取消 / 审批） | `modules/agent_runtime/application/use_cases/run_turn.py`、`run_turn_to_completion.py` | `copilot.py` 的唯一 turn 编排（保留其 claim / 幂等 / 取消 / 审批语义） | 未开始 | Session 层（主战场），Gateway Stage 4 配合 |
| X3 | `agent_sessions.graph_state`（续传状态与业务数据混装同列） | `modules/agent_runtime/adapter/persistence/models.py:56-61` | `session_events` / `session_turns` | 未开始 | Session 层 |
| X4 | `agent_turns` / `agent_session_messages` 表 | `migrations/versions/`（早期） | `session_turns` / `session_messages` | 未开始 | Session 层（Router 决策 #2） |
| X5 | 占位图 `compile_loop_graph`（节点全是 `_passthrough_*`） | `modules/agent_runtime/adapter/graph/loop.py:63-69`、`runner.py:92` | Agent Loop 方案的真实图 | 未开始 | Agent Loop 层 |

### 2.4 需要「启用」而非「清理」的资产（跟踪用，防止被误删）

| 资产 | 位置 | 状态 |
|---|---|---|
| `session_inbox` 表 | 迁移 0035 | 待启用（Gateway Stage 1）+ 改造（加列改约束） |
| `session_turns` / `session_messages` / `session_events` | 迁移 0035 | 待启用（Session 层） |
| `tool_executions` / `outbox_dead_letters` | 迁移 0035 | 待启用（Agent Loop / Execution 层） |
| `agent_sessions.channel_session_key` | 迁移 0035 | 待启用（Router Stage 2）+ 加唯一索引 |
| `agent_sessions.current_revision` | 迁移 0035 | 待启用（Session 层乐观并发；旧路径从不使用） |
| `agent_sessions.next_ingress_seq` | 待新增（迁移 0041） | Router Stage 3 |
| `admin_agents.visible_scope` / `category` / `tags` / `profile` | 现有 | **已在用**（作为 Strategy 的策略依据，不新建策略表） |

---

## 3. 防回归机制

### 3.1 扫描脚本（进 CI）

```bash
# scripts/check_no_legacy_impl.sh —— 命中即失败
set -e
cd backend

# Gateway 域
grep -rn "recent_request_ids"        modules/ && { echo "✗ G1 未清理"; exit 1; }
grep -rn "record_request_id"         modules/ && { echo "✗ G1 未清理"; exit 1; }
grep -rn "class ParsedMessage"       modules/ && { echo "✗ G4 未清理"; exit 1; }
grep -rn "ChannelMessageReceived"    modules/ && { echo "✗ G5 未清理"; exit 1; }
grep -rn "SYSTEM_USER_ID\|SYSTEM_AGENT_ID" modules/ && { echo "✗ G3 未清理"; exit 1; }
grep -rn "OrderedDict"               modules/channel/ && { echo "✗ G6 未清理"; exit 1; }
grep -rn "\"/v1/sessions"             modules/ && { echo "✗ G7/G8 未清理"; exit 1; }
grep -rn "dispatch_subscriber"       modules/ && { echo "✗ G9 未清理"; exit 1; }

# Router 域
grep -rn "build_session_key"         modules/ && { echo "✗ R4 未清理"; exit 1; }

# 跨层
grep -rn "RunTurnCompletionUseCase"  modules/ && { echo "✗ X2 未清理"; exit 1; }
grep -rn "use_cases.run_turn"        modules/ && { echo "✗ X2 未清理"; exit 1; }
grep -rn "compile_loop_graph"        modules/ && { echo "✗ X5 未清理"; exit 1; }
```

> 脚本在**对应层的 Stage 5 合并时启用**，不是一开始就开——否则旧实现还在时 CI 一直红。启用与旧条目的删除在同一个提交里完成。

### 3.2 指标看板

```
qzdap_legacy_calls_total{path="<标识>"}   # 旧路径调用次数，按台账编号标注
```

清理判定的唯一依据是**该指标归零**，不接受「代码看起来没人用了」。

### 3.3 阶段门禁

| 规则 | 说明 |
|---|---|
| 本层台账未清零 | 不得进入下一层的「切换」阶段 |
| 任一条目超期未清理 | 升级为阻塞项，在周会上过 |
| 未完成项滚期 | **不允许**——超期即升级 |

---

## 4. 更新规则

1. 每次「旧实现被新实现接管」的 PR，必须在**同一 PR** 里：
   - 给旧实现加 `@deprecated` 标记；
   - 加调用打点（`qzdap_legacy_calls_total`）；
   - 把台账对应条目的状态改为「已弃用」；
2. 每次删除旧实现的 PR，必须：
   - 把台账状态改为「已清理」；
   - 启用对应的扫描脚本规则；
3. 台账与代码不一致时，**以代码为准**并立即修正台账——台账失真比没有台账更危险。

---

## 5. 汇总

### 5.1 按状态统计

| 状态 | 条目数 | 说明 |
|---|---|---|
| 未开始 | 18 | 全部条目均未开始（新实现尚未接管） |
| 已弃用 | 0 | — |
| 待清理 | 0 | — |
| 已清理 | 0 | — |

### 5.2 按归属方案统计

| 方案 | 条目 | 编号 |
|---|---|---|
| Gateway | 9 | G1–G9 |
| Router | 4 | R1–R4 |
| Session（跨层） | 3 | X2、X3、X4 |
| Agent Loop（跨层） | 1 | X5 |
| 全部层共同 | 1 | **X1（未接线的 `backend/runtimes/agent_runtime/` 整包）** |

### 5.3 最高风险项：X1

`backend/runtimes/agent_runtime/`（19 节点 LangGraph + 全部 InMemory 假实现）**建于 2026-10-15，从未被 composition 根接线**，全包除 `langgraph` / `langchain_core` / `pydantic` 外零外部 import——物理上无法连数据库、LLM、工具服务。

它同时是**诱惑**和**陷阱**：

- **诱惑**：文件名、目录名、方案章节号都对应 v3.1，看起来像是「已经建好的新实现」，容易被当成现成基础直接接线；
- **陷阱**：它的 `agent` 节点是 `return {}`、**没有 LLMPort**，即使把 outbox 与 checkpointer 全接上也跑不出一次正常的工具调用。直接接线会得到一个「能启动但不干活」的运行时。

> **处置原则**：`runtimes/agent_runtime/` 里的部件**按需取用**（`result/events.py` 的事件类型、`outbox/` 的死信状态机、`result/sink.py` 的重放语义、`channels/gateway.py` 的 DTO 形状、`governance/approval.py` 的 TTL 与幂等校验、`graph/routing.py` 的分类器），**不整体接线**。整体接线的路径已被证伪一次，不再尝试第二次。

### 5.4 台账与方案文档的对应

| 台账条目 | 出现在 | 删除阶段 |
|---|---|---|
| G1 | Gateway §7.2、Stage 1 | Gateway Stage 1（直接删，无调用方） |
| G2 | Gateway §7.2、Stage 2 | Gateway Stage 2 |
| G3 | Gateway §7.2；Router §7.2 | Gateway Stage 2 / Router Stage 2 |
| G4、G5、G6 | Gateway §7.2、Stage 3 | Gateway Stage 3 |
| G7、G8、G9 | Gateway §7.4、Stage 4 | Gateway Stage 5 |
| R1、R2、R3、R4 | Router §7.2、§7.4 | Router Stage 2 / Stage 3 / Stage 5 |
| X2 | Gateway §7.4（配合）；Session 层方案（主战场） | Session 层 Stage（待写） |
| X3、X4 | Session 层方案（待写） | 待定 |
| X5 | Agent Loop 层方案（待写） | 待定 |
