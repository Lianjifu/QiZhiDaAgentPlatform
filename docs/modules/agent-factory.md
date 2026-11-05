# agent_factory — 智能体工厂

> 能力域之一。负责智能体的**模板与版本化**——配置轴上的「管理员建了什么、发布了哪一版」。

## 职责

- 智能体模板（tenant-scoped 命名模板）的增删改查
- 智能体版本的创建、发布、退役与版本说明
- 发布记录（release）与评测授权
- 为 agent_runtime 提供「某版本绑定了哪些模型 / 工具 / 技能 / 知识包」

## 三个聚合根

| 聚合 | 语义 | 状态机 |
|---|---|---|
| `AgentTemplate` | 命名模板，携带默认 prompt 与模型 | `active ↔ archived` |
| `AgentVersion` | 类型化的版本快照（prompt / model / 允许的工具 / 技能 / 知识包 / 路由） | `draft → published → released → retired`，**非 draft 即不可变** |
| `Release` | 一次通过门禁的发布记录，携带授权它的评测运行与分数 | — |

模板的默认值被新版本继承；版本行**快照**下 prompt 与 model，因此后来改模板**不会**改动历史版本。

## 源码位置

```
backend/modules/agent_factory/src/qzdap/modules/agent_factory/
├── domain/          entities.py（三个聚合）· value_objects.py（长度上限 / 状态枚举）· events.py · errors.py
├── application/
│   ├── services.py   AgentFactoryService
│   ├── ports.py      EvaluationQueryPort（反查评测）
│   └── use_cases/    13 个用例（见下）
└── adapter/
    ├── http/         router.py · dto.py · mappers.py
    ├── persistence/  models.py · mappers.py · repositories.py
    └── events/       MessagingAgentFactoryEventPublisher
```

## HTTP 端点

前缀 `/v1/agents`。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/v1/agents` | 模板列表 |
| POST | `/v1/agents` | 建模板 |
| GET | `/v1/agents/{aid}` | 模板详情 |
| PATCH | `/v1/agents/{aid}` | 更新模板 |
| GET | `/v1/agents/options/models` | 可选模型清单 |
| GET | `/v1/agents/options/routes` | 可选路由清单 |
| GET | `/v1/agents/{aid}/versions` | 版本列表 |
| POST | `/v1/agents/{aid}/versions` | 建版本 |
| GET | `/v1/agents/{aid}/versions/{vid}` | 版本详情 |
| PATCH | `/v1/agents/{aid}/versions/{vid}/notes` | 改版本说明 |
| POST | `/v1/agents/{aid}/versions/{vid}/publish` | 发布 |
| POST | `/v1/agents/{aid}/versions/{vid}/release` | 正式发布 |
| POST | `/v1/agents/{aid}/versions/{vid}/retire` | 退役 |
| GET | `/v1/agents/{aid}/versions/{vid}/releases` | 发布记录 |

## 数据表

| 表 | 职责 | 关键列 |
|---|---|---|
| `agent_templates` | 模板 | id / tenant_id / workspace_id / name / default_model_id / default_system_prompt / status / metadata |
| `agent_versions` | 版本 | id / template_id / version / system_prompt / model_id / allowed_tools / allowed_skills / knowledge_package_ids / route_id / status |
| `releases` | 发布记录 | id / version_id / eval_run_id / score / status / released_at |

## 关键类

| 层 | 类 | 职责 |
|---|---|---|
| domain | `AgentTemplate` `AgentVersion` `Release` | 三个聚合根，frozen dataclass |
| application | `AgentFactoryService` | 模块门面 |
| application | `CreateAgentTemplateUseCase` `UpdateAgentTemplateUseCase` `ListAgentTemplatesUseCase` `GetAgentTemplateUseCase` | 模板用例 |
| application | `CreateAgentVersionUseCase` `PublishAgentVersionUseCase` `ReleaseAgentVersionUseCase` `RetireAgentVersionUseCase` `UpdateAgentVersionNotesUseCase` `ListAgentVersionsUseCase` `GetAgentVersionUseCase` | 版本用例 |
| application | `GetReleaseUseCase` `ListReleasesUseCase` | 发布用例 |
| adapter | `MessagingAgentFactoryEventPublisher` | 发 `AgentTemplateCreated` / `AgentVersionPublished` / `AgentReleased` |

## 实现要点

- **发布事件驱动运行时生效**：`AgentVersionPublished` / `AgentReleased` 经消息总线投递给 agent_runtime 的 `agent_factory_release_subscriber`，由后者把发布结果落到 `admin_agents`
- **评测授权发布**：版本发布需要关联一次评测运行及其分数，由 `EvaluationQueryPort` 从 evaluation 模块反查版本表
- **不可变性保护**：`AgentVersion` 非 draft 状态后字段不可改，只能创建新版本
- **字段有上限**：`value_objects.py` 定义了名称 / 描述 / prompt / 工具数 / 技能数 / 知识包数的长度上限
- **策略白名单**：版本上的路由策略取值必须落在 `{fallback, quality-first, cost-first, latency-first, round-robin, weighted}` 内

## 已知边界

- ⚠️ **与 agent_runtime 的 `admin_agents` 是两套并行的目录**：`agent_factory` 写 `agent_templates` / `agent_versions`，`agent_runtime` 写 `admin_agents`。生效靠 release subscriber 把 `admin_agents.id == template_id` 对齐——**两表 ID 不同源**，是脆弱耦合
- ⚠️ `EvaluationQueryPort` 在 container 里没有显式 provider，由 lifespan 闭包提供——装配关系不显式
- ⚠️ 模板与版本**只落库，不发外部副作用**（邮件 / 通知 / webhook 之类）
