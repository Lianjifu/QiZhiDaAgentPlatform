# Enterprise-Agent-OS · Web 子项目方案文档集

> Enterprise-Agent-OS 的**配套前端子项目**文档集。
> 后端：`qizhida-agent-platform/`（FastAPI · uv workspace · 多租户 Agent 平台）
> 前端（本方案）：`qizhida-agent-platform/web/`（pnpm workspace · FSD · DDD · Hexagonal）

> **本方案架构内核**：**pnpm Workspace Monorepo + FSD（Feature-Sliced Design 6 层）+ DDD 领域建模（对齐后端 8 BC）+ Hexagonal Ports & Adapters**
>
> 四维架构各司其职：
> - **pnpm Workspace**：物理隔离（`packages/*` shared + `web/src/*` 业务）；版本/依赖管理
> - **FSD**：垂直切片 + 强制单向依赖（app → pages → widgets → features → entities → shared）
> - **DDD**：8 个 Bounded Context（**与后端 1:1 对齐**：agent / session / skill / tool / knowledge / memory / governance / identity）
> - **Hexagonal**：每个 BC 内 `model`（核心+Port）+ `lib`（Use Case）+ `api`（HttpApi/Mock/LocalStorage 三类适配器）

> **基于 docs/web-refactor/00-README.md 模板**。
> 与原模板差异：
> - 业务命名不沿用 `collab`/`home`/`cap`；按 **Agent 能力**重新划分（agent_runtime / session / tool / skill / knowledge / memory / channel / governance）
> - 与后端 8 模块 1:1 对齐（前端 BC 边界 = 后端模块边界）
> - DTO 来自后端 OpenAPI / TypeScript Codegen；mock 来自后端真实 handler（共享 fixtures）
> - Channel（IM 渠道）作为前端独立 BC（前端独有的运营配置）

---

## 文档索引（13 篇 · 00-12）

| # | 文档 | 主题 |
|---|---|---|
| 00 | [00-README.md](00-README.md) | 本文档（四维架构总览 + 与后端对齐） |
| 01 | [01-架构总览.md](01-架构总览.md) | FSD 6 层 × DDD 8 BC（对齐后端）× Hex Port/Adapter 三视角融合图 |
| 02 | [02-仓库结构.md](02-仓库结构.md) | `packages/*`（shared）+ `web/src/{app,pages,widgets,features,entities}/` |
| 03 | [03-共享内核.md](03-共享内核.md) | FSD shared 层：`@qzdap/web-ui` `@qzdap/web-api` `@qzdap/web-mock` `@qzdap/web-types` `@qzdap/web-hooks` `@qzdap/web-utils` |
| 04 | [04-模块设计.md](04-模块设计.md) | 8 BC（对齐后端 modules/）× FSD 切片 × Hex 六边形 |
| 05 | [05-跨模块协作.md](05-跨模块协作.md) | Domain Event · ACL · EventBus · 跨 BC 订阅与八模块闭环可视化 |
| 06 | [06-接口规范.md](06-接口规范.md) | RESTful + SSE + MCP Tool 协议 + DTO 类型契约 |
| 07 | [07-组合根与启动.md](07-组合根与启动.md) | composition · DepsProvider · EventBus 装配 · 路由守卫 |
| 08 | [08-持久化与迁移.md](08-持久化与迁移.md) | auth/UI state 持久化 · 离线 LocalStorage Adapter · 数据迁移策略 |
| 09 | [09-可观测性.md](09-可观测性.md) | 前端 trace · metrics · log · cost · 上报 |
| 10 | [10-测试与CI.md](10-测试与CI.md) | FSD 三层测试金字塔 + import-linter + GitHub Actions |
| 11 | [11-部署与运行.md](11-部署与运行.md) | Vite · docker-compose · 环境变量 · 性能目标 |
| 12 | [12-实施计划.md](12-实施计划.md) | 与后端 10 周节奏对齐 · 前端 4 周 + buffer |
| 13 | [13-风险与验收.md](13-风险与验收.md) | 5 类风险（FSD/DDD/Hex/性能/安全）+ 12 节验收清单 |

---

## 项目定位

`qizhida-agent-platform/web/` 是 Enterprise-Agent-OS 平台的**官方 Web Console**：

- **多租户**：前端感知 Tenant / Workspace 两级；路由 + state + UI 三层体现
- **多 Agent 类型**：Conversational / Task / Workflow / Coarse-grained 在前端统一抽象
- **能力可插拔**：前端通过"能力开关" + 路由懒加载 + dynamic import 体现后端可插拔
- **过程可观测**：前端 trace / metric / log 上报到后端 observability 模块
- **治理前置**：approval / quota / policy 在前端拦截层落地
- **效果可评估**：评测 dashboard 作为前端独立页面

## 与后端的关系

| 项 | 关系 |
|---|---|---|
| 仓库 | 与后端 **同仓库独立目录**（`qizhida-agent-platform/web/`）；uv workspace 不管前端 |
| 数据 | 全部走后端 API；前端无数据库；UI 状态本地 |
| 命名 | **与后端 modules/ 1:1 对齐**：前端 BC 名 = 后端模块名 |
| DTO 来源 | 后端 OpenAPI → TypeScript Codegen → `@qzdap/web-types` |
| Mock 来源 | 后端真实 handler 镜像（避免前后端 mock 不一致） |
| 部署 | 独立 Node 构建产物；Nginx 静态托管 / Vercel / K8s 静态 Pod |
| 起步范围 | **与后端同步**：核心闭环 4 模块先行（agent_runtime / session / skill / tool） |

## 与 docs/web-refactor/ 的关系

| 项 | 关系 |
|---|---|
| 模板来源 | docs/web-refactor/ 是 `digital-employee-platform` 老项目的 web 重构方案 |
| 复用 | 四维架构（pnpm + FSD + DDD + Hex）+ 测试与 CI + 风险验收**全部沿用** |
| 差异 | 业务命名不沿用 `collab/home/cap`；按 Agent 能力重命名；与后端 modules/ 1:1 对齐 |
| 配套 | 文档编号 00-12（与后端 qizhida-agent-platform 文档集 13 篇对齐） |

## 后端 8 个模块（前端 BC 边界来源）

| 后端 modules/ | 前端 features/ | 业务语言 | 类型 |
|---|---|---|---|
| **`agent_runtime`** | `features/agent_runtime/` | Agent / AgentVersion / Plan / Response | Core |
| **`session`** | `features/session/` | Session / Turn / Message / Stream | Core |
| **`tool`** | `features/tool/` | Tool / ToolCall / ToolProtocol | Core |
| **`skill`** | `features/skill/` | SkillPackage / SkillInvocation / RunToken | Core |
| **`knowledge`** | `features/knowledge/` | KnowledgePackage / Asset / Retriever | Core |
| **`memory`** | `features/memory/` | MemoryEntry / Recall | Supporting |
| **`governance`** | `features/governance/` | PolicyRule / Approval / AuditLog | Supporting |
| **`identity`** | `features/identity/` | Tenant / Workspace / User / Role | Generic |
| **`channel`**（前端独有） | `features/channel/` | Channel / ChannelDelivery（IM 渠道运营配置） | Supporting |
| **`observability`**（横切） | `web/src/widgets/observability/` + `web/src/app/observability/` | Trace / Metric / Log viewer | Supporting |
| **`home`**（跨 BC 视图） | `widgets/home/` + `pages/home/` | Composite UI | 跨 BC |

> **关键**：前端 BC 名 = 后端模块名（同字面）；前端观察后端模块边界，避免概念错位。

## 起步闭环

> **核心闭环优先**：agent_runtime + session + skill + tool 四模块先打通完整链路；governance 与 observability 横切所有调用。

```
User → Session → Agent Runtime → Skill / Tool / Memory / Knowledge → Response
   │       │             │
   │       │             └── trace_id 贯穿全链路
   │       └── Turn 流式 SSE
   └── identity（鉴权 / workspace 选择）
              │
              └── 治理横切（policy / approval / quota）
```

## 文档阅读顺序建议

1. 先读 `01-架构总览` 建立心智模型（与后端 `01-架构总览` 平行阅读）
2. 再读 `02-仓库结构` + `03-共享内核` 了解代码骨架
3. 接着 `04-模块设计` + `05-跨模块协作` 看模块能力（与后端 `04-模块设计` 平行阅读）
4. 然后 `06-接口规范` + `07-组合根与启动` 理解接口与启动
5. 最后 `08~11` 看运行期细节；`12~13` 看落地与验收

## 关键术语

| 术语 | 定义 |
|---|---|
| **Tenant** | 平台租户；前端感知并隔离路由与 state |
| **Workspace** | 租户内工作区；前端作为独立 store 维度 |
| **Agent** | 注册到平台的智能体；前端展示为列表 + 详情 + 版本对比 |
| **AgentVersion** | Agent 不可变版本；前端展示 + 调用绑定 |
| **Session** | Agent 执行上下文；前端 SSE 流式 |
| **Turn** | 单轮输入 + 完整响应；前端拆 stream chunk + tool_call 渲染 |
| **Tool** | 可被 Agent 调用的能力；前端展示调用过程与结果 |
| **Skill** | 沙箱内可执行能力包；前端展示包元数据与运行产物 |
| **Memory** | 跨 session 长期记忆；前端列表 + 召回 |
| **Governance** | 横切的策略 / 审批 / 配额 / 审计 |
| **Channel** | IM 渠道（飞书 / 钉钉 / 企微 / Web）；前端运营配置 |

## 一句话总结

> 现状：需要从 0 构建 qizhida-agent-platform/web。
>
> 方案：**pnpm Workspace + FSD 6 层 + DDD 8 BC（对齐后端）+ Hex Port/Adapter 四维融合**：
>
> - **物理**：`packages/*`（shared，6 个）+ `web/src/{app,pages,widgets,features,entities}`（FSD 切片）
> - **FSD 单向依赖**：`app → pages → widgets → features → entities → shared`；ESLint 强制
> - **DDD 战略**：8 BC（agent_runtime / session / skill / tool / knowledge / memory / governance / identity）+ channel 前端独有 + observability 横切
> - **DDD 战术**：BC 内 `model/`（Entity/VO/Repository Port/Domain Service/ACL/Event）+ `lib/`（Use Case）
> - **Hex 适配器**：BC 内 `api/` 下放 HttpApiAdapter（生产）/ MockApiAdapter（dev）/ LocalStorageAdapter（可选）三类
> - **mock**：`@qzdap/web-mock` 与 `@qzdap/web-api` 平行；按租户切换；生产 tree-shake 剔除
>
> 路径：**与后端同步 4 周增量 + buffer**：W1 物理 → W2 model 骨架 → W3 features 4 层 → W4 收尾 + CI 守门。