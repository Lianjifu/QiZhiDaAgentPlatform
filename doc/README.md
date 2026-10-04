# 企智搭 · 智能体平台 · 文档总览

> **新项目（greenfield）** 方案。企智搭 · 智能体平台 是新一代企业级智能体平台，**前端 4D 架构**（pnpm Workspace Monorepo + FSD + DDD + Hexagonal Ports & Adapters）与**后端 Python FastAPI 模块化单体**平行的统一设计。
>
> ⚠️ **项目关系澄清**：本文档是独立新项目方案，**与本仓库现有 `backend/` `frontend/` 旧项目无强绑定**；仅借鉴业务概念，不沿用技术栈。详见 [REVIEW.md](REVIEW.md)。

## 目录结构

```
docs/qizhida-agent-platform/
├── README.md                  ← 本文档（总索引）
├── backend/                   ← 后端 13 节方案
│   ├── 00-README.md
│   ├── 01-架构总览.md
│   ├── 02-仓库结构.md
│   ├── 03-共享内核.md
│   ├── 04-模块设计.md
│   ├── 05-跨模块协作.md
│   ├── 06-接口规范.md
│   ├── 07-组合根与启动.md
│   ├── 08-持久化与迁移.md
│   ├── 09-可观测性.md
│   ├── 10-测试与CI.md
│   ├── 11-部署与运行.md
│   ├── 12-实施计划.md
│   └── 13-风险与验收.md
└── web/                       ← 前端 13 节方案
    ├── 00-README.md
    ├── 01-架构总览.md
    ├── 02-仓库结构.md
    ├── 03-共享内核.md
    ├── 04-模块设计.md
    ├── 05-跨模块协作.md
    ├── 06-接口规范.md
    ├── 07-组合根与启动.md
    ├── 08-持久化与迁移.md
    ├── 09-可观测性.md
    ├── 10-测试与CI.md
    ├── 11-部署与运行.md
    ├── 12-实施计划.md
    └── 13-风险与验收.md
```

## 平行阅读指南

| 阅读主题 | 后端入口 | 前端入口 |
|---|---|---|
| 架构总览 | [backend/01-架构总览](backend/01-架构总览.md) | [web/01-架构总览](web/01-架构总览.md) |
| 仓库结构 | [backend/02-仓库结构](backend/02-仓库结构.md) | [web/02-仓库结构](web/02-仓库结构.md) |
| 共享内核 | [backend/03-共享内核](backend/03-共享内核.md) | [web/03-共享内核](web/03-共享内核.md) |
| 模块/BC 设计 | [backend/04-模块设计](backend/04-模块设计.md) | [web/04-模块设计](web/04-模块设计.md) |
| 跨模块/BC 协作 | [backend/05-跨模块协作](backend/05-跨模块协作.md) | [web/05-跨模块协作](web/05-跨模块协作.md) |
| 接口规范 | [backend/06-接口规范](backend/06-接口规范.md) | [web/06-接口规范](web/06-接口规范.md) |
| 组合根与启动 | [backend/07-组合根与启动](backend/07-组合根与启动.md) | [web/07-组合根与启动](web/07-组合根与启动.md) |
| 持久化与迁移 | [backend/08-持久化与迁移](backend/08-持久化与迁移.md) | [web/08-持久化与迁移](web/08-持久化与迁移.md) |
| 可观测性 | [backend/09-可观测性](backend/09-可观测性.md) | [web/09-可观测性](web/09-可观测性.md) |
| 测试与 CI | [backend/10-测试与CI](backend/10-测试与CI.md) | [web/10-测试与CI](web/10-测试与CI.md) |
| 部署与运行 | [backend/11-部署与运行](backend/11-部署与运行.md) | [web/11-部署与运行](web/11-部署与运行.md) |
| 实施计划 | [backend/12-实施计划](backend/12-实施计划.md) | [web/12-实施计划](web/12-实施计划.md) |
| 风险与验收 | [backend/13-风险与验收](backend/13-风险与验收.md) | [web/13-风险与验收](web/13-风险与验收.md) |

## BC / 模块对齐（后端 ↔ 前端 1:1）

| BC | 后端路径 | 前端 BC | 后端模块职责 | 前端 BC 职责 |
|---|---|---|---|---|
| **agent_runtime** | `modules/agent_runtime/` | `web/src/features/agent_runtime/` | Agent · AgentVersion · 模型绑定 | 列表/详情/版本/对比 UI |
| **session** | `modules/session/` | `web/src/features/session/` | Session · Turn · 流式响应 | 会话页 · Composer · 流式渲染 |
| **skill** | `modules/skill/` | `web/src/features/skill/` | Skill 包 · Skill 调用 | Skill 列表 · Skill 调用状态 |
| **tool** | `modules/tool/` | `web/src/features/tool/` | Tool/MCP 适配器 | Tool 列表 · Tool 调用 |
| **knowledge** | `modules/knowledge/` | `web/src/features/knowledge/` | 知识包 · 摄取 · 检索 | 知识包管理 · 检索 UI |
| **memory** | `modules/memory/` | `web/src/features/memory/` | 短期/长期记忆 · GDPR | 记忆列表 · 召回 UI |
| **governance** | `modules/governance/` | `web/src/features/governance/` | 策略 · 审批 · 审计 | 策略配置 · 审批 · 审计日志 |
| **identity** | `modules/identity/` | `web/src/features/identity/` | 用户 · 租户 · 工作区 · 认证 | 登录 · 用户菜单 · 租户切换 |
| **channel** | `modules/channel/` | `web/src/features/channel/` | 飞书/Teams/Webhook 渠道 | 渠道配置 · 投递日志（前端独有） |
| **observability** | `modules/observability/` | `web/src/features/observability/` | trace/metric/log/cost/quality 后端 | TraceViewer · CostDashboard · QualityDashboard |

## 关键约定

### 1. 单一真理源（DTO 类型契约）

- 后端 `openapi.yaml` 是所有 DTO 的**单一真理源**
- 前端通过 OpenAPI Codegen 从后端生成 TypeScript 类型到 `@qzdap/web-types`
- Mock 与 API 共享同一份类型契约 → Contract Test 保证一致

### 2. SSE Turn 流式协议

- 端点：`POST /v1/sessions/{id}/turns`
- 协议：`text/event-stream`
- Chunk 类型（8 种）：`message` · `tool_call` · `tool_result` · `skill_invocation` · `memory_write` · `knowledge_search` · `usage` · `done` / `error`

### 3. 错误码命名空间

`<bc>.<error>` 命名空间，例如：
- `session.not_found`
- `tool.invoke_failed`
- `governance.policy_violated`
- `auth.invalid_token`

### 4. 鉴权头四件套

| 头 | 说明 |
|---|---|
| `Authorization: Bearer {token}` | 用户 token |
| `X-Tenant-Id: {tenantId}` | 租户 |
| `X-Workspace-Id: {workspaceId}` | 工作区 |
| `X-Trace-Id: {traceId}` | 分布式追踪 |

### 5. 实施节奏（新项目从 0 开始）

- **后端**：10 周（Week 1 monorepo + 模块骨架 → Week 4-5 BC 落地 → Week 8 staging → Week 10 生产 1.0）
- **前端**：4 周交付 + buffer（Week 1 workspace + 守门 → Week 2 BC + Mock → Week 3 联调 + Observability → Week 4 验收）
- 前后端 CI 平行但独立；前后端 Week 1 同步启动；前端 Week 4 灰度上线
- 完整新项目周期：约 10 周达到 1.0 上线

## 8. 与本仓库旧项目的关系

本仓库当前 `backend/` `frontend/` 是**旧项目遗留**（Go + Python + React `@de/*`），与 qizhida-agent-platform **无强绑定**：

| 维度 | 旧项目 | 新项目 |
|---|---|---|
| 后端栈 | Go monolith + Python sidecar | Python FastAPI 模块化单体 |
| 前端包名 | `@de/*` | `@qzdap/*` |
| UI 库 | shadcn/ui + tailwind | antd |
| API 前缀 | `/api/*` 信封 | `/v1/*` 严格状态码 |
| 状态 | 已运行多年 | 设计阶段 |

新项目仅**借鉴业务概念**（Skill / Tool / Knowledge / Memory / Channel 等）；**不沿用任何代码或技术栈**。详见 [REVIEW.md](REVIEW.md)。

## 阅读建议

1. **架构师 / TL**：先读 [backend/01-架构总览](backend/01-架构总览.md) + [web/01-架构总览](web/01-架构总览.md) 建立全景
2. **后端工程师**：从 [backend/04-模块设计](backend/04-模块设计.md) 开始；对照 [web/06-接口规范](web/06-接口规范.md) 看契约
3. **前端工程师**：从 [web/04-模块设计](web/04-模块设计.md) 开始；对照 [backend/06-接口规范](backend/06-接口规范.md) 看契约
4. **DevOps / SRE**：[backend/11-部署与运行](backend/11-部署与运行.md) + [web/11-部署与运行](web/11-部署与运行.md) + [backend/09-可观测性](backend/09-可观测性.md) + [web/09-可观测性](web/09-可观测性.md)
5. **测试工程师**：[backend/10-测试与CI](backend/10-测试与CI.md) + [web/10-测试与CI](web/10-测试与CI.md)
6. **PM / 决策者**：[backend/12-实施计划](backend/12-实施计划.md) + [web/12-实施计划](web/12-实施计划.md) + [backend/13-风险与验收](backend/13-风险与验收.md) + [web/13-风险与验收](web/13-风险与验收.md)

## 修订记录

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0 | 2026-09-19 | 顶层 README + backend/ 子目录 + web/ 子目录（14 篇 × 2） |
| 1.1 | 2026-09-19 | 澄清 qizhida-agent-platform 是**新项目**（非重构旧项目）；新增"与本仓库旧项目的关系"章节；新增 [REVIEW.md](REVIEW.md) |