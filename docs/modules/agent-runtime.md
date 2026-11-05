# agent_runtime — 对话运行时

> 能力域之一，**平台的核心**。负责会话生命周期、一次 turn 的编排、SSE 流式输出、多智能体派发、智能体目录。

这是整个平台的中心：「会话」在���里不是一段聊天记录，而是**某个智能体的某个版本在跑**。

## 职责

- 会话与轮次的生命周期管理（创建 / 查询 / 关闭 / 归档 / 取消）
- 一次 turn 的完整编排：幂等 → 排队 → 装配上下文 → 推理 → 调工具 → 回灌 → 收尾
- SSE 流式输出（17 种 chunk）
- 多智能体协同（派给子智能体、每步选专家）
- 工具审批的挂起与恢复
- 智能体目录（管理员侧的 agent 配置与版本）
- 附件上传与产物下载

## 源码位置

```
backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/
├── domain/          entities.py（Session/Turn）· catalog.py（CatalogAgent）· errors.py · events.py
├── application/
│   ├── copilot.py            CopilotSessionService（会话编排门面）
│   ├── turn_entry.py         TurnEntryService（跑一轮的入口）
│   ├── one_shot_turn.py      OneShotTurnService（一次性问答 / 子 agent 用）
│   ├── channel_turn.py       ChannelTurnService（IM 渠道回合）
│   ├── catalog.py            AgentCatalogService（智能体目录）
│   ├── ports/                本模块用到的端口定义
│   └── use_cases/            CreateSessionUseCase · DelegateSubagentUseCase …
└── adapter/
    ├── http/         session_router.py · catalog_router.py · sse.py · attachments.py · artifacts.py
    ├── graph/        runner.py（SessionGraphRunner）· agent_loop.py · tools.py · state.py
    ├── turn/         executor.py · lifecycle.py · cancel.py · session_state.py
    ├── persistence/  models.py · catalog_models.py · session_journal.py · idempotency_store.py …
    ├── tools/        tool_binding_adapter.py · catalog_binding_reader.py
    ├── knowledge/    knowledge_service_adapter.py
    ├── memory/       memory_service_adapter.py
    ├── sandbox/      sandbox_adapter.py · http_client.py
    ├── llm/          模型调用适配
    └── subscribers/  agent_factory_release_subscriber.py（版本发布订阅）
```

循环本体在契约层（不在本模块）：

```
backend/runtimes/agent_runtime/src/qzdap_agent_runtime/
├── agent_loop/       runner.py · reason.py · evaluate.py · observe.py · expert.py · state.py
├── context/          builder.py（上下文装配）· compressor.py · prompts.py · tokens.py
├── session/          turn_runner.py（编排）· state.py（状态机）· completion.py · queue.py
├── gateway/          facade.py · idempotency.py · identity.py · replay.py · outbound.py · web.py
├── router/           策略链（选 agent）· 会话路由
├── memory/           retrieval.py · writer.py · eviction.py · promotion.py · policy.py
└── execution/        chat_model.py · llm_client.py · tool_binding.py
```

## HTTP 端点

**会话**

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/sessions` | 会话列表 |
| POST | `/api/sessions` | 建会话（指定 agent） |
| GET | `/api/sessions/{id}` | 会话详情 |
| DELETE | `/api/sessions/{id}` | 关闭会话 |
| GET | `/api/tasks` | 任务列表 |
| POST | `/api/tasks/{task_id}` | 任务操作 |
| **POST** | **`/api/sessions/{id}/turns/stream`** | **跑一轮（SSE 流式）** |
| POST | `/api/sessions/{id}/cancel` | 取消当前轮次 |
| POST | `/api/sessions/{id}/feedback` | 提交反馈 |
| POST | `/api/sessions/{id}/approvals/{aid}/approve` | 批准工具调用 |
| POST | `/api/sessions/{id}/approvals/{aid}/deny` | 拒绝工具调用 |
| POST | `/api/sessions/{id}/interactive/answer` | 回答交互式提问 |
| POST | `/api/sessions/{id}/plans/{pid}/approve` | 批准计划 |
| POST | `/api/sessions/{id}/plans/{pid}/deny` | 拒绝计划 |
| POST | `/api/sessions/{id}/attachments` | 上传附件 |
| GET | `/api/sessions/{id}/attachments/{aid}` | 读取附件 |
| GET | `/api/sessions/{id}/artifacts/{aid}/content` | 下载产物 |

**智能体目录（管理侧）**

`/api/admin/agents` 下的增删改查、`/versions`、`/evaluations`、`/audit`、`/star`、`/eval`、`/batch-status`、`/diff`、`/import`、`/export`、`/rollback`；用户侧 `/api/catalog/agents` 与 `/api/catalog/agents/{id}/favorite`。

## 数据表

| 表 | 职责 | 关键列 |
|---|---|---|
| `agent_sessions` | 会话 | id / tenant_id / workspace_id / owner_id / **agent_id** / **agent_version** / status / current_turn_id / metadata(JSONB) / rolling_summary |
| `session_turns` | 轮次 | id / session_id / ingress_seq / status / user_input / final_response / input_tokens / output_tokens / cost_usd / route_decision / agent_decision / pending_approval / cancel_requested / model_version |
| `session_messages` | 会话消息 | id / session_id / session_seq / role / content / tool_name |
| `session_events` | 事件流（供断线重放） | session_id / seq / kind / payload |
| `session_artifacts` | 产物（工具/模型产出） | session_id / turn_id / name / mime / size_bytes / path |
| `admin_agents` | 智能体目录 | id / name / status / version / prompts(JSONB) / model / tools(JSONB) / knowledge_refs / memory_policy / max_steps / profile / versions(JSONB) |
| `admin_agent_user_state` | 用户对 agent 的个人状态 | agent_id / user_id / starred |
| `copilot_attachments` | 附件 | session_id / name / mime / size / storage_key |

## 关键类

| 层 | 类 | 职责 |
|---|---|---|
| domain | `Session` `Turn` | 轮次/会话聚合根，frozen dataclass + 状态迁移 |
| domain | `CatalogAgent` | 智能体目录聚合根，`publish()` 生成版本快照 |
| application | `CopilotSessionService` | 会话编排门面（claim / 幂等 / 取消 / 审批合一） |
| application | `TurnEntryService` | 跑一轮的入口：读会话 + 组装 `TurnRequest` |
| application | `OneShotTurnService` | 一次性问答（子 agent 与内部调用用） |
| application | `ChannelTurnService` | IM 渠道回合驱动 |
| application | `AgentCatalogService` | 智能体目录读写 |
| application | `DelegateSubagentUseCase` | 多智能体派发 |
| contract | `TurnRunner` | 幂等 → 排队 → 执行 → 落库 → 投递 |
| contract | `AgentLoopRunner` | 循环本体：Reason → Evaluate → 审批 → 执行 → Observe |
| contract | `Evaluator` | **六个终止条件的单一判定点** |
| contract | `ContextBuilder` | 上下文按固定优先级装配 |
| contract | `IdempotencyGuard` | 入站去重 |

## 实现要点

### 一次 turn 的链路

```
POST /api/sessions/{id}/turns/stream
  → session_router.py:327        附件解析 → Gateway.accept（归一化身份 / 幂等键）
  → TurnEntryService.stream       读会话 + 历史 + agent → TurnRequest
  → TurnRunner.run                幂等 accept → claim / 排队 → 执行 → 落库先于投递
  → SessionGraphRunner            装配上下文 → 压缩 → 选专家 → 跑循环
  → AgentLoopRunner.run           Reason → Evaluate → _approval_for → _invoke → Observe
  → ModuleToolRuntime             skill → sandbox → 目录工具，落到 tool 模块唯一执行口
```

### 终止条件收在一点

`Evaluator.evaluate`（`agent_loop/evaluate.py:68`）一次性判六条：用户取消、步数上限、成本上限、上下文超限、审批挂起、工具空转。注释里写明了为什么不能分散——分散正是上一次重构失败的模式。

**成本闸门的上限来自 agent 配置**：`profile.maxCostUsd`（JSONB 自由字段，不新增表列）。没配就是不限。计价回调在循环内按「本步用量」结算，累积进 `state.cost_usd`。

### 上下文装配的固定优先级

`ContextBuilder` 六级：安全提示与治理约束 → agent 版本与工具白名单 → 租户/用户上下文 → 会话摘要与最近消息 → 记忆与知识召回 → 本轮输入与工具结果。**第 1/2/6 级永不降级**——用户这句话和工具结果丢了，模型就是在答空气。超预算时按 knowledge → memory → summary → tenant 顺序丢。

**预算口径 = 窗口 × 0.70**，与压缩器同源（不再有「Builder 硬编码 8000、压缩器按 0.7」两套口径）。

**专家的指令单独成段**（manifest source = `expert`），与 agent 的五段 prompt 分开溯源。

### 任务清单（规划）

模型用 `todo_write` 工具维护任务清单。工具输出带 `__qzdap_todos__:` 前缀 + JSON，循环解析后写进 `state.todos`，并把未完成项回灌成一段 system 消息——模型要看得见自己规划了什么，否则下一轮不会照着做。

前缀常量在 `qzdap_kernel.todo_protocol`（tool 模块与 runtime 共享同一份，不违反分层）。

### 并行工具调用

一轮里模型返回多个工具调用时：**审批逐个判完**（挂起是控制流，不能并行）→ **只读工具并行执行** → 有副作用 / 高风险 / 需审批的**串行** → 结果按**请求顺序**还原（模型读结果的顺序有意义）。

只读的判据：无副作用 + 风险 low + 不需审批。判不出来就串行——并行是优化，不是正确性。

### 每步重选专家

专家（模型 + 指令 + 工具集）可以**跟着步骤走**：每步之前问一次装配器，按这一步的上下文重新分类与选取。第一步沿用已装好的专家（上下文已按它装配过），之后每步重选。装配失败沿用当前专家——装配器故障不能打断对话。

会话绑定的 agent 不变——换的是执行者，不是归属。

### SSE chunk 类型（17 种）

定义在 `backend/libs/schema/src/qzdap_schema/dtos/turn.py:15`：

`message` · `tool_call` · `tool_result` · `skill_invocation` · `memory_write` · `knowledge_search` · `approval_required` · `context_compacted` · `usage` · `done` · `error` · `plan_proposed` · `artifact_ready` · `attachment_ready` · `workflow_invocation` · `interactive_action` · `queued`

### 多智能体协同

`DelegateSubagentUseCase`（`application/use_cases/delegate_subagent.py:71`）：

- 深度上限 `MAX_DELEGATION_DEPTH = 3`，深度记在 `session.metadata["delegation_depth"]`
- 逐项校验：父会话租户、父会话工作区、目标 agent 租户 —— 任一不符直接拒绝
- 建子会话时写 `parent_session_id` / `delegated_from_agent_id` / `delegated_from_actor_id`
- 子会话跑**同一个** turn 实现，结果 `final_response` 喂回父 agent 的 LLM

父 agent 调 `delegate_to_agent` 时，`parent_session_id` 由 `adapter/graph/agent_loop.py:170` **强制注入**——模型不该凭空造一个归属。

另一路是「每步选专家」（`CatalogAgentRouter`）：按置信度阈值 0.5 与 task_kinds / category 关键词匹配，未命中则落回会话绑定的 agent。

### 工具审批

判定在 `agent_loop/runner.py:264` `_approval_for` → `PolicyGuard.decide`：

- 需要审批的绑定由 `tool_binding_adapter.py:161` 标注（`needConfirm` 或 `risk != low`）
- 挂起：`graph/runner.py:566` → `_request_approval` → 发 `approval_required` chunk → 写 `session_turns.pending_approval`
- 恢复：`session_router.py:525/546` → `CopilotSessionService.decide_approval` → 四项校验（审批归属 / 会话归属 / 未过期 / **参数摘要一致**）→ 带 resume 重跑 → `_finish_pending` 执行被批的那次调用
- **IM 渠道下不挂起**：需要审批的工具直接不暴露给模型

审批的幂等键由 `approval_id` 派生，**不掺原轮次的键**——审批恢复时原轮次状态已推进，原键取不到会导致键漂移、重复点击挡不住。

## 已知边界

- ⚠️ `admin_agents` 与 agent_factory 的 `agent_templates` **是两套并行的目录**，靠 `admin_agents.id == template_id` 对齐，是脆弱耦合
- ⚠️ `adapter/graph/runner.py:807 _absorb_mock_artifact` 是 mock 产物吸收路径（产物曾只在 `/tmp/qzdap-mock-artifacts`）
- ⚠️ `ask_user_question` / `notify_user` / `plan_submit` / `todo_write` 四个工具**同时**是前端桩与真实能力：`todo_write` 的清单会真的进循环状态（`todo_write` ✓），其余三个仍然只回 payload 由前端渲染
- ⚠️ `session_turns.wait_status` 与 `agent_sessions.graph_state` 两列已退役，分别由 `current_turn_id` 与 `metadata["resume"]` 推导
- ⚠️ **成本闸门只按单轮累计** ✓ —— 没有跨轮次的会话级预算 ✓（`session_turns.cost_usd` 有记 ✓ —— 但没有「这个会话已经花了 $X / 上限 $Y」的判据 ✓）
- ⚠️ **上下文超限这条终止条件在循环内不可达** ✓ —— `Evaluator` 有 `context_overflow` 参数 ✓ —— 但压缩器自己处理超限 ✓ —— 走的是「压缩后仍超限就抛 `CONTEXT_TOO_LARGE`」✓（不是循环的终止条件 ✓）
- ⚠️ **没有反思 / 自我修正机制** ✓ —— 工具失败只是把错误文本回灌给模型 ✓ —— 让它自己决定换不换策略 ✓（`apply_stall_guard` 只在「同样的工具连续空转」时插一句提示 ✓）
- ⚠️ **子 agent 是串行同步派发** ✓ —— `delegate_to_agent` 会阻塞到子会话跑完 ✓（深度上限 3 ✓）—— 没有子 agent 并行 ✓
