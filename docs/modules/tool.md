# tool — 工具注册与执行

> 能力域之一。负责工具的定义、注册、调用与审计，是 agent「动手能力」的落点。

## 职责

- 工具目录的注册 / 查询 / 更新 / 删除
- 三类工具的协议派发：**内置工具** / **OpenAPI** / **MCP**
- 调用的可靠性保障：幂等、重试、熔断
- 工具调用 100% 写审计

## 源码位置

```
backend/modules/tool/src/qzdap/modules/tool/
├── domain/          entities.py（Tool · ToolCall · AuthConfig · SpecOperation）
├── application/
│   ├── services.py          ToolService（门面）
│   ├── tool_catalog.py      BUILTIN_TOOL_SPECS（内置工具声明）
│   ├── tool_schema.py       spec → JSON Schema（模型看得到参数的唯一真相）
│   ├── reliability.py       CircuitBreaker（熔断）
│   ├── idempotency.py       幂等键与参数指纹
│   └── use_cases/           RegisterTool · InvokeTool · BatchInvokeTools · …
└── adapter/
    ├── http/         router.py
    ├── persistence/  models.py（tools · tool_calls）
    └── adapters/     builtin_extra_tools.py · custom_invoker.py · mcp_runtime.py · openapi_runtime.py · tool_audit.py
```

## HTTP 端点

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/v1/tools` | 工具列表 |
| POST | `/v1/tools` | 注册工具 |
| GET | `/v1/tools/{tid}` | 工具详情 |
| PATCH | `/v1/tools/{tid}` | 更新工具 |
| DELETE | `/v1/tools/{tid}` | 删除工具 |
| POST | `/v1/tools/{name}/invoke` | 调用工具 |
| POST | `/v1/tools/batch_invoke` | 批量调用 |

## 数据表

| 表 | 职责 | 关键列 |
|---|---|---|
| `tools` | 工具定义 | id / tenant_id / name / type / spec(JSONB) / auth_config / status |
| `tool_calls` | 调用记录 | id / tool_id / tenant_id / status / request / response / duration |

**幂等的权威不在本模块**——是 `tool_executions` 表（由 agent 执行轴写入）。本模块通过 `application/idempotency.py` 复用 `qzdap_kernel.digest.request_hash` 计算参数指纹。

## 内置工具（31 个）

声明在 `application/tool_catalog.py::BUILTIN_TOOL_SPECS`，真实执行体在 `adapter/adapters/builtin_extra_tools.py`。

| 类别 | 工具 |
|---|---|
| 自检 | `echo` `reverse` `clock` |
| 网络 | `web_search` `http_fetch` `fetch_url_with_auth` |
| 文件 I/O | `bash` `read_file` `write_file` `edit_file` `ls` `glob` `grep` `apply_patch` `diff` |
| 内容处理 | `image_view` `pdf_read` `json_query` `csv_query` `convert_format` `calculator` |
| 代码库 | `git_status` `git_diff` `git_log` `code_search` |
| 平台交互 | `ask_user_question` `notify_user` `plan_submit` `todo_write` `write_artifact` `delegate_to_agent` |

每个 spec 声明 `parameters`（JSON Schema）、`idempotent`、`risk`（`low` / `medium` / `high`）。**`risk != low` 会触发人工审批**。

内置工具由 `composition/seeds.py::seed_builtin_tools` 写库，模型看到的是 `tool_schema.py` 生成的 JSON Schema。

## 实现要点

- **执行顺序固定**：skill → sandbox → 目录工具；同名时**先 skill**（`adapter/graph/agent_loop.py` 的 `ModuleToolRuntime`）
- **失败不抛穿**：返回带 `error_code` 的结果，LLM 能看到 `ERROR <code>: <message>` 并自行纠正
- **重试**：`use_cases/invoke_tool.py::_run_with_retry`，`max_attempts=3`
- **熔断**：`application/reliability.py::CircuitBreaker`，按工具名计数，**必须进程内共享单例**（否则熔断形同虚设）
- **幂等**：同键异参抛 `TOOL_IDEMPOTENCY_CONFLICT`，不静默执行
- **审计**：所有调用写 `audit_log`（actor_id / workspace_id / duration_ms / risk_level），工具侧网络出站另记 `tool.network_egress` 事件
- **actor 必须真实**：`ModuleToolRuntime.invoke` 校验 actor 存在且租户一致——工具执行是**谁的权限**就用谁的 actor

## 已知边界

- ⚠️ `ask_user_question` / `notify_user` / `plan_submit` / `todo_write` 是**前端桩**（`builtin_extra_tools.py:1258` 返回 `_stub_hint`）
- ⚠️ `web_search` 直接爬 Bing HTML，代码注释明写「生产环境应换成 Tavily/Serper（TODO）」
- ⚠️ `adapter/workspace_paths.py:7` 的沙箱路径仍是 TODO——未读 `admin_workspaces.sandbox_path`，沙箱工具的工作目录没有和租户工作区绑定
- ⚠️ `write_artifact` 上限 1MB，kind 白名单固定
- ⚠️ 网络出站**没有域名级白名单**：`web_search` / `http_fetch` 只做 content-type 白名单 + 1MiB 上限 + 3 次重定向（方案见 [待实施](../planned/sandbox-network-egress-control.md)）
