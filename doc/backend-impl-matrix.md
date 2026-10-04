# Backend 端点实现矩阵

> 调研日期: 2026-09-25
> 调研范围: 15 个 backend 模块 × web 端 mock 调用全集 × pathMap.ts 当前 89 真映射 + 33 unmatched markers
> 目的: 为后续 backend 端点实现工作做规划

---

## 0. 摘要

- **Backend 现状**: 15 模块共 **111 个 endpoint**;最多的是 agent_factory(12)/knowledge(11)/model(11)/skill(10)。
- **Web 调用全集**: ~178 个 mock path handler;pathMap 已接 89 真映射 + 33 unmatched + ~60 完全无匹配(passthrough)。
- **本期可承接范围** (用户选定): **仅补 backend 已有模块的端点** —— 约 50 个 endpoint。
- **本期不做** (后端无模块承接): zero-trust、home aggregator、workspace control、skill governance 子域、knowledge graph/sources/eval 子域、model governance 子域、channel-control 子域、audit center 等 — 见 §4 排除清单。
- **优先级 1 (本期第一批)**: identity.users/me、identity.tenants/current、platform.tenants/me、agent_factory PATCH/POST versions、orchestration sessions POST 修协议错配、skill.uninstall、knowledge docs 顶层 list、knowledge assets GET。
- **3 个协议错配**: `/api/sessions` POST(backend 要 aid)、`/api/tenant/profile` PATCH(backend 端点不存在)、`/api/auth/me`(backend 端点不存在)。

---

## 1. Backend 现状(按模块)

> 文件路径模板:`backend/modules/{module}/src/qzdap/modules/{module}/adapter/http/router.py`
> 扫描方式:`@router.<verb>(...)` 装饰器全部展开

### 1.1 端点总数

| 模块 | endpoint 数 |
|---|---|
| agent_factory | 12 |
| agent_runtime | 4 |
| channel | 6 |
| evaluation | 6 |
| governance | 9 |
| identity | 8 |
| knowledge | 11 |
| memory | 5 |
| model | 11 |
| observability_module | 3 |
| orchestration | 7 |
| platform | 6 |
| self_evolution | 6 |
| skill | 10 |
| tool | 7 |
| **合计** | **111** |

### 1.2 各模块路由详情(精简)

**agent_factory** (prefix `/v1/agents`, 12 ep): POST/GET `""`; GET/PATCH `/{aid}`; POST/GET `/{aid}/versions`; GET `/{aid}/versions/{vid}`; PATCH `/{aid}/versions/{vid}/notes`; POST `/{aid}/versions/{vid}/{publish,release,retire}`; GET `/{aid}/versions/{vid}/releases`。

**agent_runtime** (prefix `/v1`, 4 ep): POST `/agents/{aid}/sessions`; GET `/sessions/{sid}`; POST `/sessions/{sid}/{close,turn/stream}`。

**channel** (prefix `/v1`, 6 ep): POST/GET `/channels`; GET/PATCH `/channels/{cid}`; POST `/channels/{cid}/{webhook,send}`。

**evaluation** (prefix `/v1/eval`, 6 ep): GET `/datasets`; GET `/datasets/{did}`; GET `/datasets/{did}/cases`; POST/GET `/runs`; GET `/runs/{rid}`。

**governance** (prefix-less, 9 ep): POST/GET `/v1/policies`; GET/PATCH/DELETE `/v1/policies/{rid}`; GET `/v1/approvals`; GET `/v1/approvals/{aid}`; POST `/v1/approvals/{aid}/{approve,deny}`。

**identity** (prefix `/v1/identity`, 8 ep): POST `/tenants`; POST/GET `/workspaces`; POST `/users`; GET `/users/{uid}`; POST `/users/{uid}/api-keys`; POST `/users/{uid}/api-keys/{kid}/revoke`; POST `/login`。

**knowledge** (prefix `/v1/knowledge`, 11 ep): POST/GET `/packages`; GET/DELETE `/packages/{pid}`; GET/POST `/packages/{pid}/assets`; POST `/packages/{pid}/assets/{text,upload}`; POST `/packages/{pid}/search`; DELETE `/assets/{aid}`; POST `/search`。

**memory** (prefix `/v1/memories`, 5 ep): POST `""`; POST `/recall`; GET/DELETE `/{mid}`; GET `""`。

**model** (prefix `/v1`, 11 ep): POST/GET `/model-credentials`; POST `/model-credentials/{cid}/rotate`; POST/GET `/models`; GET/PATCH/DELETE `/models/{mid}`; POST `/models/{mid}/invoke`; POST/GET `/routing-policies`。

**observability_module** (prefix `/v1/observability`, 3 ep): GET `/runs`; GET `/costs`; GET `/quality/{tid}/{vid}`。

**orchestration** (prefix `/v1/orchestration`, 7 ep): POST/GET `/plans`; GET `/plans/{pid}`; POST `/plans/{pid}/runs` (202); GET `/runs/{rid}`; GET `/runs`; POST `/runs/{rid}/cancel`。

**platform** (prefix `/v1/platform`, 6 ep): GET `/plans`; GET/PUT `/subscriptions/me`; GET `/settings`; GET/PUT `/settings/{key}`。

**self_evolution** (prefix-less, 6 ep): POST/GET `/v1/evolve/candidates`; GET `/v1/evolve/candidates/{cid}`; POST `/v1/evolve/candidates/{cid}/{approve,reject,apply}`。

**skill** (prefix `/v1/skills`, 10 ep): POST/GET `""`; GET/PATCH/DELETE `/{sid}`; POST `/{sid}/{install,invoke}`; GET `/invocations/{iid}`; GET `/invocations`; POST `/invocations/{iid}/cancel`。

**tool** (prefix `/v1/tools`, 7 ep): POST/GET `""`; GET/PATCH/DELETE `/{tid}`; POST `/{name}/invoke`; POST `/batch_invoke`。

### 1.3 pathMap 漏接清单(backend 有,但 pathMap 未映射)

按模块列出需补的 pathMap 规则:

**identity** (5 项)
- `GET /v1/identity/users/me` (后端不存在,需先补 backend)
- `GET /v1/identity/tenants/current` (后端不存在,需先补 backend)
- `GET /v1/identity/users/{uid}/api-keys` (后端仅有 POST issue / POST revoke,无 list)
- `DELETE /api/api-keys` (实际是 POST revoke,pathMap 需对齐)
- `PATCH /v1/identity/workspaces/{wid}` (backend 不存在,需评估)

**platform** (5 项)
- `GET /v1/platform/plans` (backend 已有,pathMap 漏)
- `GET/PUT /v1/platform/settings` (backend 已有,pathMap 漏)
- `GET/PUT /v1/platform/settings/{key}` (backend 已有,pathMap 漏)
- `GET /v1/platform/tenants/me` (pathMap 已指向,但 backend 不存在,需补)

**governance** (2 项)
- `DELETE /v1/policies/{rid}` (backend 已有,pathMap 漏)
- `GET /v1/approvals/{aid}` (backend 已有,pathMap 漏)

**agent_factory** (7 项)
- `PATCH /v1/agents/{aid}` (backend 已有,pathMap 漏)
- `POST /v1/agents/{aid}/versions` (backend 已有,pathMap 漏)
- `GET /v1/agents/{aid}/versions/{vid}` (backend 已有,pathMap 漏)
- `PATCH /v1/agents/{aid}/versions/{vid}/notes` (backend 已有,pathMap 漏)
- `POST /v1/agents/{aid}/versions/{vid}/{publish,release,retire}` (backend 已有,pathMap 漏)
- `GET /v1/agents/{aid}/versions/{vid}/releases` (backend 已有,pathMap 漏)

**evaluation** (3 项)
- `GET /v1/eval/datasets` (backend 已有,pathMap 漏)
- `GET /v1/eval/datasets/{did}` (backend 已有,pathMap 漏)
- `GET /v1/eval/datasets/{did}/cases` (backend 已有,pathMap 漏)

**model** (3 项)
- `DELETE /v1/model-credentials/{cid}` (backend 仅有 rotate,需评估是否补)
- `PATCH/DELETE /v1/routing-policies/{rid}` (backend 不存在)
- `POST /v1/routing-policies/{rid}/draft/validate/publish` (backend 不存在)

**skill** (1 项)
- `POST /v1/skills/{sid}/uninstall` (对称 install,backend 缺)

**knowledge** (1 项)
- `GET /v1/knowledge/packages/{pid}/assets/{aid}` (已有 DELETE,缺 GET)

---

## 2. Web 端调用清单(按 domain)

> "Backend 现状": 已接 = pathMap+backend 均到位 / 部分接 = 路径通但端点缺 / 缺失 = 完全无 backend。

### 2.1 Zero-Trust / 访问治理(governance)

| Web path | Method | Backend 现状 |
|---|---|---|
| `/api/release-approvals` | GET/POST | 已接 → `/v1/approvals` |
| `/api/release-approvals/:id` | GET | 已接 |
| `/api/release-approvals/:id/approve` | POST | 已接 |
| `/api/release-approvals/:id/reject` | POST | 已接(verb 改 deny) |
| `/api/zero-trust/overview` | GET | 缺失(governance 无 ZT 子域) |
| `/api/zero-trust/policies` | GET/POST | 缺失 |
| `/api/zero-trust/policies/:id` | PATCH | 缺失 |
| `/api/zero-trust/evaluate` | POST | 缺失(policy engine) |
| `/api/zero-trust/events` | GET | 缺失 |
| `/api/zero-trust/authorizations` | GET/POST | 缺失 |
| `/api/access/{,governance,grants,reviews/complete}` | various | 缺失 |

### 2.2 Control-Plane(identity + model + channel)

**identity**:
| Web path | Method | Backend 现状 |
|---|---|---|
| `/api/auth/login` | POST | 已接 |
| `/api/auth/me` | GET | **backend 缺**(`/users/me` 不存在) |
| `/api/workspaces` | GET | 已接 |
| `/api/tenant/profile` | GET | **backend 缺**(`/tenants/current` 不存在) |
| `/api/tenant/profile` | PATCH | **已接但端点不存在**(`/v1/platform/tenants/me`) |
| `/api/api-keys` | GET | **backend 缺 list** |
| `/api/api-keys/:id` | DELETE | 缺失 |

**model**:
| Web path | Method | Backend 现状 |
|---|---|---|
| `/api/model-providers` | GET/POST | 已接 → `/v1/model-credentials` |
| `/api/model-providers/:id` | PATCH | 已接 |
| `/api/model-providers/:id` | DELETE | backend 缺(仅 rotate) |
| `/api/model-providers/:id/rotate` | POST | 已接 |
| `/api/model-providers/{discover-models,test-connection,:id/{impact,draft,validate,publish}}` | various | 缺失(整子域) |
| `/api/model-routing/policies` | GET/POST | 已接 |
| `/api/model-routing/policies/:id` | PATCH/DELETE | backend 缺 |
| `/api/model-routing/{failover-tests,policy/:id/{draft,validate,publish}}` | various | 缺失 |
| `/api/model-{governance/overview,audit,failover-test}` | various | 缺失 |
| `/api/{routes*,route-flow,export-routes,model-compare,providers*,provider-health,prompt-templates}` | various | 缺失 |

**channel**:
| Web path | Method | Backend 现状 |
|---|---|---|
| `/api/channels` | GET | 已接 |
| `/api/channels/:id` | GET | 已接 |
| `/api/channels/:id/{test,toggle,config,send}` | various | 已接(verb 修正) |
| `/api/channel-control/{overview,deployments*,policies,deliveries,dead-letters,inbound,health,audit}` | various | 缺失(整 channel-control 子域) |
| `/api/channel-{blacklist,config,health,languages,routes,templates}` | various | 缺失 |

**billing**:
| Web path | Method | Backend 现状 |
|---|---|---|
| `/api/billing` | GET | 已接 → `/v1/platform/subscriptions/me` |
| `/api/backups{,}` | GET/POST | 缺失 |
| `/api/webhooks-config` | GET | 缺失 |

### 2.3 Home / Workspace Control(新模块 — 本期不做)

| Web path | Method | Backend 现状 |
|---|---|---|
| `/api/home/{kpis,events,extra,team,alerts}` | GET | 缺失(home aggregator) |
| `/api/operations/overview` | GET | 缺失 |
| `/api/workspace-switch-history` | GET | 缺失 |
| `/api/workspaces/:id/{partners,tools,members,report,runtime,audit,policy}` | various | 缺失(workspace_control 模块) |

### 2.4 Conversation / Actions / Digital Employees / Tasks

| Web path | Method | Backend 现状 |
|---|---|---|
| `/api/conversations/:id` | GET | 缺失(backend 用 session 概念) |
| `/api/conversations/:id/tasks` | POST | 缺失 |
| `/api/conversations/:id/turn/stream` | POST | 已接(资源名改 sid) |
| `/api/actions/:id/{approve,execute,reject}` | POST | 缺失 |
| `/api/sessions` | GET | 已接 |
| `/api/sessions` | POST | **协议错配**(backend 要 aid) |
| `/api/agent-profiles{,/overview}` | GET/POST | 缺失(agent_factory 仅管 template) |
| `/api/agent-profiles/:id/{evidence,lifecycle,publish,publish-preflight,skills,capabilities,install,uninstall,conversations}` | various | 缺失 |
| `/api/agent-templates{,/:id/adopt}` | GET/POST | 缺失 |
| `/api/agent-capability-catalog` | GET | 缺失 |
| `/api/agent-template-adoptions` | GET | 缺失 |
| `/api/tasks{,/:id}` | GET/POST/PATCH | 缺失(整子域) |

### 2.5 Memory

| Web path | Method | Backend 现状 |
|---|---|---|
| `/api/memory/records` | GET/POST | 已接 |
| `/api/memory/records/:id` | GET/DELETE | 已接 |
| `/api/memory/recall` | POST | 已接 |
| `/api/memory/{audit,policy,candidates,refinement/run,overview}` | various | 缺失(整 governance 子域) |
| `/api/memory/records/:id/{expire,candidate}` | POST | 缺失 |

### 2.6 Knowledge

| Web path | Method | Backend 现状 |
|---|---|---|
| `/api/knowledge/packages` | GET/POST | 已接 |
| `/api/knowledge/packages/:id` | GET | 已接 |
| `/api/knowledge/packages/:id/delete` | DELETE | 已接(verb 改 delete) |
| `/api/knowledge/retrieve` | POST | 已接(改 `/search`) |
| `/api/knowledge/docs` | GET/POST | **backend 缺顶层 docs**(资源是 assets) |
| `/api/knowledge/doc/:id` | GET/DELETE | 已接(改 `/assets/:id`) |
| `/api/knowledge/packages/:id/assets/:aid` | GET | **backend 缺 GET**(有 DELETE) |
| `/api/knowledge/{docs/review,docs/delete,reindex,search-history,citation-trace,eval}` | various | 缺失 |
| `/api/knowledge/chunks/{top,rescore}` | GET/POST | 缺失 |
| `/api/knowledge/{sources*,governance*,audit,evaluations*,bindings*,processing-jobs,retrieval-profiles}` | various | 缺失(整子域) |
| `/api/knowledge/graph/{entities,relations}` | GET | 缺失(整图谱子域) |

### 2.7 Workflow / Orchestration / Agents / Evaluation

| Web path | Method | Backend 现状 |
|---|---|---|
| `/api/workflows` | GET/POST | 已接 → `/v1/orchestration/plans` |
| `/api/workflows/:id` | GET | 已接 |
| `/api/workflows/:id/run` | POST | 已接 |
| `/api/workflows/:id/runs` | GET | 已接(全局 + ?plan_id) |
| `/api/workflows/:id/runs/:runId` | GET | 已接 |
| `/api/workflows/:id/runs/:runId/cancel` | POST | 已接 |
| `/api/workflows/:id/{versions,trend,meta,audit,draft,validate,publish}` | various | 缺失 |
| `/api/workflows/{generate,generations,orchestration-sessions}` | POST/GET | 缺失(AI 生成子域) |
| `/api/workflow-{templates,runs,kpi,skills}` | various | 缺失 |
| `/api/evaluations` | GET/POST | 已接 → `/v1/eval/runs` |
| `/api/evaluations/:id` | GET | 已接 |
| `/api/evaluations/:id/{run,stop,retry,report}` | various | 缺失 |
| `/api/evaluations/datasets{,/:id,/:id/cases}` | GET | **pathMap 漏接,backend 已有** |
| `/api/agents` | GET/POST | 已接 → `/v1/agents` |
| `/api/agents/:id` | GET | 已接 |
| `/api/agents/:id` | PATCH | **pathMap 漏接,backend 已有** |
| `/api/agents/:id/versions` | GET | 已接 |
| `/api/agents/:id/versions` | POST | **pathMap 漏接,backend 已有** |
| `/api/agents/:id/versions/:vid` | GET | **pathMap 漏接,backend 已有** |
| `/api/agents/:id/versions/:vid/{notes,publish,release,retire}` | various | **pathMap 漏接,backend 已有** |
| `/api/agents/:id/versions/:vid/releases` | GET | **pathMap 漏接,backend 已有** |
| `/api/agents/{alerts,calls/live,rank,import,imports}` | various | 缺失(整子域) |

### 2.8 Skills / Tools / MCP

| Web path | Method | Backend 现状 |
|---|---|---|
| `/api/skills` | GET/POST | 已接 |
| `/api/skills/:id` | GET/PATCH/DELETE | 已接 |
| `/api/skills/:id/install` | POST | 已接 |
| `/api/skills/:id/invoke` | POST | 已接 |
| `/api/skills/:id/uninstall` | POST | **backend 缺** |
| `/api/skills/:id/{trace,versions,permissions,impact}` | GET | 缺失 |
| `/api/skills/:id/permissions` | PATCH | 缺失 |
| `/api/skills/{audit,catalog*,perms,import*,packs,dependency-matrix,upgrade-plan}` | various | 缺失 |
| `/api/skills/governance/{overview,health,incidents,events,trends,batch}` | GET/POST | 缺失(整 governance 子域) |
| `/api/skills/invocations{,/:invId{,/cancel}}` | GET/POST | 已接 |
| `/api/skill-{integrations,artifacts}` | GET | 缺失 |
| `/api/mcp-connections` | POST | 缺失(MCP 集成) |
| `/api/platform-tools/registry` | GET | 缺失 |
| `/api/tools` | GET/POST | 已接 → `/v1/tools` |
| `/api/tools/:id` | GET/PATCH/DELETE | 已接 |
| `/api/tools/:id/invoke` | POST | 已接 |

### 2.9 Observability / Self-Evolution / Audit

| Web path | Method | Backend 现状 |
|---|---|---|
| `/api/observability/runs` | GET | 已接 |
| `/api/observability/costs` | GET | 已接 |
| `/api/observability/quality/:tid/:vid` | GET | 已接 |
| `/api/observability/quality` (workspace 列表) | GET | **backend 缺**(需扩展) |
| `/api/audit-{center,center/export,stream}` | GET/POST | 缺失(整子域) |
| `/api/control-plane-audit`,`/api/audits` | GET | 缺失 |
| `/api/notification-channels{,/:id}` | GET/PATCH | 缺失 |
| `/api/evolve/candidates{,/:id{,/{approve,reject,apply}}}` | various | 已接 |
| `/api/evolve/dream/run` | POST | 缺失 |
| `/api/slash-commands`,`/api/message-stream`,`/api/mock/reset` | various | 缺失(mock-only) |

---

## 3. 优先级矩阵(backend 已有模块可承接的端点)

> user value: H/M/L
> 工作量: S/M/L (S = 单端点无依赖, M = 需扩展 service/repo, L = 需新 model)
> 优先级: 1-5 (1 = 优先做)

### 3.1 identity 模块补缺

| 端点 | user value | 工作量 | 依赖 | 优先级 |
|---|---|---|---|---|
| `GET /v1/identity/users/me`(补 backend) | H | S | 复用 users repo | **1** |
| `GET /v1/identity/tenants/current`(补 backend) | H | S | tenant repo | **1** |
| `GET /v1/identity/users/{uid}/api-keys`(补 list) | M | S | 已有 issue/revoke | 2 |
| 修 pathMap `/api/api-keys` DELETE → POST revoke | M | S | 仅改 pathMap | 3 |

### 3.2 platform 模块补缺

| 端点 | user value | 工作量 | 依赖 | 优先级 |
|---|---|---|---|---|
| `GET /v1/platform/tenants/me`(pathMap 已指;backend 缺) | H | S | tenant_settings 已有 | **1** |
| `GET /v1/platform/settings` + `/{key}`(pathMap 漏接) | M | S | 已有 | 2 |
| `PUT /v1/platform/settings/{key}` | M | S | 已有 | 2 |
| `GET /v1/platform/plans` | L | S | 已有 | 3 |

### 3.3 governance 模块补缺(非 zero-trust)

| 端点 | user value | 工作量 | 依赖 | 优先级 |
|---|---|---|---|---|
| `DELETE /v1/policies/{rule_id}`(pathMap 漏接,backend 已有) | M | S | 已有 | 3 |
| `GET /v1/approvals/{approval_id}`(pathMap 漏接,backend 已有) | L | S | 已有 | 3 |

### 3.4 agent_factory 模块补缺

| 端点 | user value | 工作量 | 依赖 | 优先级 |
|---|---|---|---|---|
| `PATCH /v1/agents/{aid}`(pathMap 漏接,backend 已有) | H | S | 已有 | **1** |
| `POST /v1/agents/{aid}/versions`(pathMap 漏接,backend 已有) | H | S | 已有 | **1** |
| `GET /v1/agents/{aid}/versions/{vid}` | H | S | 已有 | 2 |
| `PATCH /v1/agents/{aid}/versions/{vid}/notes` | M | S | 已有 | 2 |
| `POST /v1/agents/{aid}/versions/{vid}/{publish,release}` | H | S | 已有 | 2 |
| `POST /v1/agents/{aid}/versions/{vid}/retire` | M | S | 已有 | 3 |
| `GET /v1/agents/{aid}/versions/{vid}/releases` | M | S | 已有 | 3 |

### 3.5 orchestration / agent_runtime 模块补缺

| 端点 | user value | 工作量 | 依赖 | 优先级 |
|---|---|---|---|---|
| 修 `/api/sessions` POST 协议错配(web 补 aid 或 backend 加 aggregator) | H | M | agent_runtime | **1** |
| `PUT /v1/orchestration/plans/{id}`(改 status) | M | S | 已有 plan | 3 |
| `DELETE /v1/orchestration/plans/{id}`(backend 缺) | M | M | new | 4 |
| `GET /v1/sessions` list(backend 缺) | H | M | new | 2 |
| `GET /v1/sessions/{sid}/messages` 历史 | M | M | 已有 session | 3 |

### 3.6 evaluation 模块补缺

| 端点 | user value | 工作量 | 依赖 | 优先级 |
|---|---|---|---|---|
| `GET /v1/eval/datasets`(pathMap 漏接,backend 已有) | M | S | 已有 | 3 |
| `GET /v1/eval/datasets/{did}` | M | S | 已有 | 3 |
| `GET /v1/eval/datasets/{did}/cases` | M | S | 已有 | 3 |
| `POST /v1/eval/runs/{rid}/stop` | M | S | 已有 service 扩展 | 3 |
| `GET /v1/eval/runs/{rid}/report` | M | M | 报告聚合 | 3 |

### 3.7 observability_module 模块补缺

| 端点 | user value | 工作量 | 依赖 | 优先级 |
|---|---|---|---|---|
| `GET /v1/observability/quality` workspace 列表(扩展) | M | S | 已有 | 3 |

### 3.8 model 模块补缺

| 端点 | user value | 工作量 | 依赖 | 优先级 |
|---|---|---|---|---|
| `PATCH/DELETE /v1/routing-policies/{id}`(backend 缺) | M | S | 已有 repo | 3 |
| `DELETE /v1/model-credentials/{id}`(仅 rotate 不够) | M | S | 已有 repo | 3 |

### 3.9 skill 模块补缺

| 端点 | user value | 工作量 | 依赖 | 优先级 |
|---|---|---|---|---|
| `POST /v1/skills/{id}/uninstall`(对称 install) | H | S | skill.install | **1** |
| `GET /v1/skills/{id}/versions` | M | M | skill versioning | 3 |
| `GET /v1/skills/{id}/permissions` | M | M | RBAC | 3 |
| `GET /v1/skills/{id}/trace` | M | M | invocation history | 3 |

### 3.10 knowledge 模块补缺

| 端点 | user value | 工作量 | 依赖 | 优先级 |
|---|---|---|---|---|
| `GET /v1/knowledge/packages/{id}/assets/{aid}`(已有 delete,缺 get) | H | S | 已有 asset repo | **1** |
| 修 `/api/knowledge/docs` 顶层 list(backend 需 alias 或改 web) | H | S | 已有 | **1** |
| `POST /v1/knowledge/packages/{id}/assets/{aid}/review` | M | M | new | 3 |
| `POST /v1/knowledge/reindex` | M | M | 已有 search | 3 |
| `GET /v1/knowledge/processing-jobs` | M | M | async job | 3 |

### 3.11 memory 模块补缺

| 端点 | user value | 工作量 | 依赖 | 优先级 |
|---|---|---|---|---|
| `GET/PATCH /v1/memories/policy` | H | S | scope 已有 | **1** |
| `GET /v1/memories/audit` | M | S | audit log | 2 |
| `GET /v1/memories/candidates` 晋升候选 | M | M | new model | 2 |
| `POST /v1/memories/{id}/promote` | M | M | new | 3 |
| `GET /v1/memories/overview` 聚合 | M | M | new | 3 |

### 3.12 self_evolution 模块补缺

| 端点 | user value | 工作量 | 依赖 | 优先级 |
|---|---|---|---|---|
| `POST /v1/evolve/dream/run` 批量 dream | M | L | new sub-domain | 4 |

### 3.13 channel 模块(channel-control 子域)

| 端点 | user value | 工作量 | 依赖 | 优先级 |
|---|---|---|---|---|
| `GET/POST /v1/channels/control/deployments` | H | M | new deployment | 2 |
| `GET /v1/channels/control/policies` | H | M | delivery policy | 2 |
| `POST /v1/channels/control/deliveries` | H | M | dead-letter | 2 |
| `GET /v1/channels/control/dead-letters` | M | S |  | 2 |
| `GET /v1/channels/control/{inbound,health,audit}` | M | S |  | 3 |
| `GET /v1/channels/control/overview` | M | M | 聚合 | 3 |

---

## 4. 排除清单(本期不做 — backend 没有模块承接)

### 4.1 Zero-Trust 子域 (governance 需要新增子域)
- `/api/zero-trust/{overview,policies*,evaluate,events,authorizations}`
- `/api/access/{,governance,grants,reviews/complete}`

### 4.2 已移除的岗位对象（现统一为智能体）
- `/api/agent-profiles{,/overview}` + `/api/agent-profiles/:id/{evidence,lifecycle,publish,publish-preflight,skills,capabilities,install,uninstall,conversations}`
- `/api/agent-templates{,/:id/adopt}`
- `/api/agent-capability-catalog`
- `/api/agent-template-adoptions`
- `/api/tasks{,/:id}`

### 4.3 工作流 AI 生成 (orchestration 需要新增子域)
- `/api/workflows/{generate,generations,orchestration-sessions}`

### 4.4 Workflow templates + KPI (需新增子域)
- `/api/workflow-{templates,runs,kpi,skills}`

### 4.5 Home aggregator (新模块)
- `/api/home/{kpis,events,extra,team,alerts}`
- `/api/operations/overview`
- `/api/workspace-switch-history`

### 4.6 Workspace control (新模块)
- `/api/workspaces/:id/{partners,tools,members,report,runtime,audit,policy}`

### 4.7 Skill governance (skill 需要新增子域)
- `/api/skills/governance/{overview,health,incidents,events,trends,batch}`
- `/api/skills/{audit,catalog*,perms,import*,packs,dependency-matrix,upgrade-plan}`
- `/api/skills/:id/{uninstall,trace,versions,permissions,impact}` (注: uninstall 已在 §3.9 优先级 1)
- `/api/skill-{integrations,artifacts}`
- `/api/mcp-connections`
- `/api/platform-tools/registry`

### 4.8 Memory governance & refinement (memory 需要新增子域)
- `/api/memory/{policy,audit,candidates,refinement/run,overview}` (注: policy 已在 §3.11 优先级 1)
- `/api/memory/records/:id/candidate` POST

### 4.9 Knowledge governance & graph & sources & eval (knowledge 需要新增子域)
- `/api/knowledge/{sources*,governance*,audit,eval,bindings*,processing-jobs,retrieval-profiles,citation-trace,chunks/{top,rescore},graph/{entities,relations},evaluations*,reindex,docs/{review,delete}}`

### 4.10 Model governance & LLM-specific
- `/api/model-providers/{discover-models,test-connection,:id/{impact,draft,validate,publish}}`
- `/api/model-routing/failover-tests`
- `/api/model-{governance/overview,audit,failover-test}`
- `/api/{routes*,route-flow,export-routes,model-compare,providers*,provider-health,prompt-templates}`

### 4.11 Channel control / deploy / policy (channel-control 是大子域)
- 全 9 项 `/api/channel-control/*`

### 4.12 Self-evolution dream batch
- `/api/evolve/dream/run` POST

### 4.13 Audit center / Control-plane audit / Audit stream
- `/api/audit-{center,center/export,stream}`
- `/api/control-plane-audit`,`/api/audits`
- `/api/notification-channels{,/:id}`

### 4.14 Platform backups
- `/api/backups{,}`,`/api/webhooks-config`

### 4.15 Mock-only 杂项
- `/api/channel/{blacklist,config,health,languages,routes,templates}`
- `/api/channel/feishu/events/delivery-feishu`
- `/api/message-stream`,`/api/slash-commands`,`/api/mock/reset`

### 4.16 Agent mock-only (agent_alerts / live / rank / import)
- `/api/agents/{alerts,calls/live,rank,import,imports}`

### 4.17 Conversation / Actions (抽象层语义未对齐)
- `/api/conversations/:id{,/tasks}`
- `/api/actions/:id/{approve,execute,reject}`

---

## 附录 A. pathMap 三大类与 backend 实情对照

| 类别 | 数量 | 说明 |
|---|---|---|
| 真映射(matched=true) | 89 | pathMap 已翻译,真模式直走 backend |
| 显式 unmatched | 33 | phantom 路径,前端真模式必 404,引导补 backend |
| 完全无匹配(passthrough) | ~60+ | mock 自创端点 + pathMap 未补 |

## 附录 B. 重要 flag 提示(实施时必须修)

1. **pathMap `/api/tenant/profile` PATCH 标的是 `/v1/platform/tenants/me`,backend 不存在此端点** — 必须先补 backend 或改 pathMap。
2. **`/api/auth/me` 标的是 `/v1/identity/users/me`,backend 不存在** — 同上。
3. **`/api/sessions` POST 协议错配**:backend 要求 `/v1/agents/{aid}/sessions`,web 不传 aid — 实施时需要二选一(web补 aid 或 backend 加 aggregator)。
4. **`/api/api-keys` GET**:pathMap 指向 `/v1/identity/users/<<USER_ID>>/api-keys`,但 backend 只有 POST issue / POST revoke,**无 list endpoint** — 必须先补。
5. **knowledge 资源命名不一致**:web 用 `docs` 单数 / `doc/:id`,backend 用 `assets` — pathMap 已映射,但前端代码可能仍按 `docs` 路径调(未走 pathMap),需要全栈对齐。
6. **channels test→send verb 错配** pathMap 已修;governance reject→deny 同理。

## 附录 C. 优先级 1 端点(本期第一批 — 约 13 个)

| 端点 | 类型 | 工作量 |
|---|---|---|
| `GET /v1/identity/users/me` | 补 backend + pathMap | S |
| `GET /v1/identity/tenants/current` | 补 backend + pathMap | S |
| `GET /v1/platform/tenants/me` | 补 backend(pathMap 已指) | S |
| `PATCH /v1/agents/{aid}` | 补 pathMap | S |
| `POST /v1/agents/{aid}/versions` | 补 pathMap | S |
| 修 `/api/sessions` POST 协议错配 | 协议对齐 | M |
| `POST /v1/skills/{id}/uninstall` | 补 backend + pathMap | S |
| `GET /v1/knowledge/packages/{id}/assets/{aid}` | 补 backend + pathMap | S |
| 修 `/api/knowledge/docs` 顶层 list | backend alias 或改 web | S |
| `GET/PATCH /v1/memories/policy` | 补 backend + pathMap | S |
| ... (其余 P1 项见 §3 各模块) | | |

建议实施顺序: identity → platform → agent_factory → skill → knowledge → memory(共 6 个模块,~13 端点),完成后 pathMap 端点覆盖率从 89 → 102+,后续 priority 2-3 可在下一轮做。