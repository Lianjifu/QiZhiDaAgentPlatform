# Gateway 层重构方案

> 版本：1.5（2026-10-29：**Stage 1 已实施** —— 幂等守卫落地：契约 `qzdap_agent_runtime/gateway/` + 落库 `PostgresIdempotencyStore` + 接线 `copilot.stream_turn` + 审批恢复路径带键（G10 已修复）+ **删除 `record_request_id` / `recent_request_ids`（G1 已清理）**；详见 §10 Stage 1「实施结果」与附录 C.1）
> 沿革：v1.4（2026-10-29：**本轮重排** —— §0 按共享模板重写为 §0.1–§0.5；**限流独立成章**（§5）；**数据与表**提前到 §8、**逐文件清单**移到 §9、**边界章**移到 §7；§10.4「外部依赖的现状核实」并入 §1.6
> **v1.4 同时修正**：§0.3「选模型 → Router」**违反 D1**、§10 对照表**把 Session 的删除量记到本层**、附录 A **被引用块截断成两张表**、§3.3 `InboundMessage` **缺 `unprotected` 字段**（正文引用 6 处）、§5「L1 接入层」串用了 Memory 的层名、限流指标名与 §13.2 不一致
> 沿革：v1.3（2026-10-29：**独立审查后的 15 项修正** —— 错误码收敛、weak 键不抑制的落地、部分唯一索引、过期行清理归属、NOT NULL 列的合成值、依赖方向、前端零使用 `/v1/sessions`、`channel_deliveries` 归属）
> 适用项目：`QiZhiDaAgentPlatform`
> 状态：**已定稿**（附录 A 的 9 条决策于 2026-10-29 逐条确认；另有 1 条补充条目 #2b 于同日随一致性评审修订）
> 方案集入口：[`README.md`](README.md)
> 上位基线：**[`session-lifecycle-sequence.md`](session-lifecycle-sequence.md)** —— 会话完整生命周期的泳道划分与时序，本方案是其中 **Gateway 泳道**的展开
> 收敛机制：**[`cleanup-ledger.md`](cleanup-ledger.md)** —— 本方案对应条目 **G1–G10**
> 硬约束：**最终态只有一个实现**；先上新、后清旧（清理机制见 §0.4 与台账）
> 方案集导航：落地路线与里程碑见 [`README.md`](README.md) §6 · 系统级验收见 §7 · 外部前置依赖见 §8 · 跨层不变量见 [`session-lifecycle-sequence.md`](session-lifecycle-sequence.md) §6

---

## 0. 定位与范围

### 0.1 基线位置

> **一句话定位**：**Gateway 是平台与外部世界之间唯一的协议边界。**

它只做四件事：

1. **协议 → 标准数据**：把 HTTP / SSE / Webhook / 飞书 / 企微 / 钉钉的方言翻译成一套标准入站数据；
2. **身份 → 统一上下文**：把三种拿身份的方式（JWT principal、租户头、平台签名）收敛成一个 `ActorContext`；
3. **标准结果 → 协议**：把统一的 `ResultEvent` 编码成 SSE / IM 文本 / IM 卡片 / Webhook；
4. **边界上的横切**：验签、限流、去重、错误码映射、trace 贯穿、附件落地。

在泳道图里，Gateway 是 **① 号泳道**（见 [`session-lifecycle-sequence.md`](session-lifecycle-sequence.md)）—— 它是**唯一**与外部世界直接对话的层；Router 及其下游**全部**只经由 `InboundMessage` 与它交互，**不知道 HTTP / SSE / 飞书这些词存在**。

上位方案 v3.1 把会话能力划成十项能力域、19 个 LangGraph 节点。经 2026-10-28 的代码核对，v3.1 已经产出了一套**合同完备但从未接线**的 runtime（`backend/runtimes/agent_runtime/`），而**唯一在生产跑的**是旧 Copilot 实现（`backend/modules/agent_runtime/`）。两套并存的原因与后果见 §1.4。

本方案**只覆盖 Gateway**（含入站归一化、身份、去重幂等、入口级限流、出站编码）。**Router / Session / Context / Memory / Agent 五份方案**的重构各自做，但本方案给出的契约是它们的前置条件。它要解决的是：

1. 把 Gateway 的职责从「散落在 4 个入站路径里的隐式逻辑」变成**一个显式的、可独立验收的分层**；
2. **消灭入站侧的全部重复实现**——4 条入站路径、3 套会话 API、3 套幂等逻辑；
3. 给后面**七层**一个**稳定的标准数据契约**（Router / Session / Context / Memory / Agent Loop / Agent Router / Execution），让它们不再各自解析入参。

> **两条轴（跨层通用，见 [`agent-refactor-plan.md`](agent-refactor-plan.md) §0.2）**：Gateway 在**配置轴**上是纯粹的**取值方** —— 它**不写**任何配置，**不产出模型 / 工具偏好信号**。管理端是唯一的写入点。

### 0.2 子件

| # | 子件 | 回答的问题 | 主要失效模式 | 变更频率 |
|---|---|---|---|---|
| ① | **Channel Gateway** | 怎么到的 / 怎么回 | 协议错配 | 低 |
| ② | **Auth Identity** | 你是谁 | **安全** | 极低 |
| ③ | **Message Normalizer** | 你说了什么 | 字段丢失、语义漂移 | 高 |
| ④ | **Idempotency Guard** | 是不是同一条 | 误杀 / 漏杀 | 中 |

**为什么必须拆成四个**：变更频率差三档 —— **安全代码不能和天天在改的字段映射放同一个文件**。职责切分见 §2.2，顺序规则见 §2.3。

**横切（不是第五个子件）**：

| 横切 | 位置 | 说明 |
|---|---|---|
| **入口级限流** | §5 | 在 ①②③ **之前**的一道入口闸门；不属于任何一个子件 |
| **错误码投影** | §9.0 | 属于 ① 的出站编解码；按码查三套渠道文案 |

### 0.3 Gateway 明确不做

| 不做 | 归属 |
|---|---|
| **选 agent（会话入口的路由）** | Router |
| **选专家 agent（每步推理）** | Agent Router |
| **选模型 / 选工具** | **不选** —— 模型与工具由管理员在 **agent 配置**里绑定，运行时**查表**（Agent 方案决策 #4）。Gateway **不产出模型 / 工具偏好信号** |
| 建会话 / 起轮次 / 落库 | Session |
| 拼 prompt / 压缩 / 摘要 | Context |
| 召回与写入记忆 | Memory |
| 调 LLM / 跑工具 / 审批中断 | Agent Loop / Execution |
| **会话级配额**（每会话的轮次上限、并发上限） | Router / Session —— Gateway 只做**入口级**限流（§5） |

> **⚠️ 本轮修订（旧版本此行违反 D1）**：旧版写「选 agent / 选模型 / 判任务类型 → Router」，**错在两处**：① **选模型不是 Router 的职责** —— Router 只在**会话入口**选一次 agent，模型由 agent 配置绑定、运行时查表（Agent 决策 #4）；② **判任务类型 / 选专家**属于 **Agent Router**，不在 Gateway → Router 这一跳上。

### 0.4 实现收敛规则：最终态只有一个实现

**最终态**：任一职责在全仓只有一套实现承接。

**推进方式**：**先上新、后清旧**——新实现接管并稳定运行后，再删除旧实现。允许在清理窗口内短期并存，但**清理是必达项，不是可选项**。

**为什么不在同一次提交里一起删**：

- 并存期可以用真实流量对照新旧行为——这是唯一可靠的验证方式；
- 一次提交里同时上新 + 删旧，出问题时无法区分「新的错了」还是「旧的删早了」，回退成本高；
- 新实现的接入本身需要旧路径在场兜底（切换失败时直接回落，不中断服务）。

**但这个规则有一个致命的历史前例，必须写死防止重演**：2026-10-15 那次重构建了完整的新 runtime（8 个 Stage 全部打勾）却**从未接线**，同期旧路径继续长功能，两套并存至今。根因是——**每个 Stage 的验收标准是「单测通过」而不是「旧实现减少」**。

所以本项目的收敛机制固定为四件事：

| # | 机制 | 具体做法 |
|---|---|---|
| 1 | **弃用标记 + 观测** | 每个旧入口在被新实现接管时打 `@deprecated` + 打点 `qzdap_legacy_calls_total{entry="..."}`，使「旧实现是否还在被调用」成为**可观测事实**，而不是靠人记得 |
| 2 | **删除条件客观化** | 清理触发条件见 [`cleanup-ledger.md`](cleanup-ledger.md) §3.2 的量化判据（≥7 天 + 新路径流量占比 ≥95% + 旧路径调用累计为 0）。**不使用「发布周期」概念**——本项目无 tag / CHANGELOG / release 目标，该周期不可定义 |
| 3 | **台账化** | 全部旧实现登记在 [`cleanup-ledger.md`](cleanup-ledger.md)，每条含：旧实现位置 → 替代者 → 弃用标记 → 观测指标 → 删除条件 → 状态 → 所属方案 |
| 4 | **不可结转** | 某层的清理台账未清零，该层不得进入下一层的「切换」阶段；未完成项**不允许滚到下个 Stage** |

**回退策略**：清理窗口内（旧实现尚在）可 `git revert` 切换提交直接回落；**清理完成后旧实现不复存在，回退需重新上线旧版本**——这是「先上新后清旧」的代价，写明在此以免误判。

**本层的收敛形态**：与其它层不同 —— Gateway 要收敛的是**「入站侧的重复实现」**，不是接管一条路径。旧实现分散在 **4 条入站路径 × 3 套幂等逻辑**里，因此本层的 Stage 序列是：

| Stage | 收敛动作 | 本层的「旧代码减少」 |
|---|---|---|
| Stage 1 | 幂等键统一，旧 `record_request_id` 删除 | **有**（~25 行） |
| Stage 2 | 验签与身份统一，硬编码系统身份删除 | **有**（~60 行） |
| Stage 3 | 归一化统一，旧数据类与 LRU 去重删除 | **有**（~120 行） |
| Stage 4a | 新实现接管 | **0** —— 只停用 + 打点，进入清理窗口 |
| Stage 5 | 删除 | **全部归零** |

**唯一 owner**：台账 **X2**（第二套 turn 实现 `run_turn.py` / `run_turn_to_completion.py`）的**唯一 owner 是 Session**，删除动作在 **Session Stage 5b**。本层 Stage 4a 只做「停用 + 打点 + 确认无残留调用方」，**不删**（详见 §9.4 与 §10 的对照表）。

§9.4 是逐文件的删除清单，§10 是每个阶段「旧代码减少了什么」的记录表。

### 0.5 前置依赖清单（本方案不实现，但阻塞本方案的哪一步）

| 依赖 | 归属层 | 阻塞 | 说明 |
|---|---|---|---|
| `session_events` 真写真读 | Session | **§4.5 无感重放** | 决策 #4 已定稿为「无感重放」，因此这是硬依赖。若 Session 层未先行落地，Gateway 的重复分支降级为「返回 202 + 上次 turn_id + 标 `replay_unavailable`」，**不得静默丢弃重复请求** |
| 唯一 turn 实现（claim / 幂等 / 取消 / 审批合一） | Session | §9.4、Stage 4a | 渠道入站改造要求下游只有一套 turn 语义；本方案 Stage 4a 会连带停用第二套实现 |
| `LLMPort` 与真实 `agent` 节点 | Agent Loop | §4.2 的 `unprotected` 策略 | 决策 #5 已定稿为「不抑制 + 标 unprotected + 禁用副作用工具」，该策略由 Agent Loop（不选择副作用工具）与 Execution（拒绝执行）共同执行；两者未落地前，`unprotected` 标记只记录不生效（**此时不得启用任何有副作用的工具**，否则违反决策 #5 的前提） |
| `tool_executions` 幂等键传递 | Execution | §4.6 三层键传递链 | C 层幂等由 Execution 落地 |
| **`ErrorCode` 码收敛** | `libs/schema` + `modules/channel` + `modules/agent_runtime` | **§9.0 的投影表** | 7 个码散落在模块内异常的 `code=` 字符串里（`ErrorCode` 枚举**不含**它们）。投影表按码查文案 → **必须先收敛**。登记为横切 H8 的第一条 |
| **`modules/channel` 新增 `qzdap-agent-runtime` 依赖** | `modules/channel` | §9.2.1 的依赖方向 | webhook 端点要调 `Gateway.accept` → channel 需要依赖 runtime。**必须同步改 `pyproject.toml` 与 `uv.lock`**（横切 H6） |

> **依赖顺序建议**：Session 层的「`session_events` 落库」应先于本方案 **Stage 4b** 落地；本方案 Stage 0–4a 不受任何上游阻塞，可立即开工（Stage 4a 属 `README.md` §3.3.1 的豁免 E1）。


## 1. 现状盘点

### 1.1 四条入站路径

| # | 路径 | 入口 | 数据形状 | 缺陷 |
|---|---|---|---|---|
| A | **Web Copilot** | `POST /api/sessions/{id}/turns/stream`<br/>`modules/agent_runtime/adapter/http/session_router.py:230` | body `{content, attachmentIds, clientRequestId, model?, route_id?}`<br/>+ `X-Tenant-Id` / `X-Workspace-Id` / `X-User-Id`<br/>+ `request.state.principal` | 身份有两套来源（header 与 principal）；租户靠客户端 header 自证 |
| B | **IM 渠道** | `POST /v1/channels/{cid}/webhook`<br/>`modules/channel/adapter/http/router.py:174` | `ParsedMessage{external_user_id, external_chat_id, external_message_id, text, metadata}`<br/>`modules/channel/application/ports.py:95` | **不含 tenant / workspace / channel / trace / attachments**；`text_preview` 被截到 200 字（`channel/domain/events.py:33`） |
| C | **通用会话 API** | `POST /v1/sessions`、`POST /v1/sessions/{sid}/turn/stream`<br/>`modules/agent_runtime/adapter/http/router.py:143,209` | 与 A 同族的 body，但走 `RunTurnUseCase` | **只有 `X-User-Id`，没有租户校验**；且走的是**另一套 turn 实现** |
| D | **渠道事件总线** | `ChannelMessageReceived` → `dispatch_subscriber.py`<br/>`modules/channel/adapter/dispatch/dispatch_subscriber.py:113` | 事件 payload（**丢掉了 `external_message_id`**） | 进程内 LRU 去重；每条消息新建 session |

### 1.2 三套会话 / turn 实现

| 实现 | 位置 | claim（并发互斥） | 幂等 | 取消 | 审批 | 谁在用 |
|---|---|---|---|---|---|---|
| **① Copilot** | `application/copilot.py` + `adapter/graph/runner.py` | ✅ `try_claim` CAS | ⚠️ metadata 存 8 个 id | ✅ 跨进程 | ⚠️ 决策不落库 | 前端 Copilot 页 |
| **② use_cases** | `application/use_cases/run_turn.py` + `run_turn_to_completion.py` | ❌ | ❌ | ❌ | ❌ | 渠道入站、子代理、catalog 评测 |
| **③ 新 runtime** | `runtimes/agent_runtime/` | ⚠️ 内存锁 | ❌（turn 级） | ❌ 仅日志 | ⚠️ 有 TTL 但无 `interrupt()` | **无人使用** |

三套语义长期漂移：同一个「跑一轮」，在①里有 claim/幂等/取消/审批，在②里一样都没有。

### 1.3 幂等 / 去重现状

| 层 | 现状 | 证据 |
|---|---|---|
| web 幂等 | 读 session → 改 `metadata.recent_request_ids` → 写回，**非原子**、只留 **8** 个、**无 TTL** | `modules/agent_runtime/adapter/persistence/repositories.py:155-170` |
| IM 去重 | **进程内 `OrderedDict` LRU（1024）**，重启失效、跨 worker 无效；哈希只含文本预览 | `modules/channel/adapter/dispatch/dispatch_subscriber.py:44,113-125,253-260` |
| 工具幂等 | 旧路径**无**；新 runtime 有（内存） | `runtimes/agent_runtime/src/qzdap_agent_runtime/execution/executor.py:108,142` |
| 审批幂等 | 新 runtime 有（TTL + 同 hash 复用）；旧路径无 | `runtimes/.../governance/approval.py:126,139` |
| 存储 | `session_inbox` 表**已建但无人使用**，schema 只适合 IM | `migrations/versions/0035_session_stage2_persistence.py:196-223` |

**🔴 已知安全洞：审批重复点击会重复执行工具。**
`decide_approval` 调用 `stream_turn` 时**不传 `clientRequestId`**（`application/copilot.py:474-482`）→ `record_request_id("")` 直接返回 `True` → 幂等被跳过 → 第一轮审批执行完工具后再点一次「同意」，`try_claim` 因上一轮已结束而放行 → **工具被再执行一次**。根因是双重的：审批决策不落库 + 幂等键在恢复路径缺失。

### 1.4 两套实现并存的由来（为什么不能再来一次）

2026-10-15 一天内，v3.1 方案被执行成 17 个提交（Stage 0 → Stage 8），产出 `backend/runtimes/agent_runtime/`：19 节点图、ports、ResultEvent、outbox 死信状态机、审批 TTL、EngineSwitch 灰度、数据治理接口——**全部到位**。

但 `grep qzdap_agent_runtime` 在 `composition/`、`modules/`、`libs/` 里**零命中**。每个 Stage 的退出条件都是「纯内存 fake 可编译图 / 契约断言通过」，于是 8 个 Stage 全部打勾，产品却 100% 仍跑旧路径。`EngineSwitch` 只在自己的单测里被调用（`runtimes/.../evaluation/__init__.py:261`）。

同期真实需求继续往旧路径上堆（10-16 ~ 10-18：mock-llm chunk、model Phase 1/2/3/7、copilot Phase 1.5/12、agent_factory Phase 19、sub-agent 真派发），旧路径越养越活。

> **教训（本方案的每一步都按它设计）**：验收标准必须写成「旧代码少了哪一块、且新路径在线上真实跑过一轮」，而不是「单测通过」。

### 1.5 已有可复用的资产

| 资产 | 位置 | 状态 |
|---|---|---|
| `ErrorCode` 枚举 + HTTP status + retriable + i18n key | `libs/schema/src/qzdap_schema/dtos/errors.py:22` | ✅ 可用，**缺多渠道文案投影** |
| `session_turns` 唯一约束 `(session_id, idempotency_key)` | `migrations/.../0035_...py:107` | ✅ 表已建，无人用 |
| `tool_executions.idempotency_key` unique | `migrations/.../0035_...py` | ✅ 表已建，无人用 |
| `session_inbox` 表 | `migrations/.../0035_...py:196` | ⚠️ 已建，schema 需改造，无人用 |
| `ResultEvent` 16 种事件类型 | `runtimes/.../result/events.py` | ✅ 类型全，**无节点 dispatch** |
| outbox 死信状态机（8 次重试、指数退避+jitter） | `runtimes/.../outbox/__init__.py` | ✅ 逻辑真，**未接线** |
| `Last-Event-ID` 重放语义 | `runtimes/.../result/sink.py:54-86` | ✅ 内存实现 |
| `build_session_key` / `build_trace_id` / `payload_hash` | `runtimes/.../channels/gateway.py` | ✅ 可用 |

---

### 1.6 外部依赖的现状核实（2026-10-29）

本方案依赖的能力**在当前代码里的真实状态**（避免把假设当现状）：

| 依赖 | 状态 | 证据 | 本层动作 |
|---|---|---|---|
| Prometheus 指标底座 | ✅ 存在 | `libs/observability/src/qzdap_observability/metrics.py:22-60`（6 个指标） | 新增 `LEGACY_CALLS_TOTAL` + `LAST_CALL` gauge |
| `/metrics` 暴露 | ✅ 存在 | `composition/qzdap_app/src/qzdap/composition/main.py:237` | 无需改动 |
| `qzdap_legacy_calls_total` | ❌ **不存在** | `grep` 零命中 | **Stage 0 必须新建**，否则本层清理判据无从判定 |
| Postgres（幂等 claim / advisory lock） | ✅ 存在 | `backend/docker-compose.yml` pgvector/pgvector:pg16 | — |
| `psycopg`（驱动） | ✅ **已声明** | `runtimes/agent_runtime/pyproject.toml`：`psycopg[binary,pool]>=3.2` | 本层不需要；若 Session 层接 saver，必须改用**异步**变体（见下） |
| LangGraph checkpoint saver | ⚠️ **同步版** | `runtimes/.../graph/builder.py:144` 用的是 `langgraph.checkpoint.postgres.PostgresSaver`（同步） | 全异步仓库里会阻塞事件循环 → Session 方案已定为 `AsyncPostgresSaver`（`langgraph.checkpoint.postgres.aio`，venv 实测可用） |
| `langgraph_checkpoint_*` 表 | ❌ **不在任何迁移里** | `grep` 零命中 | 必须在 Session 迁移 0046 建表（不能依赖 saver 的 `setup()` 运行期建表） |

## 2. 目标架构：四部分

```
                          ┌──────────────────────────────────────┐
  HTTP / SSE / Webhook ──▶│ ① Channel Gateway                    │
  飞书 / 企微 / 钉钉       │   传输绑定 · 渠道注册表 · 能力声明      │
                          │   渠道实体查询 · 验签材料准备           │
                          └───────────────┬──────────────────────┘
                                          │ RawIngress
                                          ▼
                          ┌──────────────────────────────────────┐
                          │ ② Auth Identity                      │
                          │   验签 · JWT · 租户/工作区归属 · 角色     │
                          │   服务账号物化 · 信任级别判定            │
                          └───────────────┬──────────────────────┘
                                          │ AuthenticatedIngress
                                          ▼
                          ┌──────────────────────────────────────┐
                          │ ③ Message Normalizer                 │
                          │   协议字段 → 标准字段 · 附件抽取         │
                          │   幂等键计算 · 内容哈希 · trace 提取      │
                          └───────────────┬──────────────────────┘
                                          │ InboundMessage
                                          ▼
                          ┌──────────────────────────────────────┐
                          │ ④ Idempotency Guard                  │
                          │   原子 claim · 重复短路 · 重放决策       │
                          └───────────────┬──────────────────────┘
                                          │ InboundMessage（已 claim）
                                          ▼
                                       Router → Session → …
```

**出站**（对称地属于 ①）：

```
  ResultEvent ──▶ ① Channel Gateway 出站编码 ──▶ SSE / IM 文本 / IM 卡片 / Webhook
```

### 2.1 可测试的边界判据

> **把 Gateway 整个摘掉，剩下的五层应该完全不知道 HTTP、SSE、飞书这些词存在。**

这条判据直接落成一条架构测试（§11.2），比画框图有用。

### 2.2 四部分的职责切分

| | ① Channel Gateway | ② Auth Identity | ③ Message Normalizer | ④ Idempotency Guard |
|---|---|---|---|---|
| 回答的问题 | 怎么到的 / 怎么回 | 你是谁 | 你说了什么 | 是不是同一条 |
| 拥有 | 传输绑定、渠道注册表、渠道能力、响应编码 | 身份材料、密钥、JWT 主体、角色、服务账号 | 协议→标准映射、附件、幂等键原料 | claim 结果、重复判定、重放决策 |
| 不拥有 | 身份语义、消息语义 | 消息语义、任何业务判断 | 任何业务判断、任何文本改写 | 不改消息、不决定 agent、不起轮次 |
| 变更频率 | 低 | 极低 | 高 | 中 |
| 主要失效模式 | 协议错配 | **安全** | 字段丢失、语义漂移 | 误杀 / 漏杀 |

变更频率差三档，所以必须分开——安全代码不能和天天在改的字段映射放同一个文件。

### 2.3 三条必须写死的顺序规则

**① 顺序是 ①→②→③→④，但「查渠道」在 ② 之前**
IM 验签必须针对**原始字节**，且要先知道用哪把密钥 → 密钥挂在渠道配置上 → 所以渠道实体查询属于 ①，验签属于 ②。**验签必须在解析之前**，不能让未验签 payload 进解析器（现状 `modules/channel/application/services.py:224` 的顺序正确，保留）。

**② `trace_id` 在 ① 建立，不是 ③**
IM 平台的 trace id（飞书 `X-Trace-Id` / 企微 `ReqParam.Trace-Id` / 钉钉 `eventId`）是传输层 header，第 ① 步就能拿到。若等到 ③ 才建立，**鉴权失败的请求就没有 trace**——而那恰是最需要被追踪的一类。

**③ 幂等「计算」在 ③，「落库与短路」在 ④**
④ 依赖一个 `IdempotencyStore` 端口，由 Session 提供实现（表 `session_inbox` 属于会话域）。**Gateway 不直接依赖 DB**，否则它会退化成第二个持久化模块。

---

## 3. 统一标准数据

### 3.1 `RawIngress`（① 产出）

```python
@dataclass(frozen=True, slots=True)
class RawIngress:
    transport: Literal["http", "sse", "webhook", "im"]
    channel_type: ChannelType          # web / api 为合成值
    channel_id: UUID | None             # 渠道实体 ID；web / api 无（见下方「合成值」约定）
    capabilities: ChannelCapabilities   # 该渠道支不支持卡片 / 交互 / 流式
    method: str
    path: str
    headers: Mapping[str, str]         # 键统一小写
    body: bytes                        # 原始字节，验签要用
    query: Mapping[str, str]
    trace_id: str                      # ← 最早建立
    peer: str | None                   # IP，供审计与限流
    ingress_ref: str | None            # 渠道实体上的外部路径（webhook 定位用）
```

> **合成值约定（web / api 没有渠道实体，但幂等表的两列是 NOT NULL）**
>
> `session_inbox` 的 `workspace_id` 与 `channel_id` 都是 **NOT NULL**（0035:199-204），而 web / api 既没有渠道实体、workspace 也可能为空。**约定**：
>
> | 字段 | web / api 的取值 | IM 的取值 |
> |---|---|---|
> | `channel_id` | 合成常量 `'web'` / `'api'` | 渠道实体 ID 的**字符串形式** |
> | `workspace_id` | 有则用真实值；无则用**哨兵 UUID** `00000000-0000-0000-0000-000000000000` | 渠道配置上的 `workspace_id` |
>
> **为什么用哨兵而不是把列改 nullable**：唯一约束 `(tenant_id, workspace_id, channel_id, idempotency_key)` 含这两列。PostgreSQL 的普通 UNIQUE 约束里 **NULL 互不相等** —— 改成 nullable 会让「同一条消息在 workspace 为空时可以被插入多次」，**幂等直接失效**。哨兵保留了列的 NOT NULL 与索引效率，代价是「无 workspace」与「哨兵 workspace」在键空间里等价（在本平台语义下二者是同一类请求，可接受）。
>
> ⚠️ **本表 `channel_id` 是 `String(128)`，而渠道实体 ID 实际是 UUID**（webhook 路由 `channel_id: Annotated[UUID, Path()]`）。**存的是 UUID 的字符串形式**，不是 UUID 类型。迁移 0044 **不改这一列的类型** —— 改类型会动到既有索引，且字符串形式对唯一约束没有影响。

### 3.2 `AuthenticatedIngress`（② 产出）

```python
@dataclass(frozen=True, slots=True)
class AuthenticatedIngress:
    raw: RawIngress
    actor: ActorContext
    trust: TrustLevel                  # verified_hmac | jwt | signed_token | internal
    auth_method: AuthMethod            # channel_signature | jwt | api_key | internal
    auth_evidence: str                 # 审计用：密钥 id / principal / channel id
```

```python
@dataclass(frozen=True, slots=True)
class ActorContext:
    tenant_id: UUID
    workspace_id: UUID | None          # None = 该身份无工作区归属（见 §3.1 合成值约定）
    actor_id: UUID
    roles: tuple[str, ...]
    actor_kind: Literal["user", "service_account"]
```

> **信任模型差异必须保留**：web 的 actor 是「已认证用户带租户头」，IM 的 actor 是「平台签名证明的机器身份」。两者都归一成 `ActorContext`，但 `auth_method` / `trust` 不同，IM 的服务账号**不能当作用户权限使用**。
>
> 现状 IM 的 actor 是硬编码全局常量 `SYSTEM_USER_ID = 00000000-0000-0000-0000-00000000c0c0`（`modules/channel/adapter/dispatch/dispatch_subscriber.py:46`）→ 改为**渠道配置里登记的服务账号**。

### 3.3 `InboundMessage`（③ 产出，标准入站数据）

```python
@dataclass(frozen=True, slots=True)
class InboundMessage:
    # 身份
    actor: ActorContext
    # 入口
    channel_type: ChannelType
    channel_id: UUID | None
    external_chat_id: str              # 外部会话标识；web / api 填 session_id
    external_user_id: str              # 外部用户标识；web / api 填 user_id
    explicit_agent_id: UUID | None     # 显式指定的目标 agent（web / api 可传）；None = 交由 Router 按策略推导
    # 幂等
    idempotency: IdempotencyKey
    external_message_id: str | None    # 平台原始 ID，审计用
    payload_hash: str
    unprotected: bool                  # 幂等键强度不足（weak）→ 本轮**禁用有副作用的工具**（决策 #5）
    # 追踪
    trace_id: str
    # 载荷
    text: str
    attachments: tuple[AttachmentRef, ...]
    reply_to: str | None
    # 出站能力
    capabilities: ChannelCapabilities
    # 审计元数据（裁剪后，非原始 payload）
    raw_metadata: Mapping[str, Any]
```

五条设计要点：

- **`raw_metadata` ≠ 原始 payload**。原始 body 在 ③ 结束后即丢弃（可能含敏感信息）；`raw_metadata` 是裁剪后的审计视图。现状 `ParsedMessage.metadata` 把协议细节和业务参数混在一起（`modules/channel/adapter/inbound/feishu.py:69` 把 `tenant_key`/`chat_type`/`message_type` 塞进去），下游无法区分 → 新标准里协议细节归 `raw_metadata`，业务参数才进标准字段。
- **`capabilities` 前置**。渠道支不支持卡片、交互、流式，在**入站时**就确定。现状是出站时才按 `channel_type` 硬判断。
- **不做任何文本改写**。Normalizer 只翻译格式，不清洗、不截断、不摘要用户输入。
- **`explicit_agent_id` 是唯一的「显式指定 agent」入口**。Router 的规则链里「explicit」这一档读的就是它（见 `router-refactor-plan.md` §3.1 规则 2）；IM 渠道恒为 `None`。Gateway **只透传、不校验存在性**（agent 是否存在由 Router / Session 判定）。
- **不做会话 key 派生**。按生命周期基线（`session-lifecycle-sequence.md`），「外部会话标识 → 目标会话」的解析归 **Router**（「路由到会话」）。Gateway 只负责把外部标识规范化成 `external_chat_id` / `external_user_id`，**不生成 session_id、不查会话表**。
- **`unprotected` 是幂等强度的结论，不是猜测**。它在 ③ 由 `IdempotencyKey.strength` 直接推出（`weak` → `True`），④ 的 claim 路径**不再改写**它。兑现点在 **Agent 的工具绑定治理过滤**（剔除副作用工具，见 [`agent-refactor-plan.md`](agent-refactor-plan.md) §5.3.1），**不是执行时拦截** —— Gateway 只负责**如实标记**。

### 3.4 `AttachmentRef`（附件统一模型）

> **决策 #6**：本次**不迁对象存储**，只统一 `AttachmentRef` 的形状并抽出 `AttachmentStoragePort`。字节迁移是独立课题，与本次解耦。

```python
@dataclass(frozen=True, slots=True)
class AttachmentRef:
    attachment_id: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    storage: Literal["db", "object_storage"]
    uri: str                          # 内部引用，不直接外发
    text_preview: str | None          # 已抽取的文本，供 Context 用
```

现状附件二进制直接进库（`modules/agent_runtime/adapter/persistence/attachment_models.py:20` 的 `LargeBinary`），而 IM 侧附件是「不透明标记」塞进 text（`feishu.py:62` 注释明说），前端侧走 `[附件:xxx]` 占位符 + `resolve_attachment_context`（`modules/agent_runtime/adapter/http/session_router.py:248`）——**三套附件语义必须收敛成同一个 `AttachmentRef`**。

> **本次范围**：统一 `AttachmentRef` 形状并抽出 `AttachmentStoragePort`；**不迁移字节到对象存储**（保留 `LargeBinary`），迁移属独立任务，避免方案范围膨胀。

### 3.5 `ChannelCapabilities`（渠道能力声明）

```python
@dataclass(frozen=True, slots=True)
class ChannelCapabilities:
    streaming: bool = False            # 支持流式增量
    cards: bool = False                # 支持结构化卡片
    interactive: bool = False          # 支持用户交互回填
    attachments: bool = False          # 支持附件收发
    max_text_bytes: int = 4096         # 单条文本上限
    max_attachments: int = 0
```

由 ① 维护（渠道注册表的一部分），随 `RawIngress` 传给 ③，最终落在 `InboundMessage` 上。

---

## 4. 幂等与去重

### 4.1 三件事必须分开

| | A. 消息去重 | B. 轮次幂等 | C. 副作用幂等 |
|---|---|---|---|
| 语义 | 同一条**平台消息**投递两次 | 同一**客户端请求**重复到达 | 同一**工具调用**重试 |
| Key | `(tenant, workspace, channel, idempotency_key)` | `(session_id, idempotency_key)` | `(tool_call_id, idempotency_key)` + `request_hash` |
| 归属 | **Gateway（④）** | Session | Execution |
| 依赖 | ④ 原子 claim | `session_turns` 唯一约束 | `tool_executions` 唯一约束 |

Gateway 只负责 A，但 **A 的 key 必须原样传给 B 和 C**——否则三层键体系对不上（这正是现在的状态）。

### 4.2 键的构成与强度

```python
@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    value: str
    source: Literal["platform_message_id", "client_request_id", "payload_fingerprint"]
    strength: Literal["strong", "weak"]
    expires_at: datetime
```

| 优先级 | 来源 | 适用 | 强度 | TTL |
|---|---|---|---|---|
| ① | 客户端显式 `clientRequestId` | web / api | strong | 24h |
| ② | 平台原始事件 ID | 飞书 / 企微 / 钉钉 | strong | 7d |
| ③ | 内容指纹 `sha256(channel+chat+user+text+time_bucket)` | 兜底 | **weak** | 120s |
| ④ | 审批决策 `approval\|{approval_id}\|{decision}` | 审批恢复（web） | strong | 24h |

> **④ 是 2026-10-29 实施 Stage 1 时补的一档**（台账 **G10**）：审批恢复路径必须带幂等键，
> 否则「连点两次『同意』」会把工具**再执行一次**。
>
> **⚠️ 审批键只能由审批自身的标识派生，不能掺原轮次的键** —— 审批恢复时原轮次的状态
> 已经推进（`pending_approval` 被清空），原键取不到 → 同一个审批两次派生出的键**不同**
> → 重复点击挡不住。因此键的构成固定为 `approval|{approval_id}|{decision}`：
> 同一次审批的重复点击会撞键，**下一次**审批（新的 `approval_id`）不会误伤。
>
> ⚠️ `approval_id` 之外的任何东西都不进键：例如把 `clientRequestId` 拼进去会让
> 「原轮次键 + 审批键」两级判重互相干扰。

> **`time_bucket` 粒度 = 60 秒**（`floor(now / 60s)`）。这个值直接决定误杀概率：60 秒内连发两条内容相同的消息才会撞键。

**weak 的处理**（决策 #5 已定稿）：用户连发两条「好的」会被误杀，所以 weak **不做抑制，只记录**，并在 `InboundMessage` 上标记 `unprotected`。配套策略：**`unprotected` 的 turn 禁用有副作用的工具**（只允许只读工具），由 Agent Loop / Execution 执行——这样「没有幂等保护」不会静默变成「副作用可能重复执行」。

> **⚠️「不抑制」必须落到唯一约束上，否则会自相矛盾**（2026-10-29 审查发现）：
>
> §4.4 的原子 claim 是 `INSERT ... ON CONFLICT (tenant_id, workspace_id, channel_id, idempotency_key) DO NOTHING`。**如果 weak 键也参与这个唯一约束，两条内容相同、落在同一 `time_bucket` 的消息会互相冲突 —— 第二条被判为重复而被抑制**，直接违反决策 #5 与 §11.1 验收 4（「用户连发两条『好的』→ 两轮都跑」）。
>
> **落地方式**：唯一约束改为**只覆盖 strong 的部分唯一索引**（§4.3 的 DDL），weak 走**不带 arbiter 的普通 INSERT** —— 既落表可观测，又永不判重。详见 §4.3 与 §4.4。

> web / api 的 strong 是常态（前端已在传 `clientRequestId`，`frontend/web/src/features/user/copilot/copilotApi.ts:43`）。缺失属异常 → 记 warning + 走 `unprotected`，**不静默降级为 weak 抑制**。

### 4.3 `session_inbox` 表改造

> **决策 #3**：**改造现有表**（加 6 列 + 换唯一约束），**不新建 v2 表**。理由：现有表是空的（0035 建后从未被使用），改造没有迁移负担，新建反而多一张孤儿表。
>
> **⚠️ 2026-10-29 审查修订**：「换唯一约束」的具体形态是**换成只覆盖 strong 的部分唯一索引**（`WHERE key_strength = 'strong'`），不是换成普通约束 —— 否则 weak 键会参与判重，**违反决策 #5**。详见本节末尾与 §4.4。

现状三个硬伤：
1. `external_message_id` **NOT NULL**（web 塞不进 `clientRequestId` 语义）；
2. 唯一约束 `(tenant_id, channel_id, external_message_id)` **不含 `workspace_id`**，且没有键来源 / 强度 / 过期概念；
3. **没有「过期」这个状态** —— 键空间只增不减，24h 后同一个 `clientRequestId` 重发会撞上旧行被误判为重复（见 §4.4 的过期分支）。

```sql
-- migrations/versions/0044_gateway_inbox_idempotency.py
ALTER TABLE session_inbox
    ALTER COLUMN external_message_id DROP NOT NULL,
    ADD COLUMN idempotency_key  String(128) NOT NULL,
    ADD COLUMN key_source       String(32)  NOT NULL,
    ADD COLUMN key_strength     String(8)   NOT NULL,   -- 'strong' | 'weak'
    ADD COLUMN status           String(16)  NOT NULL DEFAULT 'received',
    ADD COLUMN claimed_at       TIMESTAMPTZ,
    ADD COLUMN expires_at       TIMESTAMPTZ NOT NULL;

-- 旧约束换成「只覆盖 strong 的部分唯一索引」
ALTER TABLE session_inbox DROP CONSTRAINT uq_session_inbox_dedup;
CREATE UNIQUE INDEX uq_session_inbox_idem_strong
    ON session_inbox (tenant_id, workspace_id, channel_id, idempotency_key)
    WHERE key_strength = 'strong';

CREATE INDEX ix_session_inbox_expires ON session_inbox (expires_at);
```

> **为什么是部分唯一索引而不是普通约束**（2026-10-29 审查发现）：决策 #5 要求 weak 键**不抑制**。若唯一约束覆盖全部行，两条内容相同、落在同一 `time_bucket` 的 weak 消息会互相冲突 → 第二条被误判为重复 → **违反决策 #5**。部分索引（`WHERE key_strength = 'strong'`）让 weak 行**落表可观测、但永不参与判重**。
>
> **代价**：`ON CONFLICT` 的 arbiter 必须带上同样的谓词（`ON CONFLICT (...) WHERE key_strength = 'strong' DO NOTHING`），否则推断不出这个部分索引。**这是本方案唯一需要记住的 SQL 细节。**
>
> **`workspace_id` / `channel_id` 保持 NOT NULL**：web / api 的合成值与哨兵见 §3.1「合成值约定」。**不改成 nullable** —— PostgreSQL 的 UNIQUE 约束中 NULL 互不相等，改 nullable 会让「workspace 为空」的消息被反复插入，**幂等直接失效**。
>
> **`ADD COLUMN ... NOT NULL` 的隐含前提**：本表自 0035 建起**零代码引用、零数据行**（`grep session_inbox` 只在迁移与注释里命中），所以加 NOT NULL 列无需 DEFAULT。**若表里已有数据，0044 必须先补 DEFAULT 再回填** —— 这一条要在迁移脚本的注释里写死。

`status` 取值：`received`（已收未 claim）→ `claimed`（已 claim，处理中）→ `completed`（本轮已完成）；异常分支 `abandoned`。

#### 4.3.1 过期行的清理（**必须有归属，否则键空间只增不减**）

| 维度 | 结论 |
|---|---|
| **谁清理** | **Session 的 sweeper**（`session/…/sweeper.py`）—— 因为 `session_inbox` 的**表归属是 Session**（§8），Gateway 只持端口，不直接操作这张表 |
| **清理什么** | `expires_at < now()` 的行（按批删除，单批上限 1000 行，避免长事务） |
| **清理频率** | 与 sweeper 的其它三类超时同批调度（**不是独立 cron**） |
| **为什么必须** | 唯一约束**不含 `expires_at`** —— 过期行留在表里，同一个键重发时仍会命中冲突。**不清理 = 24h 后开始持续误杀**（见 §4.4 的过期分支，它是第二道保险，不是第一道） |

> **⚠️ 这是跨层依赖**：Session 方案的 sweeper 原本只覆盖「轮次 / 审批 / 会话空闲」三类超时，**没有 `session_inbox` 的过期清理**。已同步登记到 [`session-refactor-plan.md`](session-refactor-plan.md) 的 sweeper 章节与 [`implementation-plan.md`](implementation-plan.md) §3.3。
>
> **两道保险，缺一不可**：① sweeper 定期删（减少冲突面）；② claim 时发现冲突行已过期 → 当作不存在（保证「刚好在清理前重发」也不误杀）。**只有第 ② 条也能正确工作，但第 ① 条不做，表会无限膨胀。**

#### 4.3.2 0044 的回滚

0044 是**纯新增列 + 换约束**，但**换约束会换掉幂等语义** —— 回滚必须显式：

```sql
-- 1) 删新增的索引（含部分唯一索引）
DROP INDEX IF EXISTS ix_session_inbox_expires;
DROP INDEX IF EXISTS uq_session_inbox_idem_strong;

-- 2) 删新增的列
ALTER TABLE session_inbox
    DROP COLUMN IF EXISTS expires_at,
    DROP COLUMN IF EXISTS claimed_at,
    DROP COLUMN IF EXISTS status,
    DROP COLUMN IF EXISTS key_strength,
    DROP COLUMN IF EXISTS key_source,
    DROP COLUMN IF EXISTS idempotency_key;

-- 3) 恢复 0035 的原约束
ALTER TABLE session_inbox
    ADD CONSTRAINT uq_session_inbox_dedup
    UNIQUE (tenant_id, channel_id, external_message_id);
ALTER TABLE session_inbox
    ALTER COLUMN external_message_id SET NOT NULL;
```

> **⚠️ 回滚的硬前提**：`external_message_id` 恢复 `NOT NULL` 之前，必须先把 `NULL` 的行补齐 —— 而 0035 的原语义下这些行**本来就没有这个值**（web 请求没有平台消息 ID）。
>
> **因此：回滚 0044 前，必须先把这批行的 `external_message_id` 用 `idempotency_key` 回填**，否则 `SET NOT NULL` 会失败。
>
> **回滚的语义代价**：恢复原约束 = 幂等退回「按平台消息 ID 去重」，**web 的 `clientRequestId` 语义消失**（同一条 web 消息会被受理多次）。**回滚 0044 等于放弃 web 侧的幂等** —— 这不是技术问题，是产品语义问题，必须由 Gateway 层 owner 决定。

### 4.4 原子 claim

**strong 键**（`key_strength = 'strong'`）走原子 claim：

```sql
INSERT INTO session_inbox
    (tenant_id, workspace_id, channel_id, idempotency_key, key_source, key_strength,
     external_message_id, payload_hash, status, claimed_at, expires_at, trace_id)
VALUES (...)
ON CONFLICT (tenant_id, workspace_id, channel_id, idempotency_key)
    WHERE key_strength = 'strong'
DO NOTHING
RETURNING id, status, turn_id;
```

- **返回一行** → 新消息，我方接管 → 继续往下走；
- **返回 0 行** → 重复 → 查回那一行，按下表分支。

| 查回状态 | 含义 | 动作 |
|---|---|---|
| `completed`（未过期） | 上一轮已完成 | **重放**该 turn 的事件流（§4.5） |
| `claimed`（未超时） | 正在处理 | 返回「处理中」，或挂等该 turn 的事件流 |
| `claimed`（已超时） | 处理方崩溃 | **接管**：重置 `claimed_at`，重跑 |
| `received` | 前一处理方在 claim 前崩溃 | 接管 |
| `abandoned` | 前一处理方明确放弃 | 接管（重置 `claimed_at` 与 `status`） |
| **任意（`expires_at < now()`）** | **该行已过期** | **当作不存在**：在同一事务里 `DELETE` 旧行 → 重新 `INSERT`（新 `expires_at`）→ 继续往下走。**这是「过期不误杀」的第二道保险** |

崩溃超时阈值沿用旧路径 `try_claim` 的经验（`modules/agent_runtime/adapter/persistence/repositories.py:85-108` 的 30 分钟僵尸接管）。

**weak 键**（`key_strength = 'weak'`）**不走 claim**：

```sql
INSERT INTO session_inbox
    (tenant_id, workspace_id, channel_id, idempotency_key, key_source, key_strength,
     external_message_id, payload_hash, status, claimed_at, expires_at, trace_id)
VALUES (
    :tenant_id, :workspace_id, :channel_id,
    :idempotency_key,            -- sha256(channel+chat+user+text+time_bucket)
    'payload_fingerprint',       -- key_source
    'weak',                      -- key_strength
    NULL,                        -- external_message_id：weak 键没有平台消息 ID
    :payload_hash,
    'received',                  -- status
    NULL,                        -- claimed_at：weak 不走 claim
    now() + interval '120 seconds',   -- expires_at（weak 的 TTL）
    :trace_id
);
-- 不带 ON CONFLICT：weak 行不参与唯一索引（部分索引的谓词是 key_strength='strong'），插入永不冲突
```

- **永远不判重、永远放行**（决策 #5）；
- 在 `InboundMessage` 上标 `unprotected` → 该 turn **禁用有副作用的工具**（§4.2）；
- 只进指标 `qzdap_gateway_dedup_total{outcome="weak_recorded"}`，可观测但不抑制。

> **两条路径必须分开写，不能用同一个 INSERT 糊过去**：weak 走 claim 就会被部分索引的谓词排除在冲突之外 → `ON CONFLICT` 推断不出 arbiter → **SQL 直接报错**。所以 strong 与 weak 是两条语句、两个分支。

### 4.5 重复时返回什么

| 入口 | 正确行为 | 现状 |
|---|---|---|
| web SSE | **重放上一轮事件流**（按 seq 从 `session_events` 读）→ 前端看到「内容还在」 | ❌ 抛 `DuplicateRequestError`（`application/copilot.py:237`），前端只能弹错 |
| web REST | 返回上次的 turn（202 + turn_id） | ❌ 抛错 |
| IM | 不重复回消息，记审计 | 进程内 LRU 挡掉，无记录 |

> **A 层幂等的完整实现依赖事件落库。** 旧路径没有 `session_events` 写入，所以命中重复只能报错。新 runtime 的 `session_events` 表（迁移 0035 已建）+ `get_events(turn_id, after_seq)` 重放语义（`runtimes/.../result/sink.py:54-86`）+ outbox 死信状态机正好是这块缺的东西——**这是新 runtime 最该被用上的资产**。

因此 Gateway 的幂等闭环：

```
去重命中 → 查 session_events → 按 seq 重放 → 客户端无感
         ↑ 需要 session_events 真的写、真的读
```

> **依赖声明**（决策 #4 已定稿）：本方案把「事件落库 + 重放」作为**前置依赖**。若 Session 层的方案尚未落地，Gateway 的重复分支只能降级为「返回 202 + 上次 turn_id，不重放事件」，并在 `InboundMessage` 上标记 `replay_unavailable`。**不得静默地丢弃重复请求。** 前置依赖清单见 §0.5。

> **Stage 1 的实际行为（2026-10-29 已实施）**：重复命中**仍抛 `DuplicateRequestError`**
> （前端已对该 code 做「静默忽略」处理，`frontend/web/src/features/user/copilot/CopilotPage.tsx:601`），
> **不是** 202 + turn_id，也**不是**无感重放。
>
> **Stage 1 保证的是硬要求「不重复执行」** —— 重复请求不会跑第二轮（有回归测试与真库并发测试），
> 且重复命中**有记录**（`session_inbox` 行 + 异常），不是静默丢弃。
> **无感重放是 Stage 4b 的能力**（依赖 `session_events` 真写真读），不在 Stage 1 的范围内。

### 4.6 三层键的传递链

```
Gateway   InboundMessage.idempotency.value        (strong / weak + source)
   ↓
Session   session_turns.idempotency_key            UNIQUE (session_id, idempotency_key)   ✅ 表已建
   ↓
Agent     tool_executions.idempotency_key (UNIQUE) + request_hash                        ✅ 表已建
```

---

## 5. 限流（入口级）

§0.1 声称 Gateway 做「验签、**限流**、去重、错误码映射」，但**改写前**全篇无限流设计、无阈值、无错误码、无验收。现状：**无限流**（`grep` 无任何 rate limit 逻辑），IM 渠道的入站 webhook 可被无限刷。

> **本节是独立章（v1.4 重排）**：限流**不是幂等的一部分** —— 它是**入口闸门**，必须在「解析与落库之前」发生（§11.1 验收 10）。此前它被埋在「幂等与去重」里作为小节，导致读者以为限流 = 限重复请求。**这是两回事**：幂等防「同一条消息跑两次」，限流防「一个用户刷爆入口」。

**设计**：

| 维度 | 规则 | 依据 |
|---|---|---|
| **IM 限流键** | `(tenant_id, channel_id, external_user_id)` | 用户级；防止单用户刷爆一个渠道。**IM 路径有 `external_user_id`** |
| **Web / API 限流键** | `(tenant_id, actor_id)` | ⚠️ **web / api 路径没有 `external_user_id`**（`session_router.py` 里该字段零命中）—— 所以 IM 的那个键**不适用于 web**。web 用已认证的 `actor_id` |
| 租户级 | `(tenant_id, 全局)` | 防止单租户占满 worker |
| 算法 | **双层令牌桶**（短窗 + 长窗） | 短窗挡突发，长窗挡持续 |
| 短窗 | 每分钟 N 次（建议 N=60） | — |
| 长窗 | 每小时 M 次（建议 M=600） | — |
| 超限响应 | `ErrorCode.RATE_LIMITED` → HTTP 429 | `ErrorCode` 枚举已有 `RATE_LIMITED`（status 429） |
| IM 渠道超限 | **返回 200 但不受理**（避免平台反复重推） | IM 平台对 429 的重试策略不可控 |
| Web 超限 | 返回 429 + `Retry-After` | — |

**实现位置**：Gateway 的 **① Channel Gateway**（与 `identity.py` 同级，见 §2.2），因为限流必须在**解析与落库之前**。计数器落在 `qzdap_observability`（与 `qzdap_legacy_calls_total` 同处），按 `runtimes/embedding_runtime` 的独立服务模式，或先用进程内实现（单副本够用）。

**归属决策**：限流是 Gateway 的职责还是独立能力域？现状 `modules/governance` 有 `policies` 表。**本方案把限流放在 Gateway**（它是入口边界的一部分）。**限流策略（阈值、租户配额）本轮由环境变量配置**（决策 #9），治理模块可配**留待后续** —— 不在本轮引入新配置面。

> **决策 #9（已定稿，2026-10-29）**：限流的阈值与租户配额 → **硬编码 + 环境变量覆盖**（`QZDAP_RATE_LIMIT_*`）。治理模块 `policies` 表配置**留待后续** —— 本轮**不引入新配置面**。

**验收**：
- 同一用户 1 分钟内超过 N 次 → 第 N+1 次返回 429（Web）/ 不受理（IM）；
- 限流在**落库之前**发生（被限流的请求不产生 `session_inbox` 行）；
- 限流计数进指标 `qzdap_gateway_rate_limited_total{channel_type="<type>", scope="<短窗|长窗>"}`（**与 §13.2 的指标表同名同标签** —— 此前本节写的是 `qzdap_rate_limited_total`，与指标表对不上）。

---

## 6. 出站：统一编码与投递

> **决策 #1**：出站**归 ① Channel Gateway**（与入站对称）。不单列「Result Encoder」—— 那会让渠道知识有两份。

现状缺口：`OutboundAdapter.send_reply(external_chat_id, text, metadata)`（`modules/channel/application/ports.py:112`）**只能发纯文本**，而会话层能产 16 种 chunk。IM 侧现在收不到审批卡片、plan、artifact。

出站归 ①（与入站对称，同一份渠道知识）：

```python
class ResultSink(Protocol):
    async def deliver(self, event: ResultEvent) -> DeliveryOutcome: ...
    async def replay(self, turn_id: str, after_seq: int) -> AsyncIterator[ResultEvent]: ...
```

编码规则：

| 事件 | 有卡片能力 | 无卡片能力（降级） |
|---|---|---|
| `message` | 文本消息 | 文本消息 |
| `approval_required` | 审批卡片（带按钮，回调带 approval_id） | 文本 + 「回复 YES/NO」指令 |
| `plan_proposed` | 计划卡片 | 编号文本列表 |
| `artifact_ready` | 产物卡片（含下载链接） | 文本 + 链接 |
| `interactive_action` | 交互卡片 | **降级为文本提示 + 记 degraded**（见下） |
| `usage` / `done` / `error` | 折叠或忽略 | 忽略（不打扰用户） |

原则：**降级必须保信息**。

**`interactive_action` 的降级契约**（前端消费方 `CopilotPage.tsx:506`）：

| 渠道能力 | 行为 | 前端表现 |
|---|---|---|
| `interactive: true` | 发交互卡片 | 前端渲染对应卡片（问题卡 / plan / 待办 / 委派） |
| `interactive: false` | **降级为一条 `message` 事件**，内容为可回答的文本提示（如「请回复你的选择：A / B / C」），同时置 `degraded_flags.interactive_degraded = true` | 前端按普通消息气泡显示，用户可文字回复 |

> **不得静默丢弃**：`interactive_action` 在纯文本渠道无法表达，但**可以降级为可回答的文本**。若连文本都无法表达（如 IM 的富文本限制），则发一条 `message` 说明「此操作需要在 Web 端完成」并记 degraded。

投递失败 → 重试 → 死信（复用 `runtimes/.../outbox/__init__.py` 的 8 次 + 指数退避 + jitter 状态机）。

---

## 7. 与相邻层的边界

按生命周期基线（`session-lifecycle-sequence.md`）的泳道划分，Gateway 的下游是 7 条泳道：

| 泳道 | 本方案给它的契约 | 它欠本方案的 |
|---|---|---|
| **Router** | `InboundMessage`（含 `actor` / `capabilities` / `idempotency` / `external_chat_id` / `external_user_id`）；会话 key 的派生**归 Router**，本方案不做 | 无（见 [`router-refactor-plan.md`](router-refactor-plan.md)） |
| **Session** | `IdempotencyStore` 实现（`session_inbox` 表）；`InboundMessage.idempotency.value` 写入 `session_turns.idempotency_key` | `session_events` 落库（重放前置）、`session_turns` 启用、唯一 turn 实现 |
| **Context** | `AttachmentRef.text_preview`；`actor` 供租户上下文 | 无 |
| **Memory** | `actor.actor_id` / `tenant_id`（`owner_id` 从此取得，不再靠 `X-User-Id` header） | 无 |
| **Agent Loop** | `idempotency.value` 传入 `tool_executions.idempotency_key`；`unprotected` 标记用于禁用副作用工具；记忆写入的触发点在 Agent Loop（Observe/Evaluate 之后），不在 Session | `LLMPort`、真实 `agent` 节点、`MemoryPort` |
| **Agent Router** | 无直接契约（经 Agent Loop 传递） | **专家选择的分类器**（`task_kind` → 选哪个专家 agent）。⚠️ **没有「模型策略链」** —— 模型由 agent 配置绑定、运行时**查表**（Agent 决策 #4），Gateway **不产出任何模型 / 工具偏好信号** |
| **Execution** | `idempotency.value` → `tool_executions.idempotency_key` + `request_hash`（副作用幂等） | 统一执行器（重试/超时/熔断） |

**横切**：Governance 与 Observability 作用于所有泳道；本方案只保证 Gateway 自身在治理与观测下的行为正确（鉴权失败有审计与 trace、幂等命中可观测）。

---

## 8. 数据与表终态

| 表 | 归属 | 状态 |
|---|---|---|
| `agent_sessions` | Session | 保留（`metadata.recent_request_ids` 字段随 Stage 5 删除） |
| `agent_turns` | Session | **迁数据后废弃**（Session Stage 6；新表 `session_turns` / `session_messages` 启用后删除） |
| `agent_session_messages` | Session | **迁数据后废弃**（Session Stage 6） |
| `copilot_attachments` | Gateway | 保留（本方案不迁字节） |
| `channel_deliveries` | **Gateway（`modules/channel`）** | ⚠️ **保留，但职责收窄**（2026-10-29 审查补充）：这张表现状同时承载 **inbound**（`services.py:236` 写入）与 **outbound**（`services.py:290` 写入）两类记录，`direction` 字段区分。本方案把**出站投递**移到 Gateway 的 `ResultSink`（§6）后，`modules/channel` 侧的 outbound 写入**不再产生**；**inbound 记录保留**（它是「收到过这条 webhook」的审计凭据，与本方案的幂等表 `session_inbox` 职责不同：后者管去重，前者管投递轨迹）。**迁移 0044 不动这张表** |
| `session_inbox` | **Session**（会话域） | **启用 + 改造**（加列改约束）。Gateway 只持 `IdempotencyStore` 端口，**表归 Session**，改造 DDL 由 Gateway 的迁移 0044 执行（表是 Gateway 的实现细节依赖，但归属是会话域） |
| `session_turns` | Session | 启用（B 层幂等） |
| `session_events` | Session | 启用（重放前置） |
| `tool_executions` | Execution | 启用（C 层幂等） |
| `outbox_dead_letters` | Session | 启用（出站投递） |
| `langgraph_checkpoints` / `langgraph_store` | Agent Loop | 由 Agent Loop 方案决定 |

> **本方案不新建任何表**，只改造 `session_inbox` 一张已存在但未使用的表。
>
> **归属说明（2026-10-29 修订）**：`session_inbox` 的**表归属是 Session**（会话域），Gateway 只持有 `IdempotencyStore` 端口（见 §2.3 ④）。改造该表的 DDL 放在 Gateway 的迁移 0044 里，是因为**改约束的动机来自 Gateway 的幂等语义**（幂等键强度分层），而不是表的归属。两处不冲突：谁定义语义、谁拥有表，是两件事。

---

## 9. 逐文件改造与删除清单

> **决策 #2**：`modules/channel` **保持独立模块**，实现 runtime 定义的 Protocol，Gateway 只持有端口。不把协议适配器迁进 runtime —— 边界更干净，但要拆包、改多处 import，收益不抵成本。
>
> **⚠️「迁移」一词的准确含义**（2026-10-29 审查补充）：本节说的「迁到 `gateway/…`」指的是**逻辑迁移** —— **语义搬到 runtime 的 `gateway/` 包里，旧代码在对应 Stage 被删除**。**`modules/channel` 这个模块本身不被拆散、不被并入 runtime**：它的**路由端点与渠道 CRUD 留在原处**，只是变成调用 `Gateway.accept` 的薄壳。
>
> 这样两个决策才不冲突：#2 说「模块保持独立」，本节说「逻辑搬到 runtime」—— **搬的是逻辑，不是模块**。

### 9.0 本层涉及的错误码

> **⚠️ 现状核对（2026-10-29 审查）**：`libs/schema/src/qzdap_schema/dtos/errors.py` 的 `ErrorCode` 枚举**只有 20 个成员**，**不包含**下表中除 `RATE_LIMITED` / `AUTHENTICATION_FAILED` / `FORBIDDEN` / `CONTEXT_TOO_LARGE` / `AGENT_NOT_AVAILABLE` / `SESSION_BUSY` 之外的码。那些码是**各模块 `domain/errors.py` 里异常类的自由字符串**：
> ```
> modules/channel/…/domain/errors.py:24:        code = "CHANNEL_NOT_FOUND"
> modules/agent_runtime/…/domain/errors.py:43:  code = "DUPLICATE_REQUEST"
> ```
> **所以「本层新增：无」这个结论是错的** —— 本层需要做的是**收敛**，不是新增。

| 错误码 | 现状归属 | HTTP | 本层行为 |
|---|---|---|---|
| `RATE_LIMITED` | ✅ `ErrorCode` 枚举成员 | 429 | §5 限流超限 |
| `AUTHENTICATION_FAILED` | ✅ `ErrorCode` 枚举成员 | 401 | 验签 / JWT 失败 |
| `FORBIDDEN` | ✅ `ErrorCode` 枚举成员 | 403 | 租户 / 工作区归属不符 |
| `CONTEXT_TOO_LARGE` | ✅ `ErrorCode` 枚举成员 | 413 | Context 层溢出时的透传 |
| `AGENT_NOT_AVAILABLE` | ✅ `ErrorCode` 枚举成员 | 502 | Router 未选到 agent |
| `SESSION_BUSY` | ✅ `ErrorCode` 枚举成员 | 409 | 同会话已有活动轮次 |
| `CHANNEL_NOT_FOUND` / `CHANNEL_DISABLED` | ⚠️ `modules/channel` 异常字符串 | 404 / 409 | 渠道不存在或已停用 |
| `INBOUND_ADAPTER_MISSING` | ⚠️ `modules/channel` 异常字符串 | 500 | 该渠道类型没有注册解析器 |
| `WEBHOOK_SIGNATURE_INVALID` / `WEBHOOK_TIMESTAMP_SKEW` | ⚠️ `modules/channel` 异常字符串 | 401 | 验签失败 |
| `DUPLICATE_REQUEST` | ⚠️ `modules/agent_runtime` 异常字符串 | 409 | 幂等命中且**未启用**无感重放时的兜底 |
| `TENANT_DENIED` | ⚠️ 模块内异常字符串 | 403 | 租户 / 工作区归属不符 |

**本层的动作 = 收敛 + 投影**：

1. **收敛**：把上表 ⚠️ 标记的 7 个码**提升为 `ErrorCode` 枚举成员**，并把各模块 `domain/errors.py` 的 `code = "..."` 字符串**对齐到枚举**。理由：§9.1 的 `ERROR_PROJECTION` 投影表是**按码查文案**的 —— 若码散落在两套体系里，投影表要维护两套码，而其中一套必然漏。
2. **投影**：新增 `ERROR_PROJECTION`（http / im / web 三套文案）。
3. **⚠️ 不新增码**：本方案**不引入任何新错误码**。若实施中发现某个场景确实没有对应码，**先确认现有码能否表达**，再决定新增 —— 并同步更新本表。

> **实施顺序**：错误码收敛属于**跨模块改动**（`libs/schema` + `modules/channel` + `modules/agent_runtime`），登记为横切项 **H8（跨模块外部前置）** 的第一条（见 [`implementation-plan.md`](implementation-plan.md) §5）。**它是 Stage 0 的前置** —— §9.1 的投影表建在 `ErrorCode` 之上。

**非 `ErrorCode` 的标记**（走 `flags` 或事件字段，不进错误码枚举）：

| 标记 | 载体 | 含义 |
|---|---|---|
| `replay_unavailable` | **`IdempotencyDecision` + 响应头** —— ⚠️ **不是 `InboundMessage` 字段** | 无感重放依赖未就绪，重复请求降级为 202。**为什么不是 `InboundMessage` 字段**：`InboundMessage` 在 **③ Normalizer** 就定型，而 `replay_unavailable` 是 **④ Idempotency Guard** 的判定结果 —— 它在下游才产生。载体写成 `InboundMessage` 会让下游去读一个**恒为空的字段** |
| `recall_degraded` / `compaction_degraded` / `interactive_degraded` | `ResultEvent.flags` | 降级发生，前端按策略折叠或提示 |
| `unprotected` | `InboundMessage.unprotected`（**标准数据字段**，不是 flag） | 幂等键强度不足（weak）→ 本轮**禁用有副作用的工具**（决策 #5）。在 ③ 定型，随消息一路传到 Agent 的工具绑定治理过滤 |

### 9.1 新增（`backend/runtimes/agent_runtime/src/qzdap_agent_runtime/gateway/`）

| 文件 | 内容 |
|---|---|
| `types.py` | `RawIngress` / `AuthenticatedIngress` / `InboundMessage` / `ActorContext` / `AttachmentRef` / `ChannelCapabilities` / `IdempotencyKey` |
| `identity.py` | `IdentityVerifier` Protocol、`TrustLevel`、`AuthMethod` |
| `normalizer.py` | `MessageNormalizer` Protocol + 按 `channel_type` 分派 |
| `idempotency.py` | `IdempotencyGuard`、`IdempotencyStore` Protocol、`IdempotencyDecision` |
| `channels.py` | `ChannelGateway`：渠道注册表、入站分派、出站编解码、能力声明 |
| `facade.py` | `Gateway.accept(raw)` 返回 `InboundMessage` 或 `Duplicate`；`Gateway.emit(event)` |
| `errors.py` | `ErrorCode` → 多渠道文案投影表（`ERROR_PROJECTION`） |

### 9.2 迁移（旧代码 → 新位置）

| 旧位置 | 迁到 | 动作 |
|---|---|---|
| `modules/channel/adapter/http/router.py:174` `receive_webhook` | `gateway/channels.py` | 改为产出 `RawIngress` |
| `modules/channel/application/services.py:180-250` `_verify_signature` + `_reject` | `gateway/identity.py` | 验签逻辑抽出；`ChannelService` 只保留渠道 CRUD |
| `modules/channel/application/ports.py:95` `ParsedMessage` | `gateway/normalizer.py` 的 `InboundMessage` | **删除** `ParsedMessage` |
| `modules/channel/adapter/inbound/{feishu,dingtalk,wechatwork,web}.py` `parse_webhook` | 同文件保留，实现 `MessageNormalizer` | 返回值从 `ParsedMessage` 改为 `InboundMessage` |
| `modules/channel/adapter/outbound/*.py` `send_reply` | `gateway/channels.py` 出站 | 扩展为 `ResultSink`，支持卡片 |
| `modules/agent_runtime/adapter/http/session_router.py:230-294` `stream_turn` | `gateway/channels.py`（web 入站） | 只做解析与委派，编排下沉到 Session |
| `modules/agent_runtime/adapter/http/session_router.py:39-70` `_write_audit` | `gateway/identity.py` / 审计模块 | 复用，不重复实现 |
| `modules/agent_runtime/adapter/persistence/repositories.py:155-170` `record_request_id` | `gateway/idempotency.py` | **删除**，改用 `session_inbox` 原子 claim |
| `modules/channel/adapter/dispatch/dispatch_subscriber.py:113-125` LRU 去重 | `gateway/idempotency.py` | **删除 LRU**，改用 claim |
| `modules/agent_runtime/adapter/http/attachments.py:89` `resolve_attachment_context` | `gateway/normalizer.py` | 改为产出 `AttachmentRef` |

### 9.2.1 依赖方向（**实施前必须确认，否则循环依赖**）

```
composition
   │
   ├─→ modules/agent_runtime      (Session：turn 实现 / 轮次 / 事件)
   ├─→ modules/channel            (渠道 CRUD + 验签薄壳 + 渠道适配器)
   │        │
   │        └──→ qzdap-agent-runtime   ← 本方案新增的依赖（webhook 端点要调 Gateway.accept）
   │
   └─→ qzdap-agent-runtime        (Gateway 新实现：gateway/ 包)
            └─→ kernel / schema / persistence / auth / messaging / llm / observability
```

| 事实 | 依据 |
|---|---|
| `modules/channel` **当前不依赖** `qzdap-agent-runtime` | `modules/channel/pyproject.toml` 只声明 kernel / schema / persistence / auth / messaging / vault / http / fastapi / pydantic / httpx |
| `qzdap-agent-runtime` **不依赖** `modules/channel` | `runtimes/agent_runtime/pyproject.toml` 同上，无 channel |
| **无循环** | 两者都只依赖 `kernel` / `schema` / `auth` 等叶子包 |
| **本方案新增** | `modules/channel` 增加 `qzdap-agent-runtime` 依赖；`qzdap-agent-runtime` **不增加** `qzdap-channel` 依赖 |

> **为什么 runtime 不反向依赖 channel**：Gateway 需要「渠道实体查询」（验签前要知道用哪把密钥），这通过**端口**（`ChannelDirectoryPort`）实现，实现在 `modules/channel` 侧 —— 与 §2.3 ① 的「渠道实体查询属于 ①」一致，且保持了 §2.3 ③ 的「**Gateway 不直接依赖 DB**」。
>
> **⚠️ 这是本方案唯一的跨包依赖变更**，登记在横切项 **H6（锁文件与依赖）** 与 **H8（跨模块外部前置）** 下（见 [`implementation-plan.md`](implementation-plan.md) §5）。**实施时必须同步改 `modules/channel/pyproject.toml` 与 `uv.lock`，否则 `uv sync` 后 `modules/channel` 找不到 `Gateway.accept`。**

### 9.3 保留但改造

| 文件 | 改造点 |
|---|---|
| `modules/channel/adapter/http/router.py` | 保留渠道 CRUD 端点；webhook 端点改为薄壳调用 `Gateway.accept` |
| `modules/channel/application/services.py` | 保留 `ChannelService`（渠道 CRUD + 密文轮换）；移除验签与投递职责 |
| `modules/agent_runtime/adapter/http/sse.py` | 保留 SSE 编码器；新增 `Last-Event-ID` 支持 |
| `libs/auth/src/qzdap_auth/middleware.py` | 保留；其产出的 principal 转为 `ActorContext` |

### 9.4 删除清单（Stage 4a 停用 + 打点 → Stage 5 删除）

> **决策 #7**：`/v1/sessions*` 的会话 CRUD 保留**兼容别名**（打 deprecation 日志），保留期 = **新路径流量占比 ≥95% 之后的 ≥7 天**，其 **turn 部分直接删**。前端已切 `/api/*`，不保留 turn 部分没有回退价值。

| 类别 | 具体 |
|---|---|
| 旧数据类 | `ParsedMessage`（`modules/channel/application/ports.py:95`）—— ⚠️ **当前被 4 个 inbound adapter + `adapter/inbound/__init__.py` 引用**（`feishu.py` / `dingtalk.py` / `wechatwork.py` / `web.py`），Stage 3 改完这 5 处后才真正「全仓无引用」 |
| 旧去重逻辑 | `dispatch_subscriber.py` 的 `OrderedDict` LRU（`:44`）、`_message_key`（`:253-260`）。**文件删除归本层（台账 G9）** |
| 旧幂等逻辑 | `repositories.py:155-170` `record_request_id`；`session.metadata.recent_request_ids` 字段与所有读写 |
| 旧硬编码身份 | `dispatch_subscriber.py:42-46` `SYSTEM_USER_ID` / `SYSTEM_AGENT_ID` |
| 旧入站形状 | `channel/domain/events.py` 的 `ChannelMessageReceived`（缺 `external_message_id` / `trace_id`）→ 由 `InboundMessage` 取代 |
| 旧会话 API | `/v1/sessions*`（`modules/agent_runtime/adapter/http/router.py:143-280`）与 `/api/sessions*`（`session_router.py`）**合并为一套** |
| 旧 turn 实现 | `application/use_cases/run_turn.py`、`run_turn_to_completion.py` 与 `application/copilot.py` 的 **turn 编排部分合并为一套**（保留 `copilot.py` 的 claim / 幂等 / 取消 / 审批语义为唯一实现）。⚠️ **唯一 owner 是 Session（台账 X2）** —— 本层只做「停用 + 打点 + 确认无残留调用方」，**删除动作在 Session Stage 5b**（与本层的「切 IM 入口」同 PR） |
| 旧路由 | `session_router.py` 的 `GET /v1/sessions`（与 `/api/sessions` 语义重复）—— 锚点用**符号名** `GET /v1/sessions`，行号会漂移 |
| 孤儿表 | 无（`session_inbox` / `session_turns` / `session_events` / `tool_executions` **保留并启用**，不是删除对象） |

> **注意**：`/v1/sessions*` 与 `/api/sessions*` 的合并涉及前端契约。**前端零使用 `/v1/sessions*`**（2026-10-29 核实：`frontend/packages/api/src/pathMap.ts:171-177` 的会话相关条目**全部**是 `/api/sessions*`，全仓 grep `v1/sessions` 零命中）。合并方案：**外部路径保持 `/api/sessions*` 不变**（前端零改动），`/v1/sessions*` 只保留一个兼容别名并打 deprecation，**保留期：新路径流量占比 ≥95% 之后的 ≥7 天**，到期删除。
>
> **⚠️ 因此保留兼容别名的唯一理由是「仓外消费者」，不是前端。** 这一点必须落实为一次确认动作（[`implementation-plan.md`](implementation-plan.md) 前置 **P-11**：由 API owner 确认是否存在仓外调用方）。**若确认无仓外消费者，G7 / G8 可在 Stage 5 直接删，保留期归零。**

---

## 10. 实施阶段

> 每阶段的验收都包含「**旧代码减少了什么**」这一栏。缺这一栏的阶段不算完成。
>
> **决策 #8（切换方式）**：**先上新、后清旧** —— Stage 4a 新实现接管（旧实现打弃用标记 + 打点，进入清理窗口），Stage 5 清理。**不留 feature flag 双跑**，但清理窗口内旧实现在场（这正是回退兜底的前提，详见 §12）。Stage 4b（启用无感重放）待 Session 就绪，**不豁免**。

### Stage 0：契约与地基（不改行为）

| 动作 | 产出 |
|---|---|
| 建 `gateway/` 骨架 + `types.py` | 4 个类型定稿 |
| 扩 `ErrorCode` 投影表 | `libs/schema/.../errors.py` 加 `ERROR_PROJECTION`（http / im / web 三套文案） |
| 迁移 0044 | `session_inbox` 加列改约束 |
| 建架构测试 | §11.2 的 import 禁令 |
| **收敛基础设施** | 建 `qzdap_legacy_calls_total` 指标（若尚未建立），并给本层台账条目的旧入口打点（`record_legacy_call("<编号>")`）。**没有打点就没有清理判据** —— 见 `cleanup-ledger.md` §3.2 |

**旧代码减少**：无（纯新增）。
**验收**：类型有单测；迁移可在 dev 库跑通；架构测试通过。
**验收补充**：本层每个台账条目的旧入口都有打点；`/metrics` 能查到 `qzdap_legacy_calls_total`。

### Stage 1：Idempotency Guard 落地（先做，因为它不依赖其他层）

> ✅ **已实施（2026-10-29）** —— 产出与验证见本节末尾的「实施结果」。

| 动作 | 细节 |
|---|---|
| `IdempotencyStore` 端口 + SQL 实现 | **strong / weak 两条 INSERT 路径**（§4.4）：strong 走 `ON CONFLICT (...) WHERE key_strength='strong' DO NOTHING RETURNING`；weak 走不带 arbiter 的普通 INSERT（**永不判重**，决策 #5） |
| `Gateway.accept` 编排 | ①→②→③→④ 四步串起来 |
| web 入站切过来 | `session_router.py` 的 `stream_turn` 改为先过 `Gateway.accept` |
| **审批恢复路径传幂等键** | `decide_approval` 触发的续跑请求携带原轮次的 `clientRequestId` → 连点两次「同意」只执行一次工具（台账 **G10**） |
| **删除** | `repositories.py:155-170` `record_request_id` + `session.metadata.recent_request_ids` 全部读写 |

**旧代码减少**：`record_request_id` 删除；`recent_request_ids` 从 `agent_sessions.metadata` 消失。
**验收**（**两种并发要分开测，语义不同**）：
- **同键并发**（同一 `clientRequestId` 10 次并发）→ 只起 **1** 轮，其余 9 次返回「重复」（SSE 走重放 / REST 走 202 + turn_id）；**不重复执行**；
- **同会话不同键并发**（同一 session 10 个不同 `clientRequestId`）→ 按 Router 决策 #1 的语义：**排队**（各自最终都跑，顺序按 `ingress_seq`）或 **`SESSION_BUSY`**（拒绝语义下）—— **由决策 #1 决定，不是本层能定的**。⚠️ 不同幂等键**不是**重复请求，**不得**按重复处理；
- **弱键不误杀**：同一会话 60 秒内连发 2 条内容相同的消息（「好的」）→ **两轮都跑**（weak 不抑制，标 `unprotected`）；
- **过期不误杀**：同一个 `clientRequestId` 在 24h（TTL）后重发 → **当作新消息受理**（不判重复）；
- **审批不重复执行**：连点两次「同意」→ 工具只执行一次（依赖「审批恢复路径传幂等键」）；
- **跨进程**：两个 worker 交替请求同一 `clientRequestId` → 只起 1 轮。

#### Stage 1 实施结果（2026-10-29）

| 项 | 落地位置 |
|---|---|
| **契约（无框架、无 DB）** | `backend/runtimes/agent_runtime/src/qzdap_agent_runtime/gateway/types.py`（`RawIngress` / `AuthenticatedIngress` / `ActorContext` / `InboundMessage` / `IdempotencyKey` / `IdempotencyDecision`）与 `gateway/idempotency.py`（`IdempotencyStore` 端口 + 键阶梯 + `IdempotencyGuard`） |
| **落库实现** | `backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/persistence/idempotency_store.py` —— strong 走 `ON CONFLICT (...) WHERE key_strength='strong' DO NOTHING`，weak 走不带 arbiter 的普通 INSERT（**永不判重**） |
| **接线** | `copilot.stream_turn` 在抢会话占用**之前**先过 `IdempotencyGuard.accept`；`CopilotSessionService` 新增 `idempotency` 依赖，由 `composition/.../lifespan.py` 装配 `PostgresIdempotencyStore(container.session_factory())` |
| **审批恢复路径** | `decide_approval` 生成 `approval\|{approval_id}\|{decision}` 的 strong 键（§4.2 的第 ④ 档）→ 台账 **G10 已修复** |
| **删除（旧代码减少）** | `SessionRepository.record_request_id` 的**协议方法与两处实现**（`repositories.py` / `_in_memory.py`）+ `session.metadata.recent_request_ids` 的全部读写 → 台账 **G1 已清理**；`copilot.stream_turn` 里的 `record_legacy_call("G1")` 打点一并撤除 |

> **⚠️ 抢占用与幂等的先后顺序**（实施时定下的次序，不是随意的）：
> **先幂等 claim，再抢会话占用**。
> - 先幂等：同一 `clientRequestId` 并发 10 次 → **只起 1 轮**，其余 9 次判定为「重复」（§10 Stage 1 验收第 1 条）；
> - 但会话被别的轮次占着而**本轮没跑起来**时，键**必须释放**（`IdempotencyStore.release` 删掉那一行）——
>   否则调用方用同一个键重试会被误判成「重复」，消息就永远丢了。
>
> **验收结果**：
> - 同键并发 10 次 → 只起 1 轮（真库 + 真并发：`modules/agent_runtime/tests/integration/test_idempotency_store.py::test_the_same_strong_key_concurrently_starts_only_one_turn`）；
> - weak 不误杀 → 两条相同内容的消息都跑（`::test_a_weak_key_never_suppresses`）；
> - 过期不误杀 → TTL 之后重发按新消息受理（`::test_an_expired_key_is_treated_as_a_new_message`）；
> - 审批不重复执行 → 连点两次「同意」工具只执行一次（`modules/agent_runtime/tests/unit/test_copilot_resilience.py::test_double_clicking_approve_executes_the_tool_only_once`）；
> - 不同幂等键不按重复处理（`::test_a_different_key_is_not_treated_as_a_duplicate`）。

### Stage 2：Auth Identity 收口

| 动作 | 细节 |
|---|---|
| `IdentityVerifier` 端口 | web(JWT) / IM(HMAC) / internal 三种实现 |
| 服务账号物化 | IM 的 actor 从渠道配置读，不再用全局常量 |
| 渠道验签迁出 | `channel/application/services.py` 的 `_verify_signature` → `gateway/identity.py` |
| 补 `/v1/sessions` 的租户校验 | 或随 Stage 4a 直接删除该路由 |

**旧代码减少**：`channel/application/services.py` 的验签分支删除；`dispatch_subscriber.py` 的硬编码 `SYSTEM_USER_ID` / `SYSTEM_AGENT_ID` 删除。
**验收**：伪造签名 / 过期时间戳 / 跨租户重放全部拒绝且产生审计事件；鉴权失败的请求**有 trace_id**。

### Stage 3：Message Normalizer 收口

| 动作 | 细节 |
|---|---|
| 4 个 inbound adapter 改产出 `InboundMessage` | 补 tenant / workspace / channel / trace / attachments |
| 附件统一 | `AttachmentRef` + `AttachmentStoragePort` |
| **删除** `ParsedMessage` | 全仓无引用 |
| **删除** `ChannelMessageReceived` | 由 `InboundMessage` 取代（补 `external_message_id` / `trace_id` / `payload_hash`） |

**旧代码减少**：`ParsedMessage`、`ChannelMessageReceived`、IM 侧进程内 LRU 去重全部删除。
**验收**：5 种入口归一化后，除 `channel_type` / `raw_metadata` 外字段完全一致（参数化测试）；附件三套语义收敛为一个 `AttachmentRef`。

### Stage 4a：新实现接管（出站与切换，重放降级）

> **本阶段只上新，不删旧**。旧实现在本阶段打上 `@deprecated` + 调用打点，进入清理窗口。
>
> **开工前置**：Gateway Stage 0–3 已完成。**Session 层台账未清零不阻塞本阶段** —— 这是 `README.md` §3.3.1 的**豁免 E1**：Gateway 的接管本身只依赖「重复分支可降级」这一降级路径可用，不依赖 Session 的清理完成。

| 动作 | 细节 |
|---|---|
| `ResultSink` 落地 | 出站编码 + 卡片 + 降级规则 |
| 渠道入站切过来 | `receive_webhook` → `Gateway.accept` → Router |
| **切 IM 入口**（**原子**） | `dispatch_subscriber.py` → `Gateway.accept` → 新链路。**必须与 Session Stage 5b（删 `use_cases/*`）同一个 PR** —— 否则 IM 断（台账 §3.4 的「必须原子切换」条目） |
| `/v1/sessions*` 的 turn 部分 | 停用（打弃用标记），不立即删 |
| 第二套 turn 实现 | 停用（打弃用标记），不立即删 |
| `dispatch_subscriber.py` | 停用（打弃用标记），不立即删 |
| **给以上旧路径打点** | `qzdap_legacy_calls_total{entry="..."}`，供清理判定 |
| **重复请求降级路径** | 命中重复但 `session_events` 未就绪 → 返回 202 + turn_id + `replay_unavailable`（**不静默丢弃**） |

**旧代码减少**：无删除，但全部旧路径**进入弃用与观测状态**。
**验收**：四条入站路径全部经过 `Gateway.accept`；**旧路径的调用打点覆盖率 100%**（每个待清理的旧入口都有 `record_legacy_call("<编号>")`）；新路径流量占比 ≥ 95%；重复请求在降级路径下返回 202 而非报错。

> **归零判据属于 Stage 5 的进入条件，不在这里要求** —— Stage 4a 刚接管时旧路径必然还有残留流量（长连接、缓存、灰度中的客户端）。
>
> **对外声明**：Stage 4a 状态下，重复请求**不支持无感重放**，必须显式告知调用方（202 + `replay_unavailable`）。

### Stage 4b：启用无感重放（Session 就绪后）

> **开工前置（硬依赖，不豁免）**：Session Stage 4 已完成 —— `session_events` **真写真读**（落库 + 按 seq 读取），且 Session 提供 `EventStore.get_events(turn_id, after_seq)` 读取端口（见 `session-refactor-plan.md` §6）。
>
> **本阶段不豁免「不可结转」规则**：Session 台账清零前不得启用无感重放，因为重放的正确性直接依赖 Session 的事件落库语义。

| 动作 | 细节 |
|---|---|
| `Last-Event-ID` 重放 | 从 `session_events` 按 seq 重放 |
| 降级路径移除 | 重复命中 → 直接重放事件流，不再返回 202 |
| 重放一致性校验 | 重放内容与原始事件流的 seq 对齐 |

**旧代码减少**：无（能力补齐）。
**验收**：SSE 断开后带 `Last-Event-ID` 重连 → **重放拼接结果与原流 chunk 序列的 hash 相同**、seq 连续；重放不再走 202 降级路径。

### Stage 5：旧实现清理

> **进入条件（硬性）**：连续运行 **≥ 7 天** + 新路径流量占比 **≥ 95%** + `qzdap_legacy_calls_total{entry="…"}` 窗口内**累计为 0** + 窗口内无相关生产事故。指标未归零 → 不许进入本阶段，先查为什么还有人在调。

| 动作 | 细节 |
|---|---|
| 删 `/v1/sessions*` 的 turn 部分 | |
| **配合** Session Stage 5b：删第二套 turn 实现 | ⚠️ **本层不删**（台账 X2 的唯一 owner 是 Session）。本阶段只做「确认无残留调用方」，删除动作在 Session Stage 5b（与本层的「切 IM 入口」同 PR）—— 否则会与 Session 的删除 PR 互相冲突 |
| 删 `dispatch_subscriber.py` | ⚠️ **文件删除归本层（台账 G9）**，但**必须与「切 IM 入口」+ Session Stage 5b（删 `use_cases/*`）同一个 PR** |
| 删 `agent_sessions.metadata.recent_request_ids` 残留列 | 数据清理 |
| 删孤儿索引 / 废弃常量 | |
| 全仓扫描「第二实现」 | §11.3 的扫描脚本，**进 CI** |
| 更新 `cleanup-ledger.md` 状态 | 全部标记「已清理」 |
| 更新 `docs/copilot-chat-module-architecture.md` | 现状文档必须同步 |

**旧代码减少**：§9.4 删除清单**归零**。
**验收**：§11 的全部检查项通过；台账本层全部条目为「已清理」。

### 阶段与「旧代码减少」对照表

| 阶段 | 删除/替换的旧实现 | 量级 | 旧路径状态 |
|---|---|---|---|
| Stage 1 | `record_request_id` + `recent_request_ids` | ~25 行 | 直接删除（无调用方） |
| Stage 2 | IM 验签分支、硬编码系统身份 | ~60 行 | 直接删除（无调用方） |
| Stage 3 | `ParsedMessage`、`ChannelMessageReceived`、LRU 去重 | ~120 行 | 直接删除（无调用方） |
| Stage 4a | **本层 owner 部分**：`/v1/sessions*` turn 部分（台账 G7 / G8，~138 行）+ `dispatch_subscriber.py`（G9，272 行） | **~410 行** | **停用 + 打点**（进入清理窗口，Stage 5 才删） |
| Stage 4a | ⚠️ **本层不删**：`run_turn.py`（476 行）+ `run_turn_to_completion.py`（119 行） | **0** | **停用 + 打点** —— 台账 **X2 的唯一 owner 是 Session**，删除动作在 **Session Stage 5b**（与本层的「切 IM 入口」同 PR）。旧版把这两份文件的 ~595 行算进本层 Stage 4a / Stage 5 的「旧代码减少」—— **记在了别人的账上** |
| Stage 4b | —（仅启用重放能力） | 0 | — |
| Stage 5 | 上述**本层 owner 部分**（~410 行）+ 残留列、孤儿常量 | ~430 行 | 删除（台账本层条目清零） |

> **Stage 4 与 Stage 5 拆开的原因**：Stage 4 是「新实现接管」，需要旧实现留在场做流量对照与回退兜底；Stage 5 是「清理」，有客观的进入条件（连续运行 **≥ 7 天** + 新路径流量占比 **≥ 95%** + `qzdap_legacy_calls_total{entry="…"}` 窗口内**累计为 0** + 窗口内无相关生产事故）。合并成一个阶段就失去了对照期，也失去了回退窗口。

---

## 11. 验收标准

> **本层在系统级验收中的责任**：
> 本层负责系统级验收的 **#2（五种入口行为一致）· #3（重复消息只跑一次）的幂等侧 · #7（`unprotected` 不碰副作用）的判定侧**（完整清单见 [`README.md`](README.md) §7）。

### 11.1 功能验收

1. **归一化一致**：5 种入口（web / api / 飞书 / 企微 / 钉钉）经 `Gateway.accept` 后，除 `channel_type` / `raw_metadata` 外字段完全一致；
2. **幂等**：同一 `clientRequestId` 并发 10 次 → 只起 1 轮；
3. **幂等跨进程**：两个 worker 交替请求同一 `clientRequestId` → 只起 1 轮；
4. **幂等不误杀（两种）**：① 用户连发两条相同内容（「好的」）→ **两轮都跑**（weak 不抑制）；② 同一个 `clientRequestId` 在 24h（TTL）后重发 → **当作新消息受理**（过期不判重）；
5. **审批恢复路径也带幂等键**：审批决策触发的续跑请求（`decide_approval` → `stream_turn`）**必须携带与原轮次相同的 `clientRequestId`** → 连点两次「同意」只执行一次工具。
   > ⚠️ **这是 §1.3 那个安全洞在本层的责任**：现状 `copilot.py:474-482` 的 `decide_approval` 调用 `stream_turn` 时**不传 `clientRequestId`** → `record_request_id("")` 直接返回 `True` → 幂等被跳过 → 工具被再执行一次。
   > **归属**：审批校验本身归 Session（台账 **X7** 审批吞异常）；**幂等键在恢复路径的传递**归 **Gateway**（本层）—— 幂等键由 Gateway 生成并随轮次上下文传递，恢复时复用同一个键。**两侧都要做，只做一边不够。**
6. **审批不重复执行**：连续点两次「同意」→ 工具只执行一次（**依赖第 5 条的幂等键传递**）；
7. **出站降级保信息**：IM 渠道收到 `plan_proposed` → 收到编号文本列表，不是空；
8. **trace 贯穿**：鉴权失败的 webhook 请求在 trace 里可查；
9. **渠道 session 稳定**：同一飞书群的连续 3 条消息 → 同一个 `session_id`（**依赖 Router 就绪** —— 该项验证的是 Router 的会话映射，Gateway 只保证 `external_chat_id` 归一化稳定）；
10. **限流生效**：同一用户 1 分钟内超 N 次 → 第 N+1 次被拒（Web 429 / IM 不受理），且**被拒请求不产生 `session_inbox` 行**（限流在落库之前）；
11. **降级不静默**：`interactive_action` 在纯文本渠道 → 收到一条可回答的 `message` 提示，且 `interactive_degraded` 为真；
12. **收敛可判**：每个待清理的旧入口都有 `record_legacy_call("<编号>")` 打点，`/metrics` 可见。

### 11.2 架构测试

```python
# tests/architecture/test_gateway_boundary.py
FORBIDDEN = ("fastapi", "starlette", "sqlalchemy", "asyncpg", "psycopg")
SCAN_DIRS = ("backend/runtimes", "backend/modules/agent_runtime/application",
             "backend/modules/memory/application", "backend/modules/knowledge/application")

def test_no_framework_imports_in_runtime_layers():
    """runtime 层不得依赖框架 —— 由 §2.1 的边界判据派生。"""
    for path in _py_files(SCAN_DIRS):
        for mod in FORBIDDEN:
            assert mod not in _imports_of(path), f"{path} 引入了 {mod}"
```

另加：Gateway 之外的任何模块不得 import `qzdap_agent_runtime.gateway.types` 以外的 gateway 内部模块。

### 11.3 「没有第二套实现」的扫描

**扫描脚本的唯一来源是 [`cleanup-ledger.md`](cleanup-ledger.md) §3.1**，本层**不另写一份**（写两份必然漂移，且其中一份必然忘记排除 `tests/` —— 那会让 CI 永远红、脚本必然被绕过）。

Gateway 域对应的规则：

| 旧符号 | 台账条目 |
|---|---|
| `recent_request_ids` | G1 |
| `record_request_id` | G1 |
| `class ParsedMessage` | G4 |
| `ChannelMessageReceived` | G5 |
| `SYSTEM_USER_ID` / `SYSTEM_AGENT_ID` | G3 |
| `OrderedDict`（`modules/channel/` 内） | G6 |
| `/v1/sessions` | G7 / G8 |
| `dispatch_subscriber` | G9 |

> 启用时点：**Gateway Stage 5 合并时**，与旧实现删除在同一个提交里完成。

---

## 12. 风险与回退

| 风险 | 影响 | 缓解 |
|---|---|---|
| 幂等 claim 依赖 `session_inbox` 新约束，迁移失败 | 所有入站不可用 | 迁移在 Stage 0 先行 dev 验证；失败则回退整个切换提交 |
| 「无感重放」依赖 `session_events` 落库（Session 层） | 重复请求只能返回 202，无法重放 | 降级方案：`replay_unavailable` 标记 + 返回上次 turn_id；**不静默丢弃** |
| 渠道入站改造影响 4 个 IM 平台 | IM 消息中断 | 每个平台一个独立 PR，全部走同一 `Gateway.accept` 契约；先飞书后其余 |
| **仓外调用方依赖 `/v1/sessions*`** | 外部 404 | **前端已确认零使用**（2026-10-29 核实：`pathMap.ts` 会话条目全是 `/api/sessions*`）。**唯一风险是仓外调用方** → 由前置 **P-11（API owner 确认）** 兜底；确认无则 G7 / G8 在 Stage 5 直接删（保留期归零）；确认有则保留兼容别名 ≥95% 流量后 ≥7 天 |
| 去掉 `/v1/sessions*` 的 turn 部分 | 外部 API 使用方中断 | 该 API 无文档、无前端使用；打 deprecation 日志一个周期 |
| 幂等从「报错」变「无感」 | 用户感知行为变化 | 前端无需改动（SSE 重放对前端是同构的） |
| 附件仍存 `LargeBinary` | 数据量增长后 DB 膨胀 | 本方案不处理；单独立项迁对象存储 |

**回退策略**（按 §0.4 的「先上新、后清旧」）：

| 阶段 | 回退方式 |
|---|---|
| Stage 4a/4b（接管）之后、Stage 5（清理）之前 | `git revert` 切换提交即可回落旧实现——**旧实现仍在场，这就是保留清理窗口的收益**；必要时回滚迁移 |
| Stage 5（清理）之后 | 旧实现已删除，**回退需重新上线旧版本**——这是本方案明确接受的代价 |

全程**不留 feature flag 双跑**：清理窗口内的并存是「旧实现已弃用但仍可被回退调用」，不是「两套实现由开关选择」。

---

## 13. 治理与可观测性落点

### 13.1 治理落点（Governance）

| 本层步骤 | 闸门 | 拒绝 / 降级时的行为 |
|---|---|---|
| 入站验签 | `TrustLevel` 判定；未知渠道 → 拒绝 | 返回 `CHANNEL_NOT_FOUND`（渠道不存在）/ `CHANNEL_DISABLED`（渠道停用），写审计事件 |
| Auth Identity | 租户 / 工作区 / 用户解析失败 → 拒绝 | `AUTHENTICATION_FAILED`（401，验签 / JWT 失败）/ `FORBIDDEN`（403，身份有效但无权）；**不进入 Router** |
| 限流（§5） | 租户级 QPS / 日配额 | 超限 → `RATE_LIMITED`；**不落 `session_inbox`**（不污染幂等表） |
| 消息去重（§4.4 / §4.5） | `session_inbox` 唯一约束（§4.3 的表改造） | 命中 → **无感重放**；重放依赖未就绪 → 202 + `replay_unavailable` |
| 附件引用（§3.4） | 附件归属校验 | 不通过 → 丢弃该附件，**不丢弃整条消息** |

> **本层不拥有的治理**：会话级配额（Router）、工具白名单（Agent Loop / Execution）、记忆可见范围（Memory）。Gateway 只做**入口级**治理。

### 13.2 可观测性指标（Observability）

指标名一律进 `qzdap_*` 命名空间，实现落在 `backend/libs/observability/src/qzdap_observability/metrics.py`。

| 指标名 | 类型 | 标签 | 说明 |
|---|---|---|---|
| `qzdap_gateway_ingress_total` | Counter | `channel_type`, `trust_level` | 入站消息总数（按渠道与信任级别） |
| `qzdap_gateway_auth_failures_total` | Counter | `channel_type`, `reason` | 鉴权失败数（`reason`：签名/过期/未知租户…） |
| `qzdap_gateway_dedup_total` | Counter | `channel_type`, `outcome` | 去重命中数（`outcome`：`replayed` / `replay_unavailable` / `suppressed` / **`weak_recorded`** —— weak 键「记录但不抑制」，用它观测 unprotected 的比例） |
| `qzdap_gateway_rate_limited_total` | Counter | `tenant_id`, `scope` | 限流拒绝数 |
| `qzdap_gateway_ingress_duration_seconds` | Histogram | `channel_type` | 入站处理耗时（含验签 + 归一化 + 去重） |
| `qzdap_legacy_calls_total` | Counter | `entry` | **旧实现调用计数**，标签 `entry` 为台账编号（如 `X5`）。收敛判据依赖它 |

**Span 划分**（沿用现有 trace 基础设施）：

| Span | 父子关系 | 属性 |
|---|---|---|
| `gateway.accept` | 根 | `channel_type`, `external_message_id`, `trace_id` |
| `gateway.auth` | `gateway.accept` | `trust_level`, `auth_method` |
| `gateway.normalize` | `gateway.accept` | `source_kind`, `normalized` |
| `gateway.dedup` | `gateway.accept` | `outcome`, `idempotency_strength` |

**日志**：入站拒绝必须带 `trace_id` + `external_message_id` + `reason`，**不得记录消息正文**（含 PII）。

### 13.3 审计

| 事件 | 何时写 | 内容 |
|---|---|---|
| `gateway.ingress.rejected` | 验签 / 鉴权 / 限流拒绝 | 渠道、租户（若已知）、原因、trace_id |
| `gateway.dedup.replayed` | 重复消息被重放 | 幂等键、原 turn_id |

> 审计写入走 **Governance 模块**，Gateway 只投递事件，不直接写审计表。
---

## 附录 A：已定稿的决策（2026-10-29 逐条确认）

> **修订记录**：决策 #8（切换方式）在同日按用户「先上新、后清旧」的要求修订——由「一次性同时删」改为「Stage 4a 接管 + Stage 5 清理」（Stage 4b 待 Session 就绪）。其余 8 条维持原确认结果。

以下 **9 条**决策（#1–#9）已逐条确认并定稿，另有 **#2b**（`session_inbox` 表归属）于同日随一致性评审修订。**改动其中任何一条，都必须同步修改正文对应章节，并在 §10 补记受影响的阶段。**

| # | 决策 | 定稿结果 | 影响章节 | 备选（已被否决） |
|---|---|---|---|---|
| 1 | 出站归属 | **归 ① Channel Gateway**（与入站对称） | §6、§9.2 | 单列 Result Encoder（要维护两份渠道知识） |
| 2 | `modules/channel` 去向 | **保持独立模块**，实现 runtime 定义的 Protocol；Gateway 只持有端口 | §9.2、§9.3 | 协议适配器迁进 runtime（边界更干净，但要拆包、改多处 import） |
| 2b | `session_inbox` 表归属 | **表归 Session**（会话域），Gateway 只持 `IdempotencyStore` 端口；改造 DDL 仍在 Gateway 迁移 0044 | §2.3、§4.3、§8 | 表归 Gateway（与现状写法一致，但会让 Gateway 看起来拥有会话域存储） |
| 3 | `session_inbox` | **改造现有表**（加 6 列 + 换唯一约束 → **只覆盖 strong 的部分唯一索引**），不新建 v2 表 | §4.3、§4.4 | 新建 v2 表（现有表是空的，改造无迁移负担） |
| 4 | 重复时行为 | **无感重放**（按 `session_events` 的 seq 重放事件流）；依赖未就绪时降级为 202 + turn_id + `replay_unavailable` | §4.5、§0.5 | 返回 202 不重放 / 沿用 `DUPLICATE_REQUEST` 报错 |
| 5 | weak 强度 | **不抑制 + 标 `unprotected` + Agent Loop / Execution 禁用副作用工具** | §4.2、§4.3、§4.4、§0.5 | 照常抑制（误杀用户消息）/ 拒绝受理（IM 消息丢失） |
| 6 | 附件字节 | 本次**不迁对象存储**，只统一 `AttachmentRef` 形状并抽 `AttachmentStoragePort` | §3.4、§12 | 同期迁移（范围膨胀） |
| 7 | `/v1/sessions*` | 保留会话 CRUD **兼容别名**（打 deprecation 日志；保留期 = ≥95% 流量后 ≥7 天），删除其 turn 部分 | §9.4、Stage 4a | 立即全删 |
| 8 | 切换方式 | **先上新、后清旧**：Stage 4a 新实现接管（旧实现打弃用标记 + 打点，进入清理窗口），Stage 5 清理。Stage 4b（启用无感重放）待 Session 就绪，不豁免。**不留 feature flag 双跑**，但清理窗口内旧实现在场 | §0.4、§10、§12 | 一次性同时删（失去流量对照期与回退窗口）；灰度双跑（不采纳） |
| 9 | 限流的阈值与租户配额 | **硬编码 + 环境变量覆盖**（`QZDAP_RATE_LIMIT_*`），治理侧可配留待后续 | §5 | 治理模块 `policies` 表配置（引入新配置面） |

> **决策 #5 的落地方式（2026-10-29 审查补记）**：「不抑制」不能只写在文档里 —— §4.4 的原子 claim 是 `ON CONFLICT ... DO NOTHING`，**若 weak 键也参与唯一约束，两条内容相同、落在同一 `time_bucket` 的消息会互相冲突 → 第二条被抑制**，直接违反 #5。**落地方式是 §4.3 的部分唯一索引（`WHERE key_strength = 'strong'`）+ §4.4 的 strong / weak 两条 INSERT 路径。**

> **决策 #4 与 #5 的连带义务**（定稿时一并确认）：
> - #4 使 `session_events` 落库成为 Gateway 的**硬依赖** → 已登记进 §0.5 前置依赖清单；未就绪时必须走降级路径并标记，**禁止静默丢弃重复请求**。
> - #5 使「`unprotected` 轮次禁用副作用工具」成为 **Agent Loop / Execution 的强制义务** → Agent Loop / Execution 未落地前该策略只记录不生效，但**此期间不得启用任何有副作用的工具**，否则违反 #5 的前提。

## 附录 B：现状与目标的文件对照速查

| 现状文件 | 目标状态 |
|---|---|
| `modules/agent_runtime/adapter/http/session_router.py`（656 行） | 拆薄为 web 通道适配器（约 150 行）；turn 编排迁出 |
| `modules/agent_runtime/adapter/http/router.py`（`/v1/*`） | 删除 turn 部分；CRUD 部分并入统一会话 API |
| `modules/agent_runtime/application/use_cases/run_turn.py`（476 行） | **删除**，语义并入唯一 turn 实现。⚠️ **owner 是 Session**（台账 X2）—— 本层只「停用 + 打点」，删除在 **Session Stage 5b** |
| `modules/agent_runtime/application/use_cases/run_turn_to_completion.py`（119 行） | **删除**（同上，Session Stage 5b） |
| `modules/channel/adapter/dispatch/dispatch_subscriber.py`（272 行） | **删除**（台账 G9，**本层 owner**），渠道直接进 `Gateway.accept`；与 Session Stage 5b **同 PR** |
| `modules/channel/application/ports.py` `ParsedMessage` | **删除**，替换为 `InboundMessage` |
| `modules/channel/domain/events.py` `ChannelMessageReceived` | **删除**，替换为 `InboundMessage` |
| `modules/agent_runtime/adapter/persistence/repositories.py` `record_request_id` | **删除** |
| `runtimes/agent_runtime/src/qzdap_agent_runtime/channels/gateway.py` | 重写为 `gateway/channels.py` + `gateway/normalizer.py` |
| `runtimes/agent_runtime/src/qzdap_agent_runtime/engine.py` `ChannelGateway` | 迁到 `gateway/channels.py`；`SessionEngine` 留在 Session 方案 |
| （新增）`runtimes/agent_runtime/src/qzdap_agent_runtime/gateway/` | 四部分全部 |

## 附录 C：本轮重排记录（v1.3 → v1.4）

> **本轮不是新增设计，而是把散落的隐式约定收敛成显式结构。** 每一条都对应一次具体的可核对的问题。
> **「旧 §X」= 重排前的章节号**（供追溯），**「落点」列 = 重排后的位置**。

| # | 级别 | 问题 | 修正 | 落点 |
|---|---|---|---|---|
| **G-1** | 严重 | **旧 §0 缺共享模板的四个小节** —— 另五层都是「定位与范围（基线位置 / 子件 / 明确不做 / 收敛规则）+ 前置依赖」，本层把这些内容散在旧 §1（目标与边界）与旧 §0.1（前置依赖）里，横向对照时无法与其它层对齐 | 旧 §0 重写为 §0.1 基线位置 / §0.2 子件 / §0.3 明确不做 / §0.4 实现收敛规则 / §0.5 前置依赖清单；旧 §1.1、§1.2、§1.4 分别升入 §0.1、§0.3、§0.4 | §0 |
| **G-2** | 严重 | **旧 §1.2「选 agent / 选模型 / 判任务类型 → Router」违反 D1** —— D1 已定「模型由管理员在 agent 配置里绑定、运行时查表，**不做 Model Router**」；而「判任务类型」是 **Agent Router** 的职责，不在 Gateway → Router 这一跳 | 拆成三行：**选 agent（会话入口）→ Router** / **选专家 agent（每步推理）→ Agent Router** / **选模型·选工具 → 不选**（查表，Gateway 不产出偏好信号） | §0.3 |
| **G-3** | 严重 | **旧 §12 把「模型策略链」记成 Agent Router 欠 Gateway 的债** —— 该概念已被 D1 取消，继续留着会让实现方去找一条不存在的链 | 删除「模型策略链」，改为「专家选择的分类器」，并注明 Gateway 不产出模型 / 工具偏好信号 | §7 |
| **G-4** | 严重 | **旧 §4.3 `InboundMessage` 缺 `unprotected` 字段** —— 正文至少 6 处引用它（旧 §5.2 决策说明、旧 §5.4 weak 分支、旧 §5.6 传递链、旧 §7.0 标记表、旧 §10.1 验收 4、旧 §13.1 治理表），但 dataclass 里没有 → 实现方无处可写 | dataclass 补 `unprotected: bool`；并在设计要点里写明它由 ③ 的键强度推出、④ 不改写、兑现点在 Agent 的治理过滤 | §3.3 |
| **G-5** | 严重 | **附录 A 的表被一段引用块截断成两张表** —— 决策 #5 的「落地方式」注记夹在第 5 行与第 6 行之间，渲染时第 6–9 行变成一张没有表头的表 | 把该注记移到整表之后 | 附录 A |
| **G-6** | 严重 | **旧 §8 对照表把 Session 的删除量记到本层** —— Stage 4a / Stage 5 的「~700 行 / ~730 行」里含 `run_turn.py`（476 行）+ `run_turn_to_completion.py`（119 行），但台账 **X2 的唯一 owner 是 Session**（旧 §7.4 已写明「本层不删」），表格与正文自相矛盾 | 对照表拆两行：本层 owner 部分（`/v1/sessions*` turn ~138 行 + `dispatch_subscriber.py` 272 行 = **~410 行**）与「⚠️ 本层不删」（Session 的 ~595 行，量级记 **0**） | §10 对照表 |
| **G-7** | 中 | **限流被埋在「幂等与去重」里当小节** —— 限流是**入口闸门**（必须在落库之前），与幂等（防同一条消息跑两次）是两回事；混在一起时读者会以为限流 = 限重复 | 限流独立成章，并在开头写明它与幂等的区别 | §5 |
| **G-8** | 中 | **旧 §5.7 限流决策 #9 仍写成开放问题** —— 但附录 A 已把它列为定稿 | 正文改为「决策 #9（已定稿，2026-10-29）」 | §5 |
| **G-9** | 中 | **限流指标名与旧 §13.2 的指标表对不上** —— 旧 §5.7 写 `qzdap_rate_limited_total{channel}`，旧 §13.2 写 `qzdap_gateway_rate_limited_total{tenant_id, scope}` | 统一为 §13.2 的名字与标签，并补齐 `scope` | §5 |
| **G-10** | 中 | **旧 §5.7 的「实现位置」串用了 Memory 的层名「L1 接入层」** —— Gateway 没有 L1/A1 层划分（那是 Memory 的代码层命名） | 改为「① Channel Gateway（与 `identity.py` 同级，见 §2.2）」 | §5 |
| **G-11** | 中 | **`replay_unavailable` 的载体写错** —— 旧 §7.0 写「`InboundMessage` / 响应头」，但 `InboundMessage` 在 ③ 定型，而 `replay_unavailable` 是 ④ 的判定结果 | 载体改为 **`IdempotencyDecision` + 响应头**，并写明「不是 `InboundMessage` 字段」 | §9.0 |
| **G-12** | 中 | **章节顺序与其它层不一致** —— 本层把「数据表终态」放在实施阶段**之后**、「逐文件清单」放在数据表**之前**，与另五层（数据与表 → 逐文件 → 实施阶段）相反 | 重排为 §7 边界 / §8 数据与表 / §9 逐文件与删除清单 / §10 实施阶段 / §11 验收 / §12 风险 / §13 治理 | 全文 |
| **G-13** | 中 | **旧 §10.4「外部依赖的现状核实」挂在验收标准下面** —— 它是**现状盘点**（对外部依赖的核对结果），不是验收项 | 移入现状盘点，作为「外部依赖的现状核实」 | §1.6 |
| **G-14** | 轻 | **头部写「台账 G1–G9」，但台账实有 G1–G10**（G10 = 审批恢复路径丢失幂等键，Stage 1 就在正文里引用） | 头部改为 G1–G10 | 头部 |
| **G-15** | 轻 | **旧 §4.3 写「三条设计要点」，实际列了五条** | 改为「五条设计要点」，并补第 5 条（`unprotected` 的语义与兑现点） | §3.3 |
| **G-16** | 轻 | **`InboundMessage` 的字段数与 Router 方案的引用对不上** —— Router 方案写「17 个字段」，但 dataclass 实际是 **15 个**（补 `unprotected` 后为 **16 个**） | Router 方案改为「**16 个字段**」，并同步新的章节号 | §3.3 / Router 附录 A |

### C.1 Stage 1 实施带回的三处修正（v1.4 → v1.5，2026-10-29）

| # | 级别 | 问题 | 修正 | 落点 |
|---|---|---|---|---|
| **G-17** | 严重 | **审批键若掺入原轮次的键就不稳定** —— 审批恢复时原轮次状态已推进（`pending_approval` 被清空），原键取不到 → 同一个审批两次派生出的键**不同** → 连点两次「同意」挡不住（**G10 修不掉**） | 审批键固定为 `approval\|{approval_id}\|{decision}`，**只由审批自身的稳定标识派生**；§4.2 的阶梯补第 ④ 档并写明这条约束 | §4.2 / §4.4 |
| **G-18** | 中 | **§4.5 说重复命中要「返回 202 + turn_id」，但 Stage 1 没有 REST 重复入口** —— web 只有 SSE；前端已对 `DUPLICATE_REQUEST` 做静默忽略 | Stage 1 的重复分支**沿用 `DuplicateRequestError`**，把「不重复执行」定为硬要求、「无感重放」明确归 Stage 4b（依赖 `session_events`） | §4.5 |
| **G-19** | 中 | **「先幂等还是先抢会话占用」方案里没定** —— 两个次序的失败模式不同：先抢占用则并发同键会返回「会话忙」而非「重复」；先幂等则会话忙时键被消费，重试会被误判重复 | 定为**先幂等 claim、再抢占用**，并补「本轮没跑起来就释放键」（`IdempotencyStore.release`） | §10 Stage 1 |

**跨文档同步**（本轮一并改掉的对 Gateway 章节号的引用）：

| 文档 | 改动 |
|---|---|
| `README.md` | §5.1 结构表（补 Gateway 章节偏移说明）、§3.3 依赖表的 Gateway 引用、§8 外部前置依赖的引用、§2 决策状态表的 Gateway 行 |
| `implementation-plan.md` | §3.1 的 G-13b、§3.3 的 S-10b、§3.4 的 C-22、§3.1 标题「删除 G1–G10」 |
| `cleanup-ledger.md` | §5.4 的 Gateway 五行章节引用（§7.2 / §7.4 → §9.2 / §9.4） |
| `session-refactor-plan.md` | §9 边界表、§10.1 表终态、§6 幂等键传递链、§0.5 前置依赖对 Gateway 章节的引用 |
| `router-refactor-plan.md` | 附录 A 对 Gateway 表终态的引用、`InboundMessage` 字段数与章节号 |
| `context-refactor-plan.md` | §6 边界表、§8 的 Gateway 错误码契约引用 |
| `session-lifecycle-sequence.md` | 对 Gateway 目标架构章的引用 |
