# `deepagents` 探针结果（§2.5 阻塞 4）

> 状态：**包存在，可用作 Stage 6b 主路径**
> 探针脚本：`scripts/probes/deepagents_import.py`
> 探针日期：2026-10-15
> 适用：会话模块重构方案 §2.5 阻塞 4 / §5.5 / §13.1

---

## 1. 探针结论

| 候选包名 | 是否存在 | 当前版本 | 关键 API | 结论 |
|---|---|---|---|---|
| `deepagents` | ✅ 是 | **0.7.25** | `create_deep_agent`, `SubAgent` | **采用** |
| `langchain_deepagents` | ❌ 否 | — | — | 弃用（PyPI 无此包） |
| `deep_agents` | ❌ 否 | — | — | 弃用（PyPI 无此包） |

**采用包**：`deepagents`（注意不是 `langchain-deepagents` 也不是 `deep-agents`）。

## 2. 与 LangGraph 1.x 兼容性

在隔离 venv 中同时安装 `deepagents==0.7.25` + `langgraph>=1.0,<2.0`：

| 包 | 解析版本 |
|---|---|
| `deepagents` | 0.7.25 |
| `langgraph` | **1.2.15** |
| `langchain-core` | 1.6.10 |

兼容性结论：**完全兼容**，无依赖冲突，无 API 报弃用。可直接进入 Stage 6b 实施。

## 3. `create_deep_agent` 关键签名

```python
def create_deep_agent(
    model=None,                            # 已弃用；1.0.0 起 None 不再被允许
    tools=None,
    system_prompt=None,
    middleware=(),                         # 注入自定义中间件（governance hook 点）
    subagents=None,                        # 注入 SubAgent 列表（与 §13.2 节点 14 对齐）
    skills=None,
    memory=None,                           # 跨会话记忆（与 LayeredMemory port 对齐）
    permissions=None,                      # 权限/白名单（与 PolicyGuard 对齐）
    backend=None,                          # 沙箱 backend（与 execution/ 对齐）
    interrupt_on=None,                     # 触发 interrupt 的工具名列表（与 §5.7 对齐）
    response_format=None,
    state_schema=None,
    context_schema=None,
    checkpointer=None,                     # LangGraph checkpointer（与 §4.2 对齐）
    store=None,                            # LangGraph store（与 §4.2 对齐）
    debug=False,
    name=None,
    cache=None,
): ...
```

**与方案对齐点**：

- `middleware` 参数是 §5.7 PolicyGuard 的接入点（Plan 阶段注入治理 hook）。
- `subagents` 参数直接对应 §13.2 节点 14 `subagent` 的多 agent 委派。
- `permissions` 参数与 §5.7 "工具白名单 + 风险等级" 字段对齐。
- `interrupt_on` 参数与 §13.2 节点 13 `governance` 的 interrupt 触发对齐。
- `checkpointer` + `store` 直接接收 LangGraph 1.x 的 PostgresSaver/Store。
- `memory` 参数对接 §13.4 `LayeredMemory` 协议。
- `backend` 参数对接 §7.2 `execution/` 沙箱 backend 协议。

**已知弃用警告**：`model=None` 自 `0.5.3` 起被弃用，将在 `deepagents==1.0.0` 移除。**实施要求**：`create_deep_agent(model=...)` 必须显式传 model，禁止依赖默认值。

## 4. Stage 6b 实施约束（依据本次探针结果）

1. **pyproject.toml 锁定**：
   ```toml
   deepagents = ">=0.7,<1.0"   # 1.0 之前定版，避免 model=None 移除冲击
   ```
2. **代码层显式传 model**：所有 `create_deep_agent(...)` 调用必须 `model=<BaseChatModel | str>`。
3. **Stage 6b 触发链路**：
   - `route.deep_task=true` → 主图进入节点 13 `deep_agent_plan` → 内部调用 `create_deep_agent(model=..., subagents=[...], permissions=[...], interrupt_on=[...], checkpointer=pg_saver, store=pg_store)`。
   - 节点 13 把创建的 deep agent 作为可调用对象挂载到 LangGraph 子图。
   - 节点 14 `subagent` 由 `deepagents` 内部通过 `task` 工具委派，无需我们实现 sub-agent 调度循环。
4. **回退条件**：`deepagents>=1.0` 移除 `model=None` 后，CI 必须显式校验 `model` 参数非 None。

## 5. 探针命令清单（可重放）

```bash
# 探针主脚本
uv run --with deepagents python scripts/probes/deepagents_import.py

# 完整版本 + API 表面探测
uv run --with "deepagents==0.7.25" --with "langgraph>=1.0,<2.0" \
    python -c "
import importlib.metadata as md, inspect, deepagents
print('deepagents:', md.version('deepagents'))
print('langgraph:', md.version('langgraph'))
print('langchain-core:', md.version('langchain-core'))
print(inspect.signature(deepagents.create_deep_agent))
"
```

## 6. 后续动作

1. ✅ **§2.5 阻塞 4 已收敛**：`deepagents` 包名锁定为 `deepagents`（不是 `langchain_deepagents` 也不是 `deep_agents`），版本范围 `>=0.7,<1.0`。
2. ⏭ Stage 4 可以启动：使用启发式分类器（不依赖 `deepagents`），但 `builder.py` 中 `deep_agent_plan` / `subagent` 占位节点可以预埋。
3. ⏭ Stage 6b 启动条件 = Stage 1–6a 全部合入 + 本探针结果已被评审通过。

---

**探针脚本**：[`scripts/probes/deepagents_import.py`](../../scripts/probes/deepagents_import.py)
**方案上下文**：[`session-module-refactor-plan.md`](session-module-refactor-plan.md) §2.5 阻塞 4 / §5.5 / §13.1