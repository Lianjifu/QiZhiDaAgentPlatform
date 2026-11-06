# platform — 平台设置与运营看板

> 能力域之一。负责租户级设置、套餐订阅，以及**管理台各页面数据的通用存储**。

⚠️ 本模块的「运营看板」数据**主要来自种子 JSON 文档**，不是从真实运行记录聚合而来——这是本域最需要留意的一点。

## 职责

- **租户设置**（`tenant_settings`）：key / value 的 JSONB 键值存储
- **套餐与订阅**（`plans` / `subscriptions`）
- **管理台文档存储**（`admin_ops_docs`）：31 个 collection 的通用 CRUD 载体
- 运营总览、成本聚合

## 源码位置

```
backend/modules/platform/src/qzdap/modules/platform/
├── domain/          entities.py（Plan · Subscription · TenantSetting）· errors.py · events.py
├── application/
│   ├── services.py     PlatformService
│   ├── ops_service.py  AdminOpsService（管理台文档的 CRUD / patch / action / batch / import）
│   └── use_cases/      build() 工厂：list_plans · get_plan · get_subscription · assign_subscription · list_settings · upsert_setting · aggregate_costs
└── adapter/
    ├── http/         router.py · ops_router.py · ops_mutation_router.py
    └── persistence/  models.py · repositories.py
```

## HTTP 端点

**平台设置与套餐**（前缀 `/v1/platform`）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/v1/platform/plans` | 套餐列表 |
| GET | `/v1/platform/subscriptions/me` | 当前订阅 |
| PUT | `/v1/platform/subscriptions/me` | 变更订阅 |
| GET | `/v1/platform/settings` | 设置列表 |
| GET | `/v1/platform/settings/{key}` | 单项设置 |
| PUT | `/v1/platform/settings/{key}` | 写设置 |

**运营看板**（`ops_router.py`）

`/api/admin/overview/*`（summary / alerts / trend）、`/api/admin/quotas/*`（budgets / departments / usage / alerts）、`/api/admin/notifications/*`（channels / webhooks / groups / events）、`/api/admin/evaluations/*`、`/api/admin/regressions/*`、`/api/admin/feedback/*`、`/api/admin/operations/*`、`/api/admin/audit/*`、`/api/admin/metrics/*`。

**运营变更**（`ops_mutation_router.py`）

用 `add_api_route` **批量注册**通用变更路由：`PATCH/DELETE {resource}/{doc_id}`、`POST {resource}/import`、`POST {resource}/batch-{action}`、`GET {resource}/{doc_id}/{field}`、`POST {resource}/{doc_id}/{action}`。

## 数据表

| 表 | 职责 | 关键列 |
|---|---|---|
| `plans` | 套餐 | id / code / name / limits(JSONB) / features / price_monthly_usd / status(active\|hidden\|retired) |
| `subscriptions` | 订阅（**租户级唯一**） | id / tenant_id / plan_id / status / started_at / expires_at |
| `tenant_settings` | 租户设置（租户级唯一） | id / tenant_id / key / value(JSONB) |
| `admin_ops_docs` | **管理台通用文档存储** | id / collection / doc_key / payload(JSONB) |

`admin_ops_docs` 是所有管理台页面的**同一个存储**：overview、quotas、notifications、evaluations、regressions、feedback、operations、audit、metrics 各对应一个 `collection`。

## 关键类

| 层 | 类 | 职责 |
|---|---|---|
| domain | `Plan` `Subscription` `TenantSetting` | 聚合根；`SubscriptionStatus` / `PlanStatus` 枚举 |
| application | `PlatformService` | 设置 / 套餐 / 订阅门面 |
| application | `AdminOpsService` | 管理台文档的 CRUD / patch / action / batch / duplicate / import / run_collection |
| application | `aggregate_costs` | 成本聚合（转发 observability） |

## 实现要点

- **订阅是租户级的**：迁移 0060 已 DROP `subscriptions.workspace_id`——订阅不按工作区划分
- **设置也是租户级的**：`tenant_settings` 上有租户级唯一约束
- **管理台用通用 CRUD 覆盖 31 个 collection**：不为每个页面写一套路由，而是用 `add_api_route` 批量注册
- **变更统一走 `ops_service`**：patch / action / batch / duplicate / import 都有对应的服务方法
- **成本聚合转发 observability**：`aggregate_costs` 委托给 observability 模块，本模块不重复存成本

## 已知边界

- ⚠️ **运营看板没有种子数据**：⚠️ 演示内容随演示环境退役时一并删掉了 ✓（原来的 `seed_demo_ops_docs()` ✓ —— `seeds.py` 里已无此函数 ✓），`fixtures/ops_seed.json` 也**没人调** ✓（`seed_if_empty` 只剩仓储上的方法定义 ✓，无生产调用方 ✓）→ `admin_ops_docs` 是空的 ✓ → `overview_summary`（`ops_service.py:772`）算出来全是零值 ✓ —— 看板要等真实运行数据才有内容 ✓
- ⚠️ **品牌与成员管理不在本模块**：全库无 brand 路由（前端 `--brand` 只是 CSS 变量）；成员管理在 [identity](./identity.md)
- ⚠️ `run_collection` 在 runner 未接时抛 `NotImplementedError`（`ops_service.py:161`）
- ⚠️ `import_docs` 只支持 json / jsonl / yaml / csv，且只有 5 个 collection 有专用 creator，其余走通用 create
- ⚠️ `aggregate_costs` 在 observability 未接时**静默返回空数组**（不是 503）——注释说「让 HTTP 仍返回 200」
