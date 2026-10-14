# LangGraph 1.x 升级迁移笔记（§2.5 阻塞 1）

> 状态：**升级预演通过，无代码级阻断**
> 探针脚本：`scripts/probes/langgraph_1x_smoke.py`
> 工作分支：`chore/langgraph-1x-upgrade`（worktree：`../upgrade-langgraph-1x/`）
> 探针日期：2026-10-15
> 适用：[`session-module-refactor-plan.md`](session-module-refactor-plan.md) §2.5 阻塞 1 / §13.1

---

## 1. 升级解析结果

| 包 | 旧版本 | 新版本 | 备注 |
|---|---|---|---|
| `langgraph` | `>=0.2.28` | **`1.2.15`** | 主版本断代，无破坏性 API 冲突 |
| `langgraph-prebuilt` | （未声明） | `1.1.0` | 新增依赖（§13.1 要求） |
| `langchain-core` | `>=0.3.0` | **`1.6.10`** | 主版本断代，与 langgraph 1.x 同步 |
| `langgraph-checkpoint` | （作为 langgraph 子模块） | **`4.3.0`** | **已拆分为独立包**（LangGraph 1.x 重大变更） |
| `langgraph-sdk` | （未声明） | `0.4.7` | 1.x 自动拉入 |
| `langchain-protocol` | （未声明） | `0.0.19` | 传递依赖 |

`uv lock` 解析 156 个包，**无冲突**；`uv sync` + `uv pip install -e modules/agent_runtime` 成功。

## 2. Smoke 测试结果（`scripts/probes/langgraph_1x_smoke.py`）

```text
OK: LangGraph 1.x smoke passed
{
  "invoke_final_counter": 3,
  "astream_event_kinds": ["on_chain_end", "on_chain_start", "on_chain_stream"],
  "interrupt_resumed_state": {"approved": true, "value": "hi"}
}
```

**验证矩阵**：

| §2.5 阻塞 1 要求项 | 1.x 行为 | 结果 |
|---|---|---|
| `StateGraph.add_node` / `add_edge` / `add_conditional_edges` 1.x 签名 | 与 0.x 兼容，无 breaking change | ✅ |
| `InMemorySaver`（生产用 PostgresSaver 替换） | `from langgraph.checkpoint.memory import InMemorySaver` 可用 | ✅ |
| `graph.compile()` 在 1.x 下成功 | `compile_loop_graph(llm_node=..., tools_node=...)` 返回 `CompiledStateGraph` | ✅ |
| `astream_events(version="v2")` 产出事件 | 产出 `on_chain_start` / `on_chain_end` / `on_chain_stream` | ✅ |
| `interrupt` + `Command(resume=...)` 协议 | 1.x 与 0.x 协议一致；`Command(resume=True)` 恢复时 `state["approved"]=True` | ✅ |

**未在 smoke 中验证（需 PG 才能跑）**：

- `PostgresSaver` / `PostgresStore` 实例化（Stage 2 任务）
- 进程重启后从 checkpoint 恢复（Stage 2 任务）
- `on_chat_model_stream` / `on_tool_start` 事件（需要真实 chat model 与 tool 注册，smoke 用最小可编译图）

## 3. 现有 v0 代码兼容性扫描

| 文件 | langgraph API 使用 | 1.x 兼容性 |
|---|---|---|
| `adapter/graph/runner.py:161` | `while True` 手写循环，**未使用 LangGraph**；仅 `interrupt` 作为变量名 | ✅ 无 breaking |
| `adapter/graph/loop.py` | `from langgraph.graph import END, START, StateGraph` + `compile_loop_graph` | ✅ 可编译 |
| `adapter/graph/compact.py` | 字符级压缩，**未使用 LangGraph** | ✅ 无 breaking |
| `adapter/graph/state.py` | TypedDict 定义 | ✅ TypedDict 与 langchain-core 1.x 兼容 |

**结论**：**v0 现有代码在 1.x 下 import 与 compile 全部通过，无需改动即可运行**。`while True` → graph 节点的真正重写属于 §8 Stage 4 工作（与 `runner.py:161` 替换为 19 节点图同源）。

## 4. 升级期间发现的两个工作项

### 4.1 `qzdap-vault` 必须在 `modules/agent_runtime` 显式声明

`runner.py` import 链 `agent_runtime.application.ports` → `from qzdap_vault.actor import ActorContext`。当前 `modules/agent_runtime/pyproject.toml` **未**显式声明 `qzdap-vault`，靠 `qzdap-persistence` 或其他依赖传递引入。

升级后 `uv lock` 解析路径可能不再传递引入 `qzdap-vault`，导致 `uv run python -c "from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner"` 报 `ModuleNotFoundError`。

**修复（合并到 Stage 1 PR）**：

```toml
# backend/modules/agent_runtime/pyproject.toml dependencies
"qzdap-vault",   # 新增：actor context
"qzdap-kernel",
"qzdap-schema",
"qzdap-persistence",
"qzdap-auth",
"qzdap-messaging",
"qzdap-llm",
```

### 4.2 `langgraph-checkpoint` 已独立成包

LangGraph 1.x 把 `langgraph.checkpoint` 拆为独立包 `langgraph-checkpoint==4.3.0`。如果未来 Stage 2 直接用 `from langgraph.checkpoint.postgres import PostgresSaver`，需要：

```toml
langgraph-checkpoint = ">=4.0,<5.0"   # Stage 2 加入
```

不要继续使用 `langgraph[postgres]` extras（extras 命名可能在 1.x 调整），而是显式声明。

## 5. 升级合并步骤（建议）

1. **PR 1**：把 `pyproject.toml` 升到 1.x（`langgraph>=1.0,<2.0` / `langchain-core>=1.0,<2.0` / 新增 `langgraph-prebuilt>=1.0,<2.0`）。
2. **PR 1**：补 `qzdap-vault` 显式依赖（§4.1）。
3. **PR 2（Stage 4）**：`runner.py:161` 的 `while True` 替换为 19 节点 `StateGraph`。
4. **PR 3（Stage 2）**：加 `langgraph-checkpoint` 依赖，接入 `PostgresSaver` / `PostgresStore`。

**不建议合并顺序**：把升级 PR 推到 main 之前，先用本 worktree 把 `runner.py:161` 改写完成并跑通 `While True 替换为 graph 节点后，既有 session_events fixture 能重放` 验证。

## 6. 探针命令清单（可重放）

```bash
# 升级预演（独立 worktree）
git worktree add ../upgrade-langgraph-1x -b chore/langgraph-1x-upgrade main

# 解析与安装
cd ../upgrade-langgraph-1x/backend
uv lock
uv sync
uv pip install -e modules/agent_runtime
uv pip install -e libs/vault

# Smoke 测试
uv run python scripts/probes/langgraph_1x_smoke.py

# 现有 v0 代码兼容性扫描
uv run python -c "from qzdap.modules.agent_runtime.adapter.graph.runner import SessionGraphRunner"
uv run python -c "from qzdap.modules.agent_runtime.adapter.graph.loop import compile_loop_graph; \
  compile_loop_graph(llm_node=lambda s: s, tools_node=lambda s: s)"
```

## 7. 阻塞 1 退出判定

§2.5 阻塞 1 退出条件：

- ✅ `graph_compile_smoke.py` 在 1.x 下通过
- ⏳ `runner.py:161` 的 `while True` 替换为 graph 节点后，既有 `session_events` fixture 能重放（属于 Stage 4 任务）
- ⏳ 内存 checkpointer 迁移到 Postgres 后，进程重启可恢复（属于 Stage 2 任务）

**当前阶段**：阻塞 1 预演已完成，Stage 4 与 Stage 2 的退出条件未在本预演中验证（属于后续阶段任务）。

**结论**：可以合并 PR 1（依赖升级 + qzdap-vault 补齐）；Stage 4 / Stage 2 工作按 §8 推进。

---

**smoke 脚本**：[`scripts/probes/langgraph_1x_smoke.py`](../../scripts/probes/langgraph_1x_smoke.py)（注：当前在 worktree `../upgrade-langgraph-1x/backend/scripts/probes/`，合并时移到主 worktree）
**方案上下文**：[`session-module-refactor-plan.md`](session-module-refactor-plan.md) §2.5 阻塞 1 / §13.1