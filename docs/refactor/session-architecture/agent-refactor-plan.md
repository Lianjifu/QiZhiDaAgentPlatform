# Agent 层重构方案（Agent Runtime · Agent Router · Execution Runtime）

> 版本：1.2（D1 后重新梳理骨架：配置轴与执行轴分离）
> 适用项目：`QiZhiDaAgentPlatform`
> 状态：**已定稿**（17 条审查问题已修正；**v1.2 按 D1 重新梳理了骨架**，见 §0.2；附录 A 的 8 条决策于 2026-10-29 逐条确认 —— 其中 **决策 #4 早已由用户拍板**）
> 方案集入口：[`README.md`](README.md)
> 上位基线：[`session-lifecycle-sequence.md`](session-lifecycle-sequence.md) —— 本方案实现其中 **Agent Loop / Agent Router / Execution** 三条泳道
> 收敛机制：[`cleanup-ledger.md`](cleanup-ledger.md) —— 本方案对应条目 **X5**、**X1 的 Agent 部分**
> 技术栈：**LangGraph 1.x**（图编排）· **LangChain**（工具与模型抽象）· **Deep Agents**（深度任务）
> 硬约束：**最终态只有一个实现**；先上新、后清旧
> 方案集导航：落地路线与里程碑见 [`README.md`](README.md) §6 · 系统级验收见 §7 · 外部前置依赖见 §8 · 跨层不变量见 [`session-lifecycle-sequence.md`](session-lifecycle-sequence.md) §6

---

## 0. 定位与范围

### 0.1 三段运行时在基线图上的位置

```
   ┌──────────────────────────────────────────────────────────────────────┐
   │  ⑦ Agent Runtime · Agent Loop（系统的「大脑」）                        │
   │                                                                      │
   │   Reason/Plan ──▶ Observe ──▶ Evaluate ──┐                           │
   │        ▲                                │ continue                  │
   │        └────────────────────────────────┘                           │
   └────────────┬──────────────────────────────────────────┬───────────────┘
                │ 每一步都问                            │ 每一步都问
                ▼                                       ▼
   ┌────────────────────────────┐        ┌───────────────────────────────┐
   │ ⑧ Agent Router（专家选择）   │        │ ⑨ Execution Runtime（执行）   │
   │  · 选本步由哪个专家处理      │───────▶│  · Agent 实例执行              │
   │    （本层唯一的「选择」）     │  专家  │  · Model Runtime              │
   │  · 选中的专家 = 一份配置      │        │    （按配置解析 + 调用）       │
   │    → 它的模型 / 工具即本步   │───────▶│  · Tool Runtime               │
   │      的模型 / 工具来源       │  配置   │    （按配置绑定 + 治理 + 执行） │
   └────────────────────────────┘        └───────────────────────────────┘
   ▲
   │ 只读，不写
   ┌──────────────────────────────────────────────────────────────────────┐
   │ 配置来源（管理端，不归本层）：model / tool / skill / 知识 / 流程        │
   │   → agent 配置绑定（agent_versions）→ 运行时取值（本层只读 + 治理过滤） │
   └──────────────────────────────────────────────────────────────────────┘
```

**三段的一句话职责**：

| 段 | 一句话 | 回答的问题 |
|---|---|---|
| **⑦ Agent Loop** | 决定**下一步做什么** | 继续推理？调工具？收尾？挂起审批？ |
| **⑧ Agent Router** | 决定**这一步交给谁** | 哪个专家 Agent？（**它的配置同时定下了本步的模型与工具**） |
| **⑨ Execution Runtime** | 决定**真的把它做了** | 按配置取模型与工具 → 调 LLM → 跑工具 / 沙箱 |

### 0.2 两条轴：执行轴与配置轴

**本层的全部行为都在这两条轴上；理解这两条轴，就理解了为什么本层没有 Model Router、没有 Tool Router。**

```
执行轴（横，每一步推理走一遍）
   ⑦ Agent Loop ──▶ ⑧ 专家选择 ──▶ ⑨ Execution ──┐
        ▲                                        │ 结果
        └────────────────────────────────────────┘

配置轴（纵，管理员改配置时才走一遍）
   管理员配置 model / tool / skill / 知识 / 流程
        │  （管理端写入，不归本层）
        ▼
   agent 配置绑定（agent_versions.model_id / route_id / allowed_tools / allowed_skills …）
        │  （本层只读）
        ▼
   ⑨ 按「当前执行的 agent」取值 + 治理过滤
```

| | 执行轴 | 配置轴 |
|---|---|---|
| 触发 | 每一步推理 | 管理员改配置 / agent 版本发布 |
| 本层的动作 | 循环、选专家、调用、执行 | **取值 + 治理过滤**（**不是选择**） |
| 本层写不写配置 | 不写 | **不写** —— 唯一写入点是管理端 |
| 决策 #4 的位置 | ⑧ 只选**专家** | 模型 / 工具 = **查表结果** |

> **两条轴的正交性**：执行轴决定「**什么时候用**」，配置轴决定「**有什么可用**」。**模型与工具不在执行轴上被挑选** —— 它们在配置轴上早已被管理员定好；执行轴只能把它们**取出来**。
>
> **所以**：⑧ 的「路由」只剩一项（选专家）；模型与工具的读取归 ⑨ Execution（§5.2 / §5.3）。取消 Model Router / Tool Router **不是砍功能**，而是**把两件事放回它们真正所在的轴上**。

### 0.3 子件清单（对应用户给定的结构）

| 段 | 子件 | 职责 |
|---|---|---|
| **⑦ Agent Runtime · Agent Loop** | **Reason / Plan** | 组装「上下文 + 工具 schema + 模型」→ 调模型 → 解析出文本与工具调用 |
| | **Observe** | 把工具执行结果回灌成 `tool` 消息 |
| | **Evaluate** | 判定 continue / exit / suspend / abort |
| **⑧ Agent Router** | **专家 Agent 选择** | 每一步**选由哪个专家 Agent 处理**（客服 / 销售 / 订单 / 工单…）—— **本层唯一的「选择」** |
| **⑨ Execution Runtime** | **Agent 实例执行** | 专家 Agent =「指令 + 模型 + 工具」的组合，受同一套治理、计量、幂等约束 |
| | **Model Runtime** | ① **模型解析**（按 agent 配置**查表**，不是选模型）② **调用**（流式 + 失败转移链） |
| | **Tool Runtime** | ① **工具绑定**（按 agent 配置取绑定集 + 治理过滤）② **执行**（幂等 / 重试 / 熔断 / 沙箱） |

> **配置与注册不归本层**：模型、工具、skill 的**注册**在 `modules/model` / `modules/tool` / `modules/skill`；**绑定关系写在 agent 配置里**。本层在运行时**只读**（配置轴）。

### 0.4 本层明确不做

| 不做 | 归属 |
|---|---|
| 协议解析、鉴权、幂等去重、渠道回包 | Gateway |
| **会话入口**选 agent（按业务线 / 按用户标签）、路由到哪个会话、消息排序 | Router 层 |
| 会话生命周期、轮次状态机、事件落库、审批挂起落库 | Session |
| 组装上下文、压缩、摘要、manifest | Context |
| 记忆与知识的存取 | Memory |
| 审批的**决策语义**（谁能批、批什么） | Governance |
| 工具的**注册与协议实现**（custom / openapi / mcp 的派发） | `modules/tool`（**已实现，不重复造**） |
| 模型 / 工具 / skill 的**注册与配置**（绑定关系写在 agent 配置里） | 管理端 + `modules/model` · `modules/tool` · `modules/skill`（**本层只读**） |

> **一句话**：本层管的是「**模型怎么被调用、专家怎么选、工具怎么被执行、循环什么时候停**」。

### 0.5 实现收敛规则

**最终态只有一个实现**；**先上新、后清旧**。台账条目见 [`cleanup-ledger.md`](cleanup-ledger.md)。

本层的收敛形态与其它层**不同** —— 别的层是「旧实现完整、新实现未接线」，这一层是「**两套都不完整**」：

| 实现 | LangGraph 的真实状态 | 真正的循环在哪 |
|---|---|---|
| ① 旧路径 | **编了，但用占位节点**（`compile_loop_graph(llm_node=_passthrough_llm, tools_node=_passthrough_tools)`，`runner.py:92`） | **手写的 `while True:`**（`runner.py:265` 起） |
| ② 新 runtime | **图是真的**（19 节点齐备），但 `agent` 节点是 `return {}` | **不存在** —— 推理不发生 |

> 处置原则应是「**取旧的真逻辑 + 用新的骨架重写**」，而不是「把新 runtime 接上线」。

---
## 1. 现状盘点

### 1.1 🔴 新 runtime 的 `agent` 节点是空的

```python
# runtimes/.../graph/nodes.py:617-619
def agent(state: SessionState) -> dict[str, Any]:
    """10 agent: §13.2 节点 10。Stage 1 passthrough。"""
    return {}
```

**图能编译、测试能过、但没有一次真实的模型推理。**

根因不是「忘了填」，而是**没有可填的东西**：

| 缺口 | 证据 |
|---|---|
| 新 runtime **没有 `LLMPort`** | `runtimes/.../ports.py` 有 `ToolExecutor` / `PolicyGuard` / `ToolRegistry` / `LayeredMemory`，**唯独没有 LLM 端口** |
| 没有流式工具调用装配器 | 旧路径的 `ToolCallAccumulator`（`chat_model.py:22-77`）负责合并分片 tool call —— **最容易写错的部分**，新 runtime 没有对应物 |
| 没有成本核算 | 新 runtime 有进程内的 `InMemoryCostAttribution`；旧路径的 `copilot._price_of` 走 `CatalogModelResolver.price_of` |

> **把新 runtime「接线」不是换引擎，是重写推理。**

### 1.2 🔴 19 节点图里有 5 个节点是空壳

| 节点 | 行号 |
|---|---|
| `agent` | `nodes.py:617` |
| `emit_result` | `nodes.py:1119` |
| `compact_tool_result` | `nodes.py:1124` |
| `write_turn_record` | `nodes.py:347` |
| `load_checkpoint` | `nodes.py:342` |

条件分支上的 `deep_agent_plan`（`nodes.py:841`）、`subagent`（`nodes.py:904`）在未注入依赖时也是 `return {}`。

**这 5 个空壳正好对应本方案的三段**：Agent Loop 的推理、Execution 的结果投递、Session 的轮次落库。

> **⚠️ `persist_result`（`nodes.py:1060`）不是空壳** —— 它有真实逻辑（用量记账 + 成本归属 + 异步 OnlineEvaluator），只是依赖（`get_default_usage_tracker` 等）没注入。初稿把它算成第 6 个空壳，已改正。

### 1.3 🔴 `governance` 节点的 actor 是硬编码的

```python
# runtimes/.../graph/nodes.py:644
actor = ActorContext(
    actor_id="u-1",  # Stage 5 注入
    ...
)
```

**审批的申请人永远是 `"u-1"`**。后果：审批记录的 `requester` 是假的 → 「审批人 ≠ 申请人」校验**必然失效**（旧路径 `copilot.py:466-471` 已经吞过同一个异常）；审计记的不是真实操作者。

> **同一个安全缺陷在新 runtime 里以另一种形式重现** —— 「换实现」不能靠「新代码更干净」来保证。

### 1.4 🔴 新 runtime 的执行器把幂等放在进程内

```python
# runtimes/.../execution/executor.py
class InMemoryToolExecutor:
    def __init__(self) -> None:
        self._idempotency_cache: dict[str, _IdempotencyEntry] = {}
        self._records: list[ToolCallRecord] = []
```

| 问题 | 后果 |
|---|---|
| 缓存**进程内** | 换 worker / 重启 → 幂等失效 → **副作用工具重复执行** |
| `_records` 是 `list` | 工具执行记录**不落库** → `tool_executions` 表**永远空** |

### 1.5 🔴 `execute` 节点在异步图里同步调异步执行器

```python
# runtimes/.../graph/nodes.py:794
result = run_async_from_sync(executor.execute(...))
```

在 LangGraph 的 async 图里这是纯粹的损失：工具越慢，**并发能力越差**。（Context 层的 `Compactor` 同型问题。）

### 1.6 🔴 `remember` 节点的逻辑是反的

```python
# runtimes/.../graph/nodes.py:1016-1030
for hit in memory_hits:            # ← 召回结果
    candidates.append({...})       # ← 提取事实写回 L2
```

召回结果**本来就是 L2 里的东西** → **自我强化循环**（召回 → 写回 → 召回更多）。正确语义：**Writer 的输入只能是「本轮产生的内容」**。= 台账 X12。

### 1.7 🔴 Deep Agents 的依赖其实**没有装**

```python
# runtimes/.../graph/deep_agent.py:99
class InMemoryDeepAgentFactory:
    """§5.5 / §2.5 阻塞 4 验证: deepagents==0.7.25 真实可用。

    简化版:
    - 不实际调 create_deep_agent (避免依赖外部 API key)
```

**核对结论（2026-10-29，venv 实测）**：

| 事实 | 证据 |
|---|---|
| `deepagents` **未安装** | `backend/.venv` 里 `importlib.metadata.version("deepagents")` → 抛异常 |
| `deepagents` **不在 `uv.lock`** | 全文件搜索零命中 |
| 代码里**从未 import 它** | `deep_agent.py` 的 docstring 声称「真实可用」，实现却是 `InMemoryDeepAgent`（纯进程内假实现，无 LLM） |

> **「阻塞 4 已验证」的结论是错的。** deep path 不是「接上线就能用」，而是「**依赖都没加**」。
>
> **但 API 表面是已知的**：[`../deepagents-probe-result.md`](../deepagents-probe-result.md)（2026-10-15）用隔离 venv（`uv run --with deepagents`）验证过 `deepagents==0.7.25` 与 `langgraph 1.2.15` / `langchain-core 1.6.10` **兼容、无冲突**，`create_deep_agent` 的完整签名也已记录。探针脚本 `scripts/probes/deepagents_import.py` 可重放。
>
> **因此缺的只是「把它声明成项目依赖 + 在项目 venv 里重跑一次探针」**，不是「摸黑探索 API」。

### 1.8 🟡 技术栈现状（venv 实测）

| 包 | 版本 | 声明位置 | 状态 |
|---|---|---|---|
| `langgraph` | **1.2.12** | `runtimes/agent_runtime/pyproject.toml` `>=1.0,<2.0` | ✅ 已装 |
| `langgraph-prebuilt` | **1.1.0** | 同上 `>=1.0,<2.0` | ✅ 已装，但**全仓零 import** |
| `langgraph-checkpoint-postgres` | **3.1.3** | 同上 `>=3.0,<4.0` | ✅ 已装 |
| `langchain-core` | **1.6.6** | 同上 `>=1.0,<2.0` | ✅ 已装 |
| `langchain`（全量包） | — | **未声明** | ❌ 未装 |
| `deepagents` | — | **未声明** | ❌ 未装 |

**`langgraph.prebuilt` 已提供但未被使用的关键能力**（venv 实测导出）：

```
ToolNode · create_react_agent · tools_condition · chat_agent_executor
ValidationNode · tool_validator · ToolCallTransformer
InjectedState · InjectedStore · ToolRuntime
```

**`langchain_core.tools` 已提供且已被使用**：`BaseTool` · `StructuredTool` · `@tool` · `ToolException` · `InjectedToolArg` · `InjectedToolCallId` · `BaseToolkit` · `convert_runnable_to_tool`。

**`langgraph.types` 已提供**：`interrupt` · `Command` · `Send` · `StateSnapshot` · `RetryPolicy` · `TimeoutPolicy` · `Durability`。

### 1.9 🟡 平台自己的 LLM 库与 LangChain **完全无关**

`libs/llm/src/qzdap_llm/` 是**自研**、**零 LangChain 依赖**的客户端：

| 类型 | 位置 |
|---|---|
| `ChatRequest` / `ChatMessage` / `ChatResponse` / `LLMChunk` / `Usage` | `libs/llm/.../client.py:13-63` |
| `LLMClient`（`chat` / `stream` / `embed` / `synthetic_chunks`） | `client.py:64-89` |
| `LLMRouter`（多供应商 + 故障转移 `_with_failover`） | `libs/llm/.../router.py` |
| 供应商实现 | `openai_compatible.py` / `anthropic.py` / `azure.py` / `google.py` / `mock.py` |

**这意味着**：要用 LangChain 生态（`ToolNode`、`create_react_agent`、Deep Agents），**必须有一个 `BaseChatModel` 适配器**把 `LLMClient` 包进去 —— 目前没有。

### 1.10 ✅ 平台已有真实可用的工具执行器（**不要重复造**）

`modules/tool` 的 `InvokeToolUseCase`（`application/use_cases/invoke_tool.py`）**已经在跑**，且能力比新 runtime 的 `InMemoryToolExecutor` 完整得多：

| 能力 | 现状 | 位置 |
|---|---|---|
| **治理闸门** | `policy_guard.check(actor=…, action=f"tool:execute:{tool_name}", resource=…)` | `invoke_tool.py:98-110` |
| **三协议派发** | `custom` / `openapi` / `mcp` —— `_dispatch(tool.protocol, …)` | `invoke_tool.py:141`、`_dispatch` |
| **调用落库** | `tool_calls` 表（running → succeeded / failed，带 `latency_ms`） | `invoke_tool.py:132,145,156` |
| **事件** | `ToolInvoked` / `ToolCompleted` / `ToolFailed` | `invoke_tool.py:133-186` |
| **超时** | `timeout_seconds=30.0` → `TOOL_CALL_TIMEOUT` | `invoke_tool.py:156-170` |
| **协议枚举** | `ToolProtocol` = `CUSTOM` / `OPENAPI` / `MCP` | `modules/tool/.../domain/entities.py:33-37` |
| **内置工具目录** | `echo` / `reverse` / `clock` / `web_search` / `http_fetch` / `fetch_url_with_auth` … 含 risk 标注 | `application/tool_catalog.py:31+` |
| **MCP 探活** | `/api/admin/skills/mcp/probe` | `modules/skill/.../adapter/http/router.py:54` |

**缺什么**（正是本方案要补的）：

| # | 缺口 | 后果 |
|---|---|---|
| 1 | **无幂等**（`tool_calls` 无 `idempotency_key` / `request_hash`） | 副作用工具重复执行 |
| 2 | **无重试 / 熔断** | 网络抖动直接失败 |
| 3 | **无 `unprotected` 语义** | Gateway 决策 #5 无人兑现 |

### 1.11 🔴 两张工具调用表，且唯一带幂等的那张**零引用**

| 表 | 列 | 代码引用 |
|---|---|---|
| **`tool_executions`**（0035 建） | `tool_call_id`(PK) · `idempotency_key`(**UNIQUE**) · `request_hash` · `status` · `result_ref` · `reconcile_endpoint` · `turn_id`(FK→`session_turns`) · `tenant_id` · `workspace_id` · `started_at` · `finished_at` | **零**（只在 `migrations/versions/0035_*.py` 与 `0039_*.py` 里出现） |
| **`tool_calls`**（`modules/tool` 建） | `id` · `tenant_id` · `workspace_id` · `tool_name` · `arguments` · `result` · `error_code` · `status` · `started_at` · `finished_at` · `latency_ms` | ✅ 在跑 |

**`tool_executions` 的列已经齐全**（含唯一约束与 `request_hash`）—— **不需要新迁移**，只需要**开始写它**。

### 1.12 ✅ 可直接复用的资产

| 资产 | 位置 | 处置 |
|---|---|---|
| `ToolCallAccumulator` | `adapter/graph/chat_model.py:22-77` | ✅ **迁入**（流式工具调用装配，最易写错的逻辑） |
| `stream_chat` / `complete_chat` | `adapter/graph/chat_model.py:80-200` | ✅ 迁入 Execution 的 LLM 客户端 |
| `LLMPortAdapter` | `adapter/llm/__init__.py` | ✅ 保留 —— **Stage 0 补出 runtime 的 `LLMPort` 后由它实现**（当前 `runtimes/.../ports.py` 里**还没有** `LLMPort`） |
| `SqlCatalogModelResolver`（`resolve` / `price_of`） | `adapter/persistence/catalog_model_resolver.py` | ✅ 保留，实现 `ModelResolverPort` |
| `InMemoryToolRegistry` + `from_langchain_tool` | `runtimes/.../tools/registry.py` | ✅ **保留**（LangChain `BaseTool` 适配已正确） |
| `ToolServiceAdapter`（`invoke` / `list_tools`） | `adapter/tools/tool_service_adapter.py` | ✅ **保留** —— 它已经是 Execution 的正确入口 |
| `InvokeToolUseCase` + 三协议 + `policy_guard` | `modules/tool/.../invoke_tool.py` | ✅ **保留**，本层只补幂等 / 重试 / 熔断 |
| `DeepAgentConfig` / `SubAgentSpec` / 预算常量 | `runtimes/.../graph/deep_agent.py` | ✅ 保留**类型定义** |
| `TaskKind` + `classify_task_kind_heuristic` | `runtimes/.../graph/routing.py` | ✅ 保留为**降级实现** |
| `agent_versions.route_id` / `route_strategy` | 迁移 0042 | ✅ **模型解析的落点（已存在）** |
| `admin_model_routes` / `admin_model_quotas` | 迁移 0041 / model 模块 | ✅ 保留 |

---

## 2. 目标架构与技术栈

### 2.1 技术栈落位（**每项技术用它做什么、不用它做什么**）

| 技术 | 版本 | 用在哪 | 不用在哪 |
|---|---|---|---|
| **LangGraph 1.2** | 1.2.12 ✅ | ⑦ Agent Loop 的**图骨架**；`interrupt` / `Command` 做审批中断与恢复；`AsyncPostgresSaver` 做 checkpoint；`RetryPolicy` / `TimeoutPolicy` 做节点级重试与超时 | 不用来做业务编排（轮次生命周期归 Session） |
| **LangChain（`langchain-core`）** | 1.6.6 ✅ | ⑨ 的**工具抽象**（`BaseTool` / `StructuredTool` / `@tool` / `ToolException`）与**模型抽象**（`BaseChatModel` 适配器）；`convert_runnable_to_tool` | 不引入 `langchain` 全量包（agents / chains / community 都不需要） |
| **LangGraph Prebuilt** | 1.1.0 ✅ | ⑨ 的 `ToolNode`（工具执行节点的标准实现）+ `tools_condition`（条件边）+ `tool_validator`（参数校验） | **不用 `create_react_agent`**（见决策 #1） |
| **Deep Agents** | **未安装** ❌ | ⑦ 的**深度任务分支**：规划器（planner）+ 子代理（sub-agent）+ 任务清单（todo） | 不用于简单问答路径；不接管审批与治理 |

### 2.2 为什么必须写一个 `BaseChatModel` 适配器（**决策 #2**）

**问题**：`langgraph.prebuilt.ToolNode`、`create_react_agent`、Deep Agents 全部要求模型是 `BaseChatModel` 或 `Runnable`。而平台的 `qzdap_llm.LLMClient` 是**自研类型**（`ChatRequest` / `ChatMessage` / `LLMChunk`）。

**不写适配器的后果**：

| 想用的能力 | 没有适配器时 |
|---|---|
| `ToolNode` | 只能自己写工具执行节点（放弃 prebuilt） |
| `create_react_agent` | 用不了 |
| Deep Agents | 用不了（它的核心就是 LangChain 模型 + 工具） |
| LangChain callbacks / tracing | 用不了 |

**写适配器的收益**：

```
QZDAPChatModel(BaseChatModel)          ← 唯一的新增适配层
   ├─ 内部持 qzdap_llm.LLMClient（保留全部供应商实现与故障转移）
   ├─ _stream → 调 LLMClient.stream() → 逐个 yield AIMessageChunk
   ├─ 用量 → usage_metadata（LangChain 标准字段）
   └─ 模型 id / 成本 → 由平台侧从 chunk 里取，不走 LangChain 的 cost 机制
```

> **适配器是「薄」的**：它只做**类型翻译**，不碰供应商、不碰路由、不碰成本。所有业务语义仍在平台侧。
>
> **这也是「模型解析」的落点**：`QZDAPChatModel` 是**按 agent 配置构造出来的实例** —— agent 绑定了哪个模型（`model_id` / `route_id`）、哪条降级链，都体现在「这次用哪个 `QZDAPChatModel`」上。**因为是查表而不是决策，本层不需要改 LangChain 的任何东西**（决策 #4）。

### 2.3 目标图（⑦ 的 6 节点）

```
START → reason → governance → execute → observe → evaluate
                              ▲                    │
                              └──── continue ──────┤
                                                   ↓ exit/suspend → END
```

**与 19 节点图的收敛对照**：

| 19 节点 | 处置 | 归属 |
|---|---|---|
| 1 `normalize_input` | ✗ | Gateway 已归一化 |
| 2 `acquire_turn_lock` | ✗ | Session 用轮次表 CAS（Router 决策 #9） |
| 3 `load_checkpoint` | ✗ | Session 方案的 checkpoint 端口 |
| 4 `write_turn_record` | ✗ | Session 层 |
| 5 `load_agent_context` | ✗ | Context 层 |
| 6 `recall_memory_and_knowledge` | ✗ | Context 层（Context 主动发起召回） |
| 7 `assemble_context` | ✗ | Context 层 |
| 8 `compact_if_needed` | ✗ | Context 层 |
| 9 `route` | ⚠️ 拆分 | **任务分类 → Agent Router（⑧）**；「选哪个 agent」→ Router 层 |
| 10 `agent` | ✅ 迁入 | ⑦ `reason` |
| 11 `governance` | ⚠️ 拆分 | 策略判定 → Governance；审批挂起 → Session |
| 12 `execute` | ✅ 迁入 | ⑨ Tool Runtime |
| 13 `deep_agent_plan` / 14 `subagent` | ⚠️ | Deep Agents 分支（决策 #8） |
| 15 `remember` | ✗ | Memory 层（且逻辑是反的，§1.6） |
| 16 `persist_result` | ✗ | Session 层 |
| 17 `emit_result` | ✗ | Gateway 出站 + Session 事件落库 |
| 18 `compact_tool_result` | ✗ | Context 层 |
| 19 `release_turn_lock` | ✗ | Session 层 |

> **节点数 19 → 6**。被删的 13 个节点不是「工作量」，是**职责错位** —— 它们把 Context / Session / Memory / Gateway 的活儿塞进了 Agent Loop 的图里，导致这个图**既不能整体接线**，也**没人能单独验证**。
>
> **同时删除旧路径的残留图**：`modules/.../adapter/graph/loop.py` 的 `compile_loop_graph`（台账 **X5**）—— 它用 passthrough 节点，**从来没人走过**。其中 `apply_stall_guard` 的「相同工具连续空转」护栏**值得保留**，迁入 `evaluate`。

### 2.4 目标目录结构

```
backend/runtimes/agent_runtime/src/qzdap_agent_runtime/
├── agent_loop/                    # ⑦ Agent Runtime · Agent Loop
│   ├── reason.py                  #   Reason/Plan
│   ├── observe.py                 #   Observe
│   ├── evaluate.py                #   Evaluate（六个终止条件的单一判定点）
│   ├── runner.py                  #   循环本体
│   └── graph.py                   #   LangGraph 6 节点装配 + interrupt/resume
├── agent_router/                  # ⑧ 专家 Agent 选择（唯一的「选择」）
│   ├── agent_router.py            #   选专家 Agent
│   └── classifier.py              #   任务分类（专家选择的输入）
├── execution/                     # ⑨ Execution Runtime
│   ├── chat_model.py              #   QZDAPChatModel(BaseChatModel) 适配器
│   ├── model_binding.py           #   模型解析：从 agent 配置查表 → 构造 QZDAPChatModel
│   ├── llm_client.py              #   LLM / SLM 调用 + 失败转移链
│   ├── tool_binding.py            #   工具绑定：从 agent 配置取绑定集 + 治理过滤
│   ├── tool_runtime.py            #   Tool Runtime（幂等 / 重试 / 熔断，调 modules/tool）
│   ├── agent_executor.py          #   专家 Agent 实例执行
│   └── sandbox.py                 #   代码执行环境
└── deep/                          # Deep Agents 集成（决策 #8）
    ├── factory.py
    └── planner.py
```

---
## 3. ⑦ Agent Runtime · Agent Loop

### 3.1 Reason / Plan

```
输入：AssembledContext.messages（Context）
     + 工具 schema（**从 agent 配置的绑定集取出 + 治理过滤** → BaseTool 列表）
     + 模型（**从 agent 配置解析** → QZDAPChatModel 实例）
     + 专家 Agent 指令（Agent Router 的产物）
输出：文本增量（流式 yield）+ 工具调用列表
```

| # | 要点 | 说明 |
|---|---|---|
| 1 | **工具调用装配必须用 `ToolCallAccumulator`** | 流式协议会把一次 tool call 拆成多个 delta（名字分片、参数分片）。**逐 delta 直接执行是经典 bug** —— 会拿半截参数去调工具。旧路径的 `ToolCallAccumulator` 已处理「字符串参数 vs dict 参数」「按 index 归并」「`thought_signature` 透传」 |
| 2 | **文本与工具调用分离投递** | 文本增量**立即**推给前端；工具调用**等装配完整**才执行 |
| 3 | **用 `AIMessageChunk` 承载 delta** | LangChain 标准类型 → `ToolNode` / Deep Agents 都能直接消费 |
| 4 | **用量走 `usage_metadata`** | LangChain 标准字段；成本换算仍由平台的 `price_of` 做（不用 LangChain 的 cost 机制） |
| 5 | **上下文超限交 Context** | 本层**不裁剪**；收到模型的「上下文超限」错误 → 报给 Context 层重组，连续 2 次仍超限 → 明确错误 |

### 3.2 Observe

工具结果 → 回灌：

```python
ToolMessage(content=..., tool_call_id=..., name=..., status="success" | "error")
```

| # | 要点 |
|---|---|
| 1 | **失败的工具也要回灌** —— 模型需要知道「失败了、为什么」才能换策略。用 `ToolMessage(status="error")` |
| 2 | **结果要截断** —— 截断策略归 Context 层（附件摘要档），本层只做**兜底上限**，防单条消息撑爆内存 |
| 3 | **多工具并行时回灌顺序 = 请求顺序**（模型的 `tool_calls` 数组顺序），否则模型会误判因果 |

### 3.3 Evaluate

每步结束后判定下一步：

| 判定 | 条件 | 动作 |
|---|---|---|
| **continue** | 有待执行的 tool_calls，且未超步数 / 成本 | 回到 Reason/Plan |
| **suspend** | 工具需要审批 | `interrupt()` → 交 Session 挂起轮次（`session_turns.pending_approval`） |
| **exit** | 无 tool_calls，或模型给出最终答案 | 收尾，交 Session / Context / Memory |
| **abort** | 步数 / 成本 / token 超限 | 抛明确错误（`DEEP_AGENT_BUDGET_EXCEEDED` —— ⚠️ 它目前只是**新 runtime 里的字符串常量**（`graph/deep_agent.py:25`），**不在 `ErrorCode` 枚举里** → 前端不认识这个码，本层要**新增错误码**并同步 `libs/schema`） |

> **决策 #7（已定稿）**：成本闸门 → **两级都有**：轮次级是硬闸门，深度任务级是它的一个子集（deep path 允许更大但仍有上限）。

### 3.4 循环终止条件（**必须全部兜住，且集中在一点**）

| # | 条件 | 上限来源 | 触发后的行为 |
|---|---|---|---|
| 1 | 最大步数 | agent 配置 / `DeepAgentConfig.max_steps` | 抛 `DEEP_AGENT_BUDGET_EXCEEDED` |
| 2 | 最大成本 | `max_cost_usd` | 同上 |
| 3 | 上下文超限 | 模型报错 | 交 Context 重组；连续 2 次仍超限 → 明确错误 |
| 4 | 用户取消 | `session_turns.cancel_requested` | 立即中断，产出部分结果 |
| 5 | 审批挂起 | 策略判定 | `interrupt()` → `suspend` |
| 6 | 工具连续失败 / 相同工具连续空转 | 熔断器（按工具名）；`apply_stall_guard` 护栏 | `exit` + 明确错误 |

> 这六条必须写成一个「**终止条件的单一判定点**」。分散在各个节点里是 2026-10-15 那次重构失败的模式之一 —— 每个 Stage 的验收都是「本节点单测通过」，但**没有一条测试跑完整个循环**。

### 3.5 审批中断与恢复（LangGraph `interrupt` 的正确用法）

**本层只做两件事，决策在 Governance，落地在 Session**：

```
① 调 PolicyGuard.decide(...) → allow / approve_required / deny
② allow           → 继续执行工具
   approve_required → interrupt()，把 approval_id + request_hash 交给 Session
   deny             → 产出错误，不执行工具
```

**恢复时的校验由 Session 层负责**（Session 方案 §5.6 的 5 项清单）。本层的义务只有一条：

> **恢复后执行工具前，必须重新校验 `request_hash` 与当前参数一致。** 否则「审批的是 A，执行的是 B」。

**必须修掉的两个洞**：

| 洞 | 位置 | 修法 |
|---|---|---|
| actor 硬编码 `"u-1"` | `nodes.py:644` | 从 `state` 取真实 actor；取不到 → **拒绝执行工具**（不是用假 actor 继续） |
| 审批异常被吞 | `copilot.py:466-471` | 校验失败 → 明确错误码 + 审计 |

### 3.6 记忆写入的触发点

**Writer 的输入只能是「本轮产生的内容」**：

| 可以写入 | 不能写入 |
|---|---|
| 用户本轮输入 | ❌ 召回结果 `memory_hits` |
| 模型本轮输出 | ❌ 工具返回的原始大对象（除非经过抽取） |
| 工具结果中抽出的事实 | ❌ 上一轮的写入结果（自我强化） |

触发点在 **Observe / Evaluate 之后、轮次收尾之前**（基线图上「Agent Loop → Memory 写入」那条边）。

### 3.7 深度任务分支（Deep Agents）

**Deep Agents 提供什么**（规划器 + 子代理 + 任务清单）：

```
用户请求
  → Planner（LLM）产出任务清单（todos）
  → 逐个 Sub-agent 执行（每个子代理有自己的工具集、步数预算、成本预算）
  → 汇总回主图
```

**接入方式**：

> **Deep Agents 的 API 已经探明**（[`../deepagents-probe-result.md`](../deepagents-probe-result.md)），`create_deep_agent` 的签名里**有三个参数直接对应我们的治理需求** —— **不要自己实现一套**：

| Deep Agents 参数 | 对应我们的什么 | 我们的落点 |
|---|---|---|
| `permissions` | 工具白名单 + 风险等级 | **工具绑定 + 治理过滤**（§5.3.1） |
| `interrupt_on` | 触发审批中断的工具名 | Session 的 `pending_approval`（§3.5） |
| `middleware` | 治理 hook（Plan 阶段注入） | PolicyGuard 闸门 |
| `subagents` | 多 agent 委派 | **专家 Agent 选择**（§4.1） |
| `checkpointer` / `store` | LangGraph 1.x 的 PostgresSaver / Store | Session 迁移 0046 建的表（§7.1） |
| `memory` | 跨会话记忆 | Memory 层的 `LayeredMemory` 端口 |
| `backend` | 沙箱 backend | Execution 的沙箱端口（§5.3.4） |

**三条实施约束**（来自探针，**违反会踩坑**）：

| # | 约束 | 原因 |
|---|---|---|
| 1 | **必须显式传 `model=`** | `model=None` 自 0.5.3 起弃用，**1.0.0 移除** |
| 2 | **版本钉死 `>=0.7,<1.0`** | 1.0 会移除 `model=None`，届时是 breaking change |
| 3 | **CI 显式校验 `model` 参数非 None** | 提前撞上 1.0 的破坏性变更 |

| # | 要点 |
|---|---|
| 1 | **必须先加依赖**（`deepagents` 未安装、不在 lockfile）→ 见决策 #8；**加完要在项目 venv 重跑一次探针**（原探针在隔离 venv 做的，与当前 lock 的 `langgraph 1.2.12` / `langchain-core 1.6.6` 需重新确认） |
| 2 | Deep Agents 的模型参数就是 `BaseChatModel` → **依赖 §2.2 的 `QZDAPChatModel` 适配器** |
| 3 | 子代理的工具集 = **子代理自己配置里的绑定集**（每个子代理只拿自己该用的工具） |
| 4 | 子代理的步数 / 成本预算 = `SubAgentSpec`（**已有结构**） |
| 5 | **子代理不能绕过治理** —— 子代理的工具调用同样经过 governance → execute |
| 6 | 规划器的产出（todos）要作为事件投递给前端（前端已有 `plan_proposed` chunk） |

> **决策 #8（已定稿）**：Deep Agents 的接入方式 → **先加依赖并在隔离分支验证 API 与版本，验证通过后再在 Stage 6 接线**；**在此之前只保留类型定义**。见附录 A。

---

## 4. ⑧ Agent Router · 专家 Agent 选择

> **决策 #4 之后，本层只剩一个子件**：选专家 Agent。模型与工具**不是这里选的** —— 它们随「选中的专家」的配置而定，**取值**落在 ⑨ Execution（§5.2 / §5.3）。
>
> **泳道名保持 `Agent Router` 不变**（基线图与六份方案都按这个名字引用）；变的是它的**职责**：从「三路决策」收敛为「一路选择」。

### 4.0 与 Router 层（⑤）的边界 —— **必须先分清**

| | **Router 层（⑤）** | **Agent Router（⑧）** |
|---|---|---|
| 时机 | **会话入口**（收到第一条消息时） | **每一步推理**（循环内） |
| 选什么 | 目标 **agent**（按业务线 / 用户标签 / 显式指定） | 目标**专家 Agent**（模型 / 工具 / 知识**由专家自己的配置给出**） |
| 结果 | **会话绑定**（`agent_versions` 冻结，会话内不变） | **本步的专家**（每步可变） |
| 冲突时 | 会话粘性压过显式指定（Router 决策链规则 1） | 专家选择压过会话绑定；**但模型 / 工具的来源不变** —— 它们永远取自「当前执行的那个 agent」的配置 |

> **一句话**：Router 层选「**跟谁聊**」（一次决定，整个会话）；⑧ 选「**这一步交给哪个专家**」（每步决定）。
>
> **举例**：一个「售后」会话（Router 层绑定的售后 Agent），其中一步需要查订单 → ⑧ 把这一步交给「订单专家」（**订单专家用订单专家自己配置的模型与工具**）；下一步要写工单 → 交给「工单专家」。**会话绑定没变，但每步的执行者变了。**
>
> **⚠️ 本层不做的事**：**不挑模型、不挑工具** —— 那两样都是管理员在 agent 配置里绑定的，运行时只负责**查出来并按治理规则过滤**（决策 #4）。

### 4.1 选哪个专家 Agent

**职责**：在多 Agent / 多专家场景下，决定**本步由哪个专家 Agent 处理**（客服 Agent、销售 Agent、订单 Agent、工单 Agent…）。

```
输入：本步意图（模型判定的 task_kind + 当前工具调用）
     + agent 目录里的专家清单（专家 Agent 也是 agent_versions 的一种，带 role 标签）
     + 当前会话的绑定 agent
输出：专家 Agent（agent_id + version + 指令片段）
```

| # | 规则 |
|---|---|
| 1 | **专家 Agent 是 agent 的一种 role**，复用 `agent_versions`（不新建表）。⚠️ **role 的落点**：`agent_versions` **没有 role / category 列** → 落在**模板的 `metadata` JSONB**（`category` / `tags`，见 `domain/catalog.py` 的 `apply_patch` 映射）→ **不需要新列、不需要新表**；只有当「同一模板的不同版本要扮演不同专家」时才需要版本级列（那时才要迁移） |
| 2 | **没有专家可路由时 → 落回会话绑定的 agent**（不是报错） |
| 3 | 路由决策**必须留痕**（写进 `session_turns.agent_decision` JSONB，Session 迁移 0046 已建列 —— ⚠️ **不是 `route_decision`**，那一列归 Router 写；两列语义不同、写入时刻不同，共用一列会互相覆盖）|
| 4 | **专家切换不改变会话绑定** —— 会话仍属于原 agent（否则历史上下文的解释方式会突变） |
| 5 | 专家 Agent 的工具集 = **专家自己配置里的绑定集**（§5.3.1）—— 专家本来就是一份 agent 配置，不存在「会话绑定 agent 的集合 ∩ 某个子集」 |

> **决策 #3（已定稿）**：专家 Agent 的建模 → **复用 `agent_versions` + role 标签**（不新建表）—— 专家与普通 agent 的差别只是「角色 + 工具子集 + 指令模板」，新建表会带来第三套 agent 语义。

### 4.2 专家配置即绑定来源

**「选专家」与「用什么模型 / 什么工具」是同一件事的两面** —— 因为**专家 Agent 本身就是一份 agent 配置**。

```
选专家 Agent ──▶ 取那份配置 ──▶ model_id / route_id            → ⑨ 模型解析（§5.2.1）
  （⑧ 唯一的       （本层只读）  allowed_tools / allowed_skills → ⑨ 工具绑定（§5.3.1）
    选择）                        knowledge_package_ids         → Context 层（不进本层）
```

| # | 规则 |
|---|---|
| 1 | **专家 = 一份 agent 配置**，不是「会话绑定 agent 的一个子集」—— 专家自带的模型与工具**整体替换**，**不做交集裁剪** |
| 2 | **专家切换不改变会话绑定**，但**改变本步用的模型与工具**（因为换了一份配置） |
| 3 | **落回会话绑定 agent 时，同样按它自己的配置取值** —— 不做「会话绑定的工具 ∩ 专家工具」这种二次裁剪 |
| 4 | **模型 / 工具的取值在 ⑨ Execution**（§5.2 / §5.3）；本层只负责**把选中的专家交出去** |
| 5 | 留痕记「**选了谁 + 取到了什么**」，不记策略推理过程（§4.1 规则 3） |

> **一句话**：⑧ 只回答「**这一步交给谁**」；「**他配了什么**」由 ⑨ 去取（配置轴），不由 ⑧ 去选。
---

## 5. ⑨ Execution Runtime · 执行运行时

### 5.1 Agent —— 具体 Agent 实例执行

**职责**：把「专家 Agent 的指令 + 本步上下文」变成一次实际推理。

| # | 要点 |
|---|---|
| 1 | 专家 Agent 的实例 = **`QZDAPChatModel` + 指令 + 工具集** —— 不是一个独立进程，是一次**受约束的模型调用**；其中模型来自 `model_binding`（§5.2.1）、工具来自 `tool_binding`（§5.3.1） |
| 2 | 专家 Agent 的指令来自 `agent_versions` 的 prompt 段（Context 层已把 agent 的 prompts 拼进 system） |
| 3 | 专家 Agent 的工具集 = **专家自己配置里的绑定集**（§5.3.1） |
| 4 | 专家 Agent 的调用**同样要计量与归属成本**（`session_turns.cost_usd`） |
| 5 | 专家 Agent **不持有状态** —— 状态在 LangGraph checkpoint 里 |

> **决策 #3 关联**：专家 Agent 不是一个「微进程 / 子图」，而是**「一个 prompt + 一个模型 + 一组工具」的组合**。这样它复用同一套治理、计量与幂等，不需要第二套运行时。

### 5.2 模型解析与调用（Execution 的模型侧）

#### 5.2.1 模型解析 —— **不是 Router**（决策 #4：**取消 Model Router**）

**平台的模型绑定关系是「管理员配置 → agent 绑定 → 运行时查表」**：

```
管理员在 model 模块配置模型（admin_models / admin_model_routes）
   → 配置 agent 时绑定（agent_versions.model_id 或 route_id）
      → 运行时**查表**得到这一次该用哪个模型
```

所以本层**没有「选大模型还是小模型」这个运行时决策** —— 模型是 agent 配置的绑定产物。

**取值链（解析，不是决策）**：

| # | 来源 | 落点 | 现状 |
|---|---|---|---|
| 1 | **显式指定**（请求带 model / route_id） | 请求体 | ✅ 已有（只影响这一次，不改配置） |
| 2 | **版本冻结**（agent 版本的 `model_id`） | `agent_versions.model_id` | ✅ 已有 |
| 3 | **策略路由**（agent 绑定了 `route_id`） | `agent_versions.route_id`（迁移 0042） | ✅ 已有 |
| 4 | **上游模型名解析**（`upstream_model` → `ModelId`） | `SqlCatalogModelResolver.resolve` | ✅ 已有 |
| 5 | **失败转移链**（primary + fallback） | `ModelService.stream_with_fallback` | ✅ 已有 |
| 6 | **环境默认模型** | 进程环境变量 | ✅ 已有 |

**取消的东西**（连同它们带来的跨模块前置）：

| 原方案 | 处置 |
|---|---|
| `balanced` 按 `task_kind` 分流 | ❌ **取消** —— 模型不是按任务难度在运行时挑的 |
| `route_strategy` 新取值（`latency_first` / `quality_first` / `balanced` / `cost_cap`） | ❌ **取消** —— 原本要扩展 `agent_factory` 的枚举（**跨模块前置**），既然不做运行时策略路由，这条前置一并作废 |
| `qzdap_model_routing_total{strategy, tier}` 指标 | ❌ **取消**（§12.2） |

> **若将来确实需要「同一 agent 按任务难度换模型」**，那是**一个新决策**（要么管理员在 route 配置里定死映射，要么引入运行时判定）—— **不在本方案范围内**。
> **当前口径**：**一个 agent 绑定一个模型（组）**；需要换模型 = 改 agent 配置（走版本发布），不是运行时偷偷换。

**必须保留的三个细节**（旧路径已实现，重写时最容易丢）：

| # | 细节 | 位置 |
|---|---|---|
| 1 | 解析失败 → **回退环境默认 LLM**，记 `catalog_resolve_no_match` | `chat_model.py:110-130`（`stream_chat` 起于 `:74`） |
| 2 | 租户守卫：`resolve` 的 WHERE 条件**必须含 `tenant_id`** | `catalog_model_resolver.py:60-66` |
| 3 | 策略路由（`route_id`）**优先于** `model_id` / `fallback_model_ids` | `adapter/llm/__init__.py:55-59` |

#### 5.2.2 LLM / SLM —— 调用模型完成生成

**这是本层与其它层最大的区别**：调用是**流式**的，且**工具调用以 delta 分片到达**。

| # | 要点 |
|---|---|
| 1 | `QZDAPChatModel`（`BaseChatModel` 子类）→ `_stream` 调 `LLMClient.stream()` → 逐个 yield `AIMessageChunk` |
| 2 | **工具调用装配** → `ToolCallAccumulator`（§3.1①） |
| 3 | 文本增量**边到边推**（SSE 前端低延迟） |
| 4 | 用量 → `AIMessageChunk.usage_metadata`；成本 → 平台的 `price_of` → `session_turns.cost_usd` |
| 5 | **失败转移链在这一层执行**（primary 失败 → fallback） |
| 6 | **模型上报的「上下文超限」不是本层的问题** → 交 Context 层重组 |
| 7 | **供应商级失败**（鉴权 / 限流 / 熔断）转成 `ToolException` 语义的错误，**不抛穿图** |

### 5.3 工具绑定、治理与执行（Execution 的工具侧）

**关键设计：Execution Runtime 不自己实现工具执行器。**

| 能力 | 归属 | 现状 |
|---|---|---|
| 协议派发（custom / openapi / mcp） | **`modules/tool`** | ✅ 已实现（`_dispatch`） |
| 治理闸门（`policy_guard.check`） | **`modules/tool`** | ✅ 已实现 |
| 调用落库（`tool_calls`） | **`modules/tool`** | ✅ 已实现 |
| 事件发布 | **`modules/tool`** | ✅ 已实现 |
| 超时 | **`modules/tool`**（30s 默认）+ 本层的更细粒度 | ✅ 已有 |
| **幂等** | 本层 → 落 `tool_executions` | ❌ **缺** |
| **重试 / 熔断** | 本层 | ❌ **缺** |
| **代码执行（沙箱）** | `modules/agent_runtime/adapter/sandbox/` + `runtimes/sandbox_runtime` | ⚠️ 有适配器 |
| **LLM / SLM** | 本层 `QZDAPChatModel` | ✅ 本层新建 |

**本层要做的是给 `modules/tool` 的执行路径补三样**，而不是另写一个执行器。

#### 5.3.1 绑定集读取与治理过滤 —— **不是「选择」**

**平台的工具绑定关系同样是「管理员配置 → agent 绑定 → 运行时取用」**：

```
管理员配置工具（modules/tool 的 custom / openapi / mcp；modules/skill 的 skill）
   → 配置 agent 时绑定（agent_versions.allowed_tools / allowed_skills）
      → 运行时**取绑定集** + 做**治理过滤**
```

**绑定集从哪来 —— 列已存在（迁移 0011），不需要新迁移**：

| agent 配置列 | 含义 | 本层用途 |
|---|---|---|
| `agent_versions.allowed_tools` | 允许的工具名数组 | 转成 `BaseTool` 列表 |
| `agent_versions.allowed_skills` | 允许的 skill 名数组 | 转成 `BaseTool` 列表 |
| `agent_versions.knowledge_package_ids` | 知识包 | **归 Context 层**（知识召回不进本层） |

**治理过滤（在绑定集之上）**：

```
最终暴露给模型的工具集 = agent 配置的绑定集
                        ∩ 风险策略允许集（PolicyGuard 的 risk 维度）
                        ∩ 作用域可见集（工具所属的工作区 / 数据范围）
                        − unprotected 轮次的副作用工具
```

| # | 规则 |
|---|---|
| 1 | 绑定集为空 → **不报错**，本步就是纯对话 |
| 2 | 过滤**不得**因为「筛不出工具」而阻断轮次 —— 降级为「无工具」 |
| 3 | **`unprotected` 轮次必须剔除副作用工具**（Gateway 决策 #5 的兑现点）—— **剔除，不是执行时拦截** |
| 4 | 高风险工具即使在绑定集里，也要等 `PolicyGuard` 判定（**筛不等于批**） |
| 5 | **tool / mcp / skill 统一成 `BaseTool`** —— 三种来源对模型是同一种东西（schema 相同） |
| 6 | **专家 Agent 的工具集 = 专家自己配置里的绑定集** —— 专家本来就是一份 agent 配置，不存在「会话绑定 agent 的集合 ∩ 专家子集」这种二次裁剪 |

**三种工具来源的统一**：

| 来源 | 平台的载体 | 统一到 |
|---|---|---|
| **tool**（custom / openapi） | `modules/tool` 的 `tools` 表（`ToolProtocol` = CUSTOM / OPENAPI） | `BaseTool` |
| **mcp** | `modules/tool` 的 MCP 协议派发（`MCPRuntime.list_tools` / `call_tool`） | `BaseTool` |
| **skill** | `modules/skill`（含 MCP 探活 `/api/admin/skills/mcp/probe`） | `BaseTool` |

> **「统一成 `BaseTool`」是本层的关键设计**：`ToolNode` 只认 `BaseTool`。三种来源在进入模型之前统一成 `BaseTool`，模型侧完全无感；执行时再按 `ToolMeta` 的 `protocol` 字段派发回 `modules/tool`。

**现状的缺口**：`ToolServiceAdapter.list_tools()` 已经有工具清单（含 `risk` / `needConfirm`），但：

| # | 缺口 | 修法 |
|---|---|---|
| 1 | **admin 注册的 OpenAPI / MCP 工具的 schema 是空的** —— `list_tools` 对不在内置目录里的工具返回 `{"type":"object","properties":{}}` | 工具绑定改为**从 `tools` 表的 spec 生成真实 schema** |
| 2 | **无 `unprotected` 剔除** | 按 Gateway 决策 #5 补 |

#### 5.3.2 幂等：唯一权威是 `tool_executions` 表

`tool_executions`（0035 已建）**列已经齐全**：`tool_call_id`(PK) · `idempotency_key`(UNIQUE) · `request_hash` · `status` · `result_ref` · `turn_id`(FK) · `tenant_id` · `workspace_id` · `started_at` · `finished_at`。

**执行流程**：

```
1. request_hash = sha256(canonical_json(arguments))
2. INSERT INTO tool_executions (tool_call_id, idempotency_key, request_hash, status='running', turn_id, …)
   ON CONFLICT (idempotency_key) DO NOTHING RETURNING tool_call_id
3. 冲突 → 读回既有行：
   · request_hash 不一致 → **拒绝**（TOOL_IDEMPOTENCY_CONFLICT）
     —— 同一幂等键用于不同参数，这是**调用方的 bug**，必须暴露
   · request_hash 一致且 status='succeeded' → **直接返回既有结果**（不重复执行）
   · status='running' → **并发中**，返回「执行中」错误（不重复执行）
4. 执行 → 更新行为 succeeded / failed + result_ref + finished_at
```

> **不需要新迁移** —— `tool_executions` 的列与唯一约束都已在 0035 建好。**只需要开始写它。**
>
> **`result_ref` 是引用不是正文**（String 512）—— 结果正文在 `tool_calls.result` 或对象存储，`tool_executions` 只存指针。这是**有意设计**，别改成塞正文。

**与 `tool_calls` 的关系**（两张表都要用，各司其职）：

| 表 | 职责 | 归属 |
|---|---|---|
| **`tool_executions`** | **幂等的唯一权威** + 与 `session_turns` 的关联（`turn_id` FK） | 会话域（Execution 写入） |
| **`tool_calls`** | 工具域的**调用明细**（参数、结果、耗时、协议） | `modules/tool`（已实现） |

两者用 **`tool_call_id` 关联**（`tool_executions.tool_call_id` = `tool_calls.id`）。**不合并成一张表** —— 它们的生命周期与所有者不同。

> **⚠️ 类型不一致，必须显式转换**：`tool_executions.tool_call_id` 是 **String(64)**，而 `tool_calls.id` 是 **UUID** → 写入时必须 `str(tool_call.id)`（UUID 对象无法直接落 String 列），读回比对时同理按字符串。

#### 5.3.3 重试与熔断

| # | 能力 | 规则 |
|---|---|---|
| 1 | 重试 | 指数退避 + jitter，**仅对 `idempotent=true` 且 transient 的错误** |
| 2 | 熔断 | 按**工具名**计连续失败 → 熔断 M 秒 → `TOOL_RATE_LIMITED` |
| 3 | 幂等命中 | **不重试**，直接返回既有结果 |
| 4 | 参数错误 | **不重试**（`TOOL_ARGUMENT_INVALID`） |

#### 5.3.4 沙箱（代码执行）

| # | 要点 |
|---|---|
| 1 | 沙箱调用也是一次工具调用 → **同样走 `ToolRuntime`**（超时、重试、幂等、熔断） |
| 2 | 产物（文件、stdout）走 `AttachmentRef` 形状，与 Gateway 的附件语义一致 |
| 3 | 沙箱内的网络 / 文件访问由**沙箱侧策略**决定，不由本层决定 |
| 4 | 沙箱失败 → 结构化错误，**不抛穿图** |

### 5.4 Execution Runtime 的统一契约

```
ToolRuntimePort
    async def invoke(
        *,
        tool_call_id: str,
        tool_name: str,
        arguments: dict,
        idempotency_key: str,
        turn_id: str,
        actor: ActorContext,          # ← 真实 actor，不是 "u-1"
        protected: bool,              # ← False = unprotected（禁用副作用工具）
    ) -> ToolResult:
        result, is_error, error_code, error_message, retry_after_ms, latency_ms, attempts
```

---

## 6. 与相邻层的边界

| 方向 | 契约 |
|---|---|
| Context → Agent Loop | `AssembledContext.messages`（`[{role, content}]`） |
| Agent Loop → Agent Router | `AgentSelection`（**只有专家选择一个决策** —— 模型 / 工具不是决策，见决策 #4） |
| Agent Router → Agent Catalog | `AgentCatalogService`（已有）→ category / visible_scope / profile / version / model_id / route_id |
| **Execution → Model 模块** | `ModelResolverPort.resolve` / `price_of`（`SqlCatalogModelResolver` 实现）—— **取值**，不是「选模型」 |
| **Execution → Tool 模块** | `ToolServiceAdapter.list_tools`（工具清单）+ `modules/tool` 的三种协议 —— **按绑定集取**，不是「选工具」 |
| Agent Loop → Execution | `LLMRequest` / `ToolCall` |
| Execution → `modules/tool` | `InvokeToolUseCase.execute`（**已实现，Execution 只补幂等 / 重试 / 熔断**） |
| Execution → Sandbox | `SandboxPort`（`adapter/sandbox/` 已有） |
| Agent Loop → Memory | **写入触发**（本轮产生的内容 → Writer） |
| Agent Loop → Session | 轮次状态更新、审批挂起请求、事件产出 |
| Agent Loop → Gateway | **无直接契约** —— 结果经 Session 落 `session_events`，由 Gateway 投递 |

**四个容易混的边界**：

1. **Agent Loop 不直接读记忆表** —— 召回只经 Context。
2. **Agent Router 不选「会话绑定 agent」** —— 那是 Router 层（⑤）的事；Agent Router 只选**本步的专家 Agent**；**它也不选模型、不选工具**（决策 #4）。
3. **Execution 不做决策** —— 「暴露哪些工具」是**绑定集 + 治理过滤**的结果（不是运行时选择），「要不要调」是 Agent Loop 决定的，「工具怎么执行」才是 Execution 的事。
4. **Execution 不自己实现工具协议** —— custom / openapi / mcp 的派发归 `modules/tool`。

---

## 7. 数据与表

### 7.1 表终态

| 表 / 列 | 处置 | 说明 |
|---|---|---|
| `tool_executions` | **启用（开始写入）** | 幂等的唯一权威。**列已在 0035 建齐，不需要新迁移** |
| `tool_calls` | **保留**（`modules/tool` 在用） | 工具域的调用明细，用 `tool_call_id` 与 `tool_executions` 关联 |
| `session_turns.cost_usd` | **启用**（迁移 0043 已建） | 本层写入 |
| `session_turns.agent_decision` | **启用**（迁移 0046 已建） | 本层的路由留痕：**选了哪个专家** + **解析出的模型 / 工具集**（**记「用了什么」，不记「为什么挑了它」**）。⚠️ **不写 `route_decision`** —— 那一列的唯一写者是 Router（会话入口的策略决策）|
| `agent_versions.route_id` / `route_strategy` | **保留**（迁移 0042 已建） | 模型解析的落点（`route_id` → `admin_model_routes`，迁移 0025）。⚠️ **不再扩展 `route_strategy` 的取值** —— 决策 #4 取消运行时策略路由后，**跨模块前置一并作废** |
| `agent_versions.allowed_tools` / `allowed_skills` / `knowledge_package_ids` | **保留**（迁移 0011 已建） | **工具绑定集的落点**（§5.3.1）—— **不需要新列** |
| `agent_versions.model_id` | **保留** | 版本冻结的模型 |
| `admin_model_routes` / `admin_model_quotas` | **保留** | 策略路由定义与配额 |
| checkpoint 四表（`checkpoints` / `checkpoint_blobs` / `checkpoint_writes` / `checkpoint_migrations`） | **由 Session 迁移 0046 建** | 本方案只使用，不建表。⚠️ 表名按已安装的 `langgraph-checkpoint-postgres` 3.1.3（**无 `langgraph_` 前缀**）|

### 7.2 迁移

**本方案不需要新的迁移。**

| 需要的 DDL | 已在哪个迁移 |
|---|---|
| `tool_executions` 的列 + `idempotency_key` 唯一约束 | **0035**（已建，零代码引用） |
| `session_turns.cost_usd` | **0043** |
| `session_turns.agent_decision` / `route_decision` / `ingress_seq` | **0046**（Session 方案）|
| `agent_versions.route_id` / `route_strategy` | **0042** |
| checkpoint 四表 | **0046**（Session 方案） |

> **唯一的新增依赖**是 `deepagents`（决策 #8）—— 若采纳，需在 `runtimes/agent_runtime/pyproject.toml` 声明并更新 `uv.lock`。
>
> ~~**`route_strategy` 新取值**~~ —— **决策 #4 取消后不再需要**：本方案不做运行时策略路由，`route_strategy` 保持 0042 的现有取值集合，**也不占 0049 之后的迁移编号**。

### 7.3 回滚

本方案无新迁移，**回滚 = 回退代码 + 停止写 `tool_executions`**。注意：

| # | 风险 | 说明 |
|---|---|---|
| 1 | `tool_executions` 一旦开始写，**回滚后仍是孤儿表** | 与今天的 `tool_executions` 状态一致（已建、零引用）—— 可接受 |
| 2 | `session_turns.cost_usd` 开始有值后回滚 | 值留着不影响功能（列已有，只是没人写） |
| 3 | `route_decision` 的新结构 | JSONB，**旧数据不受影响**；回滚后新数据格式不被旧代码读，但旧代码本来就不读它 |

---

## 8. 逐文件改造与删除清单

### 8.1 新增（`backend/runtimes/agent_runtime/src/qzdap_agent_runtime/`）

| 文件 | 内容 |
|---|---|
| `agent_loop/reason.py` | `Reasoner`：上下文 + 工具 schema（**从绑定集取**）+ 模型（**从配置解析**）→ 流式文本 + 工具调用（**含 `ToolCallAccumulator` 迁入**） |
| `agent_loop/observe.py` | `Observer`：工具结果 → `ToolMessage` |
| `agent_loop/evaluate.py` | `Evaluator`：continue / exit / suspend / abort（**六个终止条件的单一判定点** + `apply_stall_guard` 护栏迁入） |
| `agent_loop/runner.py` | `AgentLoopRunner`：循环本体 |
| `agent_loop/graph.py` | LangGraph 6 节点装配 + `interrupt` / `Command` 恢复 |
| `agent_router/agent_router.py` | `AgentRouter`：选专家 Agent |
| `agent_router/classifier.py` | `TaskClassifier`（启发式降级 + 生产分类器接口） |
| `execution/model_binding.py` | **模型解析**：从**当前执行的 agent** 的配置取 `model_id` / `route_id` → 构造 `QZDAPChatModel`。⚠️ **查表，不是决策**（决策 #4，见 §5.2.1） |
| `execution/tool_binding.py` | **工具绑定集读取 + 治理过滤**：从**当前执行的 agent** 的配置取绑定集（`allowed_tools` / `allowed_skills`）→ tool / mcp / skill 统一成 `BaseTool` → ∩ 风险 ∩ 作用域 → 剔除 `unprotected` 的副作用工具。⚠️ **不做「选择」**（§5.3.1） |
| `execution/chat_model.py` | `QZDAPChatModel(BaseChatModel)` 适配器（**打通 LangChain 生态的关键**）—— **模型来自 agent 配置**（§5.2.1），不是运行时挑的 |
| `execution/llm_client.py` | LLM / SLM 调用 + 失败转移链 + 用量回报 |
| `execution/tool_runtime.py` | `ToolRuntime`：幂等（`tool_executions`）+ 重试 + 熔断，调 `modules/tool` |
| `execution/agent_executor.py` | 专家 Agent 实例执行 |
| `execution/sandbox.py` | 代码执行环境（薄封装，转 `modules/agent_runtime/adapter/sandbox/`） |
| `deep/factory.py` | Deep Agents 工厂（决策 #8） |
| `deep/planner.py` | 深度任务的规划器与子代理派发 |
| `ports.py`（扩） | 补 `LLMPort` / `ModelResolverPort` / `ToolBindingPort` / `AgentRouterPort` / `ToolRuntimePort` —— ⚠️ **没有 `ToolRouterPort`**（决策 #4 取消了「工具路由」这个概念） |

### 8.2 迁移

| 旧位置 | 迁到 | 动作 |
|---|---|---|
| `adapter/graph/chat_model.py` `ToolCallAccumulator` | `agent_loop/reason.py` | **迁入**（最容易写错的逻辑） |
| `adapter/graph/chat_model.py` `stream_chat` / `complete_chat` | `execution/llm_client.py` | 迁入 |
| `adapter/graph/runner.py` 的 ReAct 循环（`_run_turn_inner`） | `agent_loop/runner.py` | **迁入并重写**（旧版把编排与治理混在一起） |
| `adapter/graph/runner.py` `_price_of` | `execution/llm_client.py` | 迁入 |
| `adapter/graph/loop.py` `apply_stall_guard` | `agent_loop/evaluate.py` | **迁入护栏** |
| `runtimes/.../graph/nodes.py` 的 `agent` / `execute` / `governance` | `agent_loop/*` + `execution/*` | 拆散重写 |
| `runtimes/.../execution/executor.py` `InMemoryToolExecutor` | `execution/tool_runtime.py` | 幂等改落库 |
| `runtimes/.../graph/routing.py` `classify_task_kind_heuristic` | `agent_router/classifier.py` | 保留为降级实现 |

### 8.3 保留但改造

| 文件 | 改造点 |
|---|---|
| `adapter/llm/__init__.py` `LLMPortAdapter` | 保留，实现 runtime 的 `LLMPort`；**被 `QZDAPChatModel` 包装** |
| `adapter/persistence/catalog_model_resolver.py` | 保留；实现 `ModelResolverPort` |
| `adapter/tools/tool_service_adapter.py` | 保留；`list_tools` 的**空 schema 问题**要修（改为从 `tools` 表 spec 生成） |
| `adapter/sandbox/*` | 保留；由 `execution/sandbox.py` 薄封装 |
| `adapter/skills/skill_service_adapter.py` | 保留；作为工具绑定的第三类来源 |
| `adapter/orchestration/subagent_adapter.py` | 保留（决策 #8 砍掉 deep path 时暂不接线） |
| `runtimes/.../tools/registry.py` | 保留；接真实工具服务（现在只有内存注册） |
| `runtimes/.../graph/deep_agent.py` | 保留**类型定义**；`InMemoryDeepAgentFactory` 视决策 #8 处置 |
| **`modules/tool/.../invoke_tool.py`** | **保留 + 补幂等 / 重试 / 熔断**（本方案的主要落点之一） |

### 8.4 删除清单

| 类别 | 具体 | 阶段 |
|---|---|---|
| 19 节点图的骨架 | `graph/nodes.py` 中被 §2.3 判为「✗」的 13 个节点函数 | **Stage 7** |
| 19 节点的装配 | `graph/builder.py` 的 `build_session_graph` → 改为 6 节点版 | **Stage 7** |
| 同步 saver 工厂 | `builder.py` 的 `from_url`（同步 `PostgresSaver`） | **Stage 7**（随 19 节点装配一并删除）。⚠️ **接线的改造不归本层** —— 归 **Session §5.3 / 迁移 0046**（改用 `AsyncPostgresSaver` + 建 checkpoint 表） |
| 进程内幂等缓存 | `executor.py` 的 `_idempotency_cache` 作为**权威**（降级为快速路径） | Stage 3 |
| 硬编码 actor | `nodes.py:644` 的 `actor_id="u-1"` | Stage 2 |
| 旧 runner 的 ReAct 循环 | `adapter/graph/runner.py` `_run_turn_inner` | **Stage 5（停用 + 打点）→ Stage 7（删除）** |
| 旧路径的**残留 LangGraph** | `adapter/graph/loop.py` 的 `compile_loop_graph`（**X5**） | **Agent Stage 7**（与 X17 **同一批**删）—— ⚠️ `runner.py:44` import 它 → 它必须活到旧 runner 退役；初稿在同一行里既写「Stage 7」又写「Session Stage 3」，已统一（台账 §5.4 同步） |

---

## 9. 实施阶段

> 每阶段验收都含「**旧代码减少了什么**」。

### Stage 0：契约与依赖

| 动作 | 细节 |
|---|---|
| 补五个端口 | `LLMPort` / `ModelResolverPort` / `ToolBindingPort` / `AgentRouterPort` / `ToolRuntimePort` 写进 runtime 的 `ports.py`（**无 `ToolRouterPort`** —— 决策 #4） |
| `QZDAPChatModel` 骨架 | `BaseChatModel` 子类，`_stream` 走 `LLMClient.stream()`；**先只支持 mock 供应商** |
| 归一 `TaskKind` 与 `TaskClassifier` | `routing.py` → `agent_router/classifier.py`（含 confidence） |
| **依赖核对** | 确认 `langgraph` / `langgraph-prebuilt` / `langchain-core` 版本满足；`deepagents` 是否加（决策 #8） |
| **收敛基础设施** | 建 `qzdap_legacy_calls_total` 指标（若尚未建立），给 X5 的旧入口打点。见 `cleanup-ledger.md` §3.2 |

**旧代码减少**：无（纯新增）。
**验收**：五个端口有契约测试；**`QZDAPChatModel` 是 `langchain_core.BaseChatModel` 的实例，且能作为 LangGraph 节点的 `model` 参数被调用**；`/metrics` 能查到 `qzdap_legacy_calls_total`。

#### 实施记录（2026-10-30 · Stage 0：契约与依赖）

| 项 | 结果 |
|---|---|
| **A-01 五个端口** | ✅ 写进 runtime 的 `ports.py` ✓ —— `LLMPort` ✓ / `ModelResolverPort` ✓ / `ToolBindingPort` ✓ / `AgentRouterPort` ✓ / `ToolRuntimePort` ✓（+ 它们要用的形状：`ToolBinding` ✓ / `AgentSelection` ✓ / `ToolInvocation` ✓ / `ToolInvocationResult` ✓）。⚠️ **没有 `ToolRouterPort`** ✓（决策 #4 ✓ —— 有一条测试专门断言它**不存在** ✓） |
| **端口的语义边界** | ⚠️ **端口只「取」不「选」** ✓ —— `LLMPort` 只管调 ✓（模型是谁由 `ModelResolverPort` **查表** ✓）；`ToolBindingPort` 只把 agent 配置里声明的绑定集**取出来** ✓（治理过滤在 ⑨ Execution 那一侧 ✓ —— 端口不重复那份规则 ✗✗）；`AgentRouterPort` 只回答「这一步交给谁」✓ |
| **A-02 `QZDAPChatModel` 骨架** | ✅ `execution/chat_model.py` ✓ —— `BaseChatModel` 子类 ✓；`_astream` → `LLMClient.stream()` ✓ → 逐个 yield `AIMessageChunk` ✓；**只做类型翻译** ✓（不碰供应商 ✓ / 不碰路由 ✓ / 不碰成本 ✓ —— §2.2 ✓）。⚠️ **同步路径明确报错** ✓（平台的客户端只有异步 ✓ —— 基类默认把同步 `_generate` 丢线程池 ✗ → `_agenerate` **必须覆盖** ✓ —— 由流式聚合 ✓） |
| **A-03 归一 `TaskKind` 与 `TaskClassifier`** | ✅ **从 `graph/routing.py` 迁到 `agent_router/classifier.py`** ✓（分类器归**专家路由**那一侧 ✓ —— 它不是图节点的附属品 ✓）。⚠️ **返回值多了置信度** ✓（`TaskClassification(kind, confidence, reason)` ✓）—— 启发式的刻度 ✓（**不是概率** ✗✗ —— 别当校准过的概率用 ✗） |
| **A-04 依赖核对** | ✅ 版本与方案 §2.1 一致 ✓：`langgraph` **1.2.12** ✓ / `langgraph-prebuilt` **1.1.0** ✓ / `langchain-core` **1.6.6** ✓；`deepagents` **未安装** ✓（决策 #8：Stage 6 可选 ✓ → **不加** ✓）。⚠️ **runtime 的 pyproject 之前只靠 checkpointer 传递引入** ✗ → **显式声明** ✓（直接 import 的依赖就该写出来 ✓）`uv.lock` 离线重锁 ✓（无版本变动 ✓） |
| **A-05 打点 X5 旧入口** | ✅ 已有 ✓（`runner.py:104` 的 `record_legacy_call("X5")` ✓ —— 占位图 `compile_loop_graph` ✓）；扫描规则**仍关着** ✓（它归 Agent Stage 7 与 `X17` 同批删 ✓） |
| **旧代码减少** | **0 行**（本 Stage 是纯新增 ✓ —— 方案 §9 的原话 ✓）；⚠️ **迁移了 `graph/routing.py`** ✓（→ `agent_router/classifier.py` ✓ —— **不是新增一份** ✗✗，「不能出现两套实现」✓），调用方跟着改 ✓（`nodes.py` ✓ / `engine.py` ✓ / `graph/__init__.py` 不再导出 ✓ / 测试 ✓） |
| **顺带修掉的一个假数据** | ⚠️ `nodes.py` 的 route 节点把 **`confidence` 写死成 1.0** ✗（那是假的 ✗✗）→ 现在取分类器给的真实置信度 ✓ + 真实 `reason` ✓ |
| 测试 | 新增 `runtimes/agent_runtime/tests/test_agent_contracts.py` ✓（11 条 ✓：五个端口的契约 ✓ + **没有 `ToolRouterPort`** ✓ + `QZDAPChatModel` 是 `BaseChatModel` 实例 ✓ + 能 `ainvoke` ✓ + 能 `astream` ✓ + 同步路径明确报错 ✓ + 分类器的置信度序 ✓）；`test_routing_heuristic.py` 跟着改 ✓（返回值多了置信度 ✓） |
| 回归 | `pytest` **1870 passed** ✓（1 失败 + 4 error 与改动前一致 ✓ —— 环境问题 ✗）；mypy **无新增** ✓（前后同 20 条 ✓）；import-lint ✓ |

⚠️ **本 Stage 之后仍未做的**（归后续 Stage ✓）：

| 项 | 归属 |
|---|---|
| 五个端口的**模块侧实现**（`LLMPortAdapter` 实现 runtime 的 `LLMPort` ✓ / 模型解析 ✓ / 绑定集读取 ✓ / 专家路由 ✓ / 工具运行时 ✓） | **Stage 1–4** ✓ |
| `QZDAPChatModel` 接**真实供应商**（解析 + 失败转移链 ✓ —— §5.2.1 的六条取值链 ✓） | **Stage 1** ✓ |
| `nodes.py` / `engine.py`（19 节点图与新 engine）—— **没有生产调用方** ✓ | **Stage 7**（整体删 ✓） |
> ⚠️ **不要用「能被 `ToolNode` 接受」当判据** —— `ToolNode` 接受的是**工具列表**，不是 chat model。工具侧的判据是「`BaseTool` 列表能被 `ToolNode` 接受」（Stage 2 的验收）。模型侧的判据是 `BaseChatModel` 实例 + 能作为 `model` 被接受 —— 这一条正是 Deep Agents（Stage 6）`create_deep_agent(model=...)` 的硬前置。

### Stage 1：LLM / SLM 调用（Execution 的模型侧）

| 动作 | 细节 |
|---|---|
| `QZDAPChatModel` 落地 | `_stream` → `AIMessageChunk`；用量 → `usage_metadata` |
| `LLMClient` 封装 | 失败转移链（primary → fallback） |
| `Reasoner` | 上下文 + 工具 schema → 流式文本 + 工具调用（**迁入 `ToolCallAccumulator`**） |
| **迁移** `adapter/graph/chat_model.py` 的 `stream_chat` / `ToolCallAccumulator` | **本 Stage 只迁入，不删** —— ⚠️ `runner.py:36`（web 路径）与 `use_cases/run_turn.py:49`（IM 路径）**都还在 import 它**；删除需 **Agent Stage 5 的 A-26**（旧循环改接）**且** **Session Stage 5b**（IM 入口切换后 `run_turn.py` 被删）**都完成** → 删除落在 **Stage 7**（保留 `LLMPortAdapter`） |

**旧代码减少**：`chat_model.py` 的**代码迁出**（~200 行）；**文件删除推迟到 Stage 7**（两个前置都完成后）。
**验收**：分片到达的 tool call 能正确装配成完整调用；文本 delta 实时到达；解析失败回退环境默认模型；**`QZDAPChatModel` 是 `BaseChatModel` 实例且能作为 LangGraph 节点的 `model` 被调用**（验证 LangChain 生态打通 —— 注意判据的对象是**模型**不是工具列表）。
>
> ⚠️ **不用 `create_react_agent` 做验收** —— 决策 #1 已定「自建 6 节点 StateGraph」。`create_react_agent` 只作为**生态打通的旁证**，不是交付物。

### Stage 2：工具绑定与治理接线

| 动作 | 细节 |
|---|---|
| **工具绑定 + 治理过滤** | 从 **agent 配置的绑定集**（`allowed_tools` / `allowed_skills`）取工具 → tool / mcp / skill **统一成 `BaseTool`**；再 ∩ 风险 ∩ 作用域；**`unprotected` 剔除副作用工具** |
| 修 `list_tools` 的空 schema | 改为从 `tools` 表的 spec 生成真实 schema |
| `governance` 接线 | 真实 actor（**删掉 `actor_id="u-1"`**）；审批挂起走 `interrupt()` |
| **真实 actor 注入到新的 `AgentLoopRunner`** | ⚠️ **不改 `runtimes/.../graph/nodes.py`** —— 那个文件从未接线、且在 Stage 7 会整体删除，在这里改它是**改死代码**。actor 从 Session 的轮次上下文（`session_turns` 的用户/租户列）注入 |

**旧代码减少**：硬编码 actor 消除（`actor_id="u-1"` 归零）。`nodes.py` 的 `governance` 节点**留到 Stage 7 随整文件删除** —— 提前改它是改死代码。
**验收**：actor 是真实用户；取不到 actor → **拒绝执行工具**；`unprotected` 轮次**不产生任何副作用工具调用**；admin 注册的 OpenAPI / MCP 工具有真实 schema。

### Stage 3：Tool Runtime 落库化（幂等 / 重试 / 熔断）

| 动作 | 细节 |
|---|---|
| `tool_executions` 开始写 | 幂等的唯一权威（`ON CONFLICT DO NOTHING` → 冲突读回） |
| `request_hash` 冲突 | **拒绝**（`TOOL_IDEMPOTENCY_CONFLICT` —— ⚠️ **该错误码目前不存在**：`ErrorCode` 枚举里没有、全仓零命中 → 本阶段要**新增**并同步 `libs/schema` 与前端契约），不静默返回旧结果 |
| 重试 / 熔断 | 指数退避 + jitter；按工具名熔断 |
| **修复 async** | `execute` 节点改 `await`，删除 `run_async_from_sync` 绕行 |
| 沙箱接入 | 作为一类工具走同一 `ToolRuntime` |
| 成本结算 | `usage` + `price_of` → `session_turns.cost_usd` —— ⚠️ **`session_turns.cost_usd` 是 0035 建的**；**0043 加的是 `agent_turns.cost_usd`**（旧表，Session Stage 6 会 DROP）→ **别写错表** |

**旧代码减少**：进程内幂等缓存降级为快速路径。`nodes.py` 的 `execute` 节点**留到 Stage 7 随整文件删除**。
**验收**：同一 `idempotency_key` 在**两个 worker** 上并发调用 → **只执行一次**；`tool_executions` 有真实行；同键不同参数 → 明确错误；成本落到 `session_turns.cost_usd`。

### Stage 4：专家 Agent 选择 + 配置取值接线

> **开工前置**：**Session 迁移 0046 已落地**（`session_turns.agent_decision` 列存在 —— 本层的路由留痕要写它）。本阶段**不依赖** Session 的 turn 实现，只依赖**表结构**。
>
> **⚠️ 本阶段不再是「三路路由」**：按决策 #4，模型与工具**不是运行时选择** —— 本阶段做的是「**从 agent 配置把模型与工具解析出来**」，并把它们**接到选中的专家**上。

| 动作 | 细节 |
|---|---|
| `AgentRouter` | 选专家 Agent；无专家 → 落回会话绑定 |
| **模型解析接线** | 把**选中专家**的 `model_id` / `route_id` 交给 Execution 的模型解析（§5.2.1）→ 构造 `QZDAPChatModel` 实例（**查表，不是决策** —— 决策 #4） |
| **工具绑定接线** | 把**选中专家**的绑定集交给 Execution 的工具绑定（§5.3.1）→ 统一成 `BaseTool` + 治理过滤 |
| 路由留痕 | 专家选择 + 模型 / 工具的**解析结果**写进 `session_turns.agent_decision`（**记「用了什么」，不记「为什么挑了它」**）。⚠️ **不写 `route_decision`**（Router 的列）|
| **每步留痕（追加式）** | 每一步的专家选择**同时**作为审计事件写进 `session_events`（`event_type = agent.expert.selected`，见 §12.3）—— `agent_decision` 是**轮次级快照**（最后一个专家），完整历史在事件流里 |

**旧代码减少**：`adapter/llm/__init__.py` 的 6 个散装参数收敛为一个端口调用。
**验收**：**专家选择有独立测试**；模型与工具的**取值**结果 == agent 配置里绑定的那些（**代码里没有运行时「挑」的逻辑** —— 决策 #4）；`agent_decision` 完整留痕、**不碰 `route_decision`**；**专家切换不改变会话绑定**。

### Stage 5：循环与终止条件

> **开工前置（硬）**：**Session Stage 3（唯一 turn 实现）已完成**。理由：Agent Loop 是**跑在一轮之内**的循环 —— 没有唯一的 turn 编排，两边都会认为自己该管这件事，产生第二套循环语义。

| 动作 | 细节 |
|---|---|
| `AgentLoopRunner` + `Evaluator` | Reason → Observe → Evaluate；**六个终止条件的单一判定点** |
| **把 `_run_turn_inner` 改接新 Builder / Writer** | ⚠️ **旧循环的最后一次改造**：`runner.py:179` 的 `_load_messages` 与 `runner.py:467` 的 `_remember` 换成对 `context/builder.py` + `memory/writer.py` 的调用。**这一步做完，X8 / X10 / X11 才真正无调用方** —— Context Stage 4 与 Memory Stage 7 才能删。**开工前置：Context Stage 1–3 与 Memory Stage 3 已完成** |
| 端到端回归 | 简单问答 / 多工具 / 工具失败 / 审批挂起恢复 / 取消 / 超预算 / 专家路由 |

**旧代码减少**：`adapter/graph/runner.py` 的 `_run_turn_inner` 停用 + 打点（台账 **X17**）。
**验收**：**存在一条端到端测试跑完整个循环**（不是逐节点单测）—— 2026-10-15 那次失败的直接教训；六个终止条件各有一条测试。

#### 实施记录（2026-10-30 · Stage 5 的 **A-26**：旧循环改接新 Builder / Writer）

> ⚠️ **只做 A-26 这一行** ✓ —— `AgentLoopRunner` / `Evaluator`（A-25）与端到端回归（A-27）**还没做** ✗。
> 理由：**A-26 是解锁项** ✓ —— 它不做，Context Stage 4（停用 X8/X9/X10）与 Memory Stage 7（删 `_remember`）**都不能开始** ✗✗。

| 项 | 结果 |
|---|---|
| 上下文装配 | `runner.py:184` 的 `_load_messages` → **新的 `ContextBuilder.build`** ✓（`context/builder.py` ✓）—— 固定优先级拼装 ✓、manifest ✓、`recall_degraded` 可见 ✓、知识命中**顺带带回**给 `knowledge_search` 事件 ✓（不必再召回一次 ✗✗） |
| 记忆写入 | `runner.py:479` 的 `_remember` → **`MemoryPort.write_turn`** ✓（端口写进 `application/ports` ✓）→ `MemoryServiceAdapter.write_turn` ✓ → `MemoryRuntimeService.write_turn` ✓ → 契约层 `memory/writer.py` **五步流水线** ✓ |
| **输入只有本轮对话** | `write_turn` 的入参**只有 `user_input` + `assistant_reply`** ✓ —— ⚠️ **不含召回结果** ✓（Memory 方案 §4.6 ✓：从召回结果反推 = 记忆的自我强化循环 ✗✗） |
| 旧函数体 | `_load_messages` / `_remember` **函数体留着** ✓ —— ⚠️ **但已无调用方** ✓（grep 只剩注释与打点 ✗）→ 删除分别归 **Context Stage 5** 与 **Memory Stage 7** ✓（**删除责任按层分** ✓ —— 不在本层越界删 ✗） |
| **旧路径变小（实测）** | 演示栈重启后发一轮真实请求：`qzdap_legacy_calls_total{entry="X8"}` = **0** ✓、`{entry="X11"}` = **0** ✓、`{entry="X9"}` = **1** ✓（压缩还没切 ✓）、`{entry="X17"}` = 1 ✓（旧循环本体仍在服役 ✓） |
| 线上行为 | `knowledge_search` 事件**正常产出** ✓（命中 3 条 ✓）→ 随后 `TURN_FAILED` ✓ —— ⚠️ **演示库没配 LLM 供应商** ✓（不是回归 ✗） |
| 端口 | `MemoryPort` 加 `write_turn` ✓（**不是新开一条写路径** ✗ —— 旧的 `write` 保留给管理面/旧调用 ✓，但轮次收尾**只走 `write_turn`** ✓） |
| 契约层边界 | `ContextBuilder` / `write_turn` 的端口都在**契约层**（`qzdap_agent_runtime` ✓），模块侧只做适配 ✓ —— import-lint 通过 ✓ |
| 测试 | 旧 fake 端口补 `write_turn` ✓（`test_graph_recall_hooks.py` / `test_loop_agent.py` ✓）—— 召回调用与写入调用**分开记录** ✓（否则「召回带 user_id」的断言会被写入调用污染 ✗） |
| 全量回归 | `pytest` **1848 passed** ✓ —— 1 个失败（`modules/model` 的 `test_catalog_http_database`）与 4 个 error（testcontainers 拉镜像超时）**在改动前后完全一致** ✓（HEAD 上同样失败 ✓ —— 环境问题 ✗ 不是本次引入 ✗） |

⚠️ **本 Stage 尚未完成的部分**（A-25 / A-27 / A-28 ✗）：

| 项 | 状态 | 门禁 |
|---|---|---|
| **A-25 `AgentLoopRunner` + `Evaluator`** | ✗ 未做 | 六个终止条件的**单一判定点** —— 旧循环的终止判定还散在 `runner.py` 里 ✗ |
| **A-27 端到端回归** | ✗ 未做 | ⚠️ **演示栈没有 LLM 供应商** ✓ → 端到端回归要么补一个 mock 供应商的测试环境 ✓，要么等真实环境 ✓ |
| **A-28 停用 + 打点 `_run_turn_inner`** | ✗ 未做 | 旧循环**仍在服役** ✓（它是唯一在跑的循环 ✗）→ 归 Stage 7 ✗ |

### Stage 6：Deep Agents（决策 #8 采纳时才做）

> **开工前置**：**Stage 1 已完成**（`QZDAPChatModel` 可用 —— Deep Agents 的模型参数必须是 LangChain 的 `BaseChatModel` 或 `Runnable`，见 §2.2）。**决策 #8 未采纳则本阶段整段跳过**，类型定义保留即可。

| 动作 | 细节 |
|---|---|
| 加依赖 | `deepagents` 进 `runtimes/agent_runtime/pyproject.toml` + 更新 `uv.lock` |
| `deep/factory.py` | `create_deep_agent` 包装，模型 = `QZDAPChatModel` |
| `deep/planner.py` | 规划器 + 子代理派发；子代理工具集 = **子代理自己配置里的绑定集** |
| 预算 | `DeepAgentConfig.max_steps` / `max_cost_usd` / `SubAgentSpec`（**已有结构**） |

**旧代码减少**：`nodes.py` 的 `deep_agent_plan` / `subagent` 空壳删除。
**验收**：深度任务能产出规划清单并逐步执行；**子代理的工具调用同样经过治理**；超预算抛明确错误。

### Stage 7：清理与封口

| 动作 | 细节 |
|---|---|
| 删 `graph/nodes.py` 的 13 个节点 | §2.3 表 |
| `graph/builder.py` 改为 6 节点版 | |
| 删 `adapter/graph/runner.py` 的 ReAct 循环 | |
| 删 `adapter/graph/loop.py` 的 `compile_loop_graph`（X5） | ⚠️ **与 X17 同批删除**（`runner.py:44` import 它 → 必须活到旧 runner 退役）；台账 §5.4 已同步为 **Agent Stage 7** |
| 删 `adapter/graph/chat_model.py`（迁出后的残留） | ⚠️ 前置：**Agent Stage 5 的 A-26** 与 **Session Stage 5b** **都**已完成（`runner.py` 与 `run_turn.py` 都不再 import 它） |
| 删 `executor.py` 的 `InMemoryToolExecutor` | |
| 启用 CI 扫描脚本 | 台账 X5 段 |
| 更新台账状态 | X5 → 已清理；X1 的 Agent 部分 → 已清理 |
| 更新现状文档 | `docs/copilot-chat-module-architecture.md` |

**旧代码减少**：§8.4 删除清单**归零** —— `graph/nodes.py` 的 13 个错位节点（~700 行）+ `graph/builder.py` 的 19 节点装配（~177 行）+ `adapter/graph/runner.py` 的 `_run_turn_inner`（~250 行）+ `adapter/graph/loop.py` 的 `compile_loop_graph`（~70 行）+ `executor.py` 的 `InMemoryToolExecutor`（~305 行），**合计约 1500 行**。
**验收**：台账 X5 与 X1 的 Agent 部分「已清理」；扫描脚本无命中。

### 阶段与「旧代码减少」对照

| 阶段 | 删除/替换 | 旧代码减少（行） | **新写入量（估算）** | 旧路径状态 |
|---|---|---|---|---|
| Stage 0 | 无（纯新增） | 0 | `tool_executions` 准备就绪（还不写） | — |
| Stage 1 | `chat_model.py` 迁出 | ~200 行 | 同上 | 停用 + 打点 |
| Stage 2 | 真实 actor 注入新 AgentLoop（硬编码 `actor_id="u-1"` 消除） | ~5 行 | 同上 | 直接替换 |
| Stage 3 | `executor.py` 的 `InMemoryToolExecutor` | ~200 行 | **`tool_executions`：每次工具调用 1 行** | 停用 + 打点 |
| Stage 4 | `adapter/llm` 的散装参数 | ~40 行 | 同上 | — |
| Stage 5 | `runner.py` 的 `_run_turn_inner` | ~250 行 | 同上 | 停用 + 打点 |
| Stage 6 | `nodes.py` 的 deep 分支空壳 | ~130 行 | 同上 | 停用 + 打点 |
| Stage 7 | 上述 + `nodes.py` 剩余 13 个节点 + `builder.py` 19 节点版 + `loop.py` | ~900 行 | 同上（不再新增） | **删除**（台账清零） |

> **新写入量的量级对照**：`tool_executions` 的行数 = **工具调用总次数**。粗估：单租户日均 1 万轮、平均 2 次工具调用 → **约 2 万行/天**，每行约 0.3–2 KB（只存指针与指纹，不存结果正文）→ **约 6–40 MB/天**。
>
> **本层是方案集里存储成本最低的一层** —— 工具调用数远小于 chunk 数（Session）与模型调用数（Context）。

---

## 10. 验收标准

> **本层在系统级验收中的责任**：
> 本层负责系统级验收的 **#5（审批中断可恢复）的执行侧 · #6（副作用不重复）· #7（`unprotected` 不碰副作用）的剔除侧 · #11（成本归属正确）**（完整清单见 [`README.md`](README.md) §7）。

### 10.1 功能验收

1. **推理真的发生**：`agent` 节点不再是 `return {}`；端到端测试能拿到模型输出；
2. **工具调用装配正确**：分片到达的 tool call 能正确合并；**不会出现半截参数被调用**；
3. **工具幂等跨进程**：两个 worker 并发执行同一 `idempotency_key` → **只执行一次**；
4. **工具调用落库**：`tool_executions` 有真实行，含 `request_hash` / `status` / `turn_id`；
5. **幂等冲突可见**：同一键不同参数 → 明确错误（不是静默返回旧结果）；
6. **`unprotected` 兑现**：`unprotected` 轮次**不产生任何副作用工具调用**；
7. **actor 真实**：审批记录的 `requester` 是真实用户；**取不到 actor → 拒绝执行**；
8. **审批恢复校验**：恢复后执行前校验 `request_hash`；不符 → 拒绝执行并报错；
9. **六个终止条件**：各有独立测试（步数 / 成本 / 上下文超限 / 取消 / 审批挂起 / 工具连续失败）；
10. **端到端循环测试**：**存在一条跑完整个 Reason→Observe→Evaluate 的测试**；
11. **专家路由正确**：本步路由到专家 Agent，但**会话绑定不变**；
12. **模型取自 agent 配置**：本次推理用的模型 == agent 配置里绑定的那个（`model_id` / `route_id` 的解析结果）；**代码里没有运行时「挑模型」的逻辑**；`agent_decision` 留痕完整；
13. **工具集取自 agent 配置**：暴露给模型的工具 == agent 绑定的 `allowed_tools` / `allowed_skills`（减去治理过滤掉的）；**不是运行时挑的**；
14. **工具三来源统一**：tool / mcp / skill 对模型是同一种 `BaseTool`；**admin 注册的 OpenAPI / MCP 工具有真实 schema**；
15. **成本归属**：`session_turns.cost_usd` 有真实值；
16. **模型降级**：模型解析失败 / 供应商故障 → 降级不崩；
17. **收敛可判**：X5 的旧入口有 `record_legacy_call("X5")` 打点，`/metrics` 可见。

### 10.2 架构测试

```python
# tests/architecture/test_agent_boundary.py
FORBIDDEN = ("fastapi", "starlette", "sqlalchemy", "asyncpg", "psycopg")
RUNTIME_DIRS = (
    "backend/runtimes/agent_runtime/src/qzdap_agent_runtime/agent_loop",
    "backend/runtimes/agent_runtime/src/qzdap_agent_runtime/agent_router",
    "backend/runtimes/agent_runtime/src/qzdap_agent_runtime/execution",
)

def test_agent_layers_have_no_framework_imports():
    """agent_loop / agent_router / execution 三层不得依赖框架。"""
    for path in _py_files(RUNTIME_DIRS):
        for mod in FORBIDDEN:
            assert mod not in _imports_of(path), f"{path} 引入了 {mod}"
```

另加：

| # | 规则 | 检查方式 |
|---|---|---|
| 1 | `agent_loop` 不得直接 import 记忆表 / 上下文表 | import 扫描（必须经端口） |
| 2 | `agent_router` 不得写业务表 | import 扫描 |
| 3 | `execution` 不得读 `session_*` 表（只写 `tool_executions`） | import 扫描 |
| 4 | `execution` 的工具调用**必须**写 `tool_executions` | 架构测试 + 集成测试断言行数 |
| 5 | **`modules/tool` 之外不得有第二套工具协议派发** | 关键字扫描（`_dispatch` / `ToolProtocol` 只允许一处） |
| 6 | **只有 `QZDAPChatModel` 一个 LangChain 模型实现** | import 扫描（不得直接 new 供应商客户端） |

### 10.3 「没有第二套实现」的扫描

| 旧符号 | 扫描范围 | 台账 |
|---|---|---|
| `graph/nodes.py` | `backend/runtimes` | X1 |
| `build_session_graph` | `backend/runtimes` | X1 |
| `InMemoryToolExecutor` | `backend/runtimes` | X1 |
| `compile_loop_graph` | `backend/modules/agent_runtime` | **X5**（与 X17 同批删，Agent Stage 7） |
| `_run_turn_inner` | `backend/modules/agent_runtime` | **X17**（⚠️ 初稿错标为 X5） |
| `ToolCallAccumulator`（旧位置） | `backend/modules/agent_runtime` | **不删** —— 它是**被迁入** `agent_loop/reason.py` 的资产。扫描规则应盯**旧位置的 import**（`from ...chat_model import ToolCallAccumulator`），而不是类名本身 |

---

## 11. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| **流式工具调用装配写错** | 半截参数被执行 → 副作用工具参数错误 | 迁入 `ToolCallAccumulator`（已验证）；补「分片 / 混合参数类型 / 无 id」三个测试 |
| **工具幂等跨 worker 失效** | 副作用重复执行（发消息 / 扣款 / 改数据） | `tool_executions` 唯一约束为唯一权威；集成测试**必须跨进程**验证 |
| **两套工具调用表继续并存** | 幂等与明细分裂，无法对账 | 决策 #6：`tool_executions` 管幂等、`tool_calls` 管明细、`tool_call_id` 关联；**禁止第三张表** |
| **模型供应商故障** | 整轮失败 | 失败转移链（现状已有）+ 环境默认模型兜底 |
| **上下文超限** | 模型报错 | 交 Context 层重组；连续 2 次仍超限 → 明确错误 |
| **成本失控** | 深度任务烧钱 | 轮次级 + 深度任务级双重预算；超限抛明确错误 |
| **`deepagents` 未装且未验证** | 引入一个未知的第三方依赖 | 决策 #8；**必须先在隔离分支验证 API 与版本**，再进主干 |
| **`route_strategy` 扩展是跨模块改动** | model / agent_factory 模块的迁移与本方案不同步 | 登记为 Stage 4 的**硬前置**；本方案不占 0049 之后的迁移号 |
| **专家 Agent 建模走偏** | 第三套 agent 语义 | 决策 #3：复用 `agent_versions` + role 标签（**落点是模板 metadata 的 `category` / `tags`**，不新建表也不新建列），不新建表 |
| **`chat_model.py` 删早了** | web / IM 两条旧路径当场 ImportError | 删除的前置是 **Agent Stage 5 的 A-26** 与 **Session Stage 5b** **都完成**（`runner.py` 与 `run_turn.py` 都不再 import 它）→ 删除落在 Stage 7 |
| **把「配置读取」写成「运行时决策」** | 又造出一个 Model Router / Tool Router，模型与工具的来源分裂 | 决策 #4 已定：**模型与工具只从 agent 配置取**；架构测试加一条「运行时不得按 task_kind 挑模型」 |
| **LangChain 适配层变成「第二个 LLM 客户端」** | 两套供应商逻辑漂移 | 适配器只做类型翻译，**不许碰供应商 / 路由 / 成本**；架构测试规则 6 |

### 11.1 回退

| 时点 | 回退方式 | 代价 |
|---|---|---|
| Stage 1–4 | `git revert` 对应提交 | 无 |
| Stage 5（循环已接管） | `git revert` 切换提交 → 旧 `while True` 循环接管 | 无（旧实现在场） |
| Stage 7（已清理） | 需**重新上线旧版本** | `tool_executions` 里的幂等记录留着（无害）；**Deep Agents 的依赖可回退** |

> **本层特有的不可逆点**：几乎没有 —— 本层不删任何业务数据。
>
> **⚠️ 回退的安全含义**：回退到旧执行器 = **恢复「工具幂等只靠进程内 dict」**（跨 worker 失效 → 副作用工具可能重复执行）。因此：
> - Stage 3 之后回退时，**必须先停用有副作用的工具**，或接受重复执行的风险；
> - `unprotected` 的工具剔除（Stage 2）**不应回退** —— 它是 Gateway 决策 #5 的兑现点，回退即违背该决策。
>
> **本层是唯一可以「部分回退」的层**：`QZDAPChatModel`（新）→ `LLMPort`（旧）的模型侧回退，与工具侧回退**互不影响**。这给了本层比其它层更大的回退自由度。
---

## 12. 治理与可观测性落点

### 12.1 治理落点（Governance）

| 本层步骤 | 闸门 | 拒绝 / 降级时的行为 |
|---|---|---|
| **模型解析**（不是选模型） | 模型白名单 / 租户可用模型 / 配额（`admin_model_quotas`） | 超配额 → 降级到可用模型；无可用模型 → 明确错误 |
| Agent Router 选专家 | 专家的可见范围（`visible_scope`） | 越权专家 → 落回会话绑定的 agent |
| **工具绑定 + 治理过滤** | agent 配置的绑定集 ∩ 风险 ∩ 作用域 | 筛不出 → **降级为「无工具」**，不阻断轮次 |
| 工具绑定的 `unprotected` 剔除 | Gateway 决策 #5 | **剔除**副作用工具（不是执行时拦截） |
| 工具执行前 | `policy_guard.check`（`modules/tool` 已有）+ `PolicyGuard.decide` | `approve_required` → `interrupt()` 挂起；`deny` → 明确错误，**不执行** |
| 恢复执行前 | `request_hash` 复核 + 审批有效期 + 审批人 ≠ 申请人 | 任一不符 → **拒绝执行 + 审计** |
| 成本 | 轮次预算 / 深度任务预算 | 超限 → `DEEP_AGENT_BUDGET_EXCEEDED` |
| 沙箱 | 沙箱侧的资源与网络策略 | 沙箱拒绝 → 结构化错误，不抛穿图 |

> **本层不拥有的治理**：审批的**决策语义**（谁能批）、租户与工作区权限（Gateway）、记忆可见范围（Memory）、会话配额（Router）。

### 12.2 可观测性指标（Observability）

指标名进 `qzdap_*` 命名空间，实现落在 `backend/libs/observability/src/qzdap_observability/metrics.py`。

| 指标名 | 类型 | 标签 | 说明 |
|---|---|---|---|
| `qzdap_agent_loop_steps` | Histogram | `agent_id` | 一次轮次内的循环步数分布 |
| `qzdap_agent_loop_outcomes_total` | Counter | `outcome` | 轮次终态（`exit` / `suspend` / `abort` / `budget_exceeded` / `cancelled`） |
| `qzdap_agent_loop_duration_seconds` | Histogram | `agent_id`, `outcome` | 轮次总耗时 |
| `qzdap_agent_router_selections_total` | Counter | `kind`, `outcome` | 专家选择数（`kind`：**`agent`**（只有专家选择是「决策」）；`outcome`：`selected` / `fallback` / `empty`）。⚠️ 原先的 `model` / `tool` 两类随决策 #4 取消 |
| `qzdap_agent_tool_binding_filtered_total` | Counter | `reason` | 被剔除的工具数（`reason`：`not_bound` / `scope` / `risk` / `unprotected`） |
| `qzdap_model_calls_total` | Counter | `provider`, `model`, `outcome` | 模型调用数（含 fallback 转移） |
| `qzdap_model_fallback_total` | Counter | `from_model`, `to_model` | 失败转移链的实际转移 |
| `qzdap_tool_executions_total` | Counter | `tool_name`, `outcome` | 工具调用结果（`succeeded` / `failed` / `timeout` / `circuit_open` / `idempotent_hit`） |
| `qzdap_tool_duration_seconds` | Histogram | `tool_name` | 工具耗时分布 |
| `qzdap_tool_retries_total` | Counter | `tool_name` | 重试次数 |
| `qzdap_tool_idempotent_hit_total` | Counter | `tool_name` | 幂等命中数（**跨 worker 生效的那个**） |
| `qzdap_tool_idempotency_conflict_total` | Counter | `tool_name` | **同键不同参数的冲突数**（调用方 bug 的信号，应告警） |
| `qzdap_llm_cost_usd_total` | Counter | `provider`, `model` | **已存在**，本层开始真正写入 |
| `qzdap_legacy_calls_total` | Counter | `entry` | 旧实现调用计数（标签 `entry` 为台账编号，如 `X5`） |

**Span 划分**：

| Span | 父子关系 | 属性 |
|---|---|---|
| `agent_loop.turn` | 根 | `agent_id`, `turn_id`, `outcome`, `steps` |
| `agent_loop.reason` | `agent_loop.turn` | `model`, `provider`, `input_tokens`, `output_tokens`, `tool_call_count` |
| `agent_router.agent` | `agent_loop.reason` | `expert_agent_id`, `fallback` |
| `execution.model_resolve` | `agent_loop.reason` | `model_id`, `source`（绑定来源：`model_id` / `route_id` / 显式） |
| `execution.tool_bind` | `agent_loop.reason` | `tool_count`, `filtered_count`, `reason` |
| `execution.tool` | `agent_loop.turn` | `tool_name`, `outcome`, `latency_ms`, `attempts`, `idempotent_hit` |
| `execution.llm` | `agent_loop.reason` | `provider`, `model`, `outcome`, `fallback_from` |

> **观测约束**：span 属性**不得包含**模型输出正文、工具入参 / 出参原文、审批 arguments。工具名与参数**摘要指纹**（`request_hash` 前 8 位）可记。

### 12.3 审计

| 事件 | 何时写 | 内容 |
|---|---|---|
| `agent.tool.executed` | 工具执行完成 | 工具名、结果状态、耗时、**参数指纹**（不记参数原文） |
| `agent.tool.denied` | 策略拒绝 | 工具名、拒绝原因 |
| `agent.approval.requested` | 挂起审批 | `approval_id`、`tool_call_id`、申请人 |
| `agent.expert.selected` | 路由到专家 Agent | 专家 id、是否回落 |
| `agent.model.fallback` | 模型失败转移 | 原模型、目标模型、失败原因 |
| `agent.budget.exceeded` | 超预算 | 已用步数 / 成本、预算值 |

> 审计写入走 Governance 模块，本层只投递事件。

---

## 附录 A：已定稿的决策（2026-10-29 逐条确认）

> 以下 **8 条**决策（#1–#8）已逐条确认并定稿（**#4 早前已拍板**，其余同日确认）。**改动其中任何一条，都必须同步修改正文对应章节，并在 §9 补记受影响的阶段。**

| # | 决策 | 定稿结果 | 备选 | 影响 |
|---|---|---|---|---|
| 1 | Agent Loop 的骨架 | **自建 6 节点 StateGraph**，复用 `langgraph.prebuilt` 的 `ToolNode` / `tools_condition` / `tool_validator`，**不用 `create_react_agent`** | 直接用 `create_react_agent`（省事，但审批中断、成本归属、`unprotected` 剔除都在它抽象之外，最终要大量 hook 改造） | 依赖面、审批中断的实现难度、平台语义的可控性 |
| 2 | 平台模型如何接入 LangChain | **写 `QZDAPChatModel(BaseChatModel)` 薄适配器**（只做类型翻译，不碰供应商 / 路由 / 成本） | 保持 `LLMPort` 独立、不接 LangChain（则 `ToolNode`、`create_react_agent`、Deep Agents 全部用不了） | LangChain 生态能否复用；是否出现「第二个 LLM 客户端」 |
| 3 | 专家 Agent 的建模 | **复用 `agent_versions` + role 标签**，不新建表 | 新建专家表 | 是否会出现第三套 agent 语义；路由查询成本 |
| **4** | **模型来源** | ✅ **已定稿（用户拍板）**：模型由**管理员在 agent 配置里绑定**，运行时**查表**，**不做 Model Router**；`balanced` 分流、`route_strategy` 新取值、`qzdap_model_routing_total` 一并取消 | （已否）运行时按 `task_kind` 挑大 / 小模型 | 本层的「路由」只剩**专家 Agent 选择**；模型与工具都是**配置读取** |
| 5 | 工具绑定与治理过滤的口径 | 绑定集 ∩ 风险 ∩ 作用域，**`unprotected` 直接剔除副作用工具** | 只在执行时拦截（事后） | Gateway 决策 #5 的兑现方式 |
| 6 | 工具幂等的落点 | **`tool_executions` 为唯一权威**（列已齐全，**不需要新迁移**）；`tool_calls` 保留为工具域明细，用 `tool_call_id` 关联 | 只用 `tool_calls`（需给它加幂等列 → 跨模块迁移）；或合并成一张表 | 幂等可靠性、两表对账成本 |
| 7 | 成本闸门的位置 | **两级**：轮次级硬闸门 + 深度任务级子集预算 | 只有轮次级 | 深度任务可用性、成本上限 |
| 8 | Deep Agents 的接入方式 | **先加依赖并在隔离分支验证 API 与版本**，验证通过后再在 Stage 6 接线；**在此之前只保留类型定义** | 直接接入主干 / 彻底不用 | 依赖风险、深度任务能力 |

> **与相邻方案的一致性要求**：
> - **决策 #5**（工具绑定与治理过滤的口径）必须与 **Gateway 决策 #5**（`unprotected` 强度）配套 —— Gateway 承诺「Agent Loop / Execution 禁用副作用工具」，兑现点在本方案 §5.3.1 规则 3；
> - **审批挂起的落点**（见 §3.5）必须与 **Session 决策 #6**（`session_turns.pending_approval`）取同一个值 —— 本层的决策 #7 是**成本闸门**，与审批无关；
> - **checkpoint 的落点**（见 §7.1 / §7.2）必须与 **Session 迁移 0046**（`langgraph_checkpoint_*` 表 + `AsyncPostgresSaver`）一致 —— 表由 Session 建，本层只使用；本层的决策 #2 是**模型接入方式**，与 checkpoint 无关；
> - **决策 #4 已定稿**（用户拍板）→ **不再有「扩展 `route_strategy` 取值集合」这个跨模块前置**（§5.2.1 与 §7.2 已同步）；本层对 model / agent_factory 模块**没有新增依赖**。

---

## 附录 B：现状 → 目标 文件对照速查

| 现状文件 | 目标状态 |
|---|---|
| `runtimes/.../graph/nodes.py`（1205 行，19 节点） | **删除**（拆入 `agent_loop/` + `agent_router/` + `execution/`） |
| `runtimes/.../graph/builder.py`（177 行，19 节点装配） | 改为 **6 节点版**（`agent_loop/graph.py`） |
| `runtimes/.../graph/state.py`（214 行） | 裁剪：只留 Agent Loop 内循环需要的状态 |
| `runtimes/.../graph/routing.py`（149 行） | → `agent_router/classifier.py` |
| `runtimes/.../graph/deep_agent.py`（207 行） | 保留**类型定义**；工厂视决策 #8 处置 |
| `runtimes/.../execution/executor.py`（305 行） | → `execution/tool_runtime.py`（幂等落库） |
| `runtimes/.../execution/lock.py`（182 行） | **降级**：Session 用轮次表 CAS（Router 决策 #9），本文件若保留只能作**优化**，不得作权威 |
| `runtimes/.../tools/registry.py` | 保留；接真实工具服务 |
| `runtimes/.../ports.py` | **扩**：补 5 个端口 |
| `modules/.../adapter/graph/chat_model.py`（200 行） | **迁出** → `execution/llm_client.py` + `agent_loop/reason.py`；**文件删除推迟到 Stage 7**（前置 = Agent A-26 + Session Stage 5b） |
| `modules/.../adapter/graph/runner.py` `_run_turn_inner` | **迁入并重写** → `agent_loop/runner.py` |
| `modules/.../adapter/graph/loop.py` `compile_loop_graph` | **删除**（X5）；`apply_stall_guard` 迁入 `agent_loop/evaluate.py` |
| `modules/.../adapter/llm/__init__.py` `LLMPortAdapter` | 保留，实现 runtime 的 `LLMPort`，被 `QZDAPChatModel` 包装 |
| `modules/.../adapter/persistence/catalog_model_resolver.py` | 保留，实现 `ModelResolverPort` |
| `modules/.../adapter/tools/tool_service_adapter.py` | 保留；**修空 schema 问题** |
| `modules/.../adapter/sandbox/*` | 保留；由 `execution/sandbox.py` 薄封装 |
| `modules/.../adapter/skills/skill_service_adapter.py` | 保留；工具绑定的第三类来源 |
| **`modules/tool/.../invoke_tool.py`** | **保留 + 补幂等 / 重试 / 熔断** |
| `tool_executions` 表 | **开始写入**（列已齐全，无需迁移） |
| `tool_calls` 表 | 保留；用 `tool_call_id` 与 `tool_executions` 关联 |
| （新增）`agent_loop/` | reason / observe / evaluate / runner / graph |
| （新增）`agent_router/` | agent_router / classifier（**只有这两件** —— 决策 #4 后没有 model_router / tool_router） |
| （新增）`execution/` | chat_model / **model_binding** / llm_client / **tool_binding** / tool_runtime / agent_executor / sandbox |
| （新增）`deep/` | factory / planner（决策 #8） |
| `agent_versions.allowed_tools` / `allowed_skills` / `knowledge_package_ids`（迁移 0011，**已存在**） | **工具绑定集的落点** —— 不需要新列（§5.3.1） |
| `agent_versions.route_id` / `route_strategy`（迁移 0042） | 模型解析的落点；**不再扩展取值**（决策 #4） |

---

## 附录 C：2026-10-29 审查修正记录

> 本方案 v1.0 → **v1.1**（审查修正）+ **v1.2**（按 D1 重新梳理骨架）的全部修正。**每条都对着 `backend/` 的代码与迁移核实过**。
>
> **决策定稿（2026-10-29）**：附录 A 的 **8 条**决策已全部拍板（**#4 早前已定**，其余同日定，取值为本方案的建议值）。

| # | 级别 | 问题 | 修正 | 落点 |
|---|---|---|---|---|
| **D1** | 设计 | **⑧ Agent Router 段与平台的实际配置模型冲突**：模型由管理员配置、绑定在 agent 配置上；工具（tool/mcp/skill）同样先配置、再在 agent 配置里绑定；知识/流程同理 → **本层不需要 Model Router**，也不需要「Tool Router 的选择」 | 取消 Model Router 与「工具选择」；模型改为**解析（查表）**、工具改为**绑定集读取 + 治理过滤**；本层的「路由」只剩**专家 Agent 选择**；连带取消 `balanced` 分流、`route_strategy` 新取值、`qzdap_model_routing_total` 指标 | §0.1 / §0.3 / §2.2 / §2.4 / §4.0 / §5.2.1 / §5.3.1 / §7.1 / §7.2 / §8.1 / §9 Stage 4 / §10.1 / §12.2 / 附录 A #4 / 实施方案 §3.6 |
| **D2** | 设计 | **v1.1 的骨架与 D1 不自洽**：D1 取消了 Model Router / Tool Router 之后，「三段 + 三路路由」的骨架还留在 §4/§5/§6/§12 —— 章节名仍叫「智能路由层」，§6 的契约里仍写着 `ModelSelection` / `ToolSelection`，§12.2 仍有 `tier` / `strategy` 这类**已被取消的路由维度** | **按「两条轴」重排**：新增 **§0.2 两条轴（执行轴 / 配置轴）** 作为全篇前提；**§4 收敛为「只选专家」**（新增 §4.2「专家配置即绑定来源」）；**模型解析移到 §5.2.1、工具绑定移到 §5.3.1**（与各自的执行侧合并）；§6 契约去掉 `ModelSelection` / `ToolSelection`；§8.1 的 `tool_binding.py` 移到 `execution/`、新增 `model_binding.py`；`ToolRouterPort` 更名 `ToolBindingPort`；§12.2 的 span 改为 `execution.model_resolve` / `execution.tool_bind` | §0.2 / §0.3 / §4 / §5.2 / §5.3 / §6 / §7.1 / §8.1 / §9 Stage 0 / §10.1 / §12.1 / §12.2 / 附录 A #5 / 附录 B / 实施方案 §3.6 / 基线 §2 |
| **S1** | 严重 | Stage 1 删 `chat_model.py` 的 `stream_chat` 会**当场打断还在服役的旧路径**（`runner.py:36/281` web 路径 + `use_cases/run_turn.py:49/249` IM 路径都 import 它） | Stage 1 改为「只迁入不删」；删除前置 = **Agent Stage 5 的 A-26** + **Session Stage 5b** 都完成 → 删除落在 Stage 7 | §8.4 / §9 Stage 1 / §9 Stage 7 / 附录 B / 实施方案 A-09 |
| **S2** | 严重 | **X5 有两个 owner**：台账 §5.4 说 Session Stage 3，实施方案 A-36/附录 B 说 Agent Stage 7，层方案 §8.4 同一行里两者并存 | 统一为 **Agent Stage 7（与 X17 同批）** —— `runner.py:44` import 它 → 必须活到旧 runner 退役；台账 §5.4 同步 | §8.4 / §9 Stage 7 / 台账 §5.4 / 实施方案 A-36 |
| **S3** | 严重 | `persist_result` 被算成第 6 个空壳 —— 它其实有真实逻辑（用量记账 + 成本归属 + 异步评测，`nodes.py:1060`） | 空壳数 6 → **5**；并在台账 §2.3.1 改正（行号 1041 → 1060） | §1.2 / 台账 §2.3.1 |
| **S4** | 严重 | `session_turns.cost_usd` 写成「迁移 0043 已建」—— 0035 建的才是 `session_turns.cost_usd`；**0043 加的是 `agent_turns.cost_usd`**（旧表，Session Stage 6 会 DROP） | 改正迁移号并加「别写错表」的警示 | §7.1 / §9 Stage 3 / 实施方案 A-19 |
| **S5** | 严重 | `TOOL_IDEMPOTENCY_CONFLICT` **不存在**（`ErrorCode` 枚举 20 个成员里没有，全仓零命中） | 明确标注「本阶段要**新增**错误码并同步前端契约」 | §9 Stage 3 / 实施方案 A-15 |
| **S6** | 严重 | 决策 #3「`agent_versions` + role 标签」与「本方案不需要新迁移」矛盾 —— `agent_versions` **没有 role/category 列** | 写明 role 落点是**模板 metadata 的 `category` / `tags`**（已存在）→ 不新建表也不新建列 | §4.1 规则 1 |
| **M1** | 中 | 行号错 4 处：`deep_agent_plan` 854 → **841**；`subagent` 918 → **904**；`persist_result` 1041 → **1060**；`run_async_from_sync` 804 → **794**；另 `adapter/llm/__init__.py` 66-78 → **55-59** | 全部改正 | §1.2 / §1.5 / §5.2.1 |
| **M2** | 中 | §10.3 扫描规则把 `_run_turn_inner` 归 **X5**（应为 **X17**）；`ToolCallAccumulator` 归 X5 也不对（它是**被迁入**的资产） | 改正；`ToolCallAccumulator` 改为「盯旧位置的 import，不盯类名」 | §10.3 |
| **M3** | 中 | `tool_executions.tool_call_id` 是 **String(64)**，`tool_calls.id` 是 **UUID** → 关联需要显式 `str()` 转换 | §5.3 加类型转换说明 | §5.3.2 |
| **M4** | 中 | `DEEP_AGENT_BUDGET_EXCEEDED` 只是**新 runtime 的字符串常量**，**不在 `ErrorCode` 枚举里** → 前端不认识 | §3.3 标注「需新增错误码」 | §3.3 |
| **M5** | 中 | 实施方案 §3.6：**A-19 依赖自指**；**A-28 编号重复**；退出判据**两个「6.」** | 全部改正 | 实施方案 §3.6 |
| **M6** | 中 | `admin_model_routes` 写成迁移 0041 —— 它来自 **0025**（0041 是 `admin_model_quotas`） | 附录 B 改注 | §1.12 |
| **M7** | 中 | `chat_model.py` 的 `stream_chat` 实际在 **:74**（方案写「80-200」） | 补正 | §5.2.1 |
| **L1** | 轻 | `LLMPortAdapter` 被写成「实现 runtime 的 `LLMPort`」，但 runtime 的 `ports.py` 里**还没有** `LLMPort` | 措辞改为「Stage 0 补出端口后由它实现」 | §1.12 |
| **L2** | 轻 | `agent_versions.allowed_tools` / `allowed_skills` / `knowledge_package_ids` **0011 就建好了** —— 正是「工具从 agent 配置取」的现成落点，方案却设计了运行时筛选 | 写进 §5.3.1 / §7.1 / 附录 B | §5.3.1 / §7.1 / 附录 B |

> **同步改动**：`implementation-plan.md`（§3.6 A-09 / A-10 / A-15 / A-19 / A-22 / A-23 / A-24 / A-28b / A-36 / 退出判据）、`cleanup-ledger.md`（§5.4 X5 归属、§2.3.1 的空壳数）、`README.md`（文档表状态、术语表、里程碑、依赖表）。

