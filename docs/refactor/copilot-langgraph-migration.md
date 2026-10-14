# 企智搭 · 对话(Copilot)重构方案
# 基于 LangChain + LangGraph + Deep Agents + LangSmith Local

> 版本:1.0 · 适用代码库:`QiZhiDaAgentPlatform`
> 状态:待评审 · 评审对象:agent_runtime 模块 + channel 模块 + 前端 copilot SPA
> 上游审计:[`functional-review-methodology.md`](../audit/functional-review-methodology.md) + 四份并行审计报告

---

## 目录

- [1. 背景与目标](#1-背景与目标)
- [2. 设计原则](#2-设计原则)
- [3. 目标架构总览](#3-目标架构总览)
- [4. 环境与依赖](#4-环境与依赖)
- [5. LangSmith Local 部署](#5-langsmith-local-部署)
- [6. 端到端 10 步重构](#6-端到端-10-步重构)
  - [6.1 Channel & Gateway](#61-channel--gateway)
  - [6.2 Session Runtime](#62-session-runtime)
  - [6.3 Context Runtime](#63-context-runtime)
  - [6.4 Memory Runtime](#64-memory-runtime)
  - [6.5 Agent Runtime](#65-agent-runtime)
  - [6.6 Routing Runtime](#66-routing-runtime)
  - [6.7 Governance & Security](#67-governance--security)
  - [6.8 Tool & Execution](#68-tool--execution)
  - [6.9 Result Return](#69-result-return)
  - [6.10 Observability](#610-observability)
- [7. 数据库 Schema 与 Alembic 迁移](#7-数据库-schema-与-alembic-迁移)
- [8. SSE Chunk 协议适配](#8-sse-chunk-协议适配)
- [9. 前端契约](#9-前端契约)
- [10. 迁移路线(8 阶段 × 6 周)](#10-迁移路线8-阶段--6-周)
- [11. 测试策略](#11-测试策略)
- [12. 风险与回退](#12-风险与回退)
- [13. 附录](#13-附录)

---

## 1. 背景与目标

### 1.1 现状(基于 [`functional-review-methodology.md`](../audit/functional-review-methodology.md) + 四份审计)

| 维度 | 已审事实 |
|---|---|
| **智能体编排** | 手写 `while True:` 循环,LangGraph `StateGraph` 仅作为占位符 [`runner.py:72, 308`](../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/runner.py) |
| **续传机制** | `SessionORM.graph_state` JSONB 自续传,`_request_approval` 返回 bogus `uuid4()` 当 factory 未接 [`runner.py:408-410`](../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/runner.py) |
| **工具 Schema** | LLM 看到的 `parameters: {properties:{}}` 空 schema [`runner.py:501-514`](../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/runner.py) |
| **超时/重试** | skill/tool/sandbox 三套不统一,**无重试** |
| **policy_guard** | `object \| None` 鸭子类型,dev 默认 None,governance 模块**未真正接入** |
| **Channel → Agent** | 断链 — channel 收到消息没有下游订阅者回灌 agent |
| **SSE chunk 落地** | 8 类承诺,Schema 11 类注册,真正 emit 6 类,前端可见 3 类 |
| **观测** | `cost_usd=0` 写死 [`runner.py:304`](../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/runner.py),前端无 usage 显示,无 trace 回放 |
| **approver 身份** | `decide_approval` 用 `UUID(int=1 if owner_id==0 else 0)` 魔数 [`copilot.py:245, 251`](../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/application/copilot.py) |

### 1.2 目标

- **保留 SSE chunk 协议 + 前端契约**:8+3 类 chunk 不变,前端零改动。
- **替换内部 runtime**:从"手写 ReAct + 占位 `StateGraph`"→"LangGraph 真图 + LangChain `@tool` + Deep Agents plan/sub-agent"。
- **打通 Channel → Agent 断链**:`event_bus.subscribe` → `engine.astream` → `channel_dispatcher.dispatch`。
- **真治理**:`PolicyGuardMiddleware` 上图,`approver_id` 真实用户身份,审计闭环。
- **本地可观测**:LangSmith Local docker 启,trace 进 docker volume,prometheus 指标仍走 `qzdap_observability`。
- **零 License 风险**:本地跑不开 SaaS,合规自验。

### 1.3 不在范围

- 不改 SSE chunk 协议。
- 不改前端 React 组件。
- 不改 `agent_factory` 模块(P8 模板/版本/发布)。
- 不动 `identity` / `governance` / `observability_module` / `evaluation` 模块的对外 HTTP 契约。

---

## 2. 设计原则

| 原则 | 落地 |
|---|---|
| **协议不变** | 8 类 SSE chunk 完全保留(`message` / `tool_call` / `tool_result` / `skill_invocation` / `memory_write` / `knowledge_search` / `usage` / `done`),适配层只换生成它们的引擎。 |
| **三框架分层** | LangChain 提供 Model/Tool/Message 原语;LangGraph 负责图编排 + interrupt + checkpoint;Deep Agents 提供 plan + sub-agent + filesystem。 |
| **状态显式化** | 全部状态进 `AgentState` TypedDict + `Checkpointer`,不再用 JSONB 黑盒。 |
| **观测内建** | LangSmith Local 自动 trace;每个节点带 `RunMetadata`;前端 SSE 与 LangSmith run 同源。 |
| **Provider-agnostic 观测** | `QZDAP_TRACE_TARGET=langsmith\|langfuse\|phoenix\|stdout` 切换,业务代码无感。 |
| **可灰度** | 新图 `engine` 与旧 `SessionGraphRunner` 并存,通过 `QZDAP_AGENT_ENGINE=v0\|v1` 切流量。 |
| **可回退** | 每个阶段可独立 revert;Checkpoint 表与 JSONB 并行写一份,出问题时秒切。 |

---

## 3. 目标架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  Channel(IM / Web / API / Webhook)                                           │
│      │                                                                      │
│      ▼                                                                      │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                       LangGraph AgentEngine                            │ │
│  │                                                                        │ │
│  │   START                                                                 │ │
│  │     │                                                                   │ │
│  │     ▼ load_context  ──►  inject 系统 prompt / tenant / workspace       │ │
│  │     ▼ recall         ──►  memory_hits(L1/L2/L3) + knowledge_hits(rerank)│ │
│  │     ▼ inject_context ──►  把检索结果拼成 system message               │ │
│  │     ▼ maybe_compact  ──►  超 70% 阈值调 LLM 摘要,否则 no-op           │ │
│  │     ▼                                                                   │ │
│  │   ┌──── agent(ReAct / Deep Agent) ──────────────────────────────┐     │ │
│  │   │                                                              │     │ │
│  │   │   思考 → tool_calls? ─yes─► tool_node ─► PolicyGuardMW ─► 执行 │     │ │
│  │   │                                              │                │     │ │
│  │   │                                              ▼                │     │ │
│  │   │                                          interrupt(审批)       │     │ │
│  │   │                                              │                │     │ │
│  │   │                                          Command(resume)      │     │ │
│  │   │                                              │                │     │ │
│  │   │                                              ▼                │     │ │
│  │   │                                       回 agent 继续          │     │ │
│  │   │                                                              │     │ │
│  │   └─ plan=research/code? ─yes─► subagent_* ─► 回 agent            │     │ │
│  │   │                                                              │     │ │
│  │   └─ final? ─yes──────────────────────────────────────────────┐  │     │ │
│  │                                                                ▼  ▼     │ │
│  │                                                          remember     │ │
│  │                                                                │        │ │
│  │                                                                ▼        │ │
│  │                                                              done       │ │
│  │                                                                │        │ │
│  │                                                                ▼        │ │
│  │                                                              END        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│      │                                                                      │
│      ▼                                                                      │
│  SSE Adapter(astream events → 8+3 类 TurnChunk)                            │
│      │                                                                      │
│      ├─► Web(SSE 推送)                                                       │
│      ├─► IM(飞书/企微/钉钉适配器)                                            │
│      ├─► Webhook(异步回调)                                                   │
│      └─► LangSmith Local(trace) + Prometheus(metrics)                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 模块拓扑

```
backend/
├── libs/
│   └── agent_runtime/             ← 新增,从 modules/agent_runtime 抽核心
│       └── src/qzdap_agent_runtime/
│           ├── graph/             # LangGraph 图
│           ├── tools/             # LangChain @tool 声明
│           ├── memory/            # LayeredMemory
│           ├── governance/        # PolicyGuardMiddleware
│           ├── channels/          # Gateway / Dispatcher
│           ├── observability/     # LangSmith + UsageTracker + 评测
│           ├── sse/               # 8 类 chunk 适配
│           └── engine.py          # 唯一门面
└── modules/
    ├── agent_runtime/             ← 改为薄壳
    └── channel/                   ← 订阅者改为调 engine.astream
```

### 3.2 数据流时序(单次 turn)

```
Channel(Web)
  → POST /api/sessions/{sid}/turns/stream
    → session_router.stream_turn()
      → engine.astream(input, config={"thread_id": sid})
        → graph.astream(input, stream_mode="events")
          ├─ load_context: 查 agent → 拼 system prompt → add_messages
          ├─ recall: LayeredMemory.recall → memory_hits / knowledge_hits
          ├─ inject_context: 把 hits 拼成 system message → add_messages
          ├─ maybe_compact: 超 token 调 LLM 摘要,否则 no-op
          ├─ agent: ChatModel.bind_tools(...)
          │     ├─ tool_calls?
          │     │    └─► tool_node
          │     │         └─► PolicyGuardMiddleware.before_tool_call
          │     │              ├─ auto-allow → execute_tool
          │     │              └─ approve_required → interrupt() ──[pause]
          │     │
          │     │              ← Command(resume=approve) ─[resume]
          │     │
          │     ├─ plan=research? → subagent_research
          │     ├─ plan=code? → subagent_code
          │     └─ final? → remember
          │
          ├─ remember: MemoryService.write_l1 / write_l2
          └─ done: UsageTracker.summary() → UsageChunk + DoneChunk
```

每一步产出的 chunk 类型在 [§8 SSE 适配](#8-sse-chunk-协议适配) 详细映射。

---

## 4. 环境与依赖

### 4.1 新增 Python 依赖(`backend/pyproject.toml`)

```toml
[project.dependencies]
langgraph = { version = ">=1.2,<2.0", extras = ["postgres"] }
langchain = ">=1.0,<2.0"
langchain-core = ">=1.0,<2.0"
langchain-community = ">=0.3"
langgraph-checkpoint = ">=4.2,<5.0"
langgraph-prebuilt = ">=1.1,<2.0"
deepagents = ">=0.2,<1.0"
psycopg-pool = ">=3.2"
pgvector = ">=0.3"
cohere = ">=5.0"
tenacity = ">=9.0"
tiktoken = ">=0.7"

[project.optional-dependencies]
trace = [
    "langsmith >= 0.4",
]
rerank = [
    "cohere >= 5.0",
]
```

### 4.2 锁定版本(`backend/uv.lock`)

- `langgraph==1.2.12`(已有)
- `langchain-core==1.6.6`(已有)
- 新增:`deepagents`、`langchain-community`、`langgraph-prebuilt==1.1.0`、`pgvector`、`cohere`、`tenacity`、`tiktoken`、`psycopg-pool`

### 4.3 环境变量(`backend/.env.example` 新增)

```bash
# Agent Engine
QZDAP_AGENT_ENGINE=v1                  # v0=旧 SessionGraphRunner;v1=新 LangGraph
QZDAP_LLM_MODEL=gpt-4o
QZDAP_LLM_TEMPERATURE=0.2

# LangGraph Checkpoint
QZDAP_LANGGRAPH_DSN=postgresql://qzdap:qzdap@127.0.0.1:9153/qzdap
QZDAP_LANGGRAPH_CHECKPOINT_TABLE=langgraph_checkpoints
QZDAP_LANGGRAPH_STORE_TABLE=langgraph_store

# Observability
QZDAP_TRACE_TARGET=langsmith           # langsmith | langfuse | phoenix | stdout
QZDAP_LANGSMITH_ENDPOINT=http://127.0.0.1:1985
QZDAP_LANGSMITH_API_KEY=lsv2_pt_local_dev_only
QZDAP_LANGSMITH_PROJECT=qzdap-dev
QZDAP_PROMETHEUS_MULTIPROC_DIR=/tmp/qzdap-prom

# Memory / Rerank
QZDAP_RERANK_PROVIDER=cohere           # cohere | none
QZDAP_COHERE_API_KEY=
QZDAP_L2_PG_TABLE=memory_l2_embeddings
QZDAP_L3_PG_TABLE=knowledge_chunks

# Governance
QZDAP_POLICY_AUTO_APPROVE_LOW_RISK=true
QZDAP_POLICY_TIMEOUT_MS=30000
```

---

## 5. LangSmith Local 部署

### 5.1 `infra/docker/docker-compose.langsmith.yml`

```yaml
version: "3.9"

# LangSmith 本地版 — 单机 dev/staging 足够。
# 数据落本地 volume,UI 开 :1984,OTLP/Backend :1985。
# 来源:langchain/langsmith-backend 官方镜像。
services:
  langsmith-backend:
    image: langchain/langsmith-backend:latest
    container_name: qzdap-langsmith
    ports:
      - "1984:1984"
      - "1985:1985"
    environment:
      - LANGCHAIN_TRACING_V2=true
      - LANGCHAIN_API_KEY=lsv2_pt_local_dev_only
      - LANGCHAIN_ENDPOINT=http://host.docker.internal:1985
      - DATABASE_URL=postgresql://langsmith:langsmith@langsmith-db:5432/langsmith
      - REDIS_URL=redis://langsmith-redis:6379
      - NEXTAUTH_URL=http://localhost:1984
      - NEXTAUTH_SECRET=dev-secret-change-me
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
    depends_on:
      langsmith-db:
        condition: service_healthy
      langsmith-redis:
        condition: service_healthy
    volumes:
      - langsmith-data:/data

  langsmith-db:
    image: postgres:16
    container_name: qzdap-langsmith-db
    environment:
      POSTGRES_USER: langsmith
      POSTGRES_PASSWORD: langsmith
      POSTGRES_DB: langsmith
    volumes:
      - langsmith-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U langsmith"]
      interval: 5s
      retries: 10

  langsmith-redis:
    image: redis:7-alpine
    container_name: qzdap-langsmith-redis
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      retries: 10

volumes:
  langsmith-data:
  langsmith-db-data:
```

### 5.2 启动命令

```bash
# 一次性
docker compose -f infra/docker/docker-compose.langsmith.yml up -d

# 等待就绪(约 30 秒)
docker compose -f infra/docker/docker-compose.langsmith.yml ps

# 浏览器
open http://localhost:1984        # UI(无认证)
# API Key: lsv2_pt_local_dev_only
```

### 5.3 应用侧接入

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/observability/langsmith.py
import os
from typing import Literal

TraceTarget = Literal["langsmith", "langfuse", "phoenix", "stdout"]

def configure_tracing(target: TraceTarget | None = None) -> None:
    target = target or os.getenv("QZDAP_TRACE_TARGET", "stdout")
    if target == "langsmith":
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = os.getenv("QZDAP_LANGSMITH_API_KEY", "lsv2_pt_local_dev_only")
        os.environ["LANGCHAIN_ENDPOINT"] = os.getenv("QZDAP_LANGSMITH_ENDPOINT", "http://127.0.0.1:1985")
        os.environ["LANGCHAIN_PROJECT"] = os.getenv("QZDAP_LANGSMITH_PROJECT", "qzdap-dev")
    elif target == "langfuse":
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_ENDPOINT"] = os.getenv(
            "QZDAP_LANGFUSE_ENDPOINT", "http://127.0.0.1:3000/api/langchain"
        )
        os.environ["LANGCHAIN_API_KEY"] = os.getenv("QZDAP_LANGFUSE_KEYS", "pk:sk")
    elif target == "phoenix":
        os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = os.getenv(
            "QZDAP_PHOENIX_ENDPOINT", "http://127.0.0.1:6006"
        )
    # else stdout:仅 prometheus + 日志
```

`graph.astream(...)` 在 LangChain 下会自动按 env 推送 trace,**框架代码无需感知目标**。

### 5.4 资源占用

- 镜像 ~ 1.2 GB
- 内存 ~ 1.5 GB(backend)+ 200 MB(db)+ 100 MB(redis)
- 磁盘 ~ 5 GB(初始) + 持续增长(trace 每条 ~ 2 KB,1k turn ≈ 2 MB)

---

## 6. 端到端 10 步重构

### 6.1 Channel & Gateway

#### 现状
- Channel 模块存在(飞书/企微/钉钉 adapter + webhook 加密 + 事件分发)
- `dispatch_subscriber` 在 `channel.message.received` 事件上**没有下游订阅者** → 断链

#### 目标
- 把 ChannelMessage → LangGraph `graph.astream` 的 input
- 把 `graph.astream` 产出的 chunk → `channel_dispatcher.dispatch` → 各 IM adapter 输出

#### 新增代码

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/channels/gateway.py
"""Channel → Agent 适配器(原 channel 模块的断链修复)。"""

from __future__ import annotations
from dataclasses import dataclass
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from qzdap_agent_runtime.engine import AgentEngine


@dataclass(slots=True)
class ChannelMessage:
    channel_type: str          # feishu | wechatwork | dingtalk | web | api
    channel_id: str
    tenant_id: UUID
    workspace_id: UUID
    user_id: UUID
    agent_id: UUID
    text: str
    attachments: list[dict]
    metadata: dict


def channel_to_input(msg: ChannelMessage) -> dict:
    """Channel 消息 → graph.astream 的初始 input。"""
    msgs = [HumanMessage(content=msg.text)]
    if msg.attachments:
        attach_text = "\n".join(
            f"[附件:{a.get('name','?')}] {a.get('url','')}" for a in msg.attachments
        )
        msgs.insert(0, HumanMessage(content=attach_text))
    return {
        "messages": msgs,
        "channel": {"type": msg.channel_type, "id": msg.channel_id},
        "attachments": msg.attachments,
        "tenant_id": str(msg.tenant_id),
        "workspace_id": str(msg.workspace_id),
        "user_id": str(msg.user_id),
        "agent_id": str(msg.agent_id),
    }


class ChannelGateway:
    """订阅 channel 事件 → 注入 engine。"""

    def __init__(self, *, engine: AgentEngine, dispatcher: "ChannelDispatcher"):
        self._engine = engine
        self._dispatcher = dispatcher

    async def on_message(self, msg: ChannelMessage) -> None:
        session = await self._engine.ensure_session(
            tenant_id=msg.tenant_id,
            workspace_id=msg.workspace_id,
            user_id=msg.user_id,
            agent_id=msg.agent_id,
            channel={"type": msg.channel_type, "id": msg.channel_id},
        )
        config = {"configurable": {"thread_id": session.id}}
        async for chunk in self._engine.astream(channel_to_input(msg), config=config):
            await self._dispatcher.dispatch(chunk, session)
```

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/channels/dispatcher.py
"""graph chunk → Channel adapter 输出。"""

from __future__ import annotations
from typing import Iterable, Protocol

from qzdap_schema.dtos.turn import TurnChunk


class ChannelAdapter(Protocol):
    """任何渠道(飞书/企微/钉钉/Web/Webhook)实现这套协议。"""
    async def stream_message(self, channel_id: str, content: str) -> None: ...
    async def send_approval_card(self, channel_id: str, tool_name: str,
                                 arguments: dict, reason: str) -> None: ...
    async def send_error(self, channel_id: str, message: str) -> None: ...
    async def finalize(self, channel_id: str) -> None: ...


class ChannelDispatcher:
    def __init__(self, adapters: dict[str, ChannelAdapter]):
        self._adapters = adapters

    async def dispatch(self, chunk: TurnChunk, session) -> None:
        adapter = self._adapters.get(session.channel_type)
        if not adapter:
            return
        cid = session.channel_id
        match chunk.kind:
            case "message":
                await adapter.stream_message(cid, chunk.content)
            case "approval_required":
                await adapter.send_approval_card(
                    cid, chunk.tool_name, chunk.arguments, chunk.reason,
                )
            case "error":
                await adapter.send_error(cid, chunk.message)
            case "done":
                await adapter.finalize(cid)
```

#### 接入原 channel 模块

```python
# backend/modules/channel/src/qzdap/modules/channel/adapter/dispatch/dispatch_subscriber.py
@event_bus.subscribe("channel.message.received")
async def on_channel_message(event: ChannelMessage):
    from qzdap_agent_runtime.channels.gateway import ChannelGateway
    gateway = ChannelGateway.from_container()  # 从 composition root 拿
    await gateway.on_message(event)
```

#### 验收

- ✅ 飞书消息 → `agent_runtime` copilot session → 流式回推
- ✅ Approval card 在 IM 上能 approve/deny → `Command(resume=...)`
- ✅ Web SSE 与 IM channel **共用同一个 `engine.astream`**

---

### 6.2 Session Runtime

#### 现状
- `SessionORM.graph_state` JSONB 自续传 [`models.py:30-73`](../../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/persistence/models.py)
- `SessionORM.metadata.rolling_summary` 存摘要,**实际跨 turn 丢失** [`runner.py:308`](../../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/runner.py)
- `decide_approval` 用魔数 `UUID(int=1)` 替身 approver [`copilot.py:245`](../../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/application/copilot.py)

#### 目标
- `AsyncPostgresSaver` 接管持久化,`thread_id = session_id`
- `AsyncPostgresStore` 接管 cross-thread 长期事实(L2/L3)
- 删除 `graph_state` JSONB 自续传 → `interrupt` + `Command(resume=...)`

#### 新增代码

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/graph/checkpoint.py
"""LangGraph Postgres Checkpointer 工厂。"""

from __future__ import annotations
import os

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore

DSN = os.getenv("QZDAP_LANGGRAPH_DSN", "postgresql://qzdap:qzdap@127.0.0.1:9153/qzdap")


async def make_checkpointer() -> AsyncPostgresSaver:
    cp = AsyncPostgresSaver.from_conn_string(DSN)
    await cp.setup()
    return cp


async def make_store() -> AsyncPostgresStore:
    store = AsyncPostgresStore.from_conn_string(DSN)
    await store.setup()
    return store
```

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/engine.py(门面)
"""AgentEngine — 整个 runtime 的唯一对外接口。"""

from __future__ import annotations
from typing import AsyncIterator, Optional
from uuid import UUID

from langgraph.graph import StateGraph
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore
from langgraph.types import Command

from qzdap_agent_runtime.graph.builder import build_graph
from qzdap_agent_runtime.sse.adapter import SSEAdapter
from qzdap_schema.dtos.turn import TurnChunk


class AgentEngine:
    def __init__(
        self,
        *,
        llm,
        tools,
        summary_llm,
        memory,
        policy_guard,
        audit,
        usage_tracker,
        checkpointer: AsyncPostgresSaver,
        store: AsyncPostgresStore,
    ):
        middleware = [
            PolicyGuardMiddleware(policy_guard=policy_guard, audit=audit),
            UsageTrackingMiddleware(tracker=usage_tracker),
        ]
        self._graph = build_graph(
            llm=llm, tools=tools, summary_llm=summary_llm,
            memory=memory, middleware=middleware,
        ).compile(checkpointer=checkpointer, store=store)
        self._sse = SSEAdapter()
        self._usage = usage_tracker

    async def ensure_session(self, *, tenant_id, workspace_id, user_id, agent_id, channel=None):
        from qzdap.modules.agent_runtime.application.service import SessionService
        return await SessionService.ensure(
            tenant_id=tenant_id, workspace_id=workspace_id,
            user_id=user_id, agent_id=agent_id, channel=channel,
        )

    async def astream(self, input: dict, *, config: dict) -> AsyncIterator[TurnChunk]:
        async for event in self._graph.astream(
            input, config=config, stream_mode="events",
        ):
            chunk = self._sse.to_chunk(event)
            if chunk:
                yield chunk

    async def astream_resume(self, value, *, config: dict) -> AsyncIterator[TurnChunk]:
        async for event in self._graph.astream(
            Command(resume=value), config=config, stream_mode="events",
        ):
            chunk = self._sse.to_chunk(event)
            if chunk:
                yield chunk

    async def get_state(self, config: dict):
        return await self._graph.aget_state(config)

    async def list_history(self, config: dict, *, limit: int = 20):
        """列出历史 checkpoint,供 UI 展示"重置到上一轮"。"""
        return [c async for c in self._graph.aget_state_history(config, limit=limit)]
```

#### 删除/废弃

- `SessionORM.graph_state` 字段保留读路径(向下兼容),不再写入
- `_request_approval` 整段逻辑删除 → `interrupt` 接管
- `decide_approval` 改为 `engine.astream_resume(approver=real_user)`

#### 验收

- ✅ 同一 session 跨进程重启,可 `aget_state` 拿回消息 + plan + rolling_summary
- ✅ Approval `approver_id` 是真实用户 UUID,不再魔数
- ✅ `langgraph_checkpoints` 表与原 `agent_sessions.graph_state` 并行 1 个月后下线

---

### 6.3 Context Runtime

#### 现状
- `_load_messages` 字符串拼接 [`runner.py:313-383`](../../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/runner.py)
- 5 段 prompt 顺序固定,无法分别压缩
- LLM 看到的工具 schema 空 `properties:{}` [`runner.py:501-514`](../../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/runner.py)

#### 目标
- LangGraph `load_context` 节点构造 system message
- LangChain `@tool(args_schema=Pydantic)` 让 LLM 看到真实 schema
- `maybe_compact` 节点调 LLM 摘要

#### 新增代码

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/graph/state.py
from __future__ import annotations
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """整个 agent runtime 的状态契约。"""
    # 消息流(LangGraph 原生 reducer)
    messages: Annotated[list[BaseMessage], add_messages]

    # 会话元信息
    session_id: str
    tenant_id: str
    workspace_id: str
    user_id: str
    agent_id: str
    channel: dict | None
    attachments: list[dict]

    # 检索结果
    memory_hits: list[dict]       # L1+L2 合并
    knowledge_hits: list[dict]    # L3

    # 计划 / 控制
    todos: list[str]              # Deep Agents 维护
    plan: str | None              # 当前 step 的目标

    # 压缩
    rolling_summary: str
    context_window: int

    # 治理
    pending_approval: dict | None

    # 控制
    step: int
    max_steps: int
    final: str | None

    # 观测
    usage: dict | None
```

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/graph/nodes.py
"""所有节点的实现。"""

from __future__ import annotations
from uuid import UUID

from langchain_core.messages import (
    SystemMessage, HumanMessage, AIMessage, ToolMessage, RemoveMessage,
)
from qzdap_agent_runtime.graph.state import AgentState

KEEP_RECENT = 6
COMPACT_RATIO = 0.7


async def load_context(state: AgentState) -> dict:
    """注入 agent 配置 + tenant/workspace 上下文。"""
    agent = await catalog_service.get_admin(UUID(state["agent_id"]))
    parts = [
        agent.prompts.get("soul", ""),
        agent.prompts.get("prompt", ""),
        agent.prompts.get("agents", ""),
        agent.prompts.get("tools", ""),
        agent.prompts.get("user", ""),
    ]
    sys = "\n\n".join(p for p in parts if p) + (
        f"\n\n[会话上下文]\n"
        f"tenant={state['tenant_id']} workspace={state['workspace_id']} "
        f"user={state['user_id']}"
    )
    return {"messages": [SystemMessage(content=sys)]}


async def inject_context(state: AgentState) -> dict:
    """把记忆/知识拼成 system message 注入。"""
    cite = "\n".join(
        f"- ({h['score']:.2f}) {h.get('citation','')} {h['content'][:400]}"
        for h in state.get("knowledge_hits", [])
    )
    mem = "\n".join(
        f"- ({h['score']:.2f}) {h['content'][:400]}"
        for h in state.get("memory_hits", [])
    )
    extra = f"\n\n相关知识:\n{cite or '(none)'}\n\n相关记忆:\n{mem or '(none)'}"
    return {"messages": [SystemMessage(content=extra)]}


async def maybe_compact(state: AgentState, *, summary_llm) -> dict:
    """超 token 阈值时调 LLM 摘要。"""
    msgs = state["messages"]
    if estimate_tokens(msgs) <= state.get("context_window", 32_000) * COMPACT_RATIO:
        return {}
    head, tail = msgs[:-KEEP_RECENT], msgs[-KEEP_RECENT:]
    if not head:
        return {}
    summary = await summary_llm.ainvoke([
        SystemMessage(
            "把以上对话压缩成 ≤ 200 字摘要,必须保留:关键决策、"
            "未完成事项、数字、用户偏好、下一步动作。返回 Markdown bullet。"
        ),
        *head,
    ])
    return {
        "messages": (
            [RemoveMessage(id=m.id) for m in head]
            + [SystemMessage(f"更早轮次摘要:\n{summary.content}")]
            + tail
        ),
        "rolling_summary": summary.content,
    }


def estimate_tokens(messages) -> int:
    """粗估(tokenizer 用 tiktoken cl100k_base 二次替换)。"""
    return sum(
        max(1, len(str(getattr(m, "content", ""))) // 4) for m in messages
    )
```

#### 验收

- ✅ LLM 看到每个 tool 真实 Pydantic schema,工具可用性↑
- ✅ 摘要由 LLM 生成,保留决策/数字/承诺
- ✅ `LoadContext → InjectContext → MaybeCompact → Agent` 四节点在 LangSmith trace 里清晰可见

---

### 6.4 Memory Runtime

#### 现状
- `MemoryServiceAdapter.recall` 单层 [`memory_service_adapter.py:16-24`](../../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/memory/memory_service_adapter.py)
- 无 rerank,无时间衰减,无 L3 接口

#### 目标
- `LayeredMemory`(L1 会话 buffer + L2 PGVector 长期事实 + L3 知识库)三层复合
- `CohereRerank` 提升 top_k 准确率
- 每层写入字段标准化(tenant/workspace/owner/scope/timestamp/turn_id)

#### 新增代码

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/memory/layered.py
"""三层记忆:L1 会话 / L2 长期事实 / L3 知识库。"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import CohereRerank
from langchain_community.vectorstores.pgvector import PGVector
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from qzdap.modules.memory.application.services import MemoryService


@dataclass(slots=True)
class MemoryHit:
    content: str
    score: float
    layer: str             # l1 | l2 | l3
    citation: str | None = None
    metadata: dict[str, Any] | None = None


class LayeredMemory:
    def __init__(
        self,
        *,
        memory_service: MemoryService,
        l2_vectorstore: PGVector,
        l3_retriever,
        rerank_top_n: int = 6,
    ):
        self._svc = memory_service
        self._l2_base = l2_vectorstore.as_retriever(search_kwargs={"k": 20})
        self._l2 = ContextualCompressionRetriever(
            base_compressor=CohereRerank(top_n=rerank_top_n),
            base_retriever=self._l2_base,
        )
        self._l3 = l3_retriever

    async def recall(
        self, query: str, *,
        k_l1: int = 4, k_l2: int = 4, k_l3: int = 4,
        tenant_id: UUID | None = None,
        workspace_id: UUID | None = None,
    ) -> list[MemoryHit]:
        hits: list[MemoryHit] = []

        # L1 - 会话 buffer(短期)
        l1_hits = await self._svc.recall_l1(
            query=query, top_k=k_l1,
            tenant_id=tenant_id, workspace_id=workspace_id,
        )
        hits.extend(
            MemoryHit(content=h["content"], score=h.get("score", 0.0), layer="l1")
            for h in l1_hits
        )

        # L2 - PGVector 长期事实(带 reranker)
        l2_docs = await self._l2.ainvoke(query)
        hits.extend(
            MemoryHit(
                content=d.page_content,
                score=float(d.metadata.get("relevance_score", 0.0)),
                layer="l2",
                metadata=d.metadata,
            )
            for d in l2_docs
        )

        # L3 - 知识库(只读,带引用)
        l3_docs = await self._l3.ainvoke(query)
        hits.extend(
            MemoryHit(
                content=d.page_content,
                score=float(d.metadata.get("score", 0.0)),
                layer="l3",
                citation=d.metadata.get("citation"),
                metadata=d.metadata,
            )
            for d in l3_docs
        )

        # 按 score 降序,跨层合并
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:k_l1 + k_l2 + k_l3]

    async def write_l1(
        self, *, tenant_id: UUID, workspace_id: UUID,
        user_id: UUID, content: str, turn_id: UUID | None = None,
    ) -> None:
        await self._svc.write(
            tenant_id=tenant_id, workspace_id=workspace_id, owner_id=user_id,
            content=content[:4000],
            metadata={
                "layer": "l1", "scope": "user",
                "turn_id": str(turn_id) if turn_id else None,
                "ts": now_iso(),
            },
        )

    async def write_l2(
        self, *, tenant_id: UUID, workspace_id: UUID,
        user_id: UUID, content: str, turn_id: UUID | None = None,
    ) -> None:
        """长期事实 — 自动调 embedding + 入 PGVector。"""
        await self._svc.write_l2(
            tenant_id=tenant_id, workspace_id=workspace_id, owner_id=user_id,
            content=content,
            metadata={
                "layer": "l2", "scope": "user",
                "turn_id": str(turn_id) if turn_id else None,
                "ts": now_iso(),
            },
        )


def now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
```

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/memory/store.py
"""LangGraph BaseStore 适配 — 长期事实以 key/value 形式存。"""

from __future__ import annotations
from langgraph.store.base import BaseStore

class QzdapStoreAdapter:
    """把 qzdap L2 长期事实映射到 LangGraph BaseStore 的 (namespace, key) 模型。"""

    def __init__(self, base_store: BaseStore, memory: LayeredMemory):
        self._store = base_store
        self._memory = memory

    async def put_fact(self, *, tenant_id, workspace_id, user_id, key, value):
        ns = ("facts", str(tenant_id), str(workspace_id), str(user_id))
        await self._store.aput(ns, key, value)

    async def get_facts(self, *, tenant_id, workspace_id, user_id, query=None):
        ns = ("facts", str(tenant_id), str(workspace_id), str(user_id))
        items = await self._store.asearch(ns, query=query, limit=20)
        return [{"key": k, "value": v} for k, v in items]
```

#### 验收

- ✅ 同一 query 同时召回 L1+L2+L3,跨层 score 排序
- ✅ `KnowledgeSearchChunk` 真正 emit(原 schema 注册但无人 yield)
- ✅ 召回结果可追溯到具体 `package_id` + `ordinal`

---

### 6.5 Agent Runtime

#### 现状
- 手写 `while True` 循环,只有 LLM ↔ tool 二元 [`runner.py:161-280`](../../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/runner.py)
- `todos=[]` 空置,无 plan/reflect
- `HARD_MAX_STEPS=16` 硬编码

#### 目标
- **轻量路径**:`create_react_agent`(langgraph-prebuilt)给简单单轮场景
- **深度路径**:`create_deep_agent`(deepagents)给调研/分析/多步任务
- LangGraph `add_conditional_edges` 真实多分支

#### 新增代码

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/graph/agent_factory.py
"""根据 agent 配置选 ReAct 或 Deep Agent。"""

from __future__ import annotations
from langgraph.prebuilt import create_react_agent
from deepagents import create_deep_agent

from qzdap.modules.agent_runtime.domain.catalog import CatalogAgent


def make_agent_node(*, llm, tools, agent: CatalogAgent):
    """根据 agent.deep_research 字段选编排范式。"""
    if agent.deep_research:
        return create_deep_agent(
            model=llm,
            tools=tools,
            subagents=[
                {
                    "name": "research",
                    "description": "多源检索 + 引用",
                    "system_prompt": "你是研究助理,严格使用 search_kb 并给出 [package:name:ordinal] 引用。",
                },
                {
                    "name": "code",
                    "description": "写代码 + 沙箱执行 + 测试",
                    "system_prompt": "你是代码助理,所有写操作走 sandbox_exec,失败必须反思重试。",
                },
            ],
            system_prompt=(
                "你是企业深度研究助手。先 plan,再委派 sub-agent,最后给用户中文报告。"
            ),
        )
    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=dynamic_prompt,
    )


def dynamic_prompt(state) -> str:
    """从 state 拉已注入的 system prompt(放在 messages[0])。"""
    return state["messages"][0].content if state["messages"] else "你是企业助手。"
```

#### 验收

- ✅ 普通 agent 走 `create_react_agent`,轻量
- ✅ `deep_research=true` 的 agent 走 `create_deep_agent`,自动 plan + sub-agent 委派
- ✅ LangSmith trace 可见每次委派与 todos 演进

---

### 6.6 Routing Runtime

#### 现状
- `next_route(state)` 二元 [`loop.py:14-25`](../../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/loop.py)
- 无 sub-agent,无并行

#### 目标
- LangGraph `add_conditional_edges` 真多分支
- `Command(goto=...)` 显式路由

#### 新增代码

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/graph/routing.py
"""Routing 决策 — agent 决定下一步走向。"""

from langgraph.graph import END
from langchain_core.messages import AIMessage


def route_after_agent(state) -> str:
    """agent 输出后:tool_calls / sub-agent / finalize / 继续思考。"""
    last = state["messages"][-1]
    if not isinstance(last, AIMessage):
        return END

    if getattr(last, "tool_calls", None):
        return "tool_node"

    plan = state.get("plan")
    if plan == "research":
        return "subagent_research"
    if plan == "code":
        return "subagent_code"

    if state.get("final"):
        return "remember"

    return END
```

#### 验收

- ✅ 单轮回复 → `END`
- ✅ tool 调用 → `tool_node` → 回 agent
- ✅ plan=research/code → sub-agent → 回 agent
- ✅ 真实 LangGraph `add_conditional_edges` 替代手写 `next_route`

---

### 6.7 Governance & Security

#### 现状
- `policy_guard: object | None` 鸭子类型,dev 默认 `None` [`tool/invoke_tool.py:74, 83`](../../../backend/modules/tool/src/qzdap/modules/tool/application/use_cases/invoke_tool.py)
- `_request_approval` 用 `UserId(UUID(int=1))` 替身 [`runner.py:416`](../../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/runner.py)
- `decide_approval` 用 `UUID(int=1 if owner_id==0 else 0)` [`copilot.py:245`](../../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/application/copilot.py)
- `except Exception: pass` 吞错 [`copilot.py:254`](../../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/application/copilot.py)

#### 目标
- `PolicyGuardMiddleware` 上 LangGraph 图
- `interrupt()` 替代 JSONB 自续传,`approver_id` 是真实用户
- 审计 + 风险评估 + 拒绝 三类决策完整

#### 新增代码

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/governance/middleware.py
"""工具执行前的治理闸门。"""

from __future__ import annotations
from typing import Any

from langgraph.types import interrupt
from langchain_core.messages import ToolMessage

from qzdap.modules.governance.application.policy_service import PolicyService
from qzdap.modules.governance.application.approval_service import ApprovalService
from qzdap.modules.governance.application.audit import AuditRecorder


class PolicyGuardMiddleware:
    def __init__(
        self,
        *,
        policy_service: PolicyService,
        approval_service: ApprovalService,
        audit: AuditRecorder,
        registry: "ToolRegistry",
    ):
        self._policy = policy_service
        self._approval = approval_service
        self._audit = audit
        self._registry = registry

    async def before_tool_call(self, state, runtime, tool_call: dict) -> Any:
        meta = self._registry.meta(tool_call["name"])

        # 1. 风险评估
        decision = await self._policy.evaluate(
            actor=runtime.context.actor,
            action=f"agent.tool.{tool_call['name']}",
            resource={"tool_id": meta.id, "arguments": tool_call["args"]},
        )
        await self._audit.record(
            actor=runtime.context.actor,
            tool=tool_call["name"],
            args=tool_call["args"],
            decision=decision.kind,
        )

        # 2. 决策分发
        if decision.kind == "deny":
            raise ToolDeniedError(decision.reason)

        if decision.kind == "approve_required":
            approval = await self._approval.create(
                actor=runtime.context.actor,
                action=f"agent.tool.{tool_call['name']}",
                resource={"arguments": tool_call["args"]},
                policy_id=decision.policy_id,
                reason=decision.reason,
            )
            user = interrupt({
                "type": "approval_required",
                "approval_id": str(approval.id),
                "tool_name": tool_call["name"],
                "arguments": tool_call["args"],
                "reason": decision.reason,
                "policy_id": decision.policy_id,
            })
            if user.get("action") != "approve":
                return ToolMessage(content="SKILL_DENIED", tool_call_id=tool_call["id"])

        # auto-allow:继续执行
        return None

    async def after_tool_call(self, state, runtime, tool_call, result) -> None:
        await self._audit.record_result(
            actor=runtime.context.actor,
            tool=tool_call["name"],
            tool_call_id=tool_call["id"],
            result=result,
        )
```

#### 审批 API 重写

```python
# backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/http/session_router.py
@router.post("/sessions/{session_id}/approvals/{approval_id}/approve")
async def approve(
    session_id: UUID, approval_id: UUID,
    actor: AuthenticatedPrincipal = Depends(require_authenticated),
):
    config = {"configurable": {"thread_id": str(session_id)}}
    async for chunk in engine.astream_resume(
        {"action": "approve", "approval_id": str(approval_id), "approver": str(actor.principal.id)},
        config=config,
    ):
        yield sse_event(chunk)


@router.post("/sessions/{session_id}/approvals/{approval_id}/deny")
async def deny(
    session_id: UUID, approval_id: UUID,
    actor: AuthenticatedPrincipal = Depends(require_authenticated),
):
    config = {"configurable": {"thread_id": str(session_id)}}
    async for chunk in engine.astream_resume(
        {"action": "deny", "approval_id": str(approval_id), "approver": str(actor.principal.id)},
        config=config,
    ):
        yield sse_event(chunk)
```

#### 验收

- ✅ approver_id 真实用户 UUID,审计链路完整
- ✅ ApprovalRequired chunk 在 SSE 里带 `arguments`,前端能渲染审批卡片
- ✅ `policy_guard` 真接入 governance,不再 None

---

### 6.8 Tool & Execution

#### 现状
- 三个适配器(SkillServiceAdapter / SandboxRuntimeAdapter / ToolServiceAdapter)无重试
- Skill `timeout_ms` 来自注册 [`skill/services.py:269`](../../../backend/modules/skill/src/qzdap/modules/skill/application/services.py)
- Tool `timeout_seconds=30.0` 默认 [`tool/invoke_tool.py:73`](../../../backend/modules/tool/src/qzdap/modules/tool/application/use_cases/invoke_tool.py)
- Schema 空

#### 目标
- LangChain `@tool(args_schema=Pydantic)` 让 LLM 看到真实 schema
- `ToolRegistry` 统一 risk/timeout/retry/backoff
- tenacity 包装重试 + 退避

#### 新增代码

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/tools/registry.py
"""统一工具注册表 — 元数据 + 重试 + 超时 + 风险标签。"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
from uuid import UUID

from langchain_core.tools import tool as langchain_tool, BaseTool
from langgraph.prebuilt import ToolNode
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, AsyncRetrying,
)
import httpx


@dataclass(slots=True)
class ToolMeta:
    id: str
    name: str
    description: str
    risk: str = "low"                # low | medium | high
    need_confirm: bool = False
    timeout_ms: int = 30_000
    max_retries: int = 0
    backoff_ms: int = 0
    policy_id: str | None = None
    args_schema: type | None = None  # Pydantic BaseModel


@dataclass(slots=True)
class _RegisteredTool:
    meta: ToolMeta
    fn: Callable[..., Awaitable[Any]]


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, _RegisteredTool] = {}

    def register(self, meta: ToolMeta, fn):
        self._tools[meta.name] = _RegisteredTool(meta=meta, fn=fn)

    def meta(self, name: str) -> ToolMeta:
        return self._tools[name].meta

    def all(self) -> list[_RegisteredTool]:
        return list(self._tools.values())

    def to_langchain_tools(self) -> list[BaseTool]:
        """导出 LangChain Tool 列表(带 schema + 描述)。"""
        out = []
        for r in self._tools.values():
            t = langchain_tool(
                r.fn,
                name=r.meta.name,
                description=r.meta.description,
                args_schema=r.meta.args_schema,
            )
            out.append(t)
        return out

    def to_tool_node(self) -> ToolNode:
        return ToolNode(self.to_langchain_tools(), handle_tool_errors=True)

    def with_retry(self, fn):
        """统一重试装饰:超时/连接错误 → 指数退避。"""
        async def wrapper(*args, **kwargs):
            meta = next(
                (r.meta for r in self._tools.values() if r.fn is fn), ToolMeta(id="", name="")
            )
            if meta.max_retries <= 0:
                return await fn(*args, **kwargs)
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(meta.max_retries),
                wait=wait_exponential(milliseconds=meta.backoff_ms or 500),
                retry=retry_if_exception_type((httpx.TimeoutException, ConnectionError, TimeoutError)),
                reraise=True,
            ):
                with attempt:
                    return await fn(*args, **kwargs)
        return wrapper
```

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/tools/kb.py
"""search_kb — L3 知识检索,Pydantic schema,带 citation。"""

from __future__ import annotations
from typing import Annotated
from uuid import UUID

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from qzdap.modules.knowledge.application.services import KnowledgeService


class SearchKbArgs(BaseModel):
    query: str = Field(..., description="搜索关键词;模型生成回答时引用回 [package:<name>:<ordinal>]")
    top_k: int = Field(5, ge=1, le=20, description="返回条数")
    package_ids: list[str] = Field(default_factory=list, description="限定知识包 id")


def make_search_kb(svc: KnowledgeService, tenant_id: UUID, workspace_id: UUID):
    @tool("search_kb", args_schema=SearchKbArgs)
    async def search_kb(*, query: str, top_k: int = 5, package_ids: list[str] | None = None) -> dict:
        """在已开通的知识库中检索资料;返回带引用的内容。"""
        hits = await svc.search_query(
            tenant_id=tenant_id, workspace_id=workspace_id,
            query=query, top_k=top_k,
            package_ids=tuple(package_ids or []),
        )
        return {
            "results": [
                {
                    "content": h.content,
                    "citation": f"[package:{h.package_name}:{h.ordinal}]",
                    "score": h.score,
                }
                for h in hits
            ],
            "artifact": {"package_ids": package_ids, "query": query},
        }
    return search_kb


class RunSkillArgs(BaseModel):
    skill_name: str = Field(..., description="Skill 名称")
    arguments: dict = Field(default_factory=dict, description="Skill 入参")


def make_run_skill(svc, tenant_id, workspace_id, user_id):
    @tool("run_skill", args_schema=RunSkillArgs)
    async def run_skill(*, skill_name: str, arguments: dict) -> dict:
        """在 sandbox 中执行已发布的 Skill。"""
        from uuid import uuid4
        try:
            result = await svc.invoke_in_sandbox(
                workspace_id=workspace_id, name=skill_name,
                arguments=arguments, call_id=uuid4(), confirmed=False,
            )
            return {**result, "ok": True}
        except Exception as e:
            return {"ok": False, "error_code": type(e).__name__, "error_message": str(e)}
    return run_skill


class SandboxExecArgs(BaseModel):
    language: str = Field("python", description="python | shell")
    code: str = Field(..., description="要执行的代码")
    timeout_ms: int = Field(30_000, ge=1_000, le=300_000, description="超时(毫秒)")


def make_sandbox_exec(client, tenant_id, workspace_id):
    @tool("sandbox_exec", args_schema=SandboxExecArgs)
    async def sandbox_exec(*, language: str, code: str, timeout_ms: int = 30_000) -> dict:
        """在隔离 sandbox 中执行 Python/Shell 代码。属于高风险操作,需审批。"""
        from uuid import uuid4
        if language not in {"python", "shell"}:
            return {"ok": False, "error_code": "SANDBOX_BAD_LANGUAGE"}
        files = {"main.py" if language == "python" else "run.sh": code}
        command = (
            ["python", "/work/main.py"] if language == "python"
            else ["sh", "/work/run.sh"]
        )
        result = await client.run_job(
            kind="exec", tenant_id=tenant_id, workspace_id=workspace_id,
            call_id=uuid4(), image="qzdap/sandbox-python:latest",
            command=command, files=files, timeout_ms=timeout_ms,
            network="none", memory_mb=256,
        )
        ok = result.get("status") == "succeeded"
        return {
            "ok": ok,
            "stdout": result.get("stdout") or "",
            "stderr": result.get("stderr") or "",
            "exit_code": result.get("exit_code"),
        }
    return sandbox_exec
```

#### 注册示例

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/composition.py
registry = ToolRegistry()

registry.register(
    ToolMeta(
        id="search_kb", name="search_kb",
        description="在已开通的知识库中检索资料,返回带 [package:name:ordinal] 引用。",
        risk="low", timeout_ms=5_000, max_retries=2, backoff_ms=500,
        args_schema=SearchKbArgs,
    ),
    make_search_kb(knowledge_svc, tenant_id, workspace_id),
)

registry.register(
    ToolMeta(
        id="run_skill", name="run_skill",
        description="在 sandbox 中执行已发布的 Skill。",
        risk="medium", need_confirm=False,
        timeout_ms=30_000, max_retries=1,
        args_schema=RunSkillArgs,
    ),
    make_run_skill(skill_svc, tenant_id, workspace_id, user_id),
)

registry.register(
    ToolMeta(
        id="sandbox_exec", name="sandbox_exec",
        description="在隔离 sandbox 中执行 Python/Shell 代码(高风险,需审批)。",
        risk="high", need_confirm=True,
        timeout_ms=60_000, max_retries=0,
        args_schema=SandboxExecArgs,
    ),
    make_sandbox_exec(sandbox_client, tenant_id, workspace_id),
)
```

#### 验收

- ✅ LLM 看到每个工具的 Pydantic schema,工具可用性↑
- ✅ 超时/重试统一,LangSmith trace 可见每次重试
- ✅ `sandbox_exec` / 高 risk 自动走 `interrupt`

---

### 6.9 Result Return

#### 现状
- Web SSE 通,IM 断链
- `DoneChunk.final_message` 直接给前端
- `MessageChunk` 累加 + `ToolCallChunk` 推 name
- `tool_result` / `skill_invocation` / `memory_write` / `knowledge_search` / `usage` **未渲染**

#### 目标
- LangGraph `astream(stream_mode="events")` → SSEAdapter → 8+3 类 TurnChunk
- 多渠道派发(同一次 run 可同时推 Web/IM/Webhook)
- Web 前端契约不变

#### 新增代码

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/sse/adapter.py
"""LangGraph events → SSE chunk 适配层。"""

from __future__ import annotations
from datetime import datetime

from qzdap_schema.dtos.turn import (
    MessageChunk, ToolCallChunk, ToolResultChunk,
    SkillInvocationChunk, MemoryWriteChunk, KnowledgeSearchChunk,
    ApprovalRequiredChunk, ContextCompactedChunk, UsageChunk,
    DoneChunk, ErrorChunk, TurnChunk,
)


def _serialize(obj) -> str:
    if isinstance(obj, str):
        return obj
    try:
        import json
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


class SSEAdapter:
    """LangGraph astream 事件 → 协议稳定的 SSE chunk。"""

    def to_chunk(self, event: dict) -> TurnChunk | None:
        name = event.get("event")
        data = event.get("data") or {}
        ts = _now_iso()

        # ── message ──────────────────────────────────────────────
        if name == "on_chat_model_stream":
            chunk = data.get("chunk")
            content = getattr(chunk, "content", "") or ""
            if not content:
                return None
            return MessageChunk(content=content, ts=ts)

        # ── tool_call ────────────────────────────────────────────
        if name == "on_tool_start":
            inp = data.get("input") or {}
            return ToolCallChunk(
                tool_name=inp.get("name") or data.get("name", "unknown"),
                arguments=inp.get("arguments", {}),
                tool_call_id=str(data.get("id", "")),
                ts=ts,
            )

        # ── tool_result ──────────────────────────────────────────
        if name == "on_tool_end":
            output = data.get("output")
            is_error = bool(
                isinstance(output, dict) and output.get("ok") is False
            )
            latency_ms = int((data.get("end_time") - data.get("start_time")).total_seconds() * 1000)
            return ToolResultChunk(
                output=_serialize(output),
                is_error=is_error,
                latency_ms=latency_ms,
                tool_call_id=str(data.get("id", "")),
                ts=ts,
            )

        # ── skill_invocation ─────────────────────────────────────
        if name == "on_custom_event" and data.get("name") == "skill_invocation":
            return SkillInvocationChunk(
                skill_name=data["data"]["skill_name"],
                arguments=data["data"].get("arguments", {}),
                ts=ts,
            )

        # ── memory_write ─────────────────────────────────────────
        if name == "on_custom_event" and data.get("name") == "memory_write":
            return MemoryWriteChunk(
                layer=data["data"]["layer"],
                preview=data["data"]["preview"],
                ts=ts,
            )

        # ── knowledge_search ─────────────────────────────────────
        if name == "on_custom_event" and data.get("name") == "knowledge_search":
            return KnowledgeSearchChunk(
                hits=data["data"]["hits"],
                ts=ts,
            )

        # ── context_compacted ────────────────────────────────────
        if name == "on_chain_start" and "compact" in str(data.get("name", "")):
            return ContextCompactedChunk(
                tokens_before=data.get("tokens_before", 0),
                tokens_after=data.get("tokens_after", 0),
                ts=ts,
            )

        # ── approval_required(interrupt)─────────────────────────
        if name == "interrupt":
            payload = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else {})
            if payload.get("type") == "approval_required":
                return ApprovalRequiredChunk(
                    approval_id=payload.get("approval_id"),
                    tool_name=payload.get("tool_name"),
                    arguments=payload.get("arguments", {}),
                    reason=payload.get("reason", ""),
                    ts=ts,
                )

        # ── done ─────────────────────────────────────────────────
        if name == "on_chain_end" and data.get("name") in {"done", "__end__"}:
            out = data.get("output") or {}
            return DoneChunk(
                final_message=out.get("final", "") if isinstance(out, dict) else str(out),
                ts=ts,
            )

        # ── error ────────────────────────────────────────────────
        if name == "on_chain_error":
            err = data.get("error")
            return ErrorChunk(
                code=type(err).__name__ if err else "Unknown",
                message=str(err) if err else "unknown error",
                ts=ts,
            )

        return None
```

#### 多渠道派发

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/channels/dispatcher.py
"""graph chunk → 多 channel adapter 输出。"""

from typing import Protocol


class ChannelAdapter(Protocol):
    async def stream_message(self, channel_id: str, content: str) -> None: ...
    async def send_approval_card(self, channel_id: str, tool_name: str,
                                 arguments: dict, reason: str) -> None: ...
    async def send_error(self, channel_id: str, message: str) -> None: ...
    async def finalize(self, channel_id: str) -> None: ...


class ChannelDispatcher:
    def __init__(self, adapters: dict[str, ChannelAdapter]):
        self._adapters = adapters

    async def dispatch(self, chunk: TurnChunk, session) -> None:
        adapter = self._adapters.get(session.channel_type)
        if not adapter:
            return
        cid = session.channel_id
        kind = chunk.kind
        if kind == "message":
            await adapter.stream_message(cid, chunk.content)
        elif kind == "approval_required":
            await adapter.send_approval_card(
                cid, chunk.tool_name, chunk.arguments, chunk.reason,
            )
        elif kind == "error":
            await adapter.send_error(cid, chunk.message)
        elif kind == "done":
            await adapter.finalize(cid)
```

#### 验收

- ✅ 同一 `engine.astream` 既可 Web SSE 推,也可 IM 适配器推
- ✅ 8+3 类 chunk 协议稳定,前端零改动
- ✅ `KnowledgeSearchChunk` / `SkillInvocationChunk` 真正 emit

---

### 6.10 Observability

#### 现状
- `cost_usd=0` 写死 [`runner.py:304`](../../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/runner.py)
- 前端不显示 usage
- 无 trace 回放
- evaluation_pass_rate=100.0 写死 [`catalog.py:142-159`](../../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/application/catalog.py)

#### 目标
- LangSmith Local 自动 trace
- `UsageTracker` 真实 cost/tokens,`UsageChunk` 真值
- 在线评测 hook,`/v1/eval/runs` 自动入队
- Prometheus 兼容导出

#### 新增代码

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/observability/langsmith.py
"""LangSmith 配置 — 由 QZDAP_TRACE_TARGET 控制目标。"""

import os
from typing import Literal

TraceTarget = Literal["langsmith", "langfuse", "phoenix", "stdout"]


def configure_tracing(target: TraceTarget | None = None) -> None:
    target = target or os.getenv("QZDAP_TRACE_TARGET", "stdout")
    if target == "langsmith":
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = os.getenv(
            "QZDAP_LANGSMITH_API_KEY", "lsv2_pt_local_dev_only"
        )
        os.environ["LANGCHAIN_ENDPOINT"] = os.getenv(
            "QZDAP_LANGSMITH_ENDPOINT", "http://127.0.0.1:1985"
        )
        os.environ["LANGCHAIN_PROJECT"] = os.getenv(
            "QZDAP_LANGSMITH_PROJECT", "qzdap-dev"
        )
    elif target == "langfuse":
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_ENDPOINT"] = os.getenv(
            "QZDAP_LANGFUSE_ENDPOINT", "http://127.0.0.1:3000/api/langchain"
        )
        os.environ["LANGCHAIN_API_KEY"] = os.getenv("QZDAP_LANGFUSE_KEYS", "pk:sk")
    elif target == "phoenix":
        os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = os.getenv(
            "QZDAP_PHOENIX_ENDPOINT", "http://127.0.0.1:6006"
        )
    # stdout:仅 prometheus + 日志
```

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/observability/usage.py
"""真实 token / cost 跟踪。"""

from __future__ import annotations
from dataclasses import dataclass

from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_community.callbacks.openai_info import get_openai_token_cost


@dataclass(slots=True)
class UsageSummary:
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float
    model: str


class UsageTracker:
    def __init__(self, model: str):
        self.cb = UsageMetadataCallbackHandler()
        self.model = model

    def callbacks(self) -> list:
        return [self.cb]

    def summary(self) -> UsageSummary:
        usage = self.cb.usage or {}
        in_t = sum(u.get("input_tokens", 0) for u in usage.values())
        out_t = sum(u.get("output_tokens", 0) for u in usage.values())
        cache_r = sum(u.get("cache_read_tokens", 0) for u in usage.values())
        cache_w = sum(u.get("cache_write_tokens", 0) for u in usage.values())
        cost = sum(
            get_openai_token_cost(u, model=self.model) for u in usage.values()
        )
        return UsageSummary(
            input_tokens=in_t, output_tokens=out_t,
            cache_read_tokens=cache_r, cache_write_tokens=cache_w,
            cost_usd=cost, model=self.model,
        )

    def to_chunk(self) -> dict:
        s = self.summary()
        return {
            "input_tokens": s.input_tokens,
            "output_tokens": s.output_tokens,
            "cache_read_tokens": s.cache_read_tokens,
            "cache_write_tokens": s.cache_write_tokens,
            "cost_usd": s.cost_usd,
        }
```

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/observability/prometheus.py
"""与 qzdap_observability 兼容的 Prometheus 导出。"""

from prometheus_client import Counter, Histogram, Gauge

TURNS_TOTAL = Counter("qzdap_turns_total", "Total turns", ["agent", "model", "result"])
TOOL_CALLS = Counter("qzdap_tool_calls_total", "Tool calls", ["tool", "risk", "result"])
APPROVALS = Counter("qzdap_approvals_total", "Approval decisions", ["decision"])
LATENCY = Histogram("qzdap_turn_latency_seconds", "Turn latency", ["agent"])
COST = Counter("qzdap_turn_cost_usd_total", "Cost per turn", ["model"])


def record_turn(agent: str, model: str, result: str, latency_s: float, cost_usd: float):
    TURNS_TOTAL.labels(agent=agent, model=model, result=result).inc()
    LATENCY.labels(agent=agent).observe(latency_s)
    COST.labels(model=model).inc(cost_usd)


def record_tool(tool: str, risk: str, result: str):
    TOOL_CALLS.labels(tool=tool, risk=risk, result=result).inc()


def record_approval(decision: str):
    APPROVALS.labels(decision=decision).inc()
```

```python
# backend/libs/agent_runtime/src/qzdap_agent_runtime/observability/evaluator.py
"""在线评测 hook — 异步入队,不阻塞主路径。"""

from __future__ import annotations
from uuid import UUID

from qzdap.modules.evaluation.application.services import EvalJobService


class OnlineEvaluator:
    def __init__(self, eval_service: EvalJobService):
        self._svc = eval_service

    async def on_done(
        self, *, session_id: UUID, agent_id: UUID,
        user_input: str, final_message: str, tool_calls: list[dict],
        latency_ms: int, cost_usd: float,
    ):
        await self._svc.enqueue(
            EvalJob(
                session_id=session_id,
                agent_id=agent_id,
                candidate_response=final_message,
                tool_call_chain=tool_calls,
                eval_suite="default_quality",
                metadata={
                    "latency_ms": latency_ms,
                    "cost_usd": cost_usd,
                    "user_input": user_input[:200],
                },
            )
        )
```

#### 与 Prometheus 集成

`main.py:233-238` 现有的 `/metrics` 路由继续走 `qzdap_observability.render_prometheus`,新增的 `qzdap_turns_total` / `qzdap_tool_calls_total` 等 counter 一起导出。无需新路由。

#### 验收

- ✅ `UsageChunk.cost_usd` 真实,前端能渲染成本徽章
- ✅ LangSmith Local UI 可看每次 turn 的完整 trace:agent / tool / sub-agent / interrupt
- ✅ Prometheus 上 `qzdap_turns_total` / `qzdap_tool_calls_total` 可监控

---

## 7. 数据库 Schema 与 Alembic 迁移

### 7.1 新增表(由 `AsyncPostgresSaver.setup()` / `AsyncPostgresStore.setup()` 自动建)

| 表名 | 用途 |
|---|---|
| `langgraph_checkpoints` | 线程级 checkpoint 主表 |
| `langgraph_checkpoint_blobs` | 大字段存储 |
| `langgraph_checkpoint_writes` | 中间写 |
| `langgraph_store` | 长期事实(跨 thread) |

`LangGraph 1.x` 的 `setup()` 自动建这些表,**不需要手写 alembic**。

### 7.2 新增 alembic 迁移:`xxxx_add_pgvector_memory_l2.py`

```python
"""add pgvector column for memory_l2 long-term facts"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "xxxx_add_pgvector_memory_l2"
down_revision = "<上一版本>"


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "memory_l2_embeddings",
        sa.Column("id", sa.dialects.postgresql.UUID, primary_key=True),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID, nullable=False, index=True),
        sa.Column("workspace_id", sa.dialects.postgresql.UUID, nullable=False, index=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID, nullable=False, index=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("metadata", sa.dialects.postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("embedding", Vector(1536), nullable=False),  # OpenAI text-embedding-3-small
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute(
        "CREATE INDEX memory_l2_embedding_idx ON memory_l2_embeddings "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade():
    op.drop_table("memory_l2_embeddings")
```

### 7.3 现有 `agent_sessions.graph_state` 字段处理

- **保留字段**(只读),1 个月后下线
- 迁移脚本:从 `graph_state["pending_approval"]` 把历史 approval 状态重放到 LangGraph `langgraph_store`
- 在 `SessionService.ensure()` 内:如果 `thread_id` 在 LangGraph 无 state 且 `graph_state` 非空 → 一次性迁移 + 写日志

---

## 8. SSE Chunk 协议适配

### 8.1 协议对照表(LangGraph 事件 → SSE chunk)

| LangGraph event | 触发位置 | SSE chunk | 备注 |
|---|---|---|---|
| `on_chat_model_stream` | agent 流式输出 | `MessageChunk` | delta 字符串 |
| `on_tool_start` | tool_node 启动 | `ToolCallChunk` | name + arguments |
| `on_tool_end` | tool_node 完成 | `ToolResultChunk` | output + latency_ms + is_error |
| `on_custom_event: skill_invocation` | skill 节点 | `SkillInvocationChunk` | skill_name + arguments |
| `on_custom_event: memory_write` | remember 节点 | `MemoryWriteChunk` | layer + preview |
| `on_custom_event: knowledge_search` | recall 节点 | `KnowledgeSearchChunk` | hits[] |
| `on_chain_start: maybe_compact` | 摘要触发 | `ContextCompactedChunk` | tokens_before/after |
| `interrupt` | 治理闸门 | `ApprovalRequiredChunk` | approval_id + tool_name + arguments + reason |
| `on_chain_end: done` | done 节点 | `DoneChunk` | final_message |
| `on_chain_error` | 任何节点抛错 | `ErrorChunk` | code + message |

### 8.2 协议稳定性保证

- 现有 `qzdap_schema.dtos.turn.TurnChunk` 子类保持不变。
- 适配层(`SSEAdapter`)是单一变更点。
- 前端 `copilotApi.ts:streamEvents` 已按 `event:` / `data:` 解析,无需改动。

### 8.3 11 类 chunk → 8 类映射

| Schema 注册 | 是否真正 emit |
|---|---|
| `MessageChunk` | ✅ |
| `ToolCallChunk` | ✅ |
| `ToolResultChunk` | ✅ |
| `SkillInvocationChunk` | ✅(首次真正 emit) |
| `MemoryWriteChunk` | ✅ |
| `KnowledgeSearchChunk` | ✅(首次真正 emit) |
| `ApprovalRequiredChunk` | ✅ |
| `ContextCompactedChunk` | ✅ |
| `UsageChunk` | ✅ |
| `DoneChunk` | ✅ |
| `ErrorChunk` | ✅ |

---

## 9. 前端契约

### 9.1 不动的部分

- `frontend/web/src/features/user/copilot/CopilotPage.tsx` 单文件 ~196 行 SSE handler
- `frontend/packages/api/src/index.ts:289-351` `streamEvents` 解析器
- `frontend/web/src/app/App.tsx:117` 路由 `/copilot/*`

### 9.2 必须补的部分(基于现有审计的已知缺口)

| 位置 | 现状 | 需要补 |
|---|---|---|
| `CopilotPage.tsx:148-154` | `tool_result` 不渲染 | 加 `case 'tool_result':` 渲染结果块(折叠/展开) |
| `CopilotPage.tsx:147` | `tool_call` 只存 name | 加 `case 'tool_call':` 渲染参数预览 |
| `CopilotPage.tsx:155` | `memory_write` 只推文本 | 加 `case 'memory_write':` 渲染 layer + preview |
| `CopilotPage.tsx:155` | `context_compacted` 只推文本 | 加 `case 'context_compacted':` 渲染 token delta |
| 缺失 | 无 `usage` 显示 | 加 `case 'usage':` 顶部右上角徽章(input/output tokens + cost) |
| `CopilotPage.tsx:190` | Plus 新建对话无 handler | 调 `POST /api/sessions` 后跳新 session |
| `CopilotPage.tsx:190` | 搜索框无 `value`/`onChange` | 接 `useState` + 过滤已加载 session |
| `CopilotPage.tsx:69-114` | 右侧 Workspace 面板装饰 | 移除,或实现真 sandbox_exec 的输出(下一阶段) |

### 9.3 双链路数据模型差异提示

后端 `agent_factory`(`/v1/agents/*`)与 `agent_runtime`(`/api/admin/agents/*`)数据模型不共享,**前端 AgentEditor 写入的是后者,模板/发布走的是前者**。前端无需改动,但需在 UI 上提示"模板/版本管理请到 `agent_factory` 模块"(下一轮)。

---

## 10. 迁移路线(8 阶段 × 6 周)

### Stage 1 · 基础设施(0.5 周)

**目标**:LangSmith Local 启起来,新依赖装上,alembic 迁移跑通。

| 任务 | PR scope |
|---|---|
| `docker compose up langsmith` 跑通 | `infra/docker/docker-compose.langsmith.yml` |
| `uv add` 新依赖 | `backend/pyproject.toml` + `uv.lock` |
| Alembic 迁移:`memory_l2_embeddings` 表 + `vector` extension | `backend/migrations/versions/xxxx_add_pgvector_memory_l2.py` |
| `.env.example` 加新环境变量 | `backend/.env.example` |

**验证**:`docker compose ps` → `http://localhost:1984` → 创建项目 `qzdap-dev`。

---

### Stage 2 · Tool 重构(1 周)

**目标**:所有工具改成 `@tool(args_schema=Pydantic)`,`ToolRegistry` 统一元数据。

| 任务 | PR scope |
|---|---|
| `ToolRegistry` + `ToolMeta` 数据类 | `libs/agent_runtime/src/qzdap_agent_runtime/tools/registry.py` |
| `search_kb` / `run_skill` / `sandbox_exec` 三个 `@tool` | `libs/agent_runtime/src/qzdap_agent_runtime/tools/{kb,skill,sandbox}.py` |
| `InvokeToolUseCase` 内 `policy_guard` 接 governance 真 service | `modules/tool/src/.../invoke_tool.py` |

**验证**:旧 ReAct 循环里把工具换成新注册表,SSE chunk 协议不变。

---

### Stage 3 · Memory 重构(1 周)

**目标**:LayeredMemory 上线,Cohere reranker 接通。

| 任务 | PR scope |
|---|---|
| `LayeredMemory` 三层复合 | `libs/agent_runtime/src/qzdap_agent_runtime/memory/layered.py` |
| `CohereRerank` 包装 | `memory/reranker.py` |
| PGVector L2 写入路径 | `memory/store.py` |
| `MemoryService.write_l2` 实现(原模块只有 `write`) | `modules/memory/.../services.py` |

**验证**:同一 query 召回三层,rank 排序合理;L2 有内容,L3 有 citation。

---

### Stage 4 · Graph 骨架(1 周)

**目标**:LangGraph 图搭好,engine.astream 跑通,旧 `SessionGraphRunner` 并存。

| 任务 | PR scope |
|---|---|
| `AgentState` TypedDict | `libs/agent_runtime/src/qzdap_agent_runtime/graph/state.py` |
| `load_context` / `recall` / `inject_context` / `maybe_compact` / `remember` / `done` 节点 | `graph/nodes.py` |
| `build_graph()` 装配 + `route_after_agent` | `graph/builder.py` |
| `SSEAdapter` LangGraph event → TurnChunk | `sse/adapter.py` |
| `AgentEngine` 门面 | `engine.py` |
| `AsyncPostgresSaver` + `AsyncPostgresStore` 工厂 | `graph/checkpoint.py` |
| composition root 加 `make_engine()` | `composition/qzdap_app/src/.../lifespan.py` |
| `session_router` 切流量:`QZDAP_AGENT_ENGINE=v0\|v1` | `modules/agent_runtime/.../session_router.py` |

**验证**:`QZDAP_AGENT_ENGINE=v1` 跑同一 turn,前端 SSE 完全一致;`v0`/`v1` 切换不影响其他模块。

---

### Stage 5 · Governance + Approval 重写(0.5 周)

**目标**:`PolicyGuardMiddleware` 上图,approver 真实用户。

| 任务 | PR scope |
|---|---|
| `PolicyGuardMiddleware` 实现 | `governance/middleware.py` |
| `approve` / `deny` endpoint 改用 `engine.astream_resume` | `session_router.py` |
| 删除 `_request_approval` JSONB 自续传 | `modules/agent_runtime/.../runner.py`(删 `_request_approval` / `_finish_pending` / `decide_approval` 旧路径) |

**验证**:sandbox_exec 触发 → interrupt → 前端 approve → `Command(resume)` → 执行 → 审计 approver=真实用户。

---

### Stage 6 · Channel 接入(1 周)

**目标**:Channel → Agent 断链修复。

| 任务 | PR scope |
|---|---|
| `ChannelGateway` + `ChannelMessage` + `channel_to_input` | `channels/gateway.py` |
| `ChannelDispatcher` + `ChannelAdapter` Protocol | `channels/dispatcher.py` |
| 飞书 / 企微 / 钉钉 `ChannelAdapter` 实现 | `channels/adapters/{feishu,wechatwork,dingtalk}.py` |
| `dispatch_subscriber` 改为调 gateway | `modules/channel/.../dispatch_subscriber.py` |

**验证**:从飞书发消息 → `engine.astream` → 飞书收 MessageChunk / ApprovalCard。

---

### Stage 7 · Deep Agents 可选(1 周)

**目标**:深度 agent 启用 plan + sub-agent。

| 任务 | PR scope |
|---|---|
| `agent_factory` 加 `deep_research: bool` 字段 | `modules/agent_factory/.../entities.py` |
| `make_agent_node` 按 `deep_research` 选 ReAct / Deep Agent | `graph/agent_factory.py` |
| sub-agent `research` / `code` 注册 | `graph/deep_agent_config.py` |
| 前端 AgentEditor 加"深度研究模式"开关 | `frontend/web/src/features/agents/components/DrawerPanels.tsx` |

**验证**:deep_research agent 自动 plan + 委派 sub-agent;LangSmith trace 可见 todos 演进。

---

### Stage 8 · Observability + 评测闭环(0.5 周)

**目标**:cost 真实,trace 进 LangSmith Local,评测异步。

| 任务 | PR scope |
|---|---|
| `UsageTracker` + `UsageChunk` 真值 | `observability/usage.py` |
| `OnlineEvaluator` 异步入队 | `observability/evaluator.py` |
| Prometheus counter 上线 | `observability/prometheus.py` |
| 前端 usage 徽章 | `frontend/web/src/features/user/copilot/CopilotPage.tsx` |
| `agent_runtime` 合成 evaluation_pass_rate 改读真实评测 | `modules/agent_runtime/.../catalog.py` |

**验证**:LangSmith UI 看每次 turn 完整 trace;Prometheus 看 `qzdap_turns_total` / `qzdap_tool_calls_total`。

---

### Stage 9 · 灰度下线(并行,不占关键路径)

| 任务 | 时间 |
|---|---|
| Stage 4-8 完成后 `QZDAP_AGENT_ENGINE=v1` 100% 跑 1 周 | +1 周 |
| 删除 `SessionORM.graph_state` 字段 | +2 周 |
| 删除 `SessionGraphRunner` 文件 | +3 周 |
| 删除 `_passthrough_llm` / `_passthrough_tools` | +3 周 |
| 清理 `prompts.py`(v1 RunTurnUseCase 已无人调) | +4 周 |

---

## 11. 测试策略

### 11.1 单元测试(`backend/libs/agent_runtime/tests/unit/`)

| 测试 | 关键断言 |
|---|---|
| `test_sse_adapter.py` | LangGraph 事件 → TurnChunk 映射完整 |
| `test_tool_registry.py` | `register` / `meta` / `to_langchain_tools` / `to_tool_node` |
| `test_layered_memory.py` | L1+L2+L3 合并排序,Cohere reranker 注入 |
| `test_policy_guard_middleware.py` | 拒绝 → raise;需要审批 → interrupt;auto-allow → 继续 |
| `test_engine.py` | `astream` / `astream_resume` / `get_state` / `list_history` |
| `test_channel_gateway.py` | ChannelMessage → graph input / chunk → dispatcher |
| `test_compact_node.py` | LLM 摘要触发 / 阈值未到 no-op |

### 11.2 集成测试(`backend/tests/integration/`)

- 真实 Postgres:`uv run pytest -m integration backend/tests/integration/test_langgraph_engine.py`
- 真实 LangSmith Local:测试 `QZDAP_TRACE_TARGET=langsmith` 下 `astream` 推送 trace 成功
- SSE 端到端:`curl -N POST /api/sessions/{sid}/turns/stream` 拿到 8+3 类 chunk

### 11.3 契约测试(`backend/tests/contract/`)

- SSE chunk 协议:每个 chunk 的 `event:` / `data:` 字段与 `qzdap_schema.dtos.turn` 一致
- REST API:`/api/sessions/*` `/api/admin/agents/*` `/api/catalog/*` 与 OpenAPI 一致

### 11.4 E2E(Playwright)

- `tests/e2e/copilot-flow.spec.ts`:
  1. 登录 → `/copilot` → 输入 → 流式 message → done
  2. 触发 sandbox_exec → ApprovalRequired → Approve → ToolResult → done
  3. 长对话触发 ContextCompacted → 摘要写入
  4. usage 徽章正确显示
- `tests/e2e/channel-flow.spec.ts`:
  1. 飞书 mock 消息 → 飞书 mock 收 MessageChunk → approve → ToolResult

### 11.5 性能基准

- 单 turn P95 < 3 s(不含 tool 等待)
- approval 中断/恢复 P95 < 200 ms
- LangSmith trace 推送延迟 < 500 ms

---

## 12. 风险与回退

### 12.1 风险表

| 风险 | 影响 | 缓解 |
|---|---|---|
| LangGraph 1.x → 2.x API 变化 | 中 | 锁 `<2.0`;CI 跑 `compile().invoke()` smoke |
| Checkpoint 表膨胀 | 中 | 每周 prune `langgraph_checkpoint_writes` 老于 30 天 |
| LangSmith 本地磁盘满 | 中 | docker volume 设 50 GB 上限 + 监控 |
| Deep Agents 增加 token 消耗 | 低-中 | 仅 `deep_research=true` 的 agent 启用,普通 agent 走轻量 ReAct |
| Channel adapter 多样 | 中 | `ChannelAdapter` Protocol 化,各 IM 一份实现,不上 magic |
| 旧 SessionGraphRunner 与新 engine 数据迁移 | 中 | 一次性脚本从 `graph_state` 迁移到 `langgraph_store`,迁移期双写 |
| Cohere API 配额/延迟 | 中 | reranker 失败 → 降级到无 rerank(纯 vector similarity) |

### 12.2 回退开关

| 开关 | 行为 |
|---|---|
| `QZDAP_AGENT_ENGINE=v0` | 走旧 `SessionGraphRunner`(默认 Stage 4 前) |
| `QZDAP_AGENT_ENGINE=v1` | 走新 LangGraph(Stage 4+ 后) |
| `QZDAP_TRACE_TARGET=stdout` | 不推 LangSmith,仅 Prometheus + 日志 |
| `QZDAP_RERANK_PROVIDER=none` | 跳过 Cohere,纯向量检索 |
| `QZDAP_POLICY_AUTO_APPROVE_LOW_RISK=false` | 低风险也走审批 |

### 12.3 蓝绿切流

- `session_router.stream_turn` 内:读 `QZDAP_AGENT_ENGINE` → 选 engine
- 用户维度灰度:`SELECT user_id FROM ... WHERE email LIKE '%@canary.%'` → v1,其他 v0

---

## 13. 附录

### 附录 A · 新目录结构

```
backend/
├── libs/agent_runtime/                              ← 新增库
│   ├── pyproject.toml
│   └── src/qzdap_agent_runtime/
│       ├── __init__.py
│       ├── engine.py                                # 门面
│       ├── composition.py                           # make_engine()
│       ├── channels/
│       │   ├── gateway.py                           # ChannelMessage → input
│       │   ├── dispatcher.py                        # chunk → adapter
│       │   └── adapters/
│       │       ├── feishu.py
│       │       ├── wechatwork.py
│       │       └── dingtalk.py
│       ├── graph/
│       │   ├── state.py                             # AgentState
│       │   ├── nodes.py                             # 所有节点
│       │   ├── routing.py                           # route_after_agent
│       │   ├── builder.py                           # build_graph()
│       │   ├── checkpoint.py                        # AsyncPostgresSaver
│       │   ├── agent_factory.py                     # ReAct vs Deep
│       │   └── deep_agent_config.py
│       ├── tools/
│       │   ├── registry.py                          # ToolRegistry
│       │   ├── kb.py                                # search_kb
│       │   ├── skill.py                             # run_skill
│       │   ├── sandbox.py                           # sandbox_exec
│       │   └── tool.py                              # invoke_custom_tool
│       ├── memory/
│       │   ├── layered.py                           # L1+L2+L3
│       │   ├── reranker.py                          # Cohere
│       │   └── store.py                             # BaseStore 适配
│       ├── governance/
│       │   ├── middleware.py                        # PolicyGuardMiddleware
│       │   ├── approval.py                          # interrupt 适配
│       │   └── audit.py                             # AuditRecorder
│       ├── observability/
│       │   ├── langsmith.py                         # configure_tracing
│       │   ├── usage.py                             # UsageTracker
│       │   ├── prometheus.py                        # counter
│       │   └── evaluator.py                         # OnlineEvaluator
│       └── sse/
│           └── adapter.py                           # LangGraph → TurnChunk
└── modules/agent_runtime/                           ← 改为薄壳
    └── src/qzdap/modules/agent_runtime/
        ├── adapter/http/
        │   ├── router.py                            # v1(向后兼容)
        │   ├── catalog_router.py                    # admin CRUD(不变)
        │   └── session_router.py                    # 接 engine
        └── application/
            ├── catalog.py                           # AgentCatalogService(不变)
            └── service.py                           # SessionService(包装 engine)
```

### 附录 B · 关键依赖版本

```toml
langgraph = ">=1.2,<2.0"
langchain = ">=1.0,<2.0"
langchain-core = ">=1.0,<2.0"
langgraph-checkpoint = ">=4.2,<5.0"
langgraph-prebuilt = ">=1.1,<2.0"
deepagents = ">=0.2,<1.0"
langchain-community = ">=0.3"
langchain-openai = ">=0.2"
pgvector = ">=0.3"
cohere = ">=5.0"
tenacity = ">=9.0"
tiktoken = ">=0.7"
psycopg-pool = ">=3.2"
```

### 附录 C · 关键环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `QZDAP_AGENT_ENGINE` | `v0` | `v0`=旧 SessionGraphRunner;`v1`=LangGraph |
| `QZDAP_LLM_MODEL` | `gpt-4o` | 主模型 |
| `QZDAP_LLM_TEMPERATURE` | `0.2` | 默认温度 |
| `QZDAP_LANGGRAPH_DSN` | `postgresql://qzdap:qzdap@127.0.0.1:9153/qzdap` | Checkpointer/Store DSN |
| `QZDAP_TRACE_TARGET` | `stdout` | `langsmith` / `langfuse` / `phoenix` / `stdout` |
| `QZDAP_LANGSMITH_ENDPOINT` | `http://127.0.0.1:1985` | LangSmith Local |
| `QZDAP_LANGSMITH_API_KEY` | `lsv2_pt_local_dev_only` | LangSmith Local |
| `QZDAP_LANGSMITH_PROJECT` | `qzdap-dev` | LangSmith project |
| `QZDAP_RERANK_PROVIDER` | `cohere` | `cohere` / `none` |
| `QZDAP_COHERE_API_KEY` | (空) | Cohere API key |
| `QZDAP_POLICY_AUTO_APPROVE_LOW_RISK` | `true` | 低风险自动放行 |
| `QZDAP_POLICY_TIMEOUT_MS` | `30000` | 工具默认超时 |

### 附录 D · 关键文件:line 替换映射

| 旧实现 | 旧 file:line | 新实现 | 新 file |
|---|---|---|---|
| `SessionGraphRunner.run_turn` while True | [`runner.py:161-280`](../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/runner.py) | `graph.astream` + LangGraph 真图 | `graph/builder.py` + `nodes.py` |
| `_load_messages` 字符串拼接 | [`runner.py:313-383`](../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/runner.py) | `load_context` + `inject_context` 节点 | `graph/nodes.py` |
| `_request_approval` JSONB 自续传 | [`runner.py:401-420`](../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/runner.py) | `PolicyGuardMiddleware` + `interrupt()` | `governance/middleware.py` |
| `_finish_pending` 手撸续跑 | [`runner.py:454-490`](../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/runner.py) | `Command(resume=...)` | `engine.astream_resume` |
| `_remember` 单点写 L1 | [`runner.py:422-452`](../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/runner.py) | `remember` 节点 + `LayeredMemory.write_l1/l2` | `graph/nodes.py` + `memory/layered.py` |
| `compact_messages` 字符级 | [`compact.py:14-50`](../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/compact.py) | `maybe_compact` LLM 摘要节点 | `graph/nodes.py` |
| `next_route` 二元 | [`loop.py:14-25`](../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/loop.py) | `route_after_agent` 真多分支 | `graph/routing.py` |
| `_openai_tools` 空 schema | [`runner.py:501-514`](../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/runner.py) | LangChain `@tool(args_schema=Pydantic)` | `tools/{kb,skill,sandbox,tool}.py` |
| `decide_approval` 魔数 approver | [`copilot.py:245, 254`](../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/application/copilot.py) | `engine.astream_resume(approver=real_user)` | `engine.py` |
| `CopilotSessionService.stream_turn` 编排 | [`copilot.py:117-218`](../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/application/copilot.py) | 薄壳,只接 `engine.astream` | `modules/agent_runtime/.../session_router.py` |
| Channel 断链 | [`channel/.../dispatch_subscriber.py`](../../backend/modules/channel/src/qzdap/modules/channel/adapter/dispatch/dispatch_subscriber.py) | `ChannelGateway.on_message` | `channels/gateway.py` |
| `UsageChunk.cost_usd=0` | [`runner.py:304`](../../backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/graph/runner.py) | `UsageTracker` + Cohere model pricing | `observability/usage.py` |

### 附录 E · 关键 SSE Chunk 协议不变性证明

- `qzdap_schema.dtos.turn.TurnChunk` 子类字段(`turn_id` / `seq` / `content` / `tool_name` / `arguments` / `output` / `is_error` / `latency_ms` / `final_message` 等)全部保留。
- 新增 chunk 类型 `SkillInvocationChunk` / `KnowledgeSearchChunk` 已在 Schema 中定义,本次首次真正 emit。
- 适配层 `SSEAdapter` 是单一变更点,LangGraph event → TurnChunk 映射见 [§8.1](#81-协议对照表langgraph-事件--sse-chunk)。
- 前端 `CopilotPage.tsx` SSE handler 加 case 即可,无需重写。

---

## 14. 评审检查表

在合并 Stage 4+ 之前,确认以下都已完成:

- [ ] LangSmith Local docker compose 起得来,UI 可访问 `http://localhost:1984`
- [ ] Alembic 迁移 `memory_l2_embeddings` 在空库跑通
- [ ] `QZDAP_AGENT_ENGINE=v0` 旧 runtime 全功能无回归
- [ ] `QZDAP_AGENT_ENGINE=v1` 新 runtime 跑同一 turn,前端 SSE 与 v0 完全一致
- [ ] 8+3 类 chunk 在 LangSmith Local trace 里可对应
- [ ] approval 中断/恢复流程通过 E2E
- [ ] Channel → Agent 端到端通过 E2E(飞书 mock)
- [ ] `usage` 在前端正确显示
- [ ] Prometheus counter 在 `/metrics` 路由出现
- [ ] 前端补完 `tool_result` / `memory_write` / `context_compacted` / `usage` 渲染

---

## 15. 时间线一览

```
Week 1:  ┌─ Stage 1(基础设施)─┐ ┌─ Stage 2(tool)─┐
Week 2:  ├─ Stage 3(memory) ──┤ ┌─ Stage 4(graph 骨架)─┐
Week 3:  ├─ Stage 4 续 ──────┤ ├─ Stage 5(governance)┤
Week 4:  ├─ Stage 6(channel) ─┤ ┌─ Stage 7(deep agents)┐
Week 5:  ├─ Stage 7 续 ──────┤ ├─ Stage 8(observability)┤
Week 6:  ├─ Stage 9 灰度下线 ─┤

并行:从 Week 1 起,LangSmith Local 容器始终在跑,所有 E2E 测试推 trace。
```

---

## 16. 一句话总结

> **保留 SSE chunk 协议 + 前端契约,内部用 LangGraph 真图 + LangChain `@tool`/`Runnable` + Deep Agents plan/sub-agent,替换"手写 ReAct + 占位 `StateGraph` + JSONB 自续传 + 缺失的 policy_guard";LangSmith Local docker 提供零 License trace;Channel → Agent 断链修复;governance 真实接入;cost/tokens 真实计算。** 28 个 finding 中 P0 6 个 + P1 4 个随之解决。
