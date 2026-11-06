# 数据通道 —— 单环境口径与历史梳理

> 目标（需求原文）：
> - 演示数据与 API 数据**严格分开，使用时不能混用**
> - **开发环境不得使用 demo 数据**；开发环境可用数据库测试数据
>
> **2026-11-06 起口径变了** ✓ —— 用户决定**只保留开发环境** ✓，
> 演示 / 预发（staging）/ 生产环境**连同相关能力一起去掉** ✓。
> ⚠️ **沙箱（gVisor）能力保留** ✓ —— 它是「智能体跑代码」的**能力** ✓，不是部署环境 ✓（§7 ✓）。
> 本文因此重写成**单环境版** ✓（文件名保持不变 ✓，避免引用断链 ✓）。
>
> 原来那条原则**没被推翻** ✓ —— 它只是从「两套环境里不许混」
> 变成「**只有一套数据：开发库里的开发租户**」✓。
>
> 标注 `[已实测]` 的数字是跑脚本量出来的，不是估的 ✓。

---

## 1. 结论先行

系统现在**只有一条数据通道** ✓：

| 维度 | 现状 |
|---|---|
| 环境 | **只有一个** ✓ —— `QZDAP_ENV ∈ {development, test, ci}` ✓ |
| 库 | **只有 `qzdap_dev`** ✓（开发库 ✓） |
| 租户 | **只有 dev 租户** ✓（slug `dev` ✓，id `uuid4()` 随机 ✓） |
| 账号 | **只有 `admin@dev.qzdap.dev` / `user@dev.qzdap.dev`** ✓ |
| 数据源 | **只有后端 API** ✓ —— 前端内存 mock 能力**已退役** ✓ |
| 种子内容 | **只有租户 / 工作区 / 账号 + 内置工具** ✓ —— **不种任何内容数据** ✓ |

⚠️ **这意味着目录页开箱是空态** ✓ —— 智能体 / 技能 / 工作流 / 知识库 /
对话 / 记忆**一个都没有** ✓（演示内容随演示环境一起退役了 ✓），
内容由管理员在管理台自己建 ✓。

⚠️ **另一类数据不受影响**：**验收样本** ✓（§12）—— 它既不是内容数据也不是
演示数据 ✓，是**第三类** ✓，仍然留在开发库里 ✓。

---

## 2. 现在的形态

```
┌──────────────────────── 开发环境（唯一环境） ────────────────────────┐
│ 前端 :9152   VITE_QZDAP_ENV=development                            │
│       │ /api → proxy                                                │
│       ▼                                                             │
│ 网关 :9150 → qzdap-app :9151   QZDAP_ENV=development               │
│       ▼                                                             │
│ Postgres :9153  qzdap_dev                                         │
│   租户 dev（uuid4）                                                 │
│   admin@dev.qzdap.dev / user@dev.qzdap.dev                         │
│   qa-tenant-a / qa-tenant-b（验收样本，§12）                          │
│ Redis :9154  db 0                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

**前端没有第二套数据源** ✓ —— `ApiClient` 只有一条 `fetch` 通路 ✓，
没有 `mockHandler` 注入 ✓，也没有 `dataMode` 字段 ✓。

### 2.1 后端

| 项 | 现状 |
|---|---|
| 环境枚举 | `Settings.env: Literal["development", "test", "ci"]` ✓ |
| 种子 profile | 只有 `dev_profile()` ✓（`seeds.py` ✓） |
| 种子内容 | `seed_identity()`（租户 / 工作区 / 账号）+ `seed_builtin_tools()`（31 个内置工具）✓ |
| 内容种子 | **无** ✓ —— 原来的 `demo_profile` / `seed_demo_*` / `DEMO_*` 规格 **全删** ✓ |
| 演示种子脚本 | **已删** ✓ —— `backend/scripts/seed_demo_data.py` 不在了 ✓ |
| 开发种子脚本 | `backend/scripts/seed_dev_data.py` ✓（幂等 ✓，可重复跑 ✓） |

⚠️ **内置工具是平台参考数据，不是内容** ✓ —— 每个租户都需要一份 ✓
（`echo` / `bash` / `web_search` / … ✓），单一来源是
`qzdap.modules.tool.application.tool_catalog.BUILTIN_TOOL_SPECS` ✓。

### 2.2 前端

| 项 | 现状 |
|---|---|
| 环境变量 | `VITE_QZDAP_ENV` **只接受 `development`** ✓（写别的值直接抛错 ✓） |
| `AppEnvironment` | 只有 `'development'` ✓ |
| `RuntimeConfig` | **没有 `dataMode`** ✓（只有一个 `environment` 字段 ✓） |
| 内存 mock | **已退役** ✓ —— 15 个 `features/*/mock-handler.ts` 全删 ✓ |
| localStorage key | `runtimeStorageKey(name)` → **`qzdap:<name>`** ✓（不再带环境段 ✓） |
| 旧 key 迁移 | `migrateLegacyStorageKeys()` ✓ —— 把 `qzdap:development:development-api:*` 搬到新 key ✓（**demo 的 key 不搬** ✓） |

⚠️ **页面测试的后端桩搬了家** ✓ —— skills / workflows / notifications 三处
从 `features/*/mock-handler.ts` 搬到 `frontend/web/src/test-utils/{skillsBackend,workflowsBackend,notificationsBackend}.ts` ✓，
其余 mock handler **连同测试一起删了** ✓。

### 2.3 脚本 / 部署

| 项 | 现状 |
|---|---|
| 栈脚本 | 只剩 dev 栈 ✓ —— `bin/qzdap-stack/run-qzdap-stack.sh` 等 ✓ |
| 演示栈脚本 | **已删** ✓ —— `run|stop|status-qzdap-demo-stack.sh` 三个都不在了 ✓ |
| 栈环境变量 | `qzdap-env.sh` 里 **`QZDAP_DEMO_*` 全删** ✓ —— 只剩 dev 那套 ✓ |
| 端口 | app :9151 ✓ / gateway :9150 ✓ / vite :9152 ✓ / pg :9153 ✓ / redis :9154 ✓ |
| `deploy/` | **整个目录已删** ✓（compose / PRODUCTION.md / env.*.example / burn_in / prometheus alerts ✓） |
| `infra/` | **整个目录已删** ✓（Dockerfile.app / nginx.compose.conf ✓） |
| CI | `.github/workflows/backend.yml` 仍用 `QZDAP_ENV: ci` ✓；`QZDAP_ALLOW_DEMO_TOKEN`（死配置 ✓）**已删** ✓ |

---

## 3. 已做对的部分（不要动）

这几条是对的，单环境口径下**继续成立** ✓：

1. **前端只有一条传输通路** ✓ —— 没有 mock 分支，也就没有 fallthrough 的问题 ✓。
2. **localStorage 的 key 有统一前缀** ✓ —— `runtimeStorageKey()` 生成 `qzdap:${name}` ✓，
   旧 key 由 `migrateLegacyStorageKeys()` 搬一次 ✓（搬完即删旧的 ✓）。
3. **后端 LLM 不混** ✓ —— 只有 `QZDAP_ENV=test` 才用 `MockLLMClient` ✓，
   其它一律 `UnavailableLLMClient`（503 ✓）或真实 `ModelService` ✓。
4. **后端只种 dev 那套** ✓ —— `profile_for_env()` 里 `development` / `test` 走
   `dev_profile()` ✓；`ci` **不种任何租户/账号** ✓（CI 自己建隔离库 ✓）。
5. **验收样本不许进不该进的 env** ✓ —— `assert_seedable_env()` 明确失败 ✓
   （不静默跳过 ✓），`FORBIDDEN_ENVS = {"demo", "production"}` 作为**兜底**留着 ✓
   （这两个 env 已经不存在了 ✓ —— 留着是为了以后再加环境时不漏拦 ✓）。

---

## 4. 历史：曾经的两条通道（已退役）

> ⚠️ 本节是**历史记录** ✓ —— 记录当时的两条通道长什么样、
> 混用混在哪、后来怎么清的 ✓。**不代表今天的现状** ✓。

第一轮清理（2026-10-28）之前，系统里有两条独立的数据通道 ✓：

| | 通道 A —— 演示数据 | 通道 B —— API 数据 |
|---|---|---|
| 数据文件 | `frontend/packages/api/src/mock.ts`（6189 行 ✓）+ `features/*/fixtures.ts` + 各域 `mock-handler.ts` ✓ | 开发库 `qzdap_dev` 里的真实表 ✓ |
| 传输 | `ApiClient` 注入 `mockHandler` ✓ —— **不发网络请求** ✓ | `ApiClient` → `fetch` → Vite proxy → 网关 :9150 → qzdap-app :9151 ✓ |
| 开关 | `VITE_QZDAP_ENV=demo` ✓ | `VITE_QZDAP_ENV=development` ✓ |
| 后端 | **完全不参与** ✓（`QZDAP_ENV=demo` 在后端几乎没被用到 ✓） | `QZDAP_ENV=development` ✓，真实端点 309 条 (路径, 方法) ✓ |

当时确认了 6 处混用 ✓，第一轮修掉 3 处 ✓：

| # | 混在哪 | 后果 | 严重度 | 现状 |
|---|---|---|---|---|
| 1 | **后端在开发库里种 demo 数据** | 开发环境的 Postgres 里有 "Demo Tenant" 和三个弱口令 demo 账号 ✓ | 🔴 高 | ✅ 已修 ✓ |
| 2 | **后端 `QZDAP_ENV=demo` 反而跳过 demo 种子** | 演示环境跑起来是空的 ✓，开发环境才有 demo 数据 ✓ —— 逻辑正好反了 ✓ | 🔴 高 | ✅ 已修 ✓ |
| 3 | **前端 mock 与后端路由严重脱节** | 后端 309 条端点 ✓，演示数据只覆盖 **4** 条 `[已实测]` ✓ | 🔴 高 | ✅ 已修 ✓（mock 退役 ✓） |
| 4 | **mock 未覆盖的路径静默返回 `null`** | 演示模式下页面显示"空数据" ✓，没有任何提示 ✓ | 🟠 中 | ✅ 已修 ✓ |
| 5 | **demo 分支写在共享 UI 代码里** | 同一段 UI 在两种模式下行为不同 ✓ | 🟠 中 | ✅ 已修 ✓ |
| 6 | **真实 API 端点读 mock 目录** | `GET /api/artifacts/{id}/content` 去读 `/tmp/qzdap-mock-artifacts` ✓ | 🟡 低 | ✅ 已修 ✓（产物表 `session_artifacts` ✓，迁移 0064 ✓） |

另有一批**死配置**：同一个开关有 3~4 个环境变量名，但只有 1 个真的生效 ✓ ——
已全部清掉 ✓（`VITE_USE_MOCK` / `VITE_DATA_MODE` / `VITE_USE_DEMO` /
`isDemoApiMode()` / `QZDAP_BAN_MOCK_TOKEN` / `QZDAP_ALLOW_DEMO_TOKEN` ✓）。

### 4.1 死配置清单（2026-10-28 已清空）

| 变量 | 原来 | 现在的状态 |
|---|---|---|
| `VITE_QZDAP_ENV` | 唯一真正生效的开关 | ✅ 保留 ✓，且是**唯一**开关 ✓（只接受 `development` ✓） |
| `VITE_USE_DEMO` | `VITE_QZDAP_ENV` 为空时的兜底 | 🗑️ **已删** ✓ |
| `VITE_DATA_MODE` | 从不读 | 🗑️ **已删** ✓ |
| `VITE_USE_MOCK` | 从不读 | 🗑️ **已删** ✓ |
| `isDemoApiMode()` | 导出但零调用 | 🗑️ **已删** ✓ |
| `QZDAP_ENV` 的 `demo` 值 | 几乎没被用到 | 🗑️ **已删** ✓（枚举只剩 `development` / `test` / `ci` ✓） |
| `QZDAP_ALLOW_DEMO_TOKEN` | 声明但零引用 | 🗑️ **已删** ✓（settings + `.env` + `.env.example` + CI ✓） |
| `QZDAP_BAN_MOCK_TOKEN` | 同上 | 🗑️ **已删** ✓ |
| `x-mock-role` / `x-mock-actor` / `x-mock-permissions` / `x-mock-user-id` 头 | demo 模式会发，后端从不读 | 🗑️ **已删** ✓ |
| `login.demoTitle` / `login.demoRoleUser` / `login.demoRoleAdmin` | 登录页「体验角色」快捷入口 | 🗑️ **已删** ✓ —— 现在是 `login.quickRole*` ✓（`LoginQuickChips` ✓ / `LoginQuickRole` ✓） |

### 4.2 契约测试守住了对齐

演示走真后端之后，「演示数据与真实 API 对齐」由**契约测试**保证 ✓
（`backend/composition/qzdap_app/tests/unit/test_frontend_pathmap_contract.py` ✓），
不再靠一次性手工审计 ✓。

⚠️ 这条测试**现在仍然在跑** ✓ —— 它守的是**前端调用面 ↔ 后端路由**的契约 ✓，
跟有几个环境无关 ✓。

---

## 5. 决策历程（记录在案）

| 决策 | 选定 | 理由 |
|---|---|---|
| **A —— 演示数据放哪** | **A2：后端 + 独立 demo 库** | "演示数据需要与真实 API 对齐"这条，A1（前端 mock）在架构上做不到 —— mock 是另一份手写的数据，只能靠人力对齐 |
| **B —— 开发环境用什么数据** | **B1：独立 dev 种子脚本** | 与 A2 同一个形状：脚本 + 独立库，两边都不混 |
| **C —— 前端 mock 怎么办** | 随 A2：前端 mock 降级为**单测夹具**，不再做运行时数据源 | 演示走 A2 之后，运行时 mock 没有存在理由 |
| **D —— 环境数量**（2026-11-06） | **只保留开发环境** ✓ | 演示环境的维护成本高于它的收益 ✓ —— 于是 A2 / B1 的「两套」塌缩成「一套」✓ |

⚠️ **决策 D 之后** ✓ —— A2 的「独立 demo 库」不再是**第二个库** ✓，
而是**唯一那个库** ✓；B1 的「独立 dev 种子脚本」不再是**第二个脚本** ✓，
而是**唯一那个脚本** ✓。§4 记的那些清理**一件都没白做** ✓ ——
它们正是「只剩一套」能成立的前提 ✓。

---

## 6. 启动闸门 → 健康检查

⚠️ **这里也变了** ✓ —— 原来有一道「生产环境启动闸门」✓
（`Container._validate_production_secrets` ✓ —— 默认密钥 / 默认后端 → **拒绝启动** ✓）。

只剩开发环境之后，**那道闸门永远不触发** ✓ —— 留着只是误导 ✓。
所以它改成了**健康检查** `Container._collect_runtime_health(settings)` ✓：

```python
# container.py
self.runtime_health = self._collect_runtime_health(settings)
```

返回 `{"degraded": [...], "issues": [...]}` ✓ —— **不抛异常** ✓：

| 字段 | 装什么 |
|---|---|
| `degraded` | 用了降级后端的项 ✓ —— 签名单关 ✓ / embedding noop ✓ / vault 直读环境变量 ✓ / 事件总线在进程内 ✓ |
| `issues` | 缺必需项 ✓ —— 主密钥为空 ✓ / 沙箱地址为空 ✓ |

结果挂在 `app.state.runtime_health` ✓ —— `/readyz` 的响应里带 `runtime` 字段 ✓
（`backend/libs/http/src/qzdap_http/health.py` ✓）。

⚠️ **配套改动** ✓：
- `lifespan.py` 里原「production 硬失败」的 model_service / channel_service 分支
  **改成一律告警** ✓；
- `ref_resolver.py` 里 prod / staging 的 fail-loud 分支**改成告警 + 跳过** ✓。

---

## 7. 沙箱能力（**保留** ✓）

⚠️ **沙箱不是部署环境** ✓ —— `backend/runtimes/sandbox_runtime/` 是「智能体跑代码」的
**能力** ✓，跟有几个环境无关 ✓。它只是把 `env` 字面量收成 `development|test|ci` ✓，
并删掉了「生产环境拒绝 stub 执行器」的分支 ✓。

gVisor (runsc) + 网络出站白名单这套**能力域**一个字没动 ✓
（详见 [`../planned/sandbox-network-egress-control.md`](../planned/sandbox-network-egress-control.md) ✓）。

---

## 8. 怎么跑起来

```bash
# 后端
cd backend && make sync && cp .env.example .env
sed -i '' "s|<paste 32-byte hex-encoded key here>|$(openssl rand -hex 32)|" .env   # macOS

# 数据层
cd backend && docker compose up -d && make db-upgrade

# 应用栈（Vite :9152 + 网关 :9150 + qzdap-app :9151）
make qzdap-up
```

| 入口 | 地址 |
|---|---|
| 前端 | `http://127.0.0.1:9152` ✓ |
| 网关 | `http://127.0.0.1:9150` ✓ |
| 后端 | `http://127.0.0.1:9151` ✓ |
| Postgres | `127.0.0.1:9153/qzdap_dev` ✓ |
| Redis | `127.0.0.1:9154` db 0 ✓ |
| 沙箱 | `http://127.0.0.1:9158` ✓（gVisor ✓） |

| 角色 | 邮箱 | 口令 |
|---|---|---|
| 管理员 → `/admin/*` ✓ | `admin@dev.qzdap.dev` ✓ | `dev-admin-password-change-me` ✓ |
| 成员 → `/copilot/*` ✓ | `user@dev.qzdap.dev` ✓ | `dev-user-password-change-me` ✓ |

⚠️ **口令与账号来源** ✓ —— `backend/composition/qzdap_app/src/qzdap/composition/settings.py`
的 `dev_*` 字段 ✓ —— `backend/.env.local` 与栈脚本**都没覆盖** ✓ → 跑的就是这些默认值 ✓。

⚠️ **LLM 供应商没配** ✓ → 发一轮必然 `TURN_FAILED` ✓ —— **这是环境没配模型，不是回归** ✓。

---

## 9. 复现本文的实测数字

```bash
# 后端端点表（309 条 (路径, 方法) / 248 条路径）
cd backend && .venv/bin/python -c "
import json
from qzdap.composition.main import create_app
s = create_app().openapi()
rows = [(p, m.upper()) for p, ops in s['paths'].items() for m in ops
        if m.lower() not in ('head', 'options')]
print(len(rows)); json.dump([{'path':p,'verb':v} for p,v in rows], open('/tmp/backend_routes.json','w'))
"
```

> ⚠️ **别用遍历 `app.routes` 的方式统计路由** ✓。这个 FastAPI 版本把
> `include_router` 包成 `_IncludedRouter` ✓，路由是**延迟**挂载的 ✓：
> `route.path` 上只有局部路径（`/login` ✓），前缀要等匹配时才补上
> （`/v1/identity/login` ✓）。遍历 `app.routes` 会拿到一张**错的**路径表 ✓ ——
> 本文的初稿就是这么错的 ✓（把 309 算成 314 ✓，还差点把一条正确的规则判成漂移 ✓）。
> **OpenAPI schema 才是运行时真正对外暴露的那份路径** ✓。

---

## 10. 顺带修掉的两个真 bug（记录在案）

### 10.1 开发账号的域名踩了个坑

原来的开发账号是 `admin@dev.local` ✓。**`.local` 是保留域名 ✓**，
后端的 `EmailStr` 校验会直接拒掉 ✓，登录请求根本到不了业务逻辑 ✓：

```
422 {"detail":[{"type":"value_error","loc":["body","email"],
      "msg":"value is not a valid email address: The part after the @-sign
             is a special-use or reserved name that cannot be used with email."}]}
```

也就是说**开发环境的快捷登录一直是登不进去的** ✓ —— 不是"分开"造成的 ✓，
是账号名本身不合法 ✓。已改成 `admin@dev.qzdap.dev` ✓（普通域名 ✓，能过校验 ✓）。
`.local` / `.test` / `.example` 这类保留域名都不能用 ✓。

### 10.2 认证边界：整个 API 都可以匿名读写

把一份烂掉的契约测试捞回来重写时，发现了一件比它本身严重得多的事 ✓。

`backend/tests/contract/test_openapi_headers.py` 断言"每个受保护的路由都要声明
`X-Tenant-Id` 请求头" ✓ —— 它断言的是**头部驱动**时代的模型 ✓，
而且从没被执行过 ✓（`backend/tests/` 不在 pytest 的 `testpaths` 里 ✓）。
今天租户来自 **JWT 的 `tid`** ✓，请求头只是交叉校验 ✓ —— 这份契约的**前提**已经过时了 ✓。

但把它当成线索去查，发现了真的洞 ✓：

```
$ curl -s -H "X-Tenant-Id: …" -H "X-Workspace-Id: …" \
       http://127.0.0.1:9151/api/catalog/agents      # 完全没有 Authorization
[{"id":"…","name":"销售线索洞察助手", …}]

$ curl -s -X POST -H "X-Tenant-Id: …" -H "X-Workspace-Id: …" \
       -d '{"name":"未授权写入测试"}' \
       http://127.0.0.1:9151/api/admin/agents         # 完全没有 Authorization
{"id":"bee70640-…","name":"未授权写入测试", …}          # ← 建成了
```

**原因是一条链** ✓：

```
没有 token → 没有 principal → 没有绑定租户 → ORM 的租户自动过滤退化成空操作
           → 路由开始相信调用方自己填的 X-Tenant-Id
```

也就是说 `X-Tenant-Id` **从来不是边界，只是提示** ✓。

**修法**：边界收进中间件链 ✓ —— `backend/libs/http/src/qzdap_http/middleware.py`
新增 `AuthRequiredMiddleware` ✓，它跑在 Auth 之后 ✓、租户/工作区守卫之前 ✓：
**没有 principal 的非公开请求一律 401** ✓。

```
ErrorEnvelope → Observability → RateLimit → CORS → Auth → AuthRequired
              → TenantGuard → WorkspaceGuard → App
```

公开端点清单走 `Settings.public_paths` ✓（`QZDAP_PUBLIC_PATHS` ✓，逗号分隔 ✓）：

```
/healthz,/livez,/readyz,/metrics,/docs,/openapi.json,
/v1/identity/login,/v1/identity/tenants,/v1/channels/*/webhook
```

带 `*` 的是 glob 规则 ✓，其余按**精确路径**匹配 ✓ —— 精确匹配很重要 ✓：
`/v1/channels` 当成前缀会把该前缀下的 CRUD 一起放开 ✓，而只想放开 webhook ✓。

⚠️ **这个改动牵出了前端一处真问题** ✓ —— 产物/附件下载用的是裸 `fetch` ✓，
不带 `Authorization` ✓ —— 以前能通是因为那个端点根本不校验 ✓。
现在下载改走 `ApiClient.download()` ✓（新加 ✓，带 token + 上下文头 ✓）。

⚠️ **配套的契约测试** ✓ —— `backend/tests/contract/test_auth_required.py` ✓
守的是**今天**的边界 ✓：

| 断言 | 守什么 |
|---|---|
| `test_public_paths_resolve_to_real_routes` | 公开端点清单里的每条规则都指向真实路由 ✓ |
| `test_public_paths_do_not_expose_mutating_routes` | 公开端点不能盖住会改数据的路由 ✓ |
| `test_webhook_pattern_only_covers_the_webhook` | glob 规则不会连 CRUD 一起放开 ✓ |
| `test_anonymous_requests_are_rejected` | 匿名访问真的被拒 ✓ |
| `test_anonymous_write_is_rejected` | 匿名**写**也被拒 ✓ |
| `test_public_endpoints_stay_reachable` | 探针不能被误锁 ✓ |

---

## 11. 前端内存 mock 的退役（时间线）

⚠️ **运行时 mock 已经彻底不存在了** ✓ —— 这一节记的是**怎么没的** ✓：

| 阶段 | 动作 |
|---|---|
| 第一轮（2026-10-28） | mock 兜底从静默 `return null` 改成抛 `E_MOCK_NOT_IMPLEMENTED` ✓ —— 页面不再假装"没有数据" ✓ |
| 第二轮（2026-10-28） | 前端不再注入 mock ✓ —— `main.tsx` 删掉全部 `wrapMockHandlerWith*` ✓，`ApiClient` 拿到的 handler 是 `undefined` ✓ |
| 第八~十轮（2026-10-28 ~ 30） | `mock.ts` 从主入口改成子路径导出 ✓（`@qzdap/web-api/mock` ✓）—— 主入口不再假装 mock 是 API 客户端的一部分 ✓ |
| **2026-11-06** | **15 个 `features/*/mock-handler.ts` 全删** ✓ —— 其中 skills / workflows / notifications 三处**搬去** `frontend/web/src/test-utils/{skillsBackend,workflowsBackend,notificationsBackend}.ts` ✓ 供页面测试用 ✓，其余**连同测试一起删了** ✓ |

⚠️ **顺带拆掉的 UI 分叉** ✓ —— `CreateSkillWizard.tsx` 的「模拟 MCP 探测」（硬编码工具列表 ✓）→
两边都调真端点 `/api/admin/skills/mcp/probe` ✓；`CopilotPage.tsx` 的「附件只写文件名」→
真上传 ✓；`AgentsPage.tsx` 的「载入演示数据」**整块删掉** ✓。

⚠️ **localStorage 的 key 也随之收成一层** ✓ —— 原来 `runtimeStorageKey()` 生成
`qzdap:${environment}:${dataMode}:${name}` ✓，现在只剩 `qzdap:${name}` ✓ ——
`RuntimeConfig` **没有 `dataMode`** ✓ 了，**只有一个环境也就不需要按环境隔离** ✓
（老 key 由 `migrateLegacyStorageKeys()` 搬一次 ✓）。

---

## 12. 第三类数据 —— 验收样本

⚠️ **验收样本既不是内容数据，也不是开发租户的数据** ✓ —— 它是**第三类** ✓：

| 类别 | 落在哪 | 谁种 | 用来验什么 |
|---|---|---|---|
| **开发租户** | 开发库 `qzdap_dev` ✓ | `QZDAP_ENV=development` 启动时 ✓ | 日常开发 ✓ |
| **验收样本** | **同一个开发库** ✓（`qa-tenant-a` / `qa-tenant-b` ✓） | `scripts/seed_acceptance_samples.py` ✓ | **验收判据** ✓（H1 ✓） |
| **内容数据** | **没有** ✓ —— 目录页开箱是空态 ✓ | 管理员在管理台自建 ✓ | —— |

⚠️ **验收样本的边界** ✓：
- **全是造出来的** ✓（邮箱用 `.invalid` ✓ —— 保证不可投递 ✓）；
- **id 用 uuid5 派生** ✓ → **可复现** ✓ → 脚本**幂等** ✓（跑两遍不重复 ✓）；
- **租户名带 `qa-`** ✓ → 一眼认得出 ✓（不会跟 dev 租户混 ✓）；
- **不许种的 env 直接拒绝** ✓（`assert_seedable_env()` ✓ —— 脚本自己拦一道 ✓，
  **不静默跳过** ✓）—— 演示 / 生产这两个 env 已经退役了 ✓，
  `FORBIDDEN_ENVS = {"demo", "production"}` 留着是**兜底** ✓。

⚠️ **验收判据在哪** ✓ —— `scripts/acceptance_check.py` ✓（**一键跑完 13 条** ✓）：
样本在不在 ✓ / 没有孤儿消息 ✓ / 有审批挂起的轮次 ✓ / 事件 seq 连续 ✓ /
策略绑定在 ✓ / **跨租户越界 = 0** ✓ / 退役的列没了 ✓。
