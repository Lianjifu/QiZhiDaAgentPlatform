# Enterprise-Agent-OS · 方案文档集

> 面向企业构建统一的 AI 智能体基础平台。
> 提供 Agent 创建、运行、编排、知识、技能、工具、模型、记忆、治理与运行监控等核心能力，形成从 Agent 构建 → 任务执行 → 过程管理 → 运行观测 → 安全治理 → 效果评估 的完整闭环。
> 平台以 **Agent Runtime** 为核心，通过统一的 Session / Context / Memory / Tool / Skill / Knowledge / Governance 能力，为企业智能体提供标准化、可复用、可治理的运行基础设施。

---

## 文档索引

| # | 文档 | 主题 |
|---|---|---|
| 01 | [架构总览](01-架构总览.md) | 设计目标、核心概念、部署拓扑、技术选型 |
| 02 | [仓库结构](02-仓库结构.md) | 目录骨架、模块划分、命名规范、依赖关系 |
| 03 | [共享内核](03-共享内核.md) | libs/* 各包职责、核心接口、可复用构件 |
| 04 | [模块设计](04-模块设计.md) | 14 个能力模块的 hexagonal 布局与端口 |
| 05 | [跨模块协作](05-跨模块协作.md) | 事件总线、端口互调、Agent 闭环事件链 |
| 06 | [接口规范](06-接口规范.md) | RESTful 严格状态码、API Key、MCP、Tool 协议 |
| 07 | [组合根与启动](07-组合根与启动.md) | composition / lifespan / DI 容器 |
| 08 | [持久化与迁移](08-持久化与迁移.md) | SQLAlchemy 2.0 / UoW / Alembic / 硬删语义 |
| 09 | [可观测性](09-可观测性.md) | trace / metrics / log / cost / quality |
| 10 | [测试与 CI](10-测试与CI.md) | 测试金字塔 / import-linter / GitHub Actions |
| 11 | [部署与运行](11-部署与运行.md) | Makefile / docker-compose / 环境变量 / 性能目标 |
| 12 | [实施计划](12-实施计划.md) | 10 周分阶段落地与里程碑 |
| 13 | [风险与验收](13-风险与验收.md) | 风险登记 / 验收清单 / 应急回滚 |

---

## 项目定位

Enterprise-Agent-OS 是从 `digital-employee-platform` 抽离出来的 **通用企业 Agent 平台**（PaaS 形态）：

- **多租户**：平台租户（Tenant）→ 工作区（Workspace）两级隔离
- **多 Agent 类型**：Conversational / Task / Workflow / Coarse-grained 等可注册
- **能力可插拔**：核心闭环 4 模块先行；知识、编排、渠道、评测等作为能力包按需启用
- **形态**：单体 FastAPI + 可选 gateway + 可选远程 runtime（沙箱 / tool runtime / embedding runtime）

## 起步闭环

> **核心闭环优先**：Agent Runtime + Skill + Tool + Memory 四模块先打通完整链路；治理与观测横切所有调用。

```
User → Agent Runtime → Tool / Skill / Memory → Response
                ↓
            Governance / Observability
```

## 与 digital-employee-platform 的关系

| 项 | 关系 |
|---|---|
| 仓库 | **独立新仓库** |
| 数据 | 完全隔离，不共享数据库 / Redis / 对象存储 |
| 命名 | 不复用 `collab` `cap` `home` 等业务域命名；按 Agent 能力重新划分 |
| 起步范围 | `digital-employee-platform` 是全量渐进；本项目 4 模块闭环先行 |
| 模板来源 | 文档结构沿用 `docs/python-refactor/`，命名与边界重新设计 |

## 模板溯源

每份文档头部标注 **"基于 docs/python-refactor/ 模板"**。
关键差异点（命名 / 起步范围 / 多租户 / Agent 闭环）在对应章节显式列出。

## 关键术语

| 术语 | 定义 |
|---|---|
| **Tenant** | 平台租户；资源、计费、配额的最上层隔离单位 |
| **Workspace** | 租户内的工作区；事件总线、治理、知识库的逻辑边界 |
| **Agent** | 注册到平台的智能体定义；含模板、版本、配置 |
| **AgentVersion** | Agent 的不可变版本；可被发布、调用、编排 |
| **Session** | Agent 执行上下文；承载 turn / message / tool_call |
| **Turn** | 单轮用户输入 + Agent 完整响应（含工具调用与流式 chunk） |
| **Tool** | 可被 Agent 调用的能力；通过 MCP / OpenAPI / 自定义协议暴露 |
| **Skill** | 带沙箱隔离的可执行能力包；通常含代码、产物、依赖 |
| **Memory** | 跨 session / 跨 turn 持久化的知识；可被检索与撤销 |
| **Governance** | 横切的策略、审批、配额、审计订阅 |
| **Channel** | 消息渠道适配（飞书 / 钉钉 / 企微 / Web） |

## 文档阅读顺序建议

1. 先读 `01-架构总览` 建立心智模型
2. 再读 `02-仓库结构` + `03-共享内核` 了解代码骨架
3. 接着 `04-模块设计` + `05-跨模块协作` 看模块能力
4. 然后 `06-接口规范` + `07-组合根与启动` 理解接口与启动
5. 最后 `08~11` 看运行期细节；`12~13` 看落地与验收
