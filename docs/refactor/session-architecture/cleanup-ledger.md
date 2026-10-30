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
3. **清理是必达项**——台账条目不允许滚到下个 Stage；某层台账未清零，该层不得进入下一层的「切换」阶段。

---

## 1. 状态机

```
未开始 ──(新实现接管 + 打弃用标记 + 打点)──▶ 已弃用
   │                                            │
   │(必须原子切换的条目)                  (量化判据见 §3.2)
   ▼                                            ▼
切换中 ──(同 PR 一起换完)──▶ 已弃用        待清理 ──(删除)──▶ 已清理
```

| 状态 | 含义 | 允许合并？ |
|---|---|---|
| 未开始 | 旧实现仍是唯一生效路径 | — |
| 切换中 | 新旧两套同时在跑，**必须同 PR 原子发布**（见 §3.4） | ❌ 必须与配套改动同 PR |
| 已弃用 | 新实现已接管；旧实现仍可被调用，但带弃用标记与调用打点 | ⚠️ 需在 PR 里说明 |
| 待清理 | 满足 §3.2 的量化判据 | ✅ 应尽快删 |
| 已清理 | 代码已删除、扫描脚本无命中 | ✅ |
| **已修复** | **修复类条目**（X14 / G10）专用：缺陷已修掉，**不进指标**，由**回归测试**判定 | ⚠️ **不可回退**（见 README §3.1.1 回退纪律 1：安全修复回退等于重新打开漏洞） |

---

## 2. 台账

> 「观测指标」统一为 `qzdap_legacy_calls_total{entry="<台账编号>"}`，在旧实现被调用的**入口处**打点。
>
> ✅ **该指标已于 2026-10-29 落地**：`libs/observability/src/qzdap_observability/metrics.py` 的 `LEGACY_CALLS_TOTAL` + `record_legacy_call(entry)`（另附 `LEGACY_CALL_LAST_TIMESTAMP` gauge）。**尚未打点** —— 各层方案的 Stage 0 仍需在旧入口调用 `record_legacy_call("<编号>")`，否则该层的清理判据仍无从判定。

### 2.0 台账条目的字段定义

每条台账条目有**六个字段**，缺一不可（否则无法判定「能不能删」）：

| 字段 | 含义 | 写法要求 |
|---|---|---|
| **#** | 条目编号 | 全局唯一。`G` = Gateway 域，`R` = Router 域，`X` = 跨层。**编号一经分配不再复用** |
| **旧实现** | 被清理的东西是什么 | **具体符号名**，不许写「旧路径」这种模糊说法 |
| **位置** | 在哪 | `文件路径:行号范围`。**行号会漂移**，但文件路径是锚点 —— 判定时以符号搜索为准 |
| **替代者** | 换成什么 | **具体文件路径**（如 `gateway/idempotency.py`）。**不许写「新实现」** —— 那等于没写 |
| **状态** | 收敛进度 | `未开始` / `切换中` / `已弃用` / `待清理` / `已清理`（状态机见 §1） |
| **所属方案** | 谁负责删 | **唯一 owner**。同一个旧实现只能由一个方案负责删除，其余方案只做「配合停用」 |

> **唯一 owner 规则**：如果两个方案都写着要删同一个东西，那么其中一个方案写错了 —— 去改台账，不是去改那个方案。

### 2.1 Gateway 域

| # | 旧实现 | 位置 | 替代者 | 状态 | 所属方案 |
|---|---|---|---|---|---|
| G1 | `record_request_id` + `session.metadata.recent_request_ids` | ~~`modules/agent_runtime/adapter/persistence/repositories.py:155-170`~~（**已删**） | `qzdap_agent_runtime/gateway/idempotency.py` + `session_inbox` 原子 claim | **已清理**（2026-10-29：Gateway Stage 1 —— `record_request_id` 的协议方法与实现、`recent_request_ids` 的全部读写**已删除**；`copilot.stream_turn` 改走 `IdempotencyGuard`；替代物 = `session_inbox` 的 strong 键部分唯一索引 + 原子 claim） | Gateway Stage 1 |
| G2 | IM 验签分支 `_verify_signature` / `_reject` | ~~`modules/channel/application/services.py:195-215`~~（**已删**） | `qzdap_agent_runtime/gateway/identity.py` 的 `HmacWebhookVerifier` | **已清理**（2026-10-29：Gateway Stage 2 —— 渠道服务里的 `_verify_signature` **已删除**，改为调用 gateway 的验签器；`_reject`（审计事件）**保留** —— 拒绝事件是当前职责，不是旧实现） | Gateway Stage 2 |
| G3 | 硬编码 `SYSTEM_USER_ID` / `SYSTEM_AGENT_ID` | ~~`modules/channel/adapter/dispatch/dispatch_subscriber.py:42-46`~~（**已删**） | **渠道配置登记的服务账号**（`channels.service_account` JSON 列，迁移 0049） | **已清理**（2026-10-29：Gateway Stage 2 —— 两个常量**已删除**；IM 的 actor 由渠道登记的服务账号物化（`ServiceAccount.from_mapping`），渠道没登记就**不跑这一轮**并留错误日志。迁移 0049 把既有全局身份**回填**进存量渠道行，升级不丢身份） | Gateway Stage 2 / Router Stage 2 |
| G4 | `ParsedMessage` 数据类 | ~~`modules/channel/application/ports.py:95-104`~~（**已删**） | `gateway/types.py` 的 `InboundMessage` | **已清理**（2026-10-29：Gateway Stage 3 —— 数据类、协议 `InboundAdapter` 与 4 个适配器的 `parse_webhook` **全部删除**；适配器改为实现 Gateway ③ 的 `MessageNormalizer.normalize()`，产出标准 `InboundMessage`） | Gateway Stage 3 |
| G5 | `ChannelMessageReceived` 事件（缺 `external_message_id` / `trace_id`） | ~~`modules/channel/domain/events.py:27-46`~~（**已删**） | `InboundMessage` + `session_inbox` | **已清理**（2026-10-29：Gateway Stage 3 —— 事件类**已删除**，入站消息本身（`InboundMessage`）就是总线事件；补上 `external_message_id` / `trace_id` / `payload_hash`。⚠️ 连带修掉两个真实缺陷：**总线按类名路由**，旧实现按 dotted 的 `TOPIC` 订阅 → 这条 IM 链路**从未被触发过**；事件定义了 `to_payload()` 而 `EventEnvelope.wrap` 只认 `_as_payload_dict()` → 载荷退化成 `{"value": "<repr>"}`。审计侧的事件名同步改为 `InboundMessage`） | Gateway Stage 3 |
| G6 | IM 进程内 LRU 去重 | ~~`modules/channel/adapter/dispatch/dispatch_subscriber.py:43-44,113-125,253-260`~~（**已删**） | `session_inbox` 原子 claim | **已清理**（2026-10-29：Gateway Stage 3 —— `OrderedDict` LRU、`_message_key`、`_evict_dedup` **全部删除**；IM 派发改为先走 ④ 的 `session_inbox` 原子 claim（跨进程可见 + 有 TTL），轮次失败时 **release**（键不该被消费）） | Gateway Stage 3 |
| G7 | `/v1/sessions*` 的 turn 部分 | ~~`modules/agent_runtime/adapter/http/router.py`~~（**已删**） | 统一会话 API（`/api/sessions*`） | **已清理**（2026-10-29：Gateway Stage 5 —— **整个 `adapter/http/router.py` 删除**（4 个 `/v1` 路由 + 依赖装配）、`adapter/http/mappers.py` 删除、`adapter/http/dto.py` 只留 `InteractiveAnswerRequest`；`composition/main.py` 的挂载删除。⚠️ **API owner 已确认无仓外调用方**（方案 §9.4 的前置 **P-11**）→ 兼容保留期归零 → **不只 turn 部分，整个 `/v1/sessions*` 一次删完**。仓内调用方同步：perf 脚本改走 `/api`、集成测试迁到 `test_session_api.py`） | Gateway Stage 5 |
| G8 | `GET /v1/sessions` 列表别名 | ~~`modules/agent_runtime/adapter/http/session_router.py`~~（**已删**） | `GET /api/sessions` | **已清理**（2026-10-29：Gateway Stage 5 —— 别名路由删除；保留期随 **P-11**（无仓外消费者）归零。⚠️ 它是**列表**查询 —— 删掉后租户过滤只剩 `/api/sessions` 一处（`copilot.list_sessions` 显式带 `tenant_id` ✓）） | Gateway Stage 5 |
| G9 | `dispatch_subscriber.py` 整体 | ~~`modules/channel/adapter/dispatch/dispatch_subscriber.py`~~（**已删**） | `Gateway.accept` 直连 | **已清理**（2026-10-30：Session Stage 5b —— 与 **X2 同 PR** 原子删除 ✓。取代它的是 `channel_turn_dispatcher.py`（**渠道侧的驱动**：解码 → 渠道/服务账号 → 跑一轮 → 出站投递 ✓）；**会话粘性**由 Session 层按 `channel_session_key` 负责 ✓。扫描规则 `dispatch\.dispatch_subscriber` 启用 ✓） | Gateway Stage 4→5（**Stage 5b 已达成** ✅） |
| G10 | **审批恢复路径丢失幂等键**：`decide_approval` 调 `stream_turn` 时**不传 `clientRequestId`** → `record_request_id("")` 直接返回 `True` → 幂等被跳过 → 连点两次「同意」工具被**再执行一次** | ~~`modules/agent_runtime/src/qzdap/modules/agent_runtime/application/copilot.py:474-482`~~（**已修**） | 审批决策带**自己的**幂等键（由 `approval_id` 派生）—— **键只由审批自身的稳定标识派生**，不掺原轮次的键（审批恢复时原轮次状态已推进、原键取不到 → 键会漂移 → 重复点击挡不住） | **已修复**（2026-10-29：Gateway Stage 1 —— `decide_approval` 生成 `approval\|{approval_id}\|{decision}` 的 strong 键；连点两次「同意」第二次被判定为重复，工具只执行一次。**判据是回归测试**：`modules/agent_runtime/tests/unit/test_copilot_resilience.py::test_double_clicking_approve_executes_the_tool_only_once`） | **Gateway Stage 1**（幂等键传递 ✅）+ **Session Stage 5**（X7 审批吞异常 ⏳）—— **两侧都要做，只做一边不够** |
| G11 | **重复请求的 202 降级路径**（Stage 4a 引入的**临时**降级：命中重复 → 202 + 上次 turn_id + `replay_unavailable`） | ~~`modules/agent_runtime/adapter/http/session_router.py`（SSE 端点的 202 分支）~~ + `DuplicateRequestError.replay_unavailable`（**已删**） | **无感重放**（`session_events` 按 seq 重放；Gateway Stage 4b） | **已清理**（2026-10-29：Gateway Stage 4b —— 202 分支与 `replay_unavailable` 字段**删除**；重复命中改为**重放上一轮的事件流**（SSE 带 `id:` 游标，支持 `Last-Event-ID` 续传），重放不了才回 409。⚠️ 这是**同一语义的两套实现**（重放 vs 降级），最终态只留重放） | Gateway Stage 4b |
| G12 | **各模块 `domain/errors.py` 里的自由字符串错误码**（Gateway 域的 15 个：`CHANNEL_NOT_FOUND` / `CHANNEL_DISABLED` / `INBOUND_ADAPTER_MISSING` / `OUTBOUND_ADAPTER_MISSING` / `WEBHOOK_SIGNATURE_INVALID` / `WEBHOOK_TIMESTAMP_SKEW` / `DUPLICATE_REQUEST` / `TENANT_DENIED` / `CHANNEL_SERVICE_ACCOUNT_MISSING` / `CHANNEL_DELIVERY_FAILED` / `IDENTITY_REJECTED` / `IDENTITY_CREDENTIALS_MISSING` / `TOKEN_INVALID` / `TOKEN_EXPIRED` / `SERVICE_ACCOUNT_NOT_CONFIGURED`）| `modules/channel/domain/errors.py` 等各模块 + `libs/auth/jwt.py` + `libs/persistence/tenant_guard.py` + `runtimes/.../gateway/identity.py` | `ErrorCode` 枚举（`libs/schema/.../errors.py`）+ `ERROR_PROJECTION` 投影表 | **已清理**（2026-10-29：Gateway Stage 0 · G-02b —— 15 个码**全部提升为 `ErrorCode` 枚举成员**，生产代码改为引用 `ErrorCode.X.value`；扫描规则 + 架构测试（`tests/architecture/test_error_code_vocabulary.py`）守门。⚠️ **方案 §9.0 的表只列了 7 个** —— 实施时发现 Gateway Stage 2/4a **自己又造了 8 个**（服务账号缺失 / 投递失败 / 出站适配器缺失 / 鉴权拒绝原因等）→ **按实况补齐到 15 个**，否则收敛只做了一半。⚠️ **其余模块自己的 ~150 个码未接管** —— 不属 Gateway 层，全量收敛是跨层工程） | Gateway Stage 0（G-02b） |

### 2.2 Router 域

| # | 旧实现 | 位置 | 替代者 | 状态 | 所属方案 |
|---|---|---|---|---|---|
| R1 | IM 每条消息新建临时 session | ~~`modules/channel/adapter/dispatch/dispatch_subscriber.py:175-186`~~（**已删**） | `channel_session_key` → `session_id` 映射 | **已清理**（2026-10-30：Session Stage 5b —— IM 的会话**按「渠道 + 聊天」粘住** ✓（`SessionManager.resolve_or_create` + `channel_session_key` 部分唯一索引 ✓）；跨消息的上下文因此能续上 ✓（旧行为：每条消息新会话 → 上下文全丢 ✗） | Router Stage 2（停用）→ Stage 5（删）→ **Session Stage 5b 已达成** ✅ |
| R2 | `agentId` 直取（无任何策略） | ~~`modules/agent_runtime/adapter/http/session_router.py:162-171`~~（**已删**） | `qzdap_agent_runtime/router/strategy.py` 的规则链 | **已清理**（2026-10-29：Router Stage 1 —— `create_session` 的 `agentId` 直取**删除**，改为把请求里的 agentId 作为「**显式指定**」这一条规则的输入交给 `RuleChainStrategy`；旧的 `record_legacy_call("R2")` 打点撤除（打点是清理**前**的观测手段），改打 `record_new_call("R2")`。⚠️ **没有策略就没有会话** —— 一条规则都没命中且工作区无兜底默认 agent 时返回 400 并说明缺什么，**不静默换 agent**） | Router Stage 1 |
| R3 | **`try_claim` 的会话互斥职责**（CAS `wait_status='running'`；⚠️ **它只有这一个职责** —— 实测无任何序号/顺序语义，旧路径从未有过顺序机制） | ~~`modules/agent_runtime/adapter/persistence/repositories.py:85-108`~~（**已删**） | `agent_sessions.current_turn_id` + `session_turns.status` 推导（执行权）—— 契约 `session/claim.py`（`TurnClaimPort`）+ 实现 `PostgresTurnClaim`（原子 CAS） | **已清理**（2026-10-30：Session Stage 3a —— `try_claim` 及其 `wait_status` CAS **删除**（`SessionRepository` 协议里的方法一并删）；执行权迁到「`current_turn_id` 占用 + 轮次状态/僵尸判定」（Session 方案 §4.4 ✓）；旧打点 `record_legacy_call("R3")` 撤除；扫描规则启用） | **Session**（Stage 3a ✅） |
| R4 | `build_session_key`（冒号拼接版） | ~~`runtimes/agent_runtime/src/qzdap_agent_runtime/channels/gateway.py`~~（**已删**） | 哈希版 `derive_session_key`（`runtimes/agent_runtime/src/qzdap_agent_runtime/router/session_key.py`） | **已清理**（2026-10-29：Router Stage 2 的 key 派生 —— 旧函数**删除**，改为 `router/session_key.py` 的**长度前缀 + sha256**（6 维，含 `channel_type` ✓）；引用点同步改（从未接线的 `engine.py` / `scripts/verify_e2e.py` / 单测）。⚠️ **扫描规则的目录原本写错**（扫 `modules/`，而旧实现在 `runtimes/` ✗ → 规则**从来没生效过**）→ 已改正并**启用**。⚠️ 按台账 §3.2，「停用 + 打点」**做不了** —— 旧实现无生产调用方，打点会得到恒为 0 的指标（比没有指标更危险 ✓）→ 按 Gateway 附录 C.8 的 **G-38 口径**（引用关系可证即当场删 ✓）执行） | Router Stage 2 |

### 2.3 跨层 / 历史遗留

| # | 旧实现 | 位置 | 替代者 | 状态 | 所属方案 |
|---|---|---|---|---|---|
| X1 | **未被接线的 `backend/runtimes/agent_runtime/` 整包**（19 节点图、InMemory 假实现、无任何 import） —— ⚠️ **2026-10-29 起不再是「整包未接线」**：Gateway 层**按需取用**了其中的 `gateway/` 子包（幂等契约与守卫），生产路径已 import 它；⚠️ **2026-10-30 起又取用了 `outbox/` 子包**（Session Stage 4b —— `OutboxWorker` / `OutboxRepository` / `to_result_event` 是**出站重试与死信的唯一实现** ✓，生产路径已 import 它 ✓）；其余部件（19 节点图等）**仍未接线** | `backend/runtimes/agent_runtime/src/qzdap_agent_runtime/` | 各层方案按泳道逐步替换；最终只保留被采用的部件 | **未开始（最高风险项）** | 各层**按需取用部件**；**删除归 Agent Stage 7**（连同 §2.3.2 的平行实现）—— ⚠️ **已被取用的部件不再删**，只删未取用的残留（扫描规则 §3.1 的三条仍成立：盯的是 `graph/nodes.py` / `build_session_graph` / `InMemoryToolExecutor`，与 `gateway/` `outbox/` 无交集 ✓） |
| X2 | 第二套 turn 实现（无 claim / 幂等 / 取消 / 审批） | ~~`modules/agent_runtime/application/use_cases/run_turn.py`~~、~~`run_turn_to_completion.py`~~（**已删**） | 契约层的 `TurnRunner`（唯一 turn 实现 ✓，保留 claim / 幂等 / 取消 / 审批语义） | **已清理**（2026-10-30：Session Stage 5b —— ① IM 入口切到**唯一 turn 实现**（`copilot.stream_turn` → 契约层 `TurnRunner` ✓）；② 两个用例**删除** ✓；③ 随之空掉的**门面** `AgentRuntimeService`（`application/services.py`）+ `close_session` / `get_session` 用例**一起删** ✓（copilot 已有同名能力 —— 留着就是第二套 ✗）；④ 「drain 到完成」收敛到契约层的 `session/completion.py`（子代理 / 评估 / 委派共用同一份 ✓）。扫描规则 `use_cases\.run_turn` / `RunTurnCompletionUseCase` / `agent_runtime\.application\.services` 启用 ✓） | Session 层（**Stage 5b 删除** ✅）；Gateway Stage 4a 切 IM 入口**同 PR** ✅ |
| X3 | `agent_sessions.graph_state`（续传状态与业务数据混装同列） | `modules/agent_runtime/adapter/persistence/models.py:56-61` | `session_events` / `session_turns` | 未开始（**替代物开始有数据**，2026-10-29：Gateway Stage 4b 连带落地了 `session_events` 的事件落库 —— 事件流真写真读了；`graph_state` 仍在写，迁移归 Session Stage 1/6。2026-10-30：Session Stage 1 补齐**旧入口打点** `record_legacy_call("X3")` —— 「没有打点就没有清理判据」） | Session 层 |
| X4 | `agent_turns` / `agent_session_messages` 表 | `migrations/versions/`（早期） | `session_turns` / `session_messages` | 未开始（**双写期已开始**，2026-10-29：Gateway Stage 4b 连带落地了 `session_turns` 的**轮次双写** —— 它是 `session_events` 的外键父行；旧表仍在写，删除归 Session Stage 6。2026-10-30：Session Stage 1 补齐**旧表写入点的打点** `record_legacy_call("X4")`（`SqlTurnRepository.add` / `SqlSessionMessageRepository.append`）—— 旧表什么时候不再被写，指标说了算。2026-10-30：Session Stage 2 落地**消息双写**（新表 `session_messages` + 旧表 `agent_session_messages` 都写）；**读仍走旧表**（切读 S-15a 要等对账窗口）。旧 ORM 改名 `LegacySessionMessageORM` —— 新旧两张表都叫「会话消息」，同名会让人以为只有一张 ✗） | Session 层（Router 决策 #2） |
| X5 | 占位图 `compile_loop_graph`（节点全是 `_passthrough_*`） | `modules/agent_runtime/adapter/graph/loop.py:63-69`、`runner.py:92` | Agent Loop 方案的真实图 | 未开始 | Agent 层（Stage 7） |
| X6 | `agent_sessions.wait_status` 列（与 `status` 表达同一状态机，取值还不一致） | ~~`modules/agent_runtime/adapter/persistence/models.py:63-67`~~（**已删**） | `current_turn_id`（互斥，台账 R3 ✅）+ `session_turns.pending_approval`（审批挂起，Session 方案 §8 ✅） | **已清理**（2026-10-30：Session Stage 3a + Stage 5a + Stage 6 —— ① 互斥职责迁到 `current_turn_id`（R3）；② 审批挂起落进 `session_turns.pending_approval`；③ 读端（会话卡片 / 任务列表的「等你确认」）改成**从轮次表推导**（一次查询，别逐会话查 ✗）；④ ORM 不再映射 + **迁移 0053 DROP 该列** ✓。扫描规则 `(\.wait_status\b|wait_status\s*=)` 启用 ✓） | Session 层（**Stage 6** ✅） |
| X7 | 审批异常吞噬 `except Exception: pass`（吞掉 `ApproverMustDiffer` / `ApprovalExpired` / `ApprovalAlreadyDecided` → 工具照常执行） | `modules/agent_runtime/src/qzdap/modules/agent_runtime/application/copilot.py:466-471` | `ErrorChunk` + 明确错误码（Session 方案 §5.6 校验清单） | **已清理**（2026-10-30：Session Stage 1 —— `except Exception: pass` 换成「记日志 + **再抛**」：审批失败（`ApproverMustDiffer` / `ApprovalExpired` / `ApprovalAlreadyDecided`）不再被吞掉，**工具不会照常执行** ✗→✓；旧打点撤除） | Session 层（**Stage 1**，比原定的 Stage 5 提前） |
| X8 | 旧上下文组装 `_load_messages`（**在跑**，消息形状正确，是新 Builder 的实现基础）—— ⚠️ 但**召回失败被静默吞掉**（`runner.py:523,549`，无 `recall_degraded`），且 `top_k`（8/6）与每条 400 字截断需一并复刻 | `modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/runner.py:495-566` | `context/builder.py`（迁入后删除原处） | 未开始 | Context 层 |
| X9 | 旧上下文压缩 `compact_messages`（纯字符截断：每条 180 字 × 20 条，无摘要模型）—— ⚠️ 但它的**工具结果清洗（截 1500 字）/ 首个 system 保留 / 摘要累加**三项行为必须复刻 | `modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/compact.py:14-50` | `context/compressor.py`（async 摘要 + 确定性降级，**降级时追加而非覆盖摘要**） | 未开始 | Context 层 |
| X10 | 四套 system prompt 模板（无记忆 / 有记忆 / 有知识 / 有记忆+知识）——分支爆炸的源头 | ~~`modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/llm/prompts.py:51-110`~~（**已删**：2026-10-30 随 X2 删除 —— 那四个函数只被 `run_turn.py` 引用 ✓，删了就成了孤儿 ✗） | `context/prompts.py` 单段式渲染 | ⚠️ **部分已清理**（旧实现已删 ✓）；Context 层的新渲染**未开始** | Context 层 |
| X11 | 旧记忆写入 `_remember`（每轮无条件写、scope 无效、autoSummarize 无实现、无幂等） | `modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/runner.py:664-694` | `memory/writer.py`（抽取 → 敏感过滤 → 去重 → 置信度） | 未开始 | Memory 层 |
| X12 | 新 runtime 的记忆写入（**逻辑反转**：从召回结果 `memory_hits` 提取事实写回 L2 → 自我强化循环） | `runtimes/agent_runtime/src/qzdap_agent_runtime/memory/layered.py`（317 行）、`graph/nodes.py:1019` | `memory/writer.py`（输入只能是本轮对话内容） | 未开始 | Memory 层 |
| X13 | `admin_memory_l1`（无 `session_id` / 无 `user_id`，只写不读，与 STM 无关） | `modules/memory/src/qzdap/modules/memory/adapter/persistence/models.py:21-33` | 退役，或改造为带 `session_id` 的 STM 缓冲（**决策 #5**：L1 处置） | 未开始 | Memory 层 |
| X14 | 记忆召回缺用户隔离（`list_l2` 与向量检索均只按 `workspace_id` 过滤 → 工作区内跨用户泄漏）。**L3 不计入**：L3 是**工作区级共享**的团队知识（决策 #1 后迁往 `modules/knowledge`），按设计对工作区内所有人可见 | `modules/memory/src/qzdap/modules/memory/adapter/persistence/repositories.py:161-165`、`adapter/persistence/vector_adapter.py:62` | 作用域过滤下推到 SQL / 向量 payload | **已修复**（2026-10-29：写入侧持久化 `owner_id` → `admin_memory_l2.user_id`（迁移 0048）+ `list_l2` 按 `user_id` 过滤 + 向量 payload 带 `user_id` 且过滤下推到 pgvector；回归测试 `modules/memory/tests/unit/test_memory_scope_isolation.py` 4 条） | Memory 层（**Stage 1**） |
| X17 | **旧路径的手写推理循环**：`runner._run_turn_inner` 的 `while True`（含 `runner.py` 里「自己拼 messages」与「自己写记忆」的分支） | `modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/runner.py:149`（调 `_load_messages` 于 `:179`、`_remember` 于 `:467`；两方法的**唯一调用点**） | `agent_loop/runner.py`（6 节点 LangGraph 图） | 未开始 | Agent 层（Stage 5 停用 → Stage 7 删，~250 行） |
| X18 | **`copilot.py` 的 turn 编排**（~600 行；claim / 幂等 / 取消 / 审批语义的**权威来源**） | `modules/agent_runtime/src/qzdap/modules/agent_runtime/application/copilot.py` | `session/turn_runner.py`（**语义迁入后删**，不是重写） | **编排已迁出**（2026-10-30：Session Stage 3b —— 编排（轮次行 / 消息 / 事件 / 终态 / 取消 / 审批挂起）**迁到契约层的 `session/turn_runner.py`** ✓；copilot 只剩「读 + 组装 + 转发」的薄壳。扫描规则收窄到旧编排的私有符号 `_fail_turn` / `_publish_chunk`（**两个都已迁走** ✓；`async def _run_turn(` 仍在 —— 那是薄壳的入口，不是旧编排 ✗）） | Session 层（**Stage 3b 删薄壳里的剩余**：清理窗口 ≥7 天且指标归零后） |
| X16 | `MemoryService` 同时提供运行时（`recall`/`write`）与管理面（`list_*/trend`）语义；管理端 `PATCH /l2/{id}` 绕过写入侧的脱敏与去重 | `modules/memory/src/qzdap/modules/memory/application/services.py`、`adapter/persistence/repositories.py:167-175` | 拆为 `MemoryRuntimeService`（平面 A）+ `MemoryAdminService`（平面 B） | 未开始 | Memory 层 |
| X15 | **L3 与 `modules/knowledge` 职责重叠 → 运行时双份注入**（L3 内容进「相关记忆」，knowledge chunks 进「相关知识」；且 L3 无向量而 chunks 有向量） | `modules/memory/.../domain/entities.py:119-188`（L3Entry）、`modules/agent_runtime/.../runner.py:517-559` | 决策 #1：L3 退役（知识统一归 knowledge）或 knowledge 降级为管道 | 未开始 | Memory 层 |
| X19 | **死表 `memory_l2_embeddings`**（迁移 0036 建，列齐全 —— 连 `user_id` / `content_hash` 都有 —— 但**零代码引用**；与生产在用的向量表 `admin_memory_vec` 职责重复） | `migrations/versions/0036_memory_l2_embeddings.py` | **DROP**（迁移 0048 内；真正的向量表是 `admin_memory_vec`，迁移 0023） | **待清理**（迁移 0048 已实现并在 dev 库执行成功；**不可逆** —— 回滚不重建该表） | Memory 层（**Stage 0**） |
| X20 | **同步 `PostgresSaver` 工厂**（`graph/builder.py` 的 `from_url`）—— 同步 saver 在**全异步**仓库里会阻塞事件循环（Session 方案 §5.3）；且**无生产调用方**（只有测试引用） | ~~runtimes/agent_runtime/src/qzdap_agent_runtime/graph/builder.py~~（**已删**） | `AsyncPostgresSaver`（`langgraph.checkpoint.postgres.aio`）—— 由 composition 的 **lifespan** 创建并持有 | **已清理**（2026-10-30：Session Stage 0 —— `from_url` 工厂删除（同步 saver 不再被 import）；`AsyncPostgresSaver` 接进 lifespan，生命周期归 composition；建表仍归**迁移 0046**（`setup()` 因此是幂等空跑）） | Session 层 |

#### X1 已核实的具体缺陷（2026-10-29 读码核对）

Agent / Execution 层方案**暂不编写**，但读码时核实到以下事实，登记在此以免丢失：

| # | 事实 | 位置 | 后果 |
|---|---|---|---|
| 1 | **新 runtime 的 `agent` 节点是 `return {}`** | `runtimes/.../graph/nodes.py:617-619` | 19 节点图能编译、单测能过，但**推理从不发生**；且新 runtime **没有 `LLMPort`** —— 「接线」实为重写 |
| 2 | **旧路径的 LangGraph 也是占位**：`compile_loop_graph(llm_node=_passthrough_llm, tools_node=_passthrough_tools)` | `modules/.../adapter/graph/loop.py:63-69`、`runner.py:92`、`runner.py:789-795` | 旧路径**真正的循环是手写 `while True`**（`runner.py:265` 起），图是**残留物**，删掉零影响 |
| 3 | **`governance` 节点硬编码 actor**：`actor_id="u-1"` | `runtimes/.../graph/nodes.py:644` | 审批申请人永远是假身份 → 「审批人 ≠ 申请人」校验必然失效；审计记的不是真实操作者 |
| 4 | **工具幂等缓存是进程内 dict**，`tool_executions` **从未被写入** | `runtimes/.../execution/executor.py` | 跨 worker / 重启后幂等失效 → **副作用工具重复执行**；执行记录、审计、成本全部无从谈起 |
| 5 | **`execute` 节点在 async 图里同步调 async 执行器**（`run_async_from_sync`） | `runtimes/.../graph/nodes.py:804` | 工具越慢并发越差（与 Context 层的 `Compactor` 同型问题） |
| 6 | **PostgresSaver 是同步版** | `runtimes/.../graph/builder.py:144` | 全异步仓库里阻塞事件循环（Session 方案 §5.3 已给结论：改 `AsyncPostgresSaver`） |
| 7 | **`remember` 节点逻辑反转**：从 `memory_hits`（召回结果）提取事实写回 L2 | `runtimes/.../graph/nodes.py:1016-1030` | **自我强化循环**：召回 → 写回 → 召回更多（= 台账 X12） |
| 8 | **`emit_result` 是 `return {}`**；`write_turn_record` / `load_checkpoint` / `compact_tool_result` 同为 `return {}` | `nodes.py:1119`、`347`、`342`、`1124` | 图的 **5** 个节点是空壳。⚠️ **`persist_result`（`nodes.py:1060`）不是空壳** —— 它有真实逻辑（用量记账 + 成本归属 + 异步评测），只是依赖没注入；初稿把它算成第 6 个空壳并把行号写成 1041（那是 `remember` 里的 `return {}`），已改正 |

> **结论**：Agent 层与其它层的形态**不同** —— 别的层是「旧实现完整、新实现未接线」，这一层是「**两套都不完整**」：旧路径循环是真的但图是残留物，新 runtime 图是真的但推理节点是空的。处置原则应是「**取旧的真逻辑 + 用新骨架重写**」，而不是「把新 runtime 接上线」。
>
> **方案已写**：[`agent-refactor-plan.md`](agent-refactor-plan.md)（2026-10-29，**已评审 v1.2**），附录 A 8 条决策（**#4 已定**）。技术栈定为 **LangGraph 1.2 + LangChain（langchain-core 1.6）+ Deep Agents**；其中 `deepagents` **未安装、不在 `uv.lock`**，需在 Stage 6 前补依赖并先验证 API。
>
> **骨架（v1.2 重排后）**：**执行轴**（每步推理：循环 → 选专家 → 执行）与**配置轴**（管理员配置 → agent 绑定 → 运行时取值）**两条正交轴**。**模型与工具在配置轴上** —— 决策 #4 取消 Model Router / Tool Router 后，⑧ 只剩「选专家」一路，模型 / 工具的**取值**归 ⑨ Execution（Agent 方案 §0.2 / §5.2.1 / §5.3.1）。

### 2.3.1 核对到的另外两处平台事实（2026-10-29，Agent 层方案的依据）

| # | 事实 | 证据 | 影响 |
|---|---|---|---|
| 1 | **工具执行器已经存在且在跑**：`modules/tool` 的 `InvokeToolUseCase` 已实现治理闸门（`policy_guard.check`）+ 三协议派发（custom / openapi / mcp）+ `tool_calls` 落库 + 事件 + 超时 | `modules/tool/.../application/use_cases/invoke_tool.py` | Execution 层**不重复造执行器**，只补幂等 / 重试 / 熔断 |
| 2 | **两张工具调用表**：唯一带幂等的 `tool_executions`（0035 建、列齐全、**零代码引用**）与在用的 `tool_calls`（`modules/tool`，无幂等字段） | `migrations/versions/0035_*.py:221-258`、`modules/tool/.../persistence/models.py:65` | `tool_executions` 作为幂等唯一权威、`tool_calls` 保留为明细，用 `tool_call_id` 关联；**不需要新迁移** |

### 2.3.2 X1 内部的平行实现（**从未接线 → 直接删**，不是「清理窗口」型）

> X1 整包太大，台账上是一条；实际落地时要拆成三块看。**这三块从未在生产跑过，所以没有「接管 → 等待 → 删除」的窗口 —— 它们要么被真实实现取代，要么直接删掉。**
>
> **它们是「建而不切」最危险的部分** —— 长得像「已经建好的新实现」，下一个人看到「`InMemoryToolExecutor` 已经写好了」就可能直接接线。

| # | 平行实现 | 生产里的唯一实现 | 语义落地于 | **删除** |
|---|---|---|---|---|
| **X1-a** | `result/events.py` 的 **16 种 `*Event`** | `libs/schema/src/qzdap_schema/dtos/turn.py` 的 **17 种 `TurnChunk`**（前端 SSE 契约在这；`*Event` 还**少了 `InteractiveActionEvent`**） | Gateway Stage 4a（出站编码） | **Agent Stage 7** |
| **X1-b** | **16 个 `InMemory*` 假实现** | 各对应的真实实现（DB / `modules/governance` / `modules/tool` / `modules/memory`） | 逐条见 [`implementation-plan.md`](implementation-plan.md) §1.5 的表 | **Agent Stage 7** |

> **X17 / X18 / X5 的区别**（三者都属「旧路径」，但处置方式不同）：
>
> | 条目 | 是什么 | 处置 |
> |---|---|---|
> | **X18** | `copilot.py` 的 turn 编排 —— **语义是对的**（claim / 幂等 / 取消 / 审批都在这） | **语义迁入** `session/turn_runner.py` 后删。**不是重写**。⚠️ **删除落在 Session Stage 3b**（切换后 ≥7 天清理窗口 + 指标归零）—— `copilot.py` 本身保留为 HTTP 薄壳 |
> | **X17** | `runner.py` 的手写 `while True` 循环 —— **与图重复**（图是残留物） | **取旧的真逻辑 + 新骨架重写**（Agent 层）。`_run_turn_inner` 内的 `_load_messages` / `_remember` 分支必须**先接线到新实现**才能删 |
> | **X5** | `compile_loop_graph`（占位图，全是 `_passthrough_*`） | **从未被走过**，直接删，零影响 |
>
> **X1-b 为什么不是「保留作测试替身」**：测试替身应该放在 `tests/` 下（这个仓库里 `modules/*/tests/` 确实有各自的 `_in_memory.py`）。放在**生产包**里、且与真实实现同名同接口，是「建而不切」的温床。**保留的是语义，不是那份假实现。**
>
> **守卫**：CI 加一条「生产包里不得存在 `InMemory*` 类」，**在全局前置阶段就启用**（拦住新增），而不是等 Agent Stage 7 清理时才建。

### 2.4 需要「启用」而非「清理」的资产（跟踪用，防止被误删）

| 资产 | 位置 | 状态 |
|---|---|---|
| `session_inbox` 表 | 迁移 0035 | 待启用（Gateway Stage 1）+ 改造（加列改约束） |
| `session_turns` / `session_messages` / `session_events` | 迁移 0035 | 待启用（Session 层） |
| `tool_executions` / `outbox_dead_letters` | 迁移 0035 | 待启用（Agent Loop / Execution 层） |
| `agent_sessions.channel_session_key` | 迁移 0035 | 待启用（Router Stage 2）+ 加唯一索引 |
| `agent_sessions.current_revision` | 迁移 0035 | 待启用（Session 层乐观并发；旧路径从不使用） |
| `agent_sessions.next_ingress_seq` | 待新增（迁移 0045） | Router Stage 3 |
| `admin_agents.visible_scope` / `category` / `tags` / `profile` | 现有 | **已在用**（作为 Strategy 的策略依据，不新建策略表） |

---

## 3. 防回归机制

### 3.1 扫描脚本（进 CI）

> ✅ **已落地（2026-10-29，Gateway Stage 5）** —— `backend/scripts/check_no_legacy_impl.sh`
> （本节的可执行形态 ✓）＋ `.github/workflows/backend.yml` 的 `legacy-scan` job。
> 用法：`bash scripts/check_no_legacy_impl.sh`（已启用的规则）/ `--stage G`（按段）/
> `--self-test`（自检）。
>
> ⚠️ **实施时对规则表做的两处收窄**（本节已同步，偏差 G-41 / G-42）：
> ① **规则表加了「状态」列**（`on` / `off`）—— G9 属于 Gateway 段但**旧实现还在场**
> （被 Session 阻塞），按段启用会让 CI 永远红；**「没启用」必须可见**（脚本报告
> 「启用 N 条 / 跳过 M 条」）。
> ② **分隔符从 `|` 换成 `;`** —— pattern 里可能有 ERE 分支（`SYSTEM_USER_ID|SYSTEM_AGENT_ID`），
> 用 `|` 分隔会把一条规则拆成多列，**「规则没生效」被误读成「扫描通过」**。
> ③ **G7/G8 的规则收窄**成「路由声明的形状」（`@router\.(get|post|put|delete|patch)\("/v1/sessions`）
> —— 宽泛的 `/v1/sessions` 会命中「文档里提到旧路径」的说明文字（那不是活引用 ✓）。

```bash
# scripts/check_no_legacy_impl.sh —— 命中即失败
#
# ⚠️ 必须排除 tests/：单测会引用被删的符号（如 test_channel_dispatch.py 引用
#    SYSTEM_USER_ID / ChannelMessageReceived，_in_memory.py 引用 record_request_id），
#    不排除则脚本永远红、必然被绕过。
#
# ⚠️ 一律用 grep -E（ERE）：macOS 自带的 BSD grep 在 BRE 下**不支持** `\|` 分支，
#    而 GNU grep 支持 —— 同一个脚本在开发机与 CI 上行为不一致，比没有脚本更危险。
#    因此下面所有 pattern 都写成 ERE 语法（`|` 分支、`.` 按正则元字符处理）。
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/backend"

# ⚠️ **注释行不算命中** —— 清理记录本身要写明「旧的 X 已删除」，那正是
#    注释里的 `X` 在。如果注释也算命中，这条规则永远红，必然被绕过
#    （「绕过一条永远红的检查」比「没有检查」更危险）。活引用一定在代码里。
_scan() {  # $1=ERE pattern  $2=目录  $3=编号
  local hits
  hits="$(grep -rEn --include='*.py' -- "$1" "$2" 2>/dev/null | grep -v '/tests/' | grep -Ev ':[0-9]+:[[:space:]]*#' || true)"
  if [ -n "$hits" ]; then
    echo "✗ $3 未清理：$1"
    echo "$hits"
    exit 1
  fi
}

# Gateway 域
_scan "recent_request_ids"        modules/          "G1"
_scan "record_request_id"         modules/          "G1"
_scan "class ParsedMessage"       modules/          "G4"
_scan "ChannelMessageReceived"    modules/          "G5"
_scan "SYSTEM_USER_ID|SYSTEM_AGENT_ID" modules/      "G3"
_scan "_verify_signature"          modules/channel/  "G2"
_scan "OrderedDict"               modules/channel/  "G6"
_scan '@router\.(get|post|put|delete|patch)\("/v1/sessions'  modules/  "G7/G8"
_scan "dispatch\.dispatch_subscriber"  modules/       "G9"   # 只盯**导入路径** —— 文档里提到旧文件名不算残留 ✓

# Gateway 域 · G12（错误码收敛）—— 码不许再以**字面量**出现，只能引用
#   `ErrorCode.X.value`。⚠️ 三个目录各一条（脚本一次只扫一个目录）。
_scan '(code|reason_code|error_code)\s*=\s*"(CHANNEL_NOT_FOUND|CHANNEL_DISABLED|INBOUND_ADAPTER_MISSING|OUTBOUND_ADAPTER_MISSING|WEBHOOK_SIGNATURE_INVALID|WEBHOOK_TIMESTAMP_SKEW|DUPLICATE_REQUEST|TENANT_DENIED|CHANNEL_SERVICE_ACCOUNT_MISSING|CHANNEL_DELIVERY_FAILED|IDENTITY_REJECTED|IDENTITY_CREDENTIALS_MISSING|TOKEN_INVALID|TOKEN_EXPIRED|SERVICE_ACCOUNT_NOT_CONFIGURED)"' modules/ "G12"
_scan '(code|reason_code|error_code)\s*=\s*"(CHANNEL_NOT_FOUND|CHANNEL_DISABLED|INBOUND_ADAPTER_MISSING|OUTBOUND_ADAPTER_MISSING|WEBHOOK_SIGNATURE_INVALID|WEBHOOK_TIMESTAMP_SKEW|DUPLICATE_REQUEST|TENANT_DENIED|CHANNEL_SERVICE_ACCOUNT_MISSING|CHANNEL_DELIVERY_FAILED|IDENTITY_REJECTED|IDENTITY_CREDENTIALS_MISSING|TOKEN_INVALID|TOKEN_EXPIRED|SERVICE_ACCOUNT_NOT_CONFIGURED)"' libs/    "G12"
_scan '(code|reason_code|error_code)\s*=\s*"(CHANNEL_NOT_FOUND|CHANNEL_DISABLED|INBOUND_ADAPTER_MISSING|OUTBOUND_ADAPTER_MISSING|WEBHOOK_SIGNATURE_INVALID|WEBHOOK_TIMESTAMP_SKEW|DUPLICATE_REQUEST|TENANT_DENIED|CHANNEL_SERVICE_ACCOUNT_MISSING|CHANNEL_DELIVERY_FAILED|IDENTITY_REJECTED|IDENTITY_CREDENTIALS_MISSING|TOKEN_INVALID|TOKEN_EXPIRED|SERVICE_ACCOUNT_NOT_CONFIGURED)"' runtimes/ "G12"

# Router 域
#   R2 的规则绑**旧入口的打点**（`record_legacy_call("R2")`）—— 打点是旧实现
#   在场的唯一事实来源（§3.2），旧实现删掉就打点一起撤除。
_scan 'record_legacy_call\("R2"\)'  modules/          "R2"
_scan "build_session_key"         runtimes/        "R4"

# 跨层
_scan "RunTurnCompletionUseCase"        modules/   "X2"
_scan "use_cases\.run_turn"              modules/   "X2"   # 只盯**导入路径** ✓
_scan "agent_runtime\.application\.services"  modules/  "X2"   # 旧门面（copilot 之后已无第二个）✓
_scan "agent_runtime\.adapter\.llm\.prompts"  modules/  "X10"  # 随 X2 变孤儿的那四个模板 ✓
_scan "(\.wait_status\b|wait_status\s*=)"  modules/  "X6"   # 只盯**引用/赋值** —— 文档里提到那列名不算残留 ✓
_scan "try_claim"                 modules/          "R3"

# Session 域（X2 / X3 / X4）
_scan "graph_state"               modules/          "X3"
_scan "agent_turns"               modules/          "X4"
_scan "agent_session_messages"    modules/          "X4"

# Session 域 · X20（同步 PostgresSaver）—— 同步 saver 在全异步仓库里会阻塞
#   事件循环（Session 方案 §5.3）；只允许 `langgraph.checkpoint.postgres.aio`。
_scan "def from_url\(url: str\)"  runtimes/         "X20"
_scan 'from langgraph\.checkpoint\.postgres import'  runtimes/    "X20"
_scan 'from langgraph\.checkpoint\.postgres import'  modules/     "X20"
_scan 'from langgraph\.checkpoint\.postgres import'  composition/ "X20"

# Session 域 · X18（copilot.py 的旧 turn 编排）
#   ⚠️ 只绑旧编排的私有符号 —— copilot.py 保留为 HTTP 薄壳，
#      stream_turn / decide_approval 在薄壳里仍会出现，不能作为扫描目标。
_scan "_fail_turn"               modules/          "X18"
_scan "_publish_chunk"           modules/          "X18"

# Context 域（X8 / X9 / X10）
_scan "compact.py"                modules/          "X9"
_scan "_load_messages"            modules/          "X8"
_scan "build_system_prompt"       modules/          "X10"

# Memory 域（X11 / X12 / X13 / X15 / X16）
_scan "layered.py"                modules/          "X12"
_scan "_remember"                 modules/          "X11"
_scan "admin_memory_l1"           modules/          "X13"
_scan "admin_memory_l3"           modules/          "X15"
_scan "class MemoryService"       modules/          "X16"
_scan "memory_l2_embeddings"     migrations/       "X19"

# Agent / Execution 域（X5 + X1）
_scan "compile_loop_graph"        modules/          "X5"
_scan "_run_turn_inner"           modules/          "X17"
_scan "from ...chat_model import ToolCallAccumulator"  modules/  "X5"   # 只盯旧位置的 import，不盯类名本身（它是**被迁入**的资产）
_scan "graph/nodes.py"            runtimes/         "X1"
_scan "build_session_graph"       runtimes/         "X1"
_scan "InMemoryToolExecutor"      runtimes/         "X1"
```

> **扫描规则必须逐条绑定到具体符号**（见上面的注意事项）。`graph_state` / `_remember` 这类**常见词**风险较高：`graph_state` 在 `agent_sessions` 上是**列名**，若业务代码里仍有 `state.graph_state` 之类的合法引用会误报。实施时按实际残留收窄到**具体的类名 / 方法名 / 表名**，并把收窄后的最终规则**回写本节**（本节是脚本的唯一来源，不允许各方案各写一份）。

> **注意 `OrderedDict` 这条**：`dispatch_subscriber` 的 LRU 去重删掉后，`modules/channel/` 下不应再有 `OrderedDict`；但若其它无害用途引入它，这条会误报 —— 因此扫描规则应**逐条绑定到具体符号**而不是宽泛的类型名。实施时按实际残留收窄。

> **脚本在**对应层的清理 Stage 合并时**启用**，不是一开始就开 —— 否则旧实现还在时 CI 一直红。**启用与旧条目的删除在同一个提交里完成。**
>
> ### 3.1.2 静态扫描的补充：单实现守卫
>
> 本节的 grep 脚本查的是「**某个旧符号还在不在**」—— 它能回答「删干净了吗」，但答不了「**有没有两套同时存在**」。
>
> 后者由一条 pytest 守卫负责：[`implementation-plan.md`](implementation-plan.md) §6.2 的 `test_single_implementation.py`，数据源是该文档 §1.2 的「关注点 → 唯一实现 → 旧实现 → 归属层 · Stage」表（**29 条**）。
>
> | 守卫 | 查什么 | 何时进 CI |
> |---|---|---|
> | 本节的 grep 脚本 | 旧符号是否残留 | 对应层的清理 Stage |
> | `test_single_implementation.py` | 同一关注点的新旧实现**是否同时存在** + 生产包是否存在 `InMemory*` | **全局前置阶段就进**（当前应全绿 —— 旧代码还在，但新的也还没接管） |
>
> **两条守卫互补**：grep 说「旧的删了没」，pytest 说「新的接管了没」。**只有两条都绿，才满足台账的「已清理」判据。**

#### 3.1.1 脚本的启用方式与自检

**启用方式**：脚本里的每条规则**逐条挂到对应的 Stage 5**。本节是规则的**唯一来源**，各层方案不得另写一份。

```bash
# 只跑已启用的规则（按阶段逐步放开）
bash scripts/check_no_legacy_impl.sh            # 全量（最终态）
bash scripts/check_no_legacy_impl.sh --stage G  # 只跑 Gateway 段
```

**自检（脚本改动后必跑）**：

```bash
# 在一个「已清理」的样例目录上跑，应全部通过
bash scripts/check_no_legacy_impl.sh --self-test
```

**三条纪律**：

| # | 纪律 | 理由 |
|---|---|---|
| 1 | **规则必须绑定到具体符号**，不许用宽泛的类型名 | `OrderedDict` 这类词会在无关地方出现 → 误报 → 脚本被加豁免 → 失去意义 |
| 2 | **pattern 一律写 ERE**，用 `grep -E` | macOS BSD grep 与 GNU grep 在 BRE 下行为不一致 |
| 3 | **新增旧实现时，同一个 PR 里加规则** | 否则旧实现被删了但规则没跟上，下一个人又写回来 |

> **为什么必须有这个脚本**：台账的「已清理」判据是**指标归零**（运行时事实），但**代码里彻底没人提**这件事只能靠静态扫描确认。两者互补：指标说「没人调用了」，扫描说「连字样都没了」。

### 3.2 指标看板（**当前不存在，必须先建**）

```
qzdap_legacy_calls_total{entry="<台账编号>"}   # 旧实现调用次数，按台账编号标注
```

清理判定的唯一依据是**该指标归零**，不接受「代码看起来没人用了」。

> ✅ **2026-10-29 已落地**：指标与 `record_legacy_call(entry)` 已写进 `libs/observability/src/qzdap_observability/metrics.py`（并有单测）。**收敛机制不再是空的。**
>
> ⚠️ **但「指标存在」≠「判据可用」** —— **旧入口还没打点**。本台账每一条目的「指标归零」判据仍需要一个**打点**才能判定（没打点的条目，指标恒为 0，看起来像「已清零」，实则从未被观测 —— **这是比没有指标更危险的状态**）。
>
> **因此：本台账的每一条目，其所属方案的 Stage 0 必须包含「给该旧入口打点」这一步**，否则该条目不得进入 Stage N（接管）之后的任何阶段。

**指标定义（照抄现有 metrics.py 的写法）**：

```python
# backend/libs/observability/src/qzdap_observability/metrics.py
LEGACY_CALLS_TOTAL = Counter(
    "qzdap_legacy_calls_total",
    "Calls into legacy implementations pending cleanup",
    labelnames=("entry",),          # 取台账编号，如 "G1" / "R3" / "X7"
    registry=metrics_registry,
)

def record_legacy_call(entry: str) -> None:
    LEGACY_CALLS_TOTAL.labels(entry=entry).inc()
```

`metrics_registry` 与 `/metrics` 暴露端点**已存在**（`libs/observability/src/qzdap_observability/metrics.py:16`），现有指标有 `qzdap_http_requests_total` / `qzdap_sse_first_chunk_seconds` / `qzdap_llm_tokens_total` / `qzdap_llm_cost_usd_total` / `qzdap_active_turns` —— 新指标与它们同源同风格，无需新增基础设施。

**打点位置**：旧实现的**入口处**（不是内部），保证「旧实现被调用」与「旧实现被调用但走的是别的分支」都能被观测到。

**打点覆盖（2026-10-30 更新，Session Stage 5b 后）**：**36 条**中 **16 条在旧实现的入口处打点** ——
本轮新增 **R3**（`try_claim` 的互斥职责）与 **X4**（旧表写入点 —— 双写期结束与否由指标说了算），
**撤除 X7 / G9 / X2 / R1**（旧实现已删 → 打点随代码一起撤除）——
`record_legacy_call("<编号>")` 落在**入口**（不是内部），保证「旧实现被调用」与
「旧实现被调用但走了别的分支」都能被观测到。

**未打点的条目 —— 全部是「打点不适用」的类型，不是遗漏**：

| 条目 | 为什么不打点 |
|---|---|
| **R4** `build_session_key` | **已删除**（2026-10-29 Router Stage 2）—— 原先在**从未接线**的 `backend/runtimes/agent_runtime/` 里、无生产调用方，打点会得到恒为 0 的指标（见 §3.2 开头）→ 按 Gateway 附录 C.8 的 **G-38 口径**（引用关系可证即当场删）直接清理 ✓ |
| **X1** 未接线的 runtime 整包 | 同上 |
| **X12** 新 runtime 的记忆写入 | 同上 |
| ~~**X4** 旧表 `agent_turns` / `agent_session_messages`~~ | **2026-10-30 起已有打点**（旧表的**写入点**：`SqlTurnRepository.add` / `SqlSessionMessageRepository.append`）—— 判据从「grep 命中数」升级为「**指标归零 = 旧表不再被写**」；扫描（§3.1）作为第二道保险 |
| **X13** `admin_memory_l1` | 数据类（同上） |
| **X19** 死表 `memory_l2_embeddings` | 数据类；已在迁移 0048 内 DROP |
| **X14** 跨用户泄漏 | **修复类** —— 判据是回归测试（`modules/memory/tests/unit/test_memory_scope_isolation.py`），不进指标 |
| **G1** `record_request_id` | **旧实现已删除**（2026-10-29 Gateway Stage 1）—— 打点随代码一起撤除 |
| **G2** IM 验签分支 | **旧实现已删除**（2026-10-29 Gateway Stage 2，验签迁到 `gateway/identity.py`）—— 打点随代码一起撤除 |
| **G3** 硬编码系统身份 | **旧实现已删除**（2026-10-29 Gateway Stage 2，改为渠道登记的服务账号）—— 打点随代码一起撤除 |
| **G4** `ParsedMessage` 数据类 | **旧实现已删除**（2026-10-29 Gateway Stage 3，由 `InboundMessage` 取代）—— 打点随代码一起撤除 |
| **G5** `ChannelMessageReceived` 事件 | **旧实现已删除**（2026-10-29 Gateway Stage 3，由 `InboundMessage` 取代）—— 打点随代码一起撤除 |
| **G6** IM 进程内 LRU 去重 | **旧实现已删除**（2026-10-29 Gateway Stage 3，由 `session_inbox` 原子 claim 取代）—— 打点随代码一起撤除 |
| **G9** `dispatch_subscriber.py` | **旧实现已删除**（2026-10-30 Session Stage 5b）—— 打点随代码一起撤除 ✓ |
| **X2** 第二套 turn 实现 | **旧实现已删除**（2026-10-30 Session Stage 5b）—— 打点随代码一起撤除 ✓ |
| **R1** IM 临时会话 | **旧实现已删除**（2026-10-30 Session Stage 5b，会话改成按 `channel_session_key` 粘住）—— 打点随代码一起撤除 ✓ |
| **G10** 审批恢复路径丢幂等键 | **修复类** —— 判据是回归测试（`modules/agent_runtime/tests/unit/test_copilot_resilience.py::test_double_clicking_approve_executes_the_tool_only_once`），不进指标 |
| **G11** 重复请求的 202 降级路径 | **旧实现已删除**（2026-10-29 Gateway Stage 4b，由「重放上一轮的事件流」取代）—— 打点随代码一起撤除 |
| **R2** `agentId` 直取 | **旧实现已删除**（2026-10-29 Router Stage 1，改为策略链的「显式指定」规则）—— 打点随代码一起撤除 |
| **X7** 审批异常吞噬 | **旧实现已删除**（2026-10-30 Session Stage 1，改为「记日志 + 再抛」）—— 打点随代码一起撤除 |
| **X20** 同步 `PostgresSaver` 工厂 | **旧实现已删除**（2026-10-30 Session Stage 0）—— 打点随代码一起撤除 |
| **R3** `try_claim` 的会话互斥职责 | **旧实现已删除**（2026-10-30 Session Stage 3a）—— 执行权迁到 `current_turn_id` + 轮次状态推导，打点随代码一起撤除 |
| **X18** `copilot.py` 的 turn 编排 | **编排已迁出**（2026-10-30 Session Stage 3b）—— 编排迁到契约层的 `session/turn_runner.py`，旧编排的私有符号（`_fail_turn` / `_publish_chunk`）都已消失，打点一并撤除；**薄壳的删除**落在 Stage 3b（清理窗口 ≥7 天） |

> **下表这 18 条**必须改用替代判据（扫描 / 测试 / 删除 / 「无生产调用方」），
> **不得**用「指标为 0」判清零。
> **修复完成后继续保留打点，会让指标永远非零、清理判据永远不成立** —— 打点是清理前的
> 观测手段，不是终态。

**无法用调用次数度量的条目**（如纯数据类、旧表、旧常量）：

| 类型 | 判据 | 替代方案 |
|---|---|---|
| 纯数据类（旧表、旧字段） | **grep 命中数归零** | CI 扫描脚本（§3.1）即为判据 |
| 旧常量 / 旧函数 | grep 命中数归零 | 同上 |
| 只在启动/定时任务里跑的旧路径 | 调用次数 | **额外打点**：在 sweeper / worker 的入口打点，值为每日执行次数；判据是「连续 N 天为 0」而非「瞬时为 0」 |

> 「瞬时为 0」对定时任务是**假阴性**（凌晨两点查都是 0）—— 判据必须是**一段时间内持续为 0**。

### 3.3 「发布周期」的定义（**当前项目无法定义，必须先定义**）

台账多处引用「稳定运行 ≥ 1 个发布周期」。但 2026-10-29 核对发现：

| 证据 | 结论 |
|---|---|
| `git tag` 无任何标签 | **没有发布单元** |
| 无 `CHANGELOG` | 无发布记录 |
| 根 `pyproject.toml` version 恒为 `0.1.0` | 无版本递增 |
| `Makefile` 只有 `qzdap-up/down/status/logs/clean` | **无 release / deploy 目标** |
| `deploy/` 只有 `run-staging.sh` + `PRODUCTION.md` | 无发布节奏约定 |
| 提交节奏约每周 100–130 次 | 有活跃度，无发布边界 |

> **结论：「发布周期」在本项目目前不可定义** —— 「等一个发布周期」可以被解释成「随时」，这个门禁形同虚设，正是 2026-10-15 那次「8 个 Stage 全打勾但从未接线」得以发生的制度缺口。

**因此本台账改用可判定的量化条件，不依赖「发布周期」这个概念**：

| 条件 | 判据 |
|---|---|
| **时间窗口** | 新实现接管后**连续运行 ≥ 7 天** |
| **流量门槛** | 窗口内新实现的请求量 **≥ 该入口 7 天平均流量的 95%**（排除「本来就没流量」的入口） |
| **归零判据** | 该旧路径的 `qzdap_legacy_calls_total{entry="<编号>"}` 在窗口内**累计为 0**；定时任务类用 `qzdap_legacy_last_call_timestamp_seconds` 判断「最后一次调用早于窗口起点」 |
| **无回退需求** | 窗口内无「因该旧路径导致的生产事故」 |

> **若将来引入真正的发布流程**（tag / CHANGELOG / release 目标），本节可替换为「≥ 1 个发布周期」，但**必须先定义发布单元**，否则门禁无效。

### 3.4 「切换中（需原子发布）」状态

部分清理动作**无法「先上新后清旧」** —— 必须一次切，否则中间态不可用。台账状态机因此新增一态：

| 状态 | 含义 | 进入条件 | 退出条件 |
|---|---|---|---|
| **切换中** | 新旧两套**同时在跑**，且必须一起发布 | 该条目被判定为「必须原子切换」 | 切换完成、进入「已弃用」或「已清理」 |

**必须原子切换的条目（2026-10-29 核对）**：

| 条目 | 为什么不能分两步 | 原子动作 |
|---|---|---|
| X2 第二套 turn 实现 | IM 渠道当前走 `dispatch_subscriber → run_turn_to_completion`；停用 turn 实现与停用渠道入口必须同 PR，否则 IM 断 | ✅ **已达成**（2026-10-30：Session Stage 5b —— 切入口与删实现**同一个 PR** ✓，IM 未断 ✓） |
| G5 `ChannelMessageReceived` | `services.py:240` 发布、`dispatch_subscriber.py:98` 消费，发布端与消费端必须同时换 | 同 PR |
| X3 `graph_state` 停写 | 同一份续传状态的读写两端 | 停写与切读同 PR |
| X6 `wait_status` 列 | 列被 repositories 写、copilot 读 | ✅ **已清理**（2026-10-30：停写 + 读端改从轮次表推导 + 迁移 0053 DROP）—— 「先停写后删列」的两步**在本轮一起做完**（中间没有跨 Stage 的依赖 ✗） |
| R1 `channel_session_key` 唯一索引 | 加索引前必须先清理历史重复值，否则 DDL 失败 | 清理 → 加索引 → 加约束，三步各自独立 PR |
| X4 旧表 DROP | 物理不可逆，无并存期 | 全量对账 + 只读窗口后再 DROP |
| `session_turns` 写入切换 | 新表零生产数据，历史全在旧表 | 双写期 → 对账 → 切读 → 停旧写 → DROP |

> **唯一 owner 规则**：同一个旧实现只能由**一个方案**负责删除。上表 X2 由 **Session 层**为唯一 owner，Gateway / Router 方案只做「配合停用」，不得单独提 PR 删除 —— 否则三个 PR 互相冲突。

### 3.5 阶段门禁

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
2. 处于「切换中」的条目，**必须与其配套改动在同一个 PR 内**提交，且 PR 描述里写明「本 PR 同时完成 X 的原子切换」；
3. 每次删除旧实现的 PR，必须：
   - 把台账状态改为「已清理」；
   - 启用对应的扫描脚本规则；
4. 台账与代码不一致时，**以代码为准**并立即修正台账——台账失真比没有台账更危险。

---

## 5. 汇总

### 5.1 按状态统计

| 状态 | 条目数 | 说明 |
|---|---|---|
| 未开始 | 19 | 旧实现仍是唯一生效路径 |
| 已弃用 | 2 | **G9**（`dispatch_subscriber.py`）、**X2**（第二套 turn 实现）—— 均已加弃用标记 + 调用打点（Gateway Stage 4a）。⚠️ **G9 / X2 的打点仍会有流量**（IM 仍走它们），Stage 5 的清零判据在切完之前不可能满足 |
| 待清理 | 1 | X19（死表 `memory_l2_embeddings`，迁移 0048 已实现并在 dev 库执行） |
| 已清理 | 12 | **R4**（`build_session_key` 冒号拼接版 —— Router Stage 2 换成哈希版 `router/session_key.py`；⚠️ 扫描规则的目录原本写错、从来没生效过，已改正并启用）、**G12**（各模块的自由字符串错误码 —— Gateway Stage 0 · G-02b 收敛进 `ErrorCode` 枚举 + 投影表）、**R2**（`agentId` 直取 —— Router Stage 1 改为规则链的「显式指定」规则）、**G7**（`/v1/sessions*` 的 turn 部分 + 整套 CRUD 别名 —— Gateway Stage 5 整段删除，P-11 确认无仓外消费者）、**G8**（`GET /v1/sessions` 列表别名 —— 同上）、**G11**（重复请求的 **202 降级路径** —— Gateway Stage 4b 删除，由「重放上一轮的事件流」取代）、**G1**（`record_request_id` + `recent_request_ids` —— Gateway Stage 1 直接删除）、**G2**（渠道内的 `_verify_signature` —— Gateway Stage 2 迁到 `gateway/identity.py`）、**G3**（硬编码 `SYSTEM_USER_ID` / `SYSTEM_AGENT_ID` —— Gateway Stage 2 改为渠道登记的服务账号）、**G4**（`ParsedMessage` 数据类 —— Gateway Stage 3 由 `InboundMessage` 取代）、**G5**（`ChannelMessageReceived` 事件 —— Gateway Stage 3 由 `InboundMessage` 取代，连带修掉「按 dotted topic 订阅」与「`to_payload` 从未被调用」两个真实缺陷）、**G6**（IM 进程内 LRU 去重 —— Gateway Stage 3 由 `session_inbox` 原子 claim 取代） |
| **已修复** | 2 | X14（跨用户泄漏）、**G10**（审批恢复路径丢幂等键）—— 判据是测试不是指标 |

> **条目数**：36 条（2026-10-29 新增 **G12** = 错误码收敛）。
> **打点覆盖率**：36 条中 **18 条已打点**，其余 18 条走替代判据（见 §3.2 的「打点覆盖」表）。
> ⚠️ **G7 / G8 / R2 的打点随旧实现一起撤除**（2026-10-29 Gateway Stage 5 / Router Stage 1）—— 打点是清理**前**的观测手段，不是终态。
> **指标本身**（`qzdap_legacy_calls_total` + `record_legacy_call`）已在
> `libs/observability/src/qzdap_observability/metrics.py` 落地并有单测。

### 5.2 按归属方案统计

| 方案 | 条目 | 编号 |
|---|---|---|
| Gateway | 12 | G1–G12（G7 / G8 / **G12** 已清理；**G9 未接管** —— 等 Session Stage 5b 的原子切换） |
| Router | 4 | R1–R4（**R2 / R4 已清理** —— Router Stage 1 / Stage 2；R1 待 Stage 2；R3 的 owner 是 Session） |
| Session（跨层） | 6 | X2、X3、X4、X6、X7、X18 |
| Context（跨层） | 3 | X8、X9、X10 |
| Memory（跨层） | 7 | X11、X12、X13、X14、X15、X16、X19 |
| Agent Loop（跨层） | 2 | X5、X17 |
| 全部层共同 | 1 | **X1（未接线的 `backend/runtimes/agent_runtime/` 整包）** |

### 5.3 最高风险项：X1

`backend/runtimes/agent_runtime/`（19 节点 LangGraph + 全部 InMemory 假实现）**建于 2026-10-15，从未被 composition 根接线**，全包除 `langgraph` / `langchain_core` / `pydantic` 外零外部 import——物理上无法连数据库、LLM、工具服务。

它同时是**诱惑**和**陷阱**：

- **诱惑**：文件名、目录名、方案章节号都对应 v3.1，看起来像是「已经建好的新实现」，容易被当成现成基础直接接线；
- **陷阱**：它的 `agent` 节点是 `return {}`、**没有 LLMPort**，即使把 outbox 与 checkpointer 全接上也跑不出一次正常的工具调用。直接接线会得到一个「能启动但不干活」的运行时。

> **处置原则**：`runtimes/agent_runtime/` 里的部件**按需取用**（`result/events.py` 的事件类型、`outbox/` 的死信状态机、`result/sink.py` 的重放语义、`channels/gateway.py` 的 DTO 形状、`governance/approval.py` 的 TTL 与幂等校验、`graph/routing.py` 的分类器、`tools/registry.py` 的 LangChain `BaseTool` 适配），**不整体接线**。整体接线的路径已被证伪一次，不再尝试第二次。
>
> **具体到 Agent 层**（见 [`agent-refactor-plan.md`](agent-refactor-plan.md) §2.3）：19 节点图**收敛为 6 节点**（`reason → governance → execute → observe → evaluate`），其中 `agent` / `execute` / `governance` 三个节点的逻辑迁入新目录，其余 13 个节点**按归属层删除**（Context / Session / Memory / Gateway 的职责不该塞在 Agent Loop 的图里）。**19 节点图的骨架不保留，但也不整体丢弃** —— 这正是「按需取用」与「整体接线」的区别。

### 5.4 台账与方案文档的对应

| 台账条目 | 出现在 | 删除阶段 |
|---|---|---|
| G1 | `gateway-refactor-plan.md` §9.2、Stage 1 | Gateway Stage 1（直接删，无调用方）—— ✅ **已执行**（2026-10-29） |
| G2 | `gateway-refactor-plan.md` §9.2、Stage 2 | Gateway Stage 2 —— ✅ **已执行**（2026-10-29） |
| G3 | `gateway-refactor-plan.md` §9.2；`router-refactor-plan.md` §7.2 | Gateway Stage 2 —— ✅ **已执行**（2026-10-29；Router Stage 2 的「按渠道解析会话」部分仍未做） |
| G4、G5、G6 | `gateway-refactor-plan.md` §9.2、Stage 3 | Gateway Stage 3 —— ✅ **已执行**（2026-10-29） |
| G7、G8、G9 | `gateway-refactor-plan.md` §9.4、Stage 4 | Gateway Stage 5 —— G7 / G8 ✅ **已执行**（2026-10-29）；**G9 未接管**（等 Session Stage 5b 的原子切换） |
| G11 | `gateway-refactor-plan.md` §4.5、§10 Stage 4b | Gateway Stage 4b —— ✅ **已执行**（2026-10-29：202 降级路径删除，改重放事件流） |
| G7、G8 | `gateway-refactor-plan.md` §9.4、§10 Stage 5 | Gateway Stage 5 —— ✅ **已执行**（2026-10-29：整个 `/v1/sessions*` 删除） |
| R1 | `router-refactor-plan.md` §7.2、§7.4 | Router Stage 2（**行为替换**；文件删除归 Gateway G9） |
| R2 | `router-refactor-plan.md` §7.2 | Router **Stage 1**（`agentId` 直取 → 策略链）—— ✅ **已执行**（2026-10-29：直取删除，改为「显式指定」规则；扫描规则 `record_legacy_call("R2")` 启用） |
| R3 | `router-refactor-plan.md` §7.4 | ⚠️ **owner 是 Session**（`try_claim` 的**互斥**职责 → `session_turns.status` 的 CAS；**它没有顺序职责**，旧路径从未有过序号机制 —— Router 的 FIFO 是全新建） |
| R4 | `router-refactor-plan.md` §7.4 | Router Stage 5（删 `build_session_key`）—— ✅ **已执行**（2026-10-29：删旧函数 + 换成 `router/session_key.py` 的哈希版；扫描规则目录改正并启用） |
| X2 | `gateway-refactor-plan.md` §9.4（配合）；`session-refactor-plan.md` §8 | Session Stage 3（停用）→ **Stage 5b（删除，与 Gateway 的 IM 入口切换同 PR）** |
| X3、X6 | `session-refactor-plan.md` §7.3、§8 | Session Stage 6 |
| X4 | `session-refactor-plan.md` §7.1；Router 决策 #2 | Session Stage 6 |
| X7 | `session-refactor-plan.md` §5.6 | Session **Stage 1** —— ✅ **已执行**（2026-10-30：吞异常改成「记日志 + 再抛」，旧打点撤除） |
| X20 | `session-refactor-plan.md` §5.3、§10 Stage 0 | Session **Stage 0** —— ✅ **已执行**（2026-10-30：同步 saver 工厂删除，`AsyncPostgresSaver` 接进 lifespan） |
| X18 | `session-refactor-plan.md` §8.2、§8.4、§9 Stage 3b | Session Stage 3（**切 web/api 入口 · 只停用**）→ **Stage 3b（删除：清理窗口 ≥7 天且指标归零后）** |
| X8 | `context-refactor-plan.md` §8.2 | **Context Stage 4**（停用，前置 = Agent A-26）→ Stage 5（删除） |
| X9 | `context-refactor-plan.md` §8.2 | **Context Stage 4**（停用，前置 = Agent A-26）→ Stage 5（删除） |
| X10 | `context-refactor-plan.md` §8.2、§3.4 | **Context Stage 4**（四套模板停用 + 打点，前置 = Agent A-26）→ Stage 5（删除） |
| X11 | `memory-refactor-plan.md` §10.2 | **Agent Stage 5 的 A-26**（接线旧循环后停用）→ **Memory Stage 7**（删除）。⚠️ **不是 Memory Stage 3** —— 旧写入点在此之前一直被旧循环调用 |
| X12 | `memory-refactor-plan.md` §10.2 | Memory **Stage 7**（**从未接线 → 无停用阶段**） |
| X13 | `memory-refactor-plan.md` §5（**决策 #5**） | Memory **Stage 7** |
| X14 | `memory-refactor-plan.md` §1.2、§3.2 | Memory Stage 1（修复，非删除） |
| X15 | `memory-refactor-plan.md` §1.9、§5.3（决策 #1） | Memory Stage 7 |
| X16 | `memory-refactor-plan.md` §1.1b、§2.2（规则 3 / 6） | Memory **Stage 0（拆分服务类，已弃用）→ Stage 7（删除原 `MemoryService` 单类）** |
| X19 | `memory-refactor-plan.md` §9.1、§9.2、§10.4 | Memory **Stage 0**（迁移 0048 内 DROP 死表 `memory_l2_embeddings`） |
| X5 | `agent-refactor-plan.md` §8.4（**旧路径的残留图** `adapter/graph/loop.py`） | **Agent Stage 7**（与 **X17 同批**删除 —— ⚠️ `runner.py:44` import 它 → 它必须活到旧 runner 退役）。⚠️ 该图**从未被走过**（passthrough 节点），**没有停用阶段**。⚠️ **注意与 X1 的 Agent 部分区分** —— 后者是新 runtime 的 19 节点图，同样归 Agent Stage 7 |
| X1（Agent 部分） | `agent-refactor-plan.md` §2.3 | Agent **Stage 7**（19 节点图拆散后删除 `graph/nodes.py`）；**只取用部件，不整体接线** |
