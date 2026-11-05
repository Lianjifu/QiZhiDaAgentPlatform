# orchestration — 工作流编排

> 能力域之一。负责工作流的定义、发布、收藏与**执行**——把「触发 → 工具 / 智能体 → 条件 → 结束」串成一条可运行的图。

## 职责

- 工作流的增删改查与发布
- 用户侧目录投影（只暴露 published）
- 收藏与运行记录
- **执行引擎**：真正按图遍历

## 源码位置

```
backend/modules/orchestration/src/qzdap/modules/orchestration/
├── domain/          entities.py（Workflow · FlowVersion · FlowRun）
├── application/
│   ├── services.py   OrchestrationService（CRUD / catalog / 收藏 / run）
│   ├── engine.py     WorkflowEngine（执行引擎）
│   ├── ports.py      WorkflowRepository · WorkflowToolPort · WorkflowAgentPort
│   └── use_cases/    ⚠️ 空目录
└── adapter/
    ├── http/         router.py
    └── persistence/  models.py · repositories.py
```

组合根接线在 `composition/qzdap_app/src/qzdap/composition/lifespan.py:1182` 与 `workflow_ports.py`——`ToolWorkflowPort` 落到 tool 模块，`AgentWorkflowPort` 落到 copilot 会话。

## HTTP 端点

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/admin/workflows` | 工作流列表 |
| POST | `/api/admin/workflows` | 建工作流 |
| GET | `/api/admin/workflows/{id}` | 工作流详情 |
| PATCH | `/api/admin/workflows/{id}` | 更新 |
| DELETE | `/api/admin/workflows/{id}` | 删除 |
| GET | `/api/catalog/workflows` | 用户侧目录（只 published） |
| GET | `/api/catalog/workflows/__runs__` | 运行记录 |
| POST | `/api/catalog/workflows/{id}/favorite` | 收藏 |
| POST | `/api/catalog/workflows/{id}/run` | **运行** |

另有 4 个 `/api/user/automations*` 别名，指向同一套逻辑。

## 数据表

| 表 | 职责 | 关键列 |
|---|---|---|
| `admin_workflows` | 工作流定义 | id / tenant_id / name / scene / status / trigger / bound_agents / initial_nodes / initial_edges / versions |
| `admin_workflow_user_state` | 收藏 | tenant_id / user_id / workflow_id（唯一键） |
| `admin_workflow_runs` | 执行记录 | id / workflow_id / name / time / result |

## 关键类

| 层 | 类 | 职责 |
|---|---|---|
| domain | `Workflow` `FlowVersion` `FlowRun` | 聚合根 |
| application | `OrchestrationService` | 模块门面 |
| application | `WorkflowEngine` | **执行引擎** |
| application | `WorkflowRunContext` `NodeOutcome` `WorkflowRunResult` | 运行时数据形状 |

## 执行引擎

`engine.py::WorkflowEngine.run` 的实际行为：

1. 从 `initial_nodes` 里找第一个 `trigger` 节点作入口
2. 循环执行，按 `kind` 分派：`trigger` / `tool` / `agent` / `condition` / `end`
3. 变量按 **Dify 风格按名字**从「变量袋」取（`_collect_inputs`）——**取不到就留空，不猜**
4. 工具节点调 `WorkflowToolPort.invoke`，智能体节点调 `WorkflowAgentPort.run`
5. 条件节点用 `sourceHandle` 选分支边
6. `MAX_STEPS = 20` 防环
7. 任一节点异常即中止，并写明停在哪一步

## 已知边界

- ⚠️ **orchestration 不发布任何事件**（`adapter/` 下只有 http 与 persistence，没有 events.py）——observability 订阅的 `WorkflowRunCompleted` **永远不会触发**
- ⚠️ `application/use_cases/` **是空目录**——所有逻辑集中在 `services.py`，与「application 层放用例」的分层约定不一致
- ⚠️ `FlowRun.time` 硬编码 `"刚刚"`，`result` 只存摘要字符串，**不存步骤明细**——排障时看不到中间步
