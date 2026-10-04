# Digital-Employee-Platform → 企智搭 · 智能体平台 后端迁移 Delta 审计

**审计日期:** 2026-09-25
**数据源:**
- `digital-employee-platform/backend/api/routes.md` — de-app 完整路由清单(146 唯一 endpoint)
- `QiZhiDaAgentPlatform/backend/modules/*/router.py` — qzdap-app 当前 15 模块 92 唯一 endpoint

## 总览

| 状态 | 数量 | 占比 |
|---|---|---|
| ✅ COVERED(直接同名/同路径) | 23 | 15.8% |
| ⚠️ DIFFERENT-NAME(模块在,路径不同) | 4 | 2.7% |
| ❌ MISSING(qzdap-app 无对应) | 119 | 81.5% |
| **总计** | **146** | 100% |

## 按 qzdap-app 模块分布

| 模块 | ✅ 直接 | ⚠️ 同名 | ❌ 缺失 | 共计 |
|---|---:|---:|---:|---:|
| model | 4 | 1 | 15 | 20 |
| channel | 0 | 0 | 17 | 17 |
| skill | 3 | 0 | 11 | 14 |
| agent_runtime | 0 | 0 | 13 | 13 |
| (无模块) — tasks | 0 | 0 | 10 | 10 |
| platform | 0 | 0 | 10 | 10 |
| identity | 6 | 0 | 3 | 9 |
| observability | 0 | 0 | 8 | 8 |
| orchestration | 4 | 0 | 4 | 8 |
| agent_factory | 0 | 1 | 6 | 7 |
| governance | 0 | 2 | 4 | 6 |
| self_evolution | 3 | 0 | 3 | 6 |
| knowledge | 1 | 0 | 5 | 6 |
| tool | 0 | 0 | 2 | 2 |

## 已覆盖 ✅(23 项 — 无需迁移)

```
POST   /api/auth/login                       → POST   /v1/identity/login
GET    /api/workspaces                       → GET    /v1/identity/workspaces
POST   /api/workspaces                       → POST   /v1/identity/workspaces
GET    /api/tenant/profile                   → GET    /v1/identity/tenants/current
GET    /api/api-keys                         → GET    /v1/identity/users/{uid}/api-keys (uid 注入)
POST   /api/api-keys                         → POST   /v1/identity/users/{uid}/api-keys
GET    /api/model-providers                  → GET    /v1/model-credentials
POST   /api/model-providers                  → POST   /v1/model-credentials
GET    /api/model-routing/policies           → GET    /v1/routing-policies
POST   /api/model-routing/policies           → POST   /v1/routing-policies
POST   /api/workflows                        → POST   /v1/orchestration/plans
GET    /api/workflows/:id                    → GET    /v1/orchestration/plans/{plan_id}
POST   /api/workflows/:id/run                → POST   /v1/orchestration/plans/{plan_id}/runs
GET    /api/workflows/:id/runs               → GET    /v1/orchestration/runs?plan_id=...
GET    /api/skills/:id                       → GET    /v1/skills/{skill_id}
POST   /api/skills/:id/install               → POST   /v1/skills/{skill_id}/install
POST   /api/skills/:id/uninstall             → POST   /v1/skills/{skill_id}/uninstall
GET    /api/knowledge/packages               → GET    /v1/knowledge/packages
GET    /api/memory/policy                    → GET    /v1/memories/policy
PATCH  /api/memory/policy                    → PATCH  /v1/memories/policy
GET    /api/evolve/candidates                → GET    /v1/evolve/candidates
POST   /api/evolve/candidates/:id/approve    → POST   /v1/evolve/candidates/{cid}/approve
POST   /api/evolve/candidates/:id/reject     → POST   /v1/evolve/candidates/{cid}/reject
```

## 部分覆盖 ⚠️(4 项 — 需 pathMap 适配或重命名)

```
PATCH  /api/zero-trust                       → PATCH  /v1/policies/{rule_id}
GET    /api/zero-trust                       → GET    /v1/policies
POST   /api/actions/:id/approve              → POST   /v1/approvals/{approval_id}/approve
POST   /api/agent-profiles/:id/release    → POST   /v1/agents/{aid}/versions/{vid}/release
PATCH  /api/model-providers/:id              → PATCH  /v1/models/{model_id}   (≠ model-credentials)
DELETE /api/model-providers/:id              → DELETE /v1/models/{model_id}
PATCH  /api/notification-channels/:id        → PATCH  /v1/channels/{channel_id} (≠ notification 专用)
POST   /api/model-invoke                     → POST   /v1/models/{model_id}/invoke
POST   /api/memory/candidates/:id/approve    → POST   /v1/evolve/candidates/{cid}/approve
GET    /api/sessions                         → GET    /v1/sessions/{sid}   (仅 :id)
POST   /api/sessions                         → POST   /v1/agents/{aid}/sessions (no plain POST)
```

## ❌ 缺失(119 项)— 迁移目标

### model (15)

```
POST   /api/model-providers/discover-models
POST   /api/model-providers/test-connection
GET    /api/model-providers/:id/impact
POST   /api/model-providers/:id/test
POST   /api/model-providers/:id/disable
PATCH  /api/model-routing/policies/:id/draft
POST   /api/model-routing/policies/:id/validate
POST   /api/model-routing/policies/:id/publish
POST   /api/model-routing/policies/:id/unpublish
POST   /api/model-routing/policies/:id/rollback
GET    /api/model-routing/policies/:id/versions
POST   /api/model-routing/failover-tests
POST   /api/model-invoke/stream
GET    /api/model-governance/overview
GET    /api/model-audit
```

### channel (17)

```
GET    /api/channel-control/deployments
POST   /api/channel-control/deployments
GET    /api/channel-control/policies
POST   /api/channel-control/policies
GET    /api/channel-control/overview
GET    /api/channel-control/dead-letters
POST   /api/channel-control/dead-letters/:id/replay
GET    /api/channel-control/audit
GET    /api/channel-control/inbound
GET    /api/notification-channels
POST   /api/notification-channels
GET    /api/webhooks-config
POST   /api/webhooks-config
POST   /api/channel/feishu/events/:deploymentId
POST   /api/channel/wecom/events/:deploymentId
POST   /api/channel/dingtalk/events/:deploymentId
```

### skill (11)

```
GET    /api/skills
GET    /api/skills/catalog
GET    /api/skills/governance/overview
POST   /api/skills/:id/lifecycle
POST   /api/skills/:id/upgrade
POST   /api/skills/:id/test
POST   /api/skills/import
POST   /api/skills/import-package
POST   /api/skills/catalog/publish
POST   /api/skills/catalog/sync
POST   /api/skills/execute
```

### agent_runtime (13) — conversations + copilot

```
GET    /api/sessions
POST   /api/sessions
GET    /api/conversations
POST   /api/conversations
GET    /api/conversations/:id
GET    /api/conversations/:id/stream
GET    /api/conversations/:id/tasks
GET    /api/conversations/:id/messages
GET    /api/copilot/conversations
POST   /api/copilot/conversations
GET    /api/copilot/conversations/:id
GET    /api/copilot/conversations/:id/messages
GET    /api/copilot/conversations/:id/stream
POST   /api/copilot/conversations/:id/messages/:mid/feedback
```

### tasks (10) — **无对应模块,需新建 `tasks` 或并入 orchestration**

```
GET    /api/tasks
POST   /api/tasks
POST   /api/tasks/:id/transition
GET    /api/tasks/:id
GET    /api/tasks/:id/audit
POST   /api/tasks/:id/approve
POST   /api/tasks/:id/takeover
POST   /api/tasks/:id/retry
PATCH  /api/tasks/:id
```

### platform (10) — billing / backups / settings / metrics / health

```
GET    /api/billing
GET    /api/backups
POST   /api/backups
POST   /api/backups/:id/approve
POST   /api/backups/:id/reject
POST   /api/backups/:id/restore-drill
PATCH  /api/tenant/profile
GET    /metrics
GET    /healthz
GET    /readyz
```

### identity (3)

```
GET    /api/workspaces/:id/members
GET    /api/workspaces/:id/quota
DELETE /api/api-keys/:id   (只有 revoke,无 delete)
```

### observability (8) — 全新 domain,目前只有 observability_module (3 endpoints,全不匹配)

```
GET    /api/audit-center
GET    /api/model-audit
GET    /api/operations/overview
GET    /api/home/kpis
GET    /api/home/team
GET    /api/home/events
GET    /api/home/alerts
POST   /api/home/alerts/:id/acknowledge
```

### orchestration (4)

```
POST   /api/workflows/:id/draft
POST   /api/workflows/:id/publish
GET    /api/workflows/:id/versions
```

### agent_factory (6)

```
GET    /api/agent-profiles        (only :id currently)
POST   /api/agent-profiles
GET    /api/agent-profiles/overview
POST   /api/agent-profiles/:id/lifecycle
POST   /api/agent-profiles/:id/evaluate
POST   /api/agent-profiles/:id/configuration
```

### governance (4)

```
GET    /api/access/governance
GET    /api/zero-trust/evaluate
POST   /api/actions/:id/execute
GET    /api/access/governance
```

### self_evolution (3)

```
POST   /api/evolve/dream/run
POST   /api/copilot/conversations/:id/messages/:mid/feedback
POST   /api/memory/candidates/:id/approve (note: different path)
```

### knowledge (5)

```
GET    /api/knowledge/docs
GET    /api/knowledge/sources
GET    /api/knowledge/governance
POST   /api/knowledge/docs
POST   /api/knowledge/reindex
```

### tool (2) — slash-commands

```
GET    /api/slash-commands
POST   /api/slash-commands
```

## 分批迁移方案(推荐顺序)

| Batch | Domain | 新增 endpoints | 主要新增/重命名 | 工作量 |
|---|---|---:|---|---|
| B1 | **memory + skills 完善** | 14 | memory overview/records/candidates/refinement/audit/expire + skill catalog/lifecycle/upgrade/import | 中 |
| B2 | **model 完善 + governance** | 22 | model discover/test/impact/routing-policy lifecycle/failover + governance access/zero-trust/evaluate | 大 |
| B3 | **agent_runtime conversations + copilot** | 14 | 全 conversations + copilot SSE + feedback | 大(SSE) |
| B4 | **agent_factory digital-employees** | 6 | digital-employees 全套 CRUD + lifecycle/release/configuration | 中 |
| B5 | **orchestration + tasks** | 13 | orchestration plans/versions + 全新 tasks 模块(10 项) | 大(新模块) |
| B6 | **channel 完善 + webhooks** | 17 | channel-control 全套 + webhook callbacks(feishu/wecom/dingtalk) | 中 |
| B7 | **observability 全新** | 8 | 全新 observability domain(audit-center, model-audit, home/*) | 大(聚合) |
| B8 | **platform + 基础** | 13 | platform billing/backups/settings + /metrics /healthz /readyz 透传 | 中 |

总计 ≈ 119 缺失 + 4 部分覆盖 = 123 项 endpoint 工作量。

## 推荐实施策略

1. **保持 de-app gateway 在 :8089 继续跑** — 不动现有前端 e2e 体验
2. **并行运行** — qzdap-app 起在新端口(:9000 via gateway, 已就绪),gateway 后面同时转发 de-app 和 qzdap-app(根据 path prefix 决定)
3. **按 Batch 灰度切** — 每 batch 完成后,pathMap 标 `unmatched: true` → 灰度 `matched: true` → 验证 → 删除 phantom
4. **完全替换** — 全部 8 batch 完成后,de-app 退场,只留 qzdap-app + 一层薄薄 gateway