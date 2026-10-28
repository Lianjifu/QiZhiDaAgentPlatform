# Gateway 层重构方案

> 版本：1.2（2026-10-29：按方案集统一更新——文档集入口、清理机制归属、阶段分期口径）
> 适用项目：`QiZhiDaAgentPlatform`
> 状态：**已定稿**（附录 A 的 8 条决策于 2026-10-29 逐条确认）
> 方案集入口：[`README.md`](README.md)
> 上位基线：**[`session-lifecycle-sequence.md`](session-lifecycle-sequence.md)** —— 会话完整生命周期的泳道划分与时序，本方案是其中 **Gateway 泳道**的展开
> 收敛机制：**[`cleanup-ledger.md`](cleanup-ledger.md)** —— 本方案对应条目 **G1–G9**
> 硬约束：**最终态只有一个实现**；先上新、后清旧（清理机制见 §1.4 与台账）

---

## 0. 本方案与上位方案的关系

上位方案 v3.1 把会话能力划成十项能力域、19 个 LangGraph 节点。经 2026-10-28 的代码核对，v3.1 已经产出了一套**合同完备但从未接线**的 runtime（`backend/runtimes/agent_runtime/`），而**唯一在生产跑的**是旧 Copilot 实现（`backend/modules/agent_runtime/`）。两套并存的原因与后果见 §2.4。

本方案是[会话生命周期基线](session-lifecycle-sequence.md)的 **Gateway 泳道**（该基线把会话拆为 Gateway / Router / Session / Context / Memory / Agent Loop / Agent Router / Execution 七条泳道 + Governance / Observability 两条横切）。它要解决的是：

1. 把 Gateway 的职责从「散落在 4 个入站路径里的隐式逻辑」变成**一个显式的、可独立验收的分层**；
2. **消灭入站侧的全部重复实现**——4 条入站路径、3 套会话 API、3 套幂等逻辑；
3. 给后面五层一个**稳定的标准数据契约**，让它们不再各自解析入参。

本方案**只覆盖 Gateway**（含入站归一化、身份、去重幂等、出站编码）。Session / Context / Memory / Agent 四层的重构在各自的方案里做，但本方案给出的契约是它们的前置条件。

### 0.1 前置依赖清单（本方案不实现，但阻塞本方案的哪一步）

| 依赖 | 归属层 | 阻塞 | 说明 |
|---|---|---|---|
| `session_events` 真写真读 | Session | **§5.5 无感重放** | 决策 #4 已定稿为「无感重放」，因此这是硬依赖。若 Session 层未先行落地，Gateway 的重复分支降级为「返回 202 + 上次 turn_id + 标 `replay_unavailable`」，**不得静默丢弃重复请求** |
| 唯一 turn 实现（claim / 幂等 / 取消 / 审批合一） | Session | §7.4、Stage 4 | 渠道入站改造要求下游只有一套 turn 语义；本方案 Stage 4 会连带删除第二套实现 |
| `LLMPort` 与真实 `agent` 节点 | Agent Loop | §5.2 的 `unprotected` 策略 | 决策 #5 已定稿为「不抑制 + 标 unprotected + 禁用副作用工具」，该策略由 Agent Loop（不选择副作用工具）与 Execution（拒绝执行）共同执行；两者未落地前，`unprotected` 标记只记录不生效（**此时不得启用任何有副作用的工具**，否则违反决策 #5 的前提） |
| `tool_executions` 幂等键传递 | Execution | §5.6 三层键传递链 | C 层幂等由 Execution 落地 |

> **依赖顺序建议**：Session 层的「`session_events` 落库」应先于本方案 Stage 4 落地；本方案 Stage 0–3 不受任何上游阻塞，可立即开工。

---

## 1. 目标与边界

### 1.1 一句话定位

> **Gateway 是平台与外部世界之间唯一的协议边界。**

它只做四件事：

1. **协议 → 标准数据**：把 HTTP / SSE / Webhook / 飞书 / 企微 / 钉钉的方言翻译成一套标准入站数据；
2. **身份 → 统一上下文**：把三种拿身份的方式（JWT principal、租户头、平台签名）收敛成一个 `ActorContext`；
3. **标准结果 → 协议**：把统一的 `ResultEvent` 编码成 SSE / IM 文本 / IM 卡片 / Webhook；
4. **边界上的横切**：验签、限流、去重、错误码映射、trace 贯穿、附件落地。

### 1.2 它明确不做

| 不做 | 归属 |
|---|---|
| 选 agent / 选模型 / 判任务类型 | Router |
| 建会话 / 起轮次 / 落库 | Session |
| 拼 prompt / 压缩 / 摘要 | Context |
| 召回与写入记忆 | Memory |
| 调 LLM / 跑工具 / 审批中断 | Agent Loop / Execution |

### 1.3 可测试的边界判据

> **把 Gateway 整个摘掉，剩下的五层应该完全不知道 HTTP、SSE、飞书这些词存在。**

这条判据直接落成一条架构测试（§10.2），比画框图有用。

### 1.4 实现收敛规则：最终态只有一个实现

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
| 1 | **弃用标记 + 观测** | 每个旧入口在被新实现接管时打 `@deprecated` + 打点 `qzdap_legacy_calls_total{path="..."}`，使「旧实现是否还在被调用」成为**可观测事实**，而不是靠人记得 |
| 2 | **删除条件客观化** | 清理触发条件 = 「新实现稳定运行 ≥ 1 个发布周期 **且** 该旧路径调用指标归零」。不靠「感觉没人用了」 |
| 3 | **台账化** | 全部旧实现登记在 [`cleanup-ledger.md`](cleanup-ledger.md)，每条含：旧实现位置 → 替代者 → 弃用标记 → 观测指标 → 删除条件 → 状态 → 所属方案 |
| 4 | **不可结转** | 某层的清理台账未清零，该层不得进入下一层的「切换」阶段；未完成项**不允许滚到下个迭代** |

**回退策略**：清理窗口内（旧实现尚在）可 `git revert` 切换提交直接回落；**清理完成后旧实现不复存在，回退需重新上线旧版本**——这是「先上新后清旧」的代价，写明在此以免误判。

§9 是逐文件的删除清单，§8 是每个阶段「旧代码减少了什么」的记录表。

---

## 2. 现状盘点

### 2.1 四条入站路径

| # | 路径 | 入口 | 数据形状 | 缺陷 |
|---|---|---|---|---|
| A | **Web Copilot** | `POST /api/sessions/{id}/turns/stream`<br/>`modules/agent_runtime/adapter/http/session_router.py:230` | body `{content, attachmentIds, clientRequestId, model?, route_id?}`<br/>+ `X-Tenant-Id` / `X-Workspace-Id` / `X-User-Id`<br/>+ `request.state.principal` | 身份有两套来源（header 与 principal）；租户靠客户端 header 自证 |
| B | **IM 渠道** | `POST /v1/channels/{cid}/webhook`<br/>`modules/channel/adapter/http/router.py:174` | `ParsedMessage{external_user_id, external_chat_id, external_message_id, text, metadata}`<br/>`modules/channel/application/ports.py:95` | **不含 tenant / workspace / channel / trace / attachments**；`text_preview` 被截到 200 字（`channel/domain/events.py:33`） |
| C | **通用会话 API** | `POST /v1/sessions`、`POST /v1/sessions/{sid}/turn/stream`<br/>`modules/agent_runtime/adapter/http/router.py:143,209` | 与 A 同族的 body，但走 `RunTurnUseCase` | **只有 `X-User-Id`，没有租户校验**；且走的是**另一套 turn 实现** |
| D | **渠道事件总线** | `ChannelMessageReceived` → `dispatch_subscriber.py`<br/>`modules/channel/adapter/dispatch/dispatch_subscriber.py:113` | 事件 payload（**丢掉了 `external_message_id`**） | 进程内 LRU 去重；每条消息新建 session |

### 2.2 三套会话 / turn 实现

| 实现 | 位置 | claim（并发互斥） | 幂等 | 取消 | 审批 | 谁在用 |
|---|---|---|---|---|---|---|
| **① Copilot** | `application/copilot.py` + `adapter/graph/runner.py` | ✅ `try_claim` CAS | ⚠️ metadata 存 8 个 id | ✅ 跨进程 | ⚠️ 决策不落库 | 前端 Copilot 页 |
| **② use_cases** | `application/use_cases/run_turn.py` + `run_turn_to_completion.py` | ❌ | ❌ | ❌ | ❌ | 渠道入站、子代理、catalog 评测 |
| **③ 新 runtime** | `runtimes/agent_runtime/` | ⚠️ 内存锁 | ❌（turn 级） | ❌ 仅日志 | ⚠️ 有 TTL 但无 `interrupt()` | **无人使用** |

三套语义长期漂移：同一个「跑一轮」，在①里有 claim/幂等/取消/审批，在②里一样都没有。

### 2.3 幂等 / 去重现状

| 层 | 现状 | 证据 |
|---|---|---|
| web 幂等 | 读 session → 改 `metadata.recent_request_ids` → 写回，**非原子**、只留 **8** 个、**无 TTL** | `modules/agent_runtime/adapter/persistence/repositories.py:155-170` |
| IM 去重 | **进程内 `OrderedDict` LRU（1024）**，重启失效、跨 worker 无效；哈希只含文本预览 | `modules/channel/adapter/dispatch/dispatch_subscriber.py:44,113-125,253-260` |
| 工具幂等 | 旧路径**无**；新 runtime 有（内存） | `runtimes/agent_runtime/src/qzdap_agent_runtime/execution/executor.py:108,142` |
| 审批幂等 | 新 runtime 有（TTL + 同 hash 复用）；旧路径无 | `runtimes/.../governance/approval.py:126,139` |
| 存储 | `session_inbox` 表**已建但无人使用**，schema 只适合 IM | `migrations/versions/0035_session_stage2_persistence.py:196-223` |

**🔴 已知安全洞：审批重复点击会重复执行工具。**
`decide_approval` 调用 `stream_turn` 时**不传 `clientRequestId`**（`application/copilot.py:474-482`）→ `record_request_id("")` 直接返回 `True` → 幂等被跳过 → 第一轮审批执行完工具后再点一次「同意」，`try_claim` 因上一轮已结束而放行 → **工具被再执行一次**。根因是双重的：审批决策不落库 + 幂等键在恢复路径缺失。

### 2.4 两套实现并存的由来（为什么不能再来一次）

2026-10-15 一天内，v3.1 方案被执行成 17 个提交（Stage 0 → Stage 8），产出 `backend/runtimes/agent_runtime/`：19 节点图、ports、ResultEvent、outbox 死信状态机、审批 TTL、EngineSwitch 灰度、数据治理接口——**全部到位**。

但 `grep qzdap_agent_runtime` 在 `composition/`、`modules/`、`libs/` 里**零命中**。每个 Stage 的退出条件都是「纯内存 fake 可编译图 / 契约断言通过」，于是 8 个 Stage 全部打勾，产品却 100% 仍跑旧路径。`EngineSwitch` 只在自己的单测里被调用（`runtimes/.../evaluation/__init__.py:261`）。

同期真实需求继续往旧路径上堆（10-16 ~ 10-18：mock-llm chunk、model Phase 1/2/3/7、copilot Phase 1.5/12、agent_factory Phase 19、sub-agent 真派发），旧路径越养越活。

> **教训（本方案的每一步都按它设计）**：验收标准必须写成「旧代码少了哪一块、且新路径在线上真实跑过一轮」，而不是「单测通过」。

### 2.5 已有可复用的资产

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

## 3. 目标架构：四部分

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

### 3.1 四部分的职责切分

| | ① Channel Gateway | ② Auth Identity | ③ Message Normalizer | ④ Idempotency Guard |
|---|---|---|---|---|
| 回答的问题 | 怎么到的 / 怎么回 | 你是谁 | 你说了什么 | 是不是同一条 |
| 拥有 | 传输绑定、渠道注册表、渠道能力、响应编码 | 身份材料、密钥、JWT 主体、角色、服务账号 | 协议→标准映射、附件、幂等键原料 | claim 结果、重复判定、重放决策 |
| 不拥有 | 身份语义、消息语义 | 消息语义、任何业务判断 | 任何业务判断、任何文本改写 | 不改消息、不决定 agent、不起轮次 |
| 变更频率 | 低 | 极低 | 高 | 中 |
| 主要失效模式 | 协议错配 | **安全** | 字段丢失、语义漂移 | 误杀 / 漏杀 |

变更频率差三档，所以必须分开——安全代码不能和天天在改的字段映射放同一个文件。

### 3.2 三条必须写死的顺序规则

**① 顺序是 ①→②→③→④，但「查渠道」在 ② 之前**
IM 验签必须针对**原始字节**，且要先知道用哪把密钥 → 密钥挂在渠道配置上 → 所以渠道实体查询属于 ①，验签属于 ②。**验签必须在解析之前**，不能让未验签 payload 进解析器（现状 `modules/channel/application/services.py:224` 的顺序正确，保留）。

**② `trace_id` 在 ① 建立，不是 ③**
IM 平台的 trace id（飞书 `X-Trace-Id` / 企微 `ReqParam.Trace-Id` / 钉钉 `eventId`）是传输层 header，第 ① 步就能拿到。若等到 ③ 才建立，**鉴权失败的请求就没有 trace**——而那恰是最需要被追踪的一类。

**③ 幂等「计算」在 ③，「落库与短路」在 ④**
④ 依赖一个 `IdempotencyStore` 端口，由 Session 提供实现（表 `session_inbox` 属于会话域）。**Gateway 不直接依赖 DB**，否则它会退化成第二个持久化模块。

---

## 4. 统一标准数据

### 4.1 `RawIngress`（① 产出）

```python
@dataclass(frozen=True, slots=True)
class RawIngress:
    transport: Literal["http", "sse", "webhook", "im"]
    channel_type: ChannelType          # web / api 为合成值
    channel_id: UUID | None             # 渠道实体 ID；web / api 无
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

### 4.2 `AuthenticatedIngress`（② 产出）

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
    workspace_id: UUID | None
    actor_id: UUID
    roles: tuple[str, ...]
    actor_kind: Literal["user", "service_account"]
```

> **信任模型差异必须保留**：web 的 actor 是「已认证用户带租户头」，IM 的 actor 是「平台签名证明的机器身份」。两者都归一成 `ActorContext`，但 `auth_method` / `trust` 不同，IM 的服务账号**不能当作用户权限使用**。
>
> 现状 IM 的 actor 是硬编码全局常量 `SYSTEM_USER_ID = 00000000-0000-0000-0000-00000000c0c0`（`modules/channel/adapter/dispatch/dispatch_subscriber.py:46`）→ 改为**渠道配置里登记的服务账号**。

### 4.3 `InboundMessage`（③ 产出，标准入站数据）

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
    # 幂等
    idempotency: IdempotencyKey
    external_message_id: str | None    # 平台原始 ID，审计用
    payload_hash: str
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

三条设计要点：

- **`raw_metadata` ≠ 原始 payload**。原始 body 在 ③ 结束后即丢弃（可能含敏感信息）；`raw_metadata` 是裁剪后的审计视图。现状 `ParsedMessage.metadata` 把协议细节和业务参数混在一起（`modules/channel/adapter/inbound/feishu.py:69` 把 `tenant_key`/`chat_type`/`message_type` 塞进去），下游无法区分 → 新标准里协议细节归 `raw_metadata`，业务参数才进标准字段。
- **`capabilities` 前置**。渠道支不支持卡片、交互、流式，在**入站时**就确定。现状是出站时才按 `channel_type` 硬判断。
- **不做任何文本改写**。Normalizer 只翻译格式，不清洗、不截断、不摘要用户输入。
- **不做会话 key 派生**。按生命周期基线（`session-lifecycle-sequence.md`），「外部会话标识 → 目标会话」的解析归 **Router**（「路由到会话」）。Gateway 只负责把外部标识规范化成 `external_chat_id` / `external_user_id`，**不生成 session_id、不查会话表**。

### 4.4 `AttachmentRef`（附件统一模型）

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

### 4.5 `ChannelCapabilities`（渠道能力声明）

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

## 5. 幂等与去重

### 5.1 三件事必须分开

| | A. 消息去重 | B. 轮次幂等 | C. 副作用幂等 |
|---|---|---|---|
| 语义 | 同一条**平台消息**投递两次 | 同一**客户端请求**重复到达 | 同一**工具调用**重试 |
| Key | `(tenant, workspace, channel, idempotency_key)` | `(session_id, idempotency_key)` | `(tool_call_id, idempotency_key)` + `request_hash` |
| 归属 | **Gateway（④）** | Session | Execution |
| 依赖 | ④ 原子 claim | `session_turns` 唯一约束 | `tool_executions` 唯一约束 |

Gateway 只负责 A，但 **A 的 key 必须原样传给 B 和 C**——否则三层键体系对不上（这正是现在的状态）。

### 5.2 键的构成与强度

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

**weak 的处理**（决策 #5 已定稿）：用户连发两条「好的」会被误杀，所以 weak **不做抑制，只记录**，并在 `InboundMessage` 上标记 `unprotected`。配套策略：**`unprotected` 的 turn 禁用有副作用的工具**（只允许只读工具），由 Agent Loop / Execution 执行——这样「没有幂等保护」不会静默变成「副作用可能重复执行」。

> web / api 的 strong 是常态（前端已在传 `clientRequestId`，`frontend/web/src/features/user/copilot/copilotApi.ts:43`）。缺失属异常 → 记 warning + 走 `unprotected`，**不静默降级为 weak 抑制**。

### 5.3 `session_inbox` 表改造

现状两个硬伤：`external_message_id` **NOT NULL**（web 塞不进 `clientRequestId` 语义）；唯一约束 `(tenant_id, channel_id, external_message_id)` **不含 `workspace_id`**，且没有键来源 / 强度 / 过期概念。

```sql
-- migrations/versions/0040_gateway_inbox_idempotency.py
ALTER TABLE session_inbox
    ALTER COLUMN external_message_id DROP NOT NULL,
    ADD COLUMN idempotency_key  String(128) NOT NULL,
    ADD COLUMN key_source       String(32)  NOT NULL,
    ADD COLUMN key_strength     String(8)   NOT NULL,
    ADD COLUMN status           String(16)  NOT NULL DEFAULT 'received',
    ADD COLUMN claimed_at       TIMESTAMPTZ,
    ADD COLUMN expires_at       TIMESTAMPTZ NOT NULL;

ALTER TABLE session_inbox DROP CONSTRAINT uq_session_inbox_dedup;
ALTER TABLE session_inbox
    ADD CONSTRAINT uq_session_inbox_idem
    UNIQUE (tenant_id, workspace_id, channel_id, idempotency_key);

CREATE INDEX ix_session_inbox_expires ON session_inbox (expires_at);
```

`status` 取值：`received`（已收未 claim）→ `claimed`（已 claim，处理中）→ `completed`（本轮已完成）；异常分支 `abandoned`。

### 5.4 原子 claim

```sql
INSERT INTO session_inbox
    (tenant_id, workspace_id, channel_id, idempotency_key, key_source, key_strength,
     external_message_id, payload_hash, status, claimed_at, expires_at, trace_id)
VALUES (...)
ON CONFLICT (tenant_id, workspace_id, channel_id, idempotency_key) DO NOTHING
RETURNING id, status, turn_id;
```

- **返回一行** → 新消息，我方接管 → 继续往下走；
- **返回 0 行** → 重复 → 查回那一行，按下表分支。

| 查回状态 | 含义 | 动作 |
|---|---|---|
| `completed` | 上一轮已完成 | **重放**该 turn 的事件流（§5.5） |
| `claimed`（未超时） | 正在处理 | 返回「处理中」，或挂等该 turn 的事件流 |
| `claimed`（已超时） | 处理方崩溃 | **接管**：重置 `claimed_at`，重跑 |
| `received` | 前一处理方在 claim 前崩溃 | 接管 |

崩溃超时阈值沿用旧路径 `try_claim` 的经验（`modules/agent_runtime/adapter/persistence/repositories.py:85-108` 的 30 分钟僵尸接管）。

### 5.5 重复时返回什么

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

> **依赖声明**（决策 #4 已定稿）：本方案把「事件落库 + 重放」作为**前置依赖**。若 Session 层的方案尚未落地，Gateway 的重复分支只能降级为「返回 202 + 上次 turn_id，不重放事件」，并在 `InboundMessage` 上标记 `replay_unavailable`。**不得静默地丢弃重复请求。** 前置依赖清单见 §0.1。

### 5.6 三层键的传递链

```
Gateway   InboundMessage.idempotency.value        (strong / weak + source)
   ↓
Session   session_turns.idempotency_key            UNIQUE (session_id, idempotency_key)   ✅ 表已建
   ↓
Agent     tool_executions.idempotency_key (UNIQUE) + request_hash                        ✅ 表已建
```

---

## 6. 出站：统一编码与投递

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
| `interactive_action` | 交互卡片 | **丢弃并记 degraded**（无法在纯文本渠道表达） |
| `usage` / `done` / `error` | 折叠或忽略 | 忽略（不打扰用户） |

原则：**降级必须保信息**。唯一的例外是 `interactive_action`——它在纯文本渠道无法表达，此时应记 `degraded` 而非静默丢弃。

投递失败 → 重试 → 死信（复用 `runtimes/.../outbox/__init__.py` 的 8 次 + 指数退避 + jitter 状态机）。

---

## 7. 逐文件改造清单

### 7.1 新增（`backend/runtimes/agent_runtime/src/qzdap_agent_runtime/gateway/`）

| 文件 | 内容 |
|---|---|
| `types.py` | `RawIngress` / `AuthenticatedIngress` / `InboundMessage` / `ActorContext` / `AttachmentRef` / `ChannelCapabilities` / `IdempotencyKey` |
| `identity.py` | `IdentityVerifier` Protocol、`TrustLevel`、`AuthMethod` |
| `normalizer.py` | `MessageNormalizer` Protocol + 按 `channel_type` 分派 |
| `idempotency.py` | `IdempotencyGuard`、`IdempotencyStore` Protocol、`IdempotencyDecision` |
| `channels.py` | `ChannelGateway`：渠道注册表、入站分派、出站编解码、能力声明 |
| `facade.py` | `Gateway.accept(raw) -> InboundMessage \| Duplicate`；`Gateway.emit(event)` |
| `errors.py` | `ErrorCode` → 多渠道文案投影表 |

### 7.2 迁移（旧代码 → 新位置）

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

### 7.3 保留但改造

| 文件 | 改造点 |
|---|---|
| `modules/channel/adapter/http/router.py` | 保留渠道 CRUD 端点；webhook 端点改为薄壳调用 `Gateway.accept` |
| `modules/channel/application/services.py` | 保留 `ChannelService`（渠道 CRUD + 密文轮换）；移除验签与投递职责 |
| `modules/agent_runtime/adapter/http/sse.py` | 保留 SSE 编码器；新增 `Last-Event-ID` 支持 |
| `libs/auth/src/qzdap_auth/middleware.py` | 保留；其产出的 principal 转为 `ActorContext` |

### 7.4 删除清单（Stage 4 停用 + 打点 → Stage 5 删除）

| 类别 | 具体 |
|---|---|
| 旧数据类 | `ParsedMessage`（`modules/channel/application/ports.py:95`） |
| 旧去重逻辑 | `dispatch_subscriber.py` 的 `OrderedDict` LRU（`:44`）、`_message_key`（`:253-260`） |
| 旧幂等逻辑 | `repositories.py:155-170` `record_request_id`；`session.metadata.recent_request_ids` 字段与所有读写 |
| 旧硬编码身份 | `dispatch_subscriber.py:42-46` `SYSTEM_USER_ID` / `SYSTEM_AGENT_ID` |
| 旧入站形状 | `channel/domain/events.py` 的 `ChannelMessageReceived`（缺 `external_message_id` / `trace_id`）→ 由 `InboundMessage` 取代 |
| 旧会话 API | `/v1/sessions*`（`modules/agent_runtime/adapter/http/router.py:143-280`）与 `/api/sessions*`（`session_router.py`）**合并为一套** |
| 旧 turn 实现 | `application/use_cases/run_turn.py`、`run_turn_to_completion.py` 与 `application/copilot.py` 的 **turn 编排部分合并为一套**（保留 `copilot.py` 的 claim / 幂等 / 取消 / 审批语义为唯一实现） |
| 旧路由 | `session_router.py:541` 的 `GET /v1/sessions`（与 `/api/sessions` 语义重复） |
| 孤儿表 | 无（`session_inbox` / `session_turns` / `session_events` / `tool_executions` **保留并启用**，不是删除对象） |

> **注意**：`/v1/sessions*` 与 `/api/sessions*` 的合并涉及前端契约。前端目前只用 `/api/*`（`frontend/web/src/features/user/copilot/copilotApi.ts`）与 `/v1/sessions`（列表）。合并方案：**外部路径保持 `/api/sessions*` 不变**（前端零改动），`/v1/sessions*` 只保留一个兼容别名并打 deprecation，**一个发布周期后删除**。

---

## 8. 实施阶段

> 每阶段的验收都包含「**旧代码减少了什么**」这一栏。缺这一栏的阶段不算完成。

### Stage 0：契约与地基（不改行为）

| 动作 | 产出 |
|---|---|
| 建 `gateway/` 骨架 + `types.py` | 4 个类型定稿 |
| 扩 `ErrorCode` 投影表 | `libs/schema/.../errors.py` 加 `ERROR_PROJECTION`（http / im / web 三套文案） |
| 迁移 0040 | `session_inbox` 加列改约束 |
| 建架构测试 | §10.2 的 import 禁令 |

**旧代码减少**：无（纯新增）。
**验收**：类型有单测；迁移可在 dev 库跑通；架构测试通过。

### Stage 1：Idempotency Guard 落地（先做，因为它不依赖其他层）

| 动作 | 细节 |
|---|---|
| `IdempotencyStore` 端口 + SQL 实现 | `INSERT ... ON CONFLICT DO NOTHING RETURNING` |
| `Gateway.accept` 编排 | ①→②→③→④ 四步串起来 |
| web 入站切过来 | `session_router.py` 的 `stream_turn` 改为先过 `Gateway.accept` |
| **删除** | `repositories.py:155-170` `record_request_id` + `session.metadata.recent_request_ids` 全部读写 |

**旧代码减少**：`record_request_id` 删除；`recent_request_ids` 从 `agent_sessions.metadata` 消失。
**验收**：
- 同一 `clientRequestId` 重复 10 次并发 → 只起 1 轮，其余 9 次返回 `Duplicate`；
- 不同 `clientRequestId` 并发 → 1 轮成功 + 9 次 `SESSION_BUSY`（不重复执行）；
- 幂等窗口 24h 内有效（跨进程验证：两个 worker 交替请求）。

### Stage 2：Auth Identity 收口

| 动作 | 细节 |
|---|---|
| `IdentityVerifier` 端口 | web(JWT) / IM(HMAC) / internal 三种实现 |
| 服务账号物化 | IM 的 actor 从渠道配置读，不再用全局常量 |
| 渠道验签迁出 | `channel/application/services.py` 的 `_verify_signature` → `gateway/identity.py` |
| 补 `/v1/sessions` 的租户校验 | 或随 Stage 4 直接删除该路由 |

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

### Stage 4：新实现接管（出站与切换）

> **开工前置**：Session 层的「`session_events` 真写真读」必须已落地（决策 #4 的硬依赖，见 §0.1）。未落地时本阶段**可以开工但不能启用重放**——重复分支走降级路径（202 + turn_id + `replay_unavailable`），并在合并说明里写明「重放待 Session 层上线后开启」。
>
> **本阶段只上新，不删旧**。旧实现在本阶段打上 `@deprecated` + 调用打点，进入清理窗口。

| 动作 | 细节 |
|---|---|
| `ResultSink` 落地 | 出站编码 + 卡片 + 降级规则 |
| `Last-Event-ID` 重放 | 依赖 `session_events` 落库（Session 层前置，见 §0.1） |
| 渠道入站切过来 | `receive_webhook` → `Gateway.accept` → Router |
| `/v1/sessions*` 的 turn 部分 | 停用（打弃用标记），不立即删 |
| 第二套 turn 实现 | 停用（打弃用标记），不立即删 |
| `dispatch_subscriber.py` | 停用（打弃用标记），不立即删 |
| **给以上旧路径打点** | `qzdap_legacy_calls_total{path="..."}`，供清理判定 |

**旧代码减少**：无删除，但全部旧路径**进入弃用与观测状态**。
**验收**：四条入站路径全部经过 `Gateway.accept`；旧路径调用指标归零。

### Stage 5：旧实现清理

> **进入条件（硬性）**：Stage 4 的旧路径调用指标**归零**且**已稳定运行 ≥ 1 个发布周期**。指标未归零 → 不许进入本阶段，先查为什么还有人在调。

| 动作 | 细节 |
|---|---|
| 删 `/v1/sessions*` 的 turn 部分 | |
| 删第二套 turn 实现 | `use_cases/run_turn.py` + `run_turn_to_completion.py` 与 `copilot.py` 合并 |
| 删 `dispatch_subscriber.py` | |
| 删 `agent_sessions.metadata.recent_request_ids` 残留列 | 数据清理 |
| 删孤儿索引 / 废弃常量 | |
| 全仓扫描「第二实现」 | §10.3 的扫描脚本，**进 CI** |
| 更新 `cleanup-ledger.md` 状态 | 全部标记「已清理」 |
| 更新 `docs/copilot-chat-module-architecture.md` | 现状文档必须同步 |

**旧代码减少**：§7.4 删除清单**归零**。
**验收**：§10 的全部检查项通过；台账本层全部条目为「已清理」。

### 阶段与「旧代码减少」对照表

| 阶段 | 删除/替换的旧实现 | 量级 | 旧路径状态 |
|---|---|---|---|
| Stage 1 | `record_request_id` + `recent_request_ids` | ~25 行 | 直接删除（无调用方） |
| Stage 2 | IM 验签分支、硬编码系统身份 | ~60 行 | 直接删除（无调用方） |
| Stage 3 | `ParsedMessage`、`ChannelMessageReceived`、LRU 去重 | ~120 行 | 直接删除（无调用方） |
| Stage 4 | `/v1/sessions*` turn 部分、`run_turn.py`、`run_turn_to_completion.py`、`dispatch_subscriber.py` | **~700 行** | **停用 + 打点**（进入清理窗口，Stage 5 才删） |
| Stage 5 | 上述 ~700 行 + 残留列、孤儿常量 | ~730 行 | 删除（台账清零） |

> **Stage 4 与 Stage 5 拆开的原因**：Stage 4 是「新实现接管」，需要旧实现留在场做流量对照与回退兜底；Stage 5 是「清理」，有客观的进入条件（调用指标归零 + 稳定运行 ≥ 1 个发布周期）。合并成一个阶段就失去了对照期，也失去了回退窗口。

---

## 9. 数据表终态

| 表 | 归属 | 状态 |
|---|---|---|
| `agent_sessions` | Session | 保留（`metadata.recent_request_ids` 字段随 Stage 5 删除） |
| `agent_turns` | Session | **保留**（现状在用） |
| `agent_session_messages` | Session | **保留**（现状在用） |
| `copilot_attachments` | Gateway | 保留（本方案不迁字节） |
| `session_inbox` | Gateway（④） | **启用 + 改造**（加列改约束） |
| `session_turns` | Session | 启用（B 层幂等） |
| `session_events` | Session | 启用（重放前置） |
| `tool_executions` | Execution | 启用（C 层幂等） |
| `outbox_dead_letters` | Session | 启用（出站投递） |
| `langgraph_checkpoints` / `langgraph_store` | Agent Loop | 由 Agent Loop 方案决定 |

> **本方案不新建任何表**，只改造 `session_inbox` 一张已存在但未使用的表。

---

## 10. 验收标准

### 10.1 功能验收

1. **归一化一致**：5 种入口（web / api / 飞书 / 企微 / 钉钉）经 `Gateway.accept` 后，除 `channel_type` / `raw_metadata` 外字段完全一致；
2. **幂等**：同一 `clientRequestId` 并发 10 次 → 只起 1 轮；
3. **幂等跨进程**：两个 worker 交替请求同一 `clientRequestId` → 只起 1 轮；
4. **幂等不误杀**：用户连发两条相同内容（「好的」）→ **两轮都跑**（weak 不抑制）；
5. **审批不重复执行**：连续点两次「同意」→ 工具只执行一次；
6. **出站降级保信息**：IM 渠道收到 `plan_proposed` → 收到编号文本列表，不是空；
7. **trace 贯穿**：鉴权失败的 webhook 请求在 trace 里可查；
8. **渠道 session 稳定**：同一飞书群的连续 3 条消息 → 同一个 `session_id`。

### 10.2 架构测试

```python
# tests/architecture/test_gateway_boundary.py
FORBIDDEN = ("fastapi", "starlette", "sqlalchemy", "asyncpg", "psycopg")
SCAN_DIRS = ("backend/runtimes", "backend/modules/agent_runtime/application",
             "backend/modules/memory/application", "backend/modules/knowledge/application")

def test_no_framework_imports_in_runtime_layers():
    """runtime 层不得依赖框架 —— 由 §1.3 的边界判据派生。"""
    for path in _py_files(SCAN_DIRS):
        for mod in FORBIDDEN:
            assert mod not in _imports_of(path), f"{path} 引入了 {mod}"
```

另加：Gateway 之外的任何模块不得 import `qzdap_agent_runtime.gateway.types` 以外的 gateway 内部模块。

### 10.3 「没有第二套实现」的扫描脚本

```bash
# 在对应层的 Stage 5 合并时启用并进 CI；命中即失败
grep -rn "recent_request_ids" backend/ && exit 1
grep -rn "record_request_id" backend/ && exit 1
grep -rn "class ParsedMessage" backend/ && exit 1
grep -rn "ChannelMessageReceived" backend/ && exit 1
grep -rn "SYSTEM_USER_ID\|SYSTEM_AGENT_ID" backend/ && exit 1
grep -rn "OrderedDict" backend/modules/channel/ && exit 1
grep -rn "RunTurnCompletionUseCase" backend/ && exit 1
grep -rn "\"/v1/sessions" backend/ && exit 1
```

---

## 11. 风险与回退

| 风险 | 影响 | 缓解 |
|---|---|---|
| 幂等 claim 依赖 `session_inbox` 新约束，迁移失败 | 所有入站不可用 | 迁移在 Stage 0 先行 dev 验证；失败则回退整个切换提交 |
| 「无感重放」依赖 `session_events` 落库（Session 层） | 重复请求只能返回 202，无法重放 | 降级方案：`replay_unavailable` 标记 + 返回上次 turn_id；**不静默丢弃** |
| 渠道入站改造影响 4 个 IM 平台 | IM 消息中断 | 每个平台一个独立 PR，全部走同一 `Gateway.accept` 契约；先飞书后其余 |
| 前端依赖 `/v1/sessions` | 前端 404 | 保留兼容别名一个发布周期，Stage 5 后删；前端已切 `/api/*` |
| 去掉 `/v1/sessions*` 的 turn 部分 | 外部 API 使用方中断 | 该 API 无文档、无前端使用；打 deprecation 日志一个周期 |
| 幂等从「报错」变「无感」 | 用户感知行为变化 | 前端无需改动（SSE 重放对前端是同构的） |
| 附件仍存 `LargeBinary` | 数据量增长后 DB 膨胀 | 本方案不处理；单独立项迁对象存储 |

**回退策略**（按 §1.4 的「先上新、后清旧」）：

| 阶段 | 回退方式 |
|---|---|
| Stage 4（接管）之后、Stage 5（清理）之前 | `git revert` 切换提交即可回落旧实现——**旧实现仍在场，这就是保留清理窗口的收益**；必要时回滚迁移 |
| Stage 5（清理）之后 | 旧实现已删除，**回退需重新上线旧版本**——这是本方案明确接受的代价 |

全程**不留 feature flag 双跑**：清理窗口内的并存是「旧实现已弃用但仍可被回退调用」，不是「两套实现由开关选择」。

---

## 12. 与其余泳道的衔接

按生命周期基线（`session-lifecycle-sequence.md`）的泳道划分，Gateway 的下游是 7 条泳道：

| 泳道 | 本方案给它的契约 | 它欠本方案的 |
|---|---|---|
| **Router** | `InboundMessage`（含 `actor` / `capabilities` / `idempotency` / `external_chat_id` / `external_user_id`）；会话 key 的派生**归 Router**，本方案不做 | 无（见 [`router-refactor-plan.md`](router-refactor-plan.md)） |
| **Session** | `IdempotencyStore` 实现（`session_inbox` 表）；`InboundMessage.idempotency.value` 写入 `session_turns.idempotency_key` | `session_events` 落库（重放前置）、`session_turns` 启用、唯一 turn 实现 |
| **Context** | `AttachmentRef.text_preview`；`actor` 供租户上下文 | 无 |
| **Memory** | `actor.actor_id` / `tenant_id`（`owner_id` 从此取得，不再靠 `X-User-Id` header） | 无 |
| **Agent Loop** | `idempotency.value` 传入 `tool_executions.idempotency_key`；`unprotected` 标记用于禁用副作用工具；记忆写入的触发点在 Agent Loop（Observe/Evaluate 之后），不在 Session | `LLMPort`、真实 `agent` 节点、`MemoryPort` |
| **Agent Router** | 无直接契约（经 Agent Loop 传递） | 模型策略链、`task_kind` 分类器 |
| **Execution** | `idempotency.value` → `tool_executions.idempotency_key` + `request_hash`（副作用幂等） | 统一执行器（重试/超时/熔断） |

**横切**：Governance 与 Observability 作用于所有泳道；本方案只保证 Gateway 自身在治理与观测下的行为正确（鉴权失败有审计与 trace、幂等命中可观测）。

---

## 附录 A：已定稿的决策（2026-10-29 逐条确认）

> **修订记录**：决策 #8（切换方式）在同日按用户「先上新、后清旧」的要求修订——由「一次性同时删」改为「Stage 4 接管 + Stage 5 清理」。其余 7 条维持原确认结果。

以下 8 条决策已逐条确认并定稿。**改动其中任何一条，都必须同步修改正文对应章节，并在 §8 补记受影响的阶段。**

| # | 决策 | 定稿结果 | 影响章节 | 备选（已被否决） |
|---|---|---|---|---|
| 1 | 出站归属 | **归 ① Channel Gateway**（与入站对称） | §6、§7.2 | 单列 Result Encoder（要维护两份渠道知识） |
| 2 | `modules/channel` 去向 | **保持独立模块**，实现 runtime 定义的 Protocol；Gateway 只持有端口 | §7.2、§7.3 | 协议适配器迁进 runtime（边界更干净，但要拆包、改多处 import） |
| 3 | `session_inbox` | **改造现有表**（加 6 列 + 换唯一约束），不新建 v2 表 | §5.3 | 新建 v2 表（现有表是空的，改造无迁移负担） |
| 4 | 重复时行为 | **无感重放**（按 `session_events` 的 seq 重放事件流）；依赖未就绪时降级为 202 + turn_id + `replay_unavailable` | §5.5、§0.1 | 返回 202 不重放 / 沿用 `DUPLICATE_REQUEST` 报错 |
| 5 | weak 强度 | **不抑制 + 标 `unprotected` + Agent Loop / Execution 禁用副作用工具** | §5.2、§0.1 | 照常抑制（误杀用户消息）/ 拒绝受理（IM 消息丢失） |
| 6 | 附件字节 | 本次**不迁对象存储**，只统一 `AttachmentRef` 形状并抽 `AttachmentStoragePort` | §4.4、§11 | 同期迁移（范围膨胀） |
| 7 | `/v1/sessions*` | 保留会话 CRUD **兼容别名一个发布周期**（打 deprecation 日志），删除其 turn 部分 | §7.4、Stage 4 | 立即全删 |
| 8 | 切换方式 | **先上新、后清旧**：Stage 4 新实现接管（旧实现打弃用标记 + 打点，进入清理窗口），Stage 5 清理。**不留 feature flag 双跑**，但清理窗口内旧实现在场 | §1.4、§8、§11 | 一次性同时删（失去流量对照期与回退窗口）；灰度双跑（不采纳） |

> **决策 #4 与 #5 的连带义务**（定稿时一并确认）：
> - #4 使 `session_events` 落库成为 Gateway 的**硬依赖** → 已登记进 §0.1 前置依赖清单；未就绪时必须走降级路径并标记，**禁止静默丢弃重复请求**。
> - #5 使「`unprotected` 轮次禁用副作用工具」成为 **Agent Loop / Execution 的强制义务** → Agent Loop / Execution 未落地前该策略只记录不生效，但**此期间不得启用任何有副作用的工具**，否则违反 #5 的前提。

## 附录 B：现状与目标的文件对照速查

| 现状文件 | 目标状态 |
|---|---|
| `modules/agent_runtime/adapter/http/session_router.py`（656 行） | 拆薄为 web 通道适配器（约 150 行）；turn 编排迁出 |
| `modules/agent_runtime/adapter/http/router.py`（`/v1/*`） | 删除 turn 部分；CRUD 部分并入统一会话 API |
| `modules/agent_runtime/application/use_cases/run_turn.py`（476 行） | **删除**，语义并入唯一 turn 实现 |
| `modules/agent_runtime/application/use_cases/run_turn_to_completion.py` | **删除** |
| `modules/channel/adapter/dispatch/dispatch_subscriber.py` | **删除**，渠道直接进 `Gateway.accept` |
| `modules/channel/application/ports.py` `ParsedMessage` | **删除**，替换为 `InboundMessage` |
| `modules/channel/domain/events.py` `ChannelMessageReceived` | **删除**，替换为 `InboundMessage` |
| `modules/agent_runtime/adapter/persistence/repositories.py` `record_request_id` | **删除** |
| `runtimes/agent_runtime/src/qzdap_agent_runtime/channels/gateway.py` | 重写为 `gateway/channels.py` + `gateway/normalizer.py` |
| `runtimes/agent_runtime/src/qzdap_agent_runtime/engine.py` `ChannelGateway` | 迁到 `gateway/channels.py`；`SessionEngine` 留在 Session 方案 |
| （新增）`runtimes/agent_runtime/src/qzdap_agent_runtime/gateway/` | 四部分全部 |
