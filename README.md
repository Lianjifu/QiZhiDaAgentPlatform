# 企智搭 · 智能体平台

> **QiZhiDa · Agent Platform（QZDAP）** — 企业级智能体工作台：管理员建设能力并治理运行，成员从已开放目录选用智能体、知识、技能和工作流去完成工作。

后端 **Python 3.12 + FastAPI 模块化单体**，前端 **React 18 + Vite** 工作台（用户侧 + 管理侧）。默认联调路径：

```
浏览器 :9152  →  网关 :9150  →  qzdap-app :9151  →  Postgres :9153
```

## 界面预览

以下截图来自 `pnpm --filter web dev:demo`（前端内存演示数据，无需后端）。

### 登录

管理员与成员从同一登录页进入，角色分流到 `/admin/*` 或工作区。

![登录工作台](docs/images/demo/login.png)

### 用户侧

成员从已开放目录选用能力，在对话里把工作做完。

| 首页 | 对话 |
|---|---|
| ![首页](docs/images/demo/user-home.png) | ![对话](docs/images/demo/user-copilot.png) |

![协作](docs/images/demo/user-team.png)

### 管理侧

管理员建设目录、治理用量，并用评测与链路看质量。

| 运营概览 | 智能体管理 |
|---|---|
| ![运营概览](docs/images/demo/admin-overview.png) | ![智能体管理](docs/images/demo/admin-agents.png) |

| 知识管理 | 额度管理 |
|---|---|
| ![知识管理](docs/images/demo/admin-knowledge.png) | ![额度管理](docs/images/demo/admin-quotas.png) |

| 评测中心 | 调用链路 |
|---|---|
| ![评测中心](docs/images/demo/admin-evaluations.png) | ![调用链路](docs/images/demo/admin-operations.png) |

## 核心特性

- **多 BC 模块化后端**：15 个能力域（identity / agent_runtime / skill / tool / knowledge / memory / model / channel / orchestration / governance / evaluation / self_evolution / observability / platform / agent_factory）+ 10 个共享内核包，严格六边形分层 + import-linter 守护边界。
- **双侧工作台**：用户侧选用与执行，管理侧建设与治理，登录按 JWT 工作区分流到 `/admin/*` 或工作区。
- **流式对话协议**：`POST /v1/sessions/{id}/turns`，8 种 SSE chunk（message / tool_call / tool_result / skill_invocation / memory_write / knowledge_search / usage / done）。
- **企业级治理**：多租户 + 多工作区（`X-Tenant-Id` / `X-Workspace-Id`），额度、审计、灰度、合规开关。
- **质量闭环**：评测中心、回归追踪、用户反馈 + 调用链路 + 工具审计。
- **演示模式**：`VITE_USE_DEMO=true` 不连后端即可全界面浏览。

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | React 18 · Vite · Tailwind · pnpm workspace（`@qzdap/web-{api,ui,hooks,types,utils}`） |
| 后端 | Python 3.12 · FastAPI · uv workspace（`qzdap.*`） |
| 架构 | 模块化单体 · 六边形 Ports & Adapters · import-linter 边界守护 |
| 数据 | Postgres + pgvector · Redis · MinIO |
| 鉴权 | JWT · `Authorization` / `X-Tenant-Id` / `X-Workspace-Id` / `X-Trace-Id` |
| 观测 | Prometheus · Grafana · OpenTelemetry |
| 编排 | k8s · Envoy（见 [`infra/`](./infra/)） |

## 快速开始

依赖：后端 `uv`，前端 `pnpm`。开发栈脚本拉起 qzdap-app + 网关 + Vite，默认端口 9152 / 9150 / 9151 / 9153。

```bash
# 准备
cd backend && make sync && cp .env.example .env && make db-upgrade
cd ../frontend && pnpm install

# 回到仓库根
make qzdap-up          # 启动
make qzdap-status      # 查看端口
make qzdap-down        # 停止
```

打开 [http://127.0.0.1:9152](http://127.0.0.1:9152)，使用种子账号登录：

| 角色 | 邮箱 | 密码 |
|---|---|---|
| 管理员 | `admin@acme.com` | `dev-admin-password-change-me` |
| 成员 | `user@acme.com` | `dev-admin-password-change-me` |

### 仅前端（演示数据）

不连后端即可浏览界面：

```bash
cd frontend
pnpm --filter web dev:demo
# http://127.0.0.1:9152
```

真实 API 是默认：`pnpm --filter web dev`（`VITE_USE_DEMO=false`，Vite 代理到网关）。

### 仅后端

```bash
cd backend
make sync
docker compose up -d       # PG（pgvector）+ Redis + MinIO
cp .env.example .env
make db-upgrade
make run-app               # 联调用 make qzdap-up（:9151）
curl http://127.0.0.1:9151/healthz
```

后端命令须在 `backend/` 下执行。环境变量一律 `QZDAP_*`，Python 包名 `qzdap.*`，前端包名 `@qzdap/web-*`。

## 用户侧

从管理端已发布、并对工作区开放的目录中浏览选用，再进入对话或执行。

| 页面 | 说明 |
|---|---|
| 首页 | 查看今天需要处理的事项 |
| 对话 | 发起对话并跟进执行结果（流式 SSE） |
| 智能体 | 浏览并选用管理员已开放的智能体，进入对话 |
| 知识 | 基于企业资料获取可信答案 |
| 技能 | 选用已发布的 Skill / Tool / MCP |
| 工作流 | 选用团队已发布的工作流 |
| 任务 | 跟进待确认、执行中与已完成事项 |
| 协作 | 共享团队智能体与知识（工作区成员、目录） |
| 设置 | 个人资料、账号安全、通知与偏好 |

## 管理侧

列表默认每页 10 条，点击行进入详情；「新建」进入独立页面。运营类走 `/api/admin/*`，目录类走 `/api/catalog/*`。

| 模块 | 说明 |
|---|---|
| 运营概览 | 平台健康：调用量、可用率、告警、服务状态、热门智能体 |
| 智能体管理 | 创建、配置、审核并发布企业智能体 |
| 技能管理 | 维护 Skill / Tool / MCP 等可调用能力 |
| 知识管理 | 管理知识库、资料来源和访问权限 |
| 记忆管理 | 短期会话、长期事实与知识层记忆 |
| 工作流管理 | 编排、发布可执行工作流 |
| 模型配置 | 接入供应商（API Key、地址、协议），拉取模型列表并配置路由 |
| 额度管理 | 预算、部门用量、告警阈值 |
| 渠道配置 | 飞书、企微、钉钉、Web 对话入口与通知组 / Webhook |
| 评测中心 | 用套件评测智能体、知识与流程质量 |
| 回归追踪 | 对比基线，发现版本退化 |
| 用户反馈 | 收集赞踩与工单，按规则分诊处理 |
| 调用链路 | 还原会话中智能体 / 工具 / MCP 的完整调用过程 |
| 工具审计 | 审查工具调用、权限越界与风险规则 |
| 运行指标 | 观测可用率、延迟、Token 与成本 |
| 平台设置 | 品牌、合规开关和成员 |

用户侧的智能体、知识、技能、工作流分别来自以上目录，**仅已发布并对工作区开放的条目可被选用**。

## 仓库结构

```
.
├── backend/                       Python 3.12 + FastAPI + uv workspace（qzdap.*）
│   ├── libs/                      10 个共享内核
│   ├── modules/                   15 个能力域
│   ├── composition/qzdap_app/     组合根 = 唯一部署产物
│   ├── runtimes/                  embedding_runtime · sandbox_runtime
│   ├── packs/                     示例 pack
│   └── migrations/                Alembic
├── frontend/                      pnpm workspace
│   ├── web/                       工作台 SPA
│   └── packages/                  @qzdap/web-{api,ui,hooks,types,utils}
├── bin/qzdap-stack/               本机开发栈：Vite(:9152) + 网关(:9150) + qzdap-app(:9151) + Postgres(:9153)
├── deploy/                        部署脚本与编排
├── infra/                         k8s / envoy / prometheus / grafana
├── docs/                          ADR、runbook 与演示截图
└── README.md
```

## 工程约定

- 提交规范：**Conventional Commits**（commitlint 校验）
- 后端 pre-commit：ruff · mypy（strict）· lint-imports · gitleaks
- 多租户请求携带 `X-Tenant-Id` 与 `X-Workspace-Id`
- 演示模式 `VITE_USE_DEMO=true` 只注入本地 mock，生产构建不触达
- 命名空间：Python `qzdap.*`、前端 `@qzdap/web-*`、环境变量 `QZDAP_*`