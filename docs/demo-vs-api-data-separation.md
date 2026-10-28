# 演示数据 vs API 数据 —— 现状梳理与拆分方案

> 目标（需求原文）：
> - 演示数据与 API 数据**严格分开，使用时不能混用**
> - **开发环境不得使用 demo 数据**；开发环境可用数据库测试数据
> - **演示环境可用 demo 数据**，且 demo 数据要与真实 API **对齐**
>
> 本文先把这两条通道的现状理清（第一部分～第四部分），再给目标状态和落地步骤（第五部分～第七部分）。
> 标注 `[已实测]` 的数字是跑脚本量出来的，不是估的。
>
> **状态**：§7 记录了目标状态，§6.2 记录了第一轮（与方案无关的清理），
> §9 记录了第二轮 —— 按决策 A2/B1 把**演示环境真正立起来**（独立 demo 库 +
> 独立 demo 后端实例 + 演示栈脚本）。

---

## 1. 结论先行

系统里有两条独立的数据通道，**前端传输层是不混的**（`ApiClient` 在有 mock 时永远不发网络请求）。
问题不在"有没有分开"，而在**分开的严密程度不够**。梳理时确认了 6 处混用，
第一轮清理已经修掉 3 处（1、2、4）：

| # | 混在哪 | 后果 | 严重度 | 现状 |
|---|---|---|---|---|
| 1 | **后端在开发库里种 demo 数据** | 开发环境的 Postgres 里有 "Demo Tenant" 和三个弱口令 demo 账号 | 🔴 高 | ✅ 已修（§6.2-3） |
| 2 | **后端 `QZDAP_ENV=demo` 反而跳过 demo 种子** | 演示环境跑起来是空的，开发环境才有 demo 数据 —— 逻辑正好反了 | 🔴 高 | ✅ 已修（§6.2-3） |
| 3 | **前端 mock 与后端路由严重脱节** | 后端 309 条 (路径, 方法) 端点，演示数据只覆盖 **4** 条 `[已实测]` | 🔴 高 | ✅ 已修（§9 —— 演示改走后端，mock 不再是运行时数据源） |
| 4 | **mock 未覆盖的路径静默返回 `null`** | 演示模式下页面显示"空数据"，没有任何提示 | 🟠 中 | ✅ 已修（§6.2-6） |
| 5 | **demo 分支写在共享 UI 代码里** | 同一段 UI 在两种模式下行为不同 | 🟠 中 | ✅ 已修（§9 —— 附件与 MCP 探测的 demo 分支已拆） |
| 6 | **真实 API 端点读 mock 目录** | `GET /api/artifacts/{id}/content` 去读 `/tmp/qzdap-mock-artifacts` | 🟡 低 | ⚠️ 未修 |

另有一批**死配置**：同一个开关有 3~4 个环境变量名，但只有 1 个真的生效 —— 已全部清掉（§4）。

---

## 2. 两条通道的现状

> ⚠️ 本节描述的是**第一轮清理前**的通道形态。第二轮（A2）之后，
> **两条通道共用同一套前端代码、同一个 API 协议**，区别只在后端实例和库 ——
> 见 §9。

### 通道 A —— 演示数据（demo）

| 维度 | 现状 |
|---|---|
| 数据文件 | `frontend/packages/api/src/mock.ts`（6189 行）+ `frontend/web/src/features/*/fixtures.ts` + 各域 `mock-handler.ts` |
| 传输 | `ApiClient` 注入 `mockHandler`，走 `if (this.mockHandler) { ... }` 分支，**不发网络请求** |
| 开关 | `VITE_QZDAP_ENV=demo`（唯一开关，2026-10-28 起去掉了 `VITE_USE_DEMO` 旁路） |
| 后端 | **完全不参与**（`QZDAP_ENV=demo` 在后端几乎没被用到） |
| 依赖 | 不启后端也能跑 |

### 通道 B —— API 数据（development）

| 维度 | 现状 |
|---|---|
| 传输 | `ApiClient` → `fetch` → Vite proxy → gateway :9150 → qzdap-app :9151 → Postgres / Redis |
| 开关 | `VITE_QZDAP_ENV=development`（或不设置） |
| 后端 | `QZDAP_ENV=development`，真实端点 309 条 (路径, 方法) / 248 条路径 `[已实测]` |
| 数据 | 开发库 `qzdap_dev` 里的真实表 —— 但里面混着 demo 种子（见 §3.1） |

### 两条通道的关系

```
                    ┌──────────────── 前端进程 ────────────────┐
                    │  resolveRuntimeConfig()                 │
                    │    VITE_QZDAP_ENV=demo ──► dataMode=demo │
                    │    VITE_QZDAP_ENV=dev  ──► dataMode=dev  │
                    └───────────────┬─────────────────────────┘
                                    │
                    ┌───────────────▼─────────────────────────┐
                    │  ApiClient.request / upload / streamEvents│
                    │    if (mockHandler) → 内存 mock           │
                    │    else             → fetch → 网关 → 后端 │
                    └──────────────────────────────────────────┘
```

**前端这一层是干净的**：mock 分支里没有 fallthrough 到 `fetch`，`fetch` 分支里也没有回头碰 mock。

---

## 3. 混用的 6 个地方（补齐前的快照）

> ⚠️ 本节记录的是**第一轮清理之前**的事实。第一轮已经修掉 1、2、4 三条
> （见 [§6.2](#62-第一轮落地与决策无关的清理)），3、5、6、7 还留着。

### 3.1 🔴 后端在开发库里种 demo 数据

`backend/composition/qzdap_app/src/qzdap/composition/lifespan.py:1227` 的 `ensure_default_resources()`：

| 位置（补齐前） | 事实 |
|---|---|
| `backend/composition/qzdap_app/src/qzdap/composition/lifespan.py` 的 `ensure_default_resources` | 门禁是 `settings.env not in {"development", "test"}` → **development 和 test 会跑，demo 不会跑** |
| 同上 | 建租户 `slug="demo"` / `display_name="Demo Tenant"` |
| 同上 | 建账号 `admin@example.com`、`admin@acme.com`、`user@acme.com`，密码统一是 `dev_admin_password`（默认 `dev-admin-password-change-me`） |
| 同上 | 建 30 个内置工具（echo / reverse / clock / web_search / bash / read_file / …） |

> 补齐后这些搬到了 `backend/composition/qzdap_app/src/qzdap/composition/seeds.py`
> 的 `demo_profile()` / `dev_profile()`，启动时按 `QZDAP_ENV` 二选一。

两个问题：

1. **开发环境按需求不应有 demo 数据，但现在有** —— 而且是弱口令账号。
2. **`QZDAP_ENV=demo` 恰好被排除在外**（白名单是 `{development, test}`）。演示环境跑起来反而是**空的**，demo 数据在开发环境。**这与需求正好相反。**

补充：旧代码有个"若库里已有租户就复用第一个租户"的分支，所以非空开发库不会再多造一个 Demo Tenant；但三个 demo 账号仍会被创建。

### 3.2 🔴 `QZDAP_ENV=demo` 在后端几乎是空壳

`backend/composition/qzdap_app/src/qzdap/composition/settings.py:21` 声明了 `env` 枚举含 `demo`，但全代码库只有一处真正读它：

- `backend/composition/qzdap_app/src/qzdap/composition/container.py:501` —— 判断是否允许 `noop` embedding adapter。

而 `backend/composition/qzdap_app/src/qzdap/composition/settings.py:52-53` 的 `ban_mock_token` / `allow_demo_token` **全代码库零引用**，是纯死配置。

结论：**后端没有"演示环境"这个概念**，只有一个空壳枚举值。

### 3.3 🔴 前端 mock 与后端路由严重脱节

`[已实测]` 数字：

| 指标 | 数值 |
|---|---|
| 后端实际路由 | **314** 条（从 `create_app()` 的路由树里跑出来的，含 `/api/*` 和 `/v1/*`） |
| 其中演示模式有数据（mock 返回非 null） | **4** 条 |
| mock 返回 `null`（演示模式显示空数据） | **307** 条 |
| mock 抛错 | **3** 条 |
| mock 里实现的端点数 | 132 |
| 其中在 `pathMap.ts` 里有映射规则的 | **17** 条 |
| 其余 115 条原样透传，真模式打到后端大多 404 | |

有 demo 数据的只有这 4 条：

```
GET  /api/knowledge/docs
GET  /api/sessions
POST /api/sessions
GET  /api/tasks
```

**pathMap 的"审计标准"没有人守。** `frontend/packages/api/src/pathMap.ts:1-30` 的文件头注释里写着：

> Batch 7 audit 标准: 路径对应 `@router.<verb>("<path>")` 必须存在于 `backend/modules/{module}/.../router.py` 之一

但这只是**一次性手工审计**的记录，**没有任何测试在执行这条标准**。所以它一直在漂移。

### 3.4 🟠 mock 未覆盖的路径静默返回 `null`

`frontend/packages/api/src/mock.ts:6188` 是 mock handler 的兜底 `return null`。

`frontend/packages/api/src/index.ts:107`（`request`）、`:200`（`upload`）、`:276`（`streamEvents`）三处都是 `if (this.mockHandler) { const data = await this.mockHandler(...); return data as T }` —— **拿到 `null` 就原样返回**，不报错。

后果举例：演示模式下发一条消息，`streamEvents` 走 mock 分支：

```ts
// packages/api/src/index.ts:276-281
if (this.mockHandler) {
  const data = await this.mockHandler(path, { ...opts, method: 'POST', ... });
  yield { event: 'message', data };        // data === null
  yield { event: 'done', data: { kind: 'done' } };
  return;
}
```

mock 里**没有** `/api/sessions/{id}/turns/stream` 的实现（`mock.ts:5914-5915` 只有会话列表和创建），所以演示模式下对话**只会得到一条空消息然后立刻 done** —— 界面表现为"助手回了个空"。

### 3.5 🟠 demo 分支写在共享 UI 代码里

| 位置 | 分支内容 |
|---|---|
| `frontend/web/src/features/user/copilot/CopilotPage.tsx:184` | `demoMode` → 附件只写文件名不上传（因为 mock 没实现 attachment 上传） |
| `frontend/web/src/features/agents/AgentsPage.tsx:152` | `demoMode` → 才让"载入演示数据"，否则弹窗拒绝 |
| `frontend/web/src/features/skills/components/CreateSkillWizard.tsx:146` | 同上 |

每个 demo 分支的存在，都对应着 mock 的一个缺口。这不是"风格问题"，而是**契约漂移在 UI 层的表现**。

### 3.6 🟡 真实 API 端点读 mock 目录

`backend/modules/agent_runtime/src/qzdap/modules/agent_runtime/adapter/http/session_router.py:530`：

```python
root = Path("/tmp/qzdap-mock-artifacts").resolve()
```

`GET /api/artifacts/{artifact_id}/content` —— 一个**真 API 端点**去读 mock 目录。写这个目录的 `MockLLMClient`（`backend/libs/llm/src/qzdap_llm/mock.py:96`）只在 `QZDAP_ENV=test` 时启用（`backend/composition/qzdap_app/src/qzdap/composition/container.py:212-218`），所以开发/演示环境下这个端点**永远是 404**。

### 3.7 补充：4 处 `fetch()` 绕过 mock

以下代码直接调 `fetch`，**不经过 `ApiClient`**，因此在演示模式下会打到真实网络：

| 位置 | 用途 | 演示模式下的后果 |
|---|---|---|
| `frontend/web/src/features/auth/login/useLogin.ts:71` | 控制面登录兜底 | 仅在主登录失败且判定"身份服务不可用"时触发（`useLogin.ts:191`），demo 下 mock 登录成功，**基本不会走到**；但边界上仍是一条逃逸路径 |
| `frontend/web/src/features/agents/AgentEditor.tsx:358` | `/api/dev/skills/{name}/invoke` | 演示模式会真发请求 |
| `frontend/web/src/features/user/copilot/blocks/ArtifactCard.tsx:185,207` | 下载产物 | 演示模式会真发请求 |
| `frontend/web/src/features/user/copilot/blocks/AttachmentChip.tsx:24` | 下载附件 | 演示模式会真发请求 |

---

## 4. 死配置清单（2026-10-28 已清空）

### 前端

| 变量 | 原来 | 现在的状态 |
|---|---|---|
| `VITE_QZDAP_ENV` | 唯一真正生效的开关 | ✅ 保留，且是**唯一**开关 |
| `VITE_USE_DEMO` | `VITE_QZDAP_ENV` 为空时的兜底 | 🗑️ **已删** —— 演示模式只能靠 `VITE_QZDAP_ENV=demo` 显式打开 |
| `VITE_DATA_MODE` | 从不读 | 🗑️ **已删**（`.env.example`） |
| `VITE_USE_MOCK` | 从不读 | 🗑️ **已删**（`.env` / `.env.local`） |
| `isDemoApiMode()` | 导出但零调用 | 🗑️ **已删**（`api-mode.ts`） |

前端现在跑在 API 模式，是因为 `frontend/web/.env` / `.env.local` **显式写了** `VITE_QZDAP_ENV=development` —— 不再是"恰好没写"。

另外 `backend/.env.local` 里写过 `VITE_QZDAP_ENV=development`，但 **Vite 只读 `frontend/web/` 下的 env 文件**，那行是无效的 —— 🗑️ **已删**（换成一行注释说明前端的开关在哪）。

### 后端

| 变量 | 原来 | 现在的状态 |
|---|---|---|
| `QZDAP_ENV` | `demo` 值几乎没被用到 | ✅ 保留，并且 `demo` **现在真的会种演示数据**（§7） |
| `QZDAP_ALLOW_DEMO_TOKEN` | `backend/composition/qzdap_app/src/qzdap/composition/settings.py` 里声明但零引用 | 🗑️ **已删**（settings + `.env` + `.env.example` + `deploy/env.*.example`） |
| `QZDAP_BAN_MOCK_TOKEN` | 同上 | 🗑️ **已删**（同上） |

### 前端其它

| 项 | 状态 |
|---|---|
| `x-mock-role` / `x-mock-actor` / `x-mock-permissions` / `x-mock-user-id` 头 | `frontend/web/src/main.tsx:110` 在 demo 模式会发，但**后端从不读**（grep 零结果）。留着无害（后端忽略未知头），但也别指望它起什么作用 |
| `login.demoTitle` / `login.demoRoleUser` / `login.demoRoleAdmin` | 登录页的「体验角色」快捷入口 —— **原来在所有模式下都显示**，包括开发环境（见 §6） |

---

## 5. 已经做对的部分（不要动）

这几条是对的，拆分方案应该保持：

1. **前端传输层不混** —— `packages/api/src/index.ts:107 / :200 / :276` 三处 `if (this.mockHandler)` 分支里没有 fallthrough。
2. **localStorage 按环境隔离** —— `frontend/web/src/lib/environment.ts:40` 的 `runtimeStorageKey` 生成 `qzdap:${environment}:${dataMode}:${name}`，切模式不会串号 / 串 token。
3. **开发模式无视 mock 开关** —— `frontend/web/src/lib/environment.test.ts:23-33` 明确断言 `VITE_USE_MOCK=true` 在 development 下无效。这条**正是需求要的**，只是没有对应的"数据源"层面的强制。
4. **后端 LLM 不混** —— `backend/composition/qzdap_app/src/qzdap/composition/container.py:212-218`：只有 `QZDAP_ENV=test` 才用 `MockLLMClient`，其它一律 `UnavailableLLMClient`（503）或真实 `ModelService`。
5. **后端 `production` / `staging` 不种 demo 租户** —— `lifespan.py:1251` 的白名单不含这两个。

---

## 6. 决策与第一轮落地（2026-10-28）

### 6.1 决策

| 决策 | 选定 | 理由 |
|---|---|---|
| **A —— 演示数据放哪** | **A2：后端 + 独立 demo 库** | "演示数据需要与真实 API 对齐"这条，A1（前端 mock）在架构上做不到 —— mock 是另一份手写的数据，只能靠人力对齐。后端 `QZDAP_ENV=demo` 的空壳已经在 settings 里，补起来比新建一套便宜 |
| **B —— 开发环境用什么数据** | **B1：独立 dev 种子脚本** | 与 A2 同一个形状：脚本 + 独立库，两边都不混 |
| **C —— 前端 mock 怎么办** | 随 A2：前端 mock 降级为**单测夹具**，不再做运行时数据源 | 演示走 A2 之后，运行时 mock 没有存在理由 |
| **推进方式** | 先做与决策无关的清理 | 见 §7.2 |

### 6.2 第一轮落地：与决策无关的清理

这一轮做的是**不管 A/B/C 怎么选都要做**的部分。

| # | 做了什么 | 位置 |
|---|---|---|
| 1 | **清死配置** | 删 `VITE_USE_MOCK` / `VITE_DATA_MODE` / `VITE_USE_DEMO` / `isDemoApiMode()` / `QZDAP_BAN_MOCK_TOKEN` / `QZDAP_ALLOW_DEMO_TOKEN`；`frontend/web/.env(.local)` 显式写 `VITE_QZDAP_ENV=development`；删掉 `backend/.env.local` 里那行 Vite 根本读不到的 `VITE_QZDAP_ENV` |
| 2 | **单一模式开关** | `resolveRuntimeConfig()` 只认 `VITE_QZDAP_ENV`。没写 → development；写 `demo` → demo。演示模式没有旁路开关可走 |
| 3 | **后端种子按环境分流** | 新增 `backend/composition/qzdap_app/src/qzdap/composition/seeds.py`：`demo` env 种 demo 租户 + demo 账号；`development` / `test` env 种 **dev** 租户 + dev 账号。**开发环境不再产生任何 demo 数据**，而 `QZDAP_ENV=demo` 终于会种演示数据（之前正好反着） |
| 4 | **两套独立种子脚本** | `backend/scripts/seed_dev_data.py`（开发测试数据，默认还会**清掉**库里残留的 demo 行）和 `backend/scripts/seed_demo_data.py`（演示数据）。两者幂等，可重复跑 |
| 5 | **登录页按模式隔离** | 登录页的「一键登录」原来在**所有模式**下都摆着 `admin@acme.com` / `user@acme.com`（开发环境也摆），密码还是写死的。现在由 `quickLoginAccounts.ts` 按模式取：demo → 演示账号，开发 → `admin@dev.qzdap.dev`。两套密码不共用 |
| 6 | **mock 兜底显式失败** | `mock.ts` 末尾的 `return null` 改成抛 `E_MOCK_NOT_IMPLEMENTED`。以前未实现的端点静默返回空，页面显示"没有数据"，看不出是缺端点 —— 那正是漂移没人发现的原因 |
| 7 | **pathMap 审计变成测试** | 新增 `backend/composition/qzdap_app/tests/unit/test_frontend_pathmap_contract.py`：pathMap 每条规则指向的 (路径, 方法) 必须真的存在于后端；标了 `unmatched` 的端点后端不能已经实现（否则"未接入"就成了谎报） |
| 8 | **composition 的测试终于会跑** | `pyproject.toml` 的 `testpaths` 加了 `composition` —— 之前 `backend/tests/` 和 `backend/composition/` **都不在 testpaths 里**，CI 从来没跑过它们（生产环境密钥闸门测试也在里面） |

**第 7 项当场查出两处真漂移**（都已修）：

| 漂移 | 修法 |
|---|---|
| `GET /api/api-keys → /v1/identity/users/{uid}/api-keys` —— 后端那个路径只有 POST（签发），没有 GET（列表） | pathMap 的 method 改成 `POST`（method 记的是**后端真实的方法**） |
| `POST /api/release-approvals → /v1/approvals` —— 后端只有 GET（列表），没有创建端点（审批由 agent runtime 内部创建） | 留在 `KNOWN_BACKEND_GAPS` 里并写明原因；后端补上后删掉即可 |

### 6.3 还没做（依赖 A2 / B1）

> 📌 第二轮（A2）之后这一节的进度见 §9.3。

| 项 | 说明 |
|---|---|
| 演示用的独立 demo 库 | 需要在 compose / 部署里加一个 `qzdap_demo` 库 + 一个 `QZDAP_ENV=demo` 的后端实例。种子脚本和 env 开关已经就位，缺的是环境本身 |
| 前端 mock 降级为单测夹具 | 演示走 A2 之后，`mock.ts`（6189 行）不再做运行时数据源 —— 要么删，要么只留单测用 |
| 拆掉 UI 里剩下的 demo 分支 | §3.5 的三处：`frontend/web/src/features/agents/AgentsPage.tsx`「载入演示数据」、`frontend/web/src/features/skills/components/CreateSkillWizard.tsx` 的文件上传、`frontend/web/src/features/user/copilot/CopilotPage.tsx` 的附件只写文件名。demo 走后端之后这些分支应该消失，而不是各写各的 |
| `GET /api/artifacts/{id}/content` 读 mock 目录 | §3.6 —— 真 API 端点读 `/tmp/qzdap-mock-artifacts`。要改成产物表 / 对象存储 |
| 4 处 `fetch()` 绕过 mock | §3.7 —— 演示走 A2 之后这些会真的打后端，得确认每一条都有对应端点 |

---

## 7. 目标状态

### 开发环境（development）

- 数据库里**不含任何 demo 数据**。开发要用的数据来自**明确命名的开发种子脚本**
  （`backend/scripts/seed_dev_data.py`），产出的是"开发测试数据"（dev 租户 /
  `admin@dev.qzdap.dev`），与 demo 数据在命名、目录、脚本上完全分开。
- 后端 `QZDAP_ENV=development` 时只种 dev 那套。
- 前端 `dataMode` 恒为 `development-api`；**应用代码里不允许出现 demo 分支**。
- 演示用 mock 只允许存在于**前端单测**里，不进 dev 运行时。

### 演示环境（demo）

- 数据来源**单一**：后端 API + 独立的 demo 库（决策 A2）。
- 演示库由 `backend/scripts/seed_demo_data.py` 灌，演示账号只有 demo 那套。
- 与真实 API 对齐由**契约测试**保证（§6.2 第 7 项），不再靠一次性手工审计。

---

## 9. 第二轮：演示环境真正立起来（决策 A2 / B1，2026-10-28）

### 9.1 目标状态长什么样

第一轮把"不该混的"清掉了，但**演示环境本身还不存在** —— demo 模式只能靠前端
内存 mock。第二轮按 A2 把它补齐：

```
┌─────────────── 开发环境 ───────────────┐   ┌─────────────── 演示环境 ───────────────┐
│ 前端 :9152  VITE_QZDAP_ENV=development │   │ 前端 :9162  VITE_QZDAP_ENV=demo        │
│        │ /api → proxy                 │   │        │ /api → proxy                 │
│        ▼                                │   │        ▼                                │
│ 后端 :9151  QZDAP_ENV=development      │   │ 后端 :9161  QZDAP_ENV=demo             │
│        ▼                                │   │        ▼                                │
│ Postgres  qzdap_dev                    │   │ Postgres  qzdap_demo                   │
│   admin@dev.qzdap.dev                       │   │   admin@acme.com / user@acme.com       │
│   租户 dev                                │   │   租户 demo (…0001)                    │
│ Redis db 0                              │   │ Redis db 1 (前缀 qzdap:events:demo:)   │
└─────────────────────────────────────────┘   └─────────────────────────────────────────┘
```

**前端代码两边完全一样** —— 没有 `if (demoMode)`，没有 mock 注入。
演示数据因此天然与真实 API 对齐：它就是 API 返出来的。

### 9.2 做了什么

| # | 做了什么 | 位置 |
|---|---|---|
| 1 | **建库脚本** | `backend/scripts/ensure_database.py` —— 连 `postgres` 维护库建库（幂等），名字只允许字母数字下划线 |
| 2 | **演示栈启动脚本** | `bin/qzdap-stack/run-qzdap-demo-stack.sh` —— 建库 → 迁移 → `seed_demo_data.py` → 起 demo 后端 → 起演示前端。配套 `stop-qzdap-demo-stack.sh` / `status-qzdap-demo-stack.sh` |
| 3 | **demo 端口 / 库 / Redis 旋钮** | `bin/qzdap-stack/qzdap-env.sh`：`QZDAP_DEMO_APP_PORT=9161`、`QZDAP_DEMO_DATABASE_URL=…/qzdap_demo`、`QZDAP_DEMO_REDIS_URL=redis://…:9154/1`、`QZDAP_DEMO_EVENT_REDIS_STREAM_PREFIX=qzdap:events:demo:`、`QZDAP_DEMO_FRONTEND_PORT=9162` |
| 4 | **前端不再注入 mock** | `frontend/web/src/main.tsx` 删掉全部 `wrapMockHandlerWith*` 注入和 `x-mock-*` 头；`ApiClient` 拿到的 mock handler 是 `undefined` |
| 5 | **`apiEnabled` 这个开关被删掉** | 它在新架构下恒为 `true`（两边都走 API），留着只会让人以为"还能关掉 API"。`api-mode.ts` 里那个 `if (!apiEnabled) return ''` 的死分支一并删掉 |
| 6 | **UI 里最后两处 demo 分支拆掉** | `CreateSkillWizard.tsx` 的"模拟 MCP 探测"（硬编码 github/drive/crm 工具列表）→ 两边都调真端点 `/api/admin/skills/mcp/probe`；`CopilotPage.tsx` 的"附件只写文件名"→ 两边都真上传 |
| 7 | **空态也能看到错误提示** | `CopilotPage.tsx` 的 `notices` 原来只在"有消息"分支渲染 —— 空态（默认界面）里"请先打开会话"这类提示完全静默。现在空态也渲染 |
| 8 | **开发账号的域名改成合法的** | `admin@dev.local` → `admin@dev.qzdap.dev`（`.local` 是保留域名，后端 `EmailStr` 会拒掉，详见 §9.3.2） |

### 9.3 拆分效果（实测）

两个库互不相干 —— 直接查 Postgres：

```
$ docker exec qzdap-postgres psql -U postgres -d qzdap_dev  -tAc "select distinct tenant_id from users"
31d19ce5-b15d-4356-9e14-cd445bb0fde8          ← dev 租户

$ docker exec qzdap-postgres psql -U postgres -d qzdap_dev  -tAc "select email from users order by email"
admin@dev.qzdap.dev

$ docker exec qzdap-postgres psql -U postgres -d qzdap_demo -tAc "select distinct tenant_id from users"
00000000-0000-0000-0000-000000000001          ← demo 租户

$ docker exec qzdap-postgres psql -U postgres -d qzdap_demo -tAc "select email from users order by email"
admin@acme.com
user@acme.com
```

**没有一条 demo 数据漏进开发库，也没有一条开发数据漏进演示库。**
账号、密码、租户、库、Redis db 全部不共用。

演示栈跑起来之后的实测：

```
$ curl -s http://127.0.0.1:9161/healthz   → 200
$ curl -s http://127.0.0.1:9161/readyz    → 200
$ curl -s http://127.0.0.1:9162/          → 200   （演示前端）
$ curl -s -X POST http://127.0.0.1:9162/v1/identity/login \
       -d '{"email":"admin@acme.com","password":"demo-password-change-me"}'
  → 200，token 里 tenant_id=00000000-0000-0000-0000-000000000001
```

**两边的账号互相登不进去**（不只是"数据不共享"，是**凭据也不通用**）：

```
$ curl -s -X POST http://127.0.0.1:9151/v1/identity/login \
       -d '{"email":"admin@acme.com","password":"demo-password-change-me"}'   # 开发后端收演示账号
  → 401 INVALID_CREDENTIALS
$ curl -s -X POST http://127.0.0.1:9161/v1/identity/login \
       -d '{"email":"admin@dev.qzdap.dev","password":"dev-admin-password-change-me"}'  # 演示后端收开发账号
  → 401 INVALID_CREDENTIALS
```

### 9.3.1 浏览器实测（两个前端各跑一遍）

用 headless Chrome 分别打开两个前端，点了角色快捷登录，看网络请求：

| | 演示前端 :9162 | 开发前端 :9152 |
|---|---|---|
| 登录页角色 chip | **普通用户登录** + **管理员登录** | **只有管理员登录**（dev 账号） |
| 登录请求 | `POST /v1/identity/login` | `POST /v1/identity/login` |
| 登录后 | `GET /api/admin/overview/summary` → 落到 `/admin/overview` | 同左 |
| 右上角徽标 | **演示环境** | 当前工作空间 |
| 左下角账号 | **Demo Admin** | Dev Admin |
| 控制台报错 | 无（只有一条 SVG `path` 的老 warning） | 同左 |

关键点：**演示前端走的也是真 API**（`POST /v1/identity/login`），
不是内存 mock —— 演示数据就是后端返的，所以跟真实 API 天然对齐。

### 9.3.2 开发账号的域名踩了个坑

原来的开发账号是 `admin@dev.local`。**`.local` 是保留域名，后端的
`EmailStr` 校验会直接拒掉**，登录请求根本到不了业务逻辑：

```
422 {"detail":[{"type":"value_error","loc":["body","email"],
      "msg":"value is not a valid email address: The part after the @-sign
             is a special-use or reserved name that cannot be used with email."}]}
```

也就是说**开发环境的快捷登录一直是登不进去的** —— 不是"分开"造成的，
是账号名本身不合法。已改成 `admin@dev.qzdap.dev`（普通域名，能过校验）。
`.local` / `.test` / `.example` 这类保留域名都不能用。

### 9.4 §6.3 的进度

| 项 | 状态 |
|---|---|
| 演示用的独立 demo 库 | ✅ 第 8 轮做完（§9.2 第 1~3 项） |
| 前端 mock 降级为单测夹具 | ✅ 第 10 轮做完 —— `mock.ts` 不再从 `@qzdap/web-api` 主入口导出，改走 `@qzdap/web-api/mock` 子路径；运行时的模块图里已经没有它（§10.3） |
| 拆掉 UI 里剩下的 demo 分支 | ✅ 第 8 轮拆了附件 + MCP 探测；第 10 轮拆了 `AgentsPage` 的「载入演示数据」（§10.3） |
| `GET /api/artifacts/{id}/content` 读 mock 目录 | ✅ 第 10 轮改成**只在 `QZDAP_ENV=test` 下**提供，其它环境明确 404（§10.2） |
| 4 处 `fetch()` 绕过 mock | ✅ 第 10 轮把产物/附件下载改走 `ApiClient.download()`（带 token）；`useLogin` 的登录兜底打的是公开端点，`AgentEditor` 的 dev 试运行本来就自己带 token（§10.3） |

### 9.5 演示内容（第二、十轮补齐）

第一轮时 demo 种子只灌了**租户 + 两个账号 + 30 个内置工具**，**没有任何业务内容** ——
演示环境打开是空的。现在补齐了四个域：

| 域 | 数量 | 种子函数 | 走的真实路径 |
|---|---|---|---|
| 智能体 | 5 | `seed_demo_agents()` | `AgentCatalogService.create()` → `CatalogAgent.create()` → `apply_patch()` → `publish()`（**带 `versions[0].snapshot` 版本快照**，`version = v1`） |
| 技能 | 3 | `seed_demo_skills()` | `SkillService.create()` + `update(status=published)`（**Skill.create 强制 draft，不发布的话用户侧目录是空的**） |
| 工作流 | 3 | `seed_demo_workflows()` | `OrchestrationService.create()`，`boundAgents` 绑的是**真智能体 id**（按名字解析，不是悬空 id） |
| 知识库 + 文档 | 2 库 / 3 文档 | `seed_demo_knowledge()` | `KnowledgeService.create_kb()` + `ingest_doc()`（本地切块，**不调嵌入模型**） |
| 多轮对话 | 3 段 / 15 条消息 | `seed_demo_conversations()` | 直接写 `agent_sessions` + `agent_session_messages`（**模拟数据，不调模型**） |
| 三层记忆 | 3 / 5 / 3 条 | `seed_demo_memory()` | 直接写 `admin_memory_l1/l2/l3`（**聊天提炼不出来，所以造一批**；见 §11.2） |

智能体分类覆盖销售支持 / 客服应答 / 数据分析 / 文案创作 / 企业通用 五类；
每个智能体引用的工具名都取自 `BUILTIN_TOOL_SPECS`（不会调不到工具）；
`prompts.user` 里以 `-` 开头的行会被 `to_catalog_dict()` 取成开场白。

**隔离**：判断写在每个种子函数内部 —— `profile.label != "demo"` 直接返回空列表，
**连 session 都不碰**（测试故意传 `session=None`，碰了就会炸而不是悄悄写进开发库）。

**幂等**：按名字去重，重复跑种子脚本 / 重启演示后端都不会塞出第二份。

```bash
$ docker exec qzdap-postgres psql -U postgres -d qzdap_demo -tAc \
    "select 'agents='||(select count(*) from admin_agents)
         ||' skills='||(select count(*) from admin_skills)
         ||' workflows='||(select count(*) from admin_workflows)
         ||' kbs='||(select count(*) from admin_knowledge_kbs)
         ||' docs='||(select count(*) from admin_knowledge_docs)"
agents=5 skills=3 workflows=3 kbs=2 docs=3

$ docker exec qzdap-postgres psql -U postgres -d qzdap_dev -tAc "select count(*) from admin_agents"
0
```

#### 多轮对话（模拟数据，不接模型）

演示环境**不接 LLM 供应商也能有"聊过的记录"** —— `seed_demo_conversations()`
直接写会话与消息：

| 项 | 内容 |
|---|---|
| 会话 | 3 段：`上周各渠道毛利对比` / `本周新线索分派` / `导出功能偶发失败的标准回复` |
| 归属 | 分别挂在 `user@acme.com`（2 段）和 `admin@acme.com`（1 段）名下 |
| 内容 | 每人 5 条消息：user / tool / assistant 交替，含一次工具调用（`csv_query`、`web_search`） |
| 幂等 | 按「owner + 标题」去重 |

注意：前端加载历史会话时会**过滤掉 `role='tool'` 的消息**
（`CopilotPage.tsx:214`），所以工具调用在界面上看不到 —— 这跟真实对话
重载后的表现一致；工具消息的作用是让历史记录本身是真实的。

**浏览器实测**（演示前端 :9162）：

| 页面 | 结果 |
|---|---|
| `/copilot` | 会话列表有演示会话；点开「上周各渠道毛利对比」能看到完整的多轮问答 |
| `/admin/agents`（管理员） | 「5 个智能体 · 5 已发布」，逐条列出 |
| `/agents`（普通用户） | 「开放 5 · 已选用 0」，点「浏览并选用」抽屉里 5 个智能体，每个都有「选用」和「开始对话」 |
| `/skills` | 「可浏览 3」 |
| `/knowledge` | 「可浏览 3」（3 篇文档） |
| `/automations` | 工作流目录里 3 个（2 个已发布 / 1 个草稿） |
| `/admin/memory` | 「3 条短期会话 · 5 条长期记忆 · 3 条团队知识」；新建 / flush / 确认 / 晋升全部可点 |
| `/copilot` | 「与企智搭平台向导对话」，开场白就是种进去的那句「企智搭能接哪些类型的知识库？」 |

### 9.6 对话还差最后一步：LLM 供应商

演示智能体现在能选、能开会话，**发消息会拿到 503** —— 因为演示环境还没配 LLM 供应商。
这是**故意的**：仓库只在 `QZDAP_ENV=test` 下才用 Mock LLM，demo 环境不假装有模型。

演示智能体的 `model` 字段统一是 `deepseek-chat`（`DEMO_AGENT_MODEL`）。
运营在 `/admin/models` 建供应商时，**上游模型 id 用这个名字**，这些智能体就能直接对话
（`SqlCatalogModelResolver.resolve()` 按 `upstream_model` 匹配同租户同工作空间的模型行）。

顺带修掉一个一直存在的 bug：`CopilotPage` 里那句"未配置 LLM 供应商"的引导语
原来靠正则匹配错误文案里的 `(HTTP 503)`，而流式请求的消息是
`流式请求失败（HTTP 503）` —— **全角括号**，正则从来没匹配上，提示语一直退化成原始报错。
现在改成看结构化的 `status` / `code`（`normalizeError`），并补了回归测试
（`CopilotPage.llm-unavailable.test.tsx`）。

---

## 10. 第八～十轮：认证边界与遗留清理

### 10.1 发现：整个 API 都可以匿名读写

把 §9 那份烂掉的契约测试捞回来重写时，发现了一件比它本身严重得多的事。

`backend/tests/contract/test_openapi_headers.py` 断言"每个受保护的路由都要声明
`X-Tenant-Id` 请求头" —— 它断言的是**头部驱动**时代的模型，而且从没被执行过
（`backend/tests/` 不在 pytest 的 `testpaths` 里）。今天租户来自 **JWT 的 `tid`**，
请求头只是交叉校验，所以这份契约的**前提**已经过时了。

但把它当成线索去查，发现了真的洞：

```
$ curl -s -H "X-Tenant-Id: …" -H "X-Workspace-Id: …" \
       http://127.0.0.1:9161/api/catalog/agents      # 完全没有 Authorization
[{"id":"…","name":"销售线索洞察助手", …}]

$ curl -s -X POST -H "X-Tenant-Id: …" -H "X-Workspace-Id: …" \
       -d '{"name":"未授权写入测试"}' \
       http://127.0.0.1:9161/api/admin/agents         # 完全没有 Authorization
{"id":"bee70640-…","name":"未授权写入测试", …}          # ← 建成了
```

**原因是一条链**：

```
没有 token → 没有 principal → 没有绑定租户 → ORM 的租户自动过滤退化成空操作
           → 路由开始相信调用方自己填的 X-Tenant-Id
```

也就是说 `X-Tenant-Id` **从来不是边界，只是提示**。全库 310 条 (路径, 方法) 路由里，
**295 条**没有声明任何认证依赖，其中 164 条会改数据。网关（`qzdap-gateway.py`）
和 Envoy 配置也都不做认证 —— 是纯透传。

### 10.2 修法：边界交给中间件

不去给 295 条路由逐个加依赖（那既不现实，又容易漏），而是把边界收进中间件链：

`backend/libs/http/src/qzdap_http/middleware.py` 新增 `AuthRequiredMiddleware` ——
它跑在 Auth 之后、租户/工作区守卫之前：**没有 principal 的非公开请求一律 401**。

```
ErrorEnvelope → Observability → RateLimit → CORS → Auth → AuthRequired
              → TenantGuard → WorkspaceGuard → App
```

公开端点清单走 `Settings.public_paths`（`QZDAP_PUBLIC_PATHS`，逗号分隔）：

```
/healthz,/livez,/readyz,/metrics,/docs,/openapi.json,
/v1/identity/login,/v1/identity/tenants,/v1/channels/*/webhook
```

带 `*` 的是 glob 规则，其余按**精确路径**匹配 —— 精确匹配很重要：
`/v1/channels` 当成前缀会把该前缀下的 CRUD 一起放开，而只想放开 webhook。

改完之后：

```
$ curl -s -o /dev/null -w "%{http_code}" -H "X-Tenant-Id: …" …/api/catalog/agents
401
$ curl -s -o /dev/null -w "%{http_code}" -X POST -d '{"name":"x"}' …/api/admin/agents
401
$ curl -s -o /dev/null -w "%{http_code}" …/api/sessions
401
$ curl -s -o /dev/null -w "%{http_code}" …/healthz
200
```

**这个改动牵出了前端一处真问题**：产物/附件下载用的是裸 `fetch`，不带
`Authorization` —— 以前能通是因为那个端点根本不校验。现在下载改走
`ApiClient.download()`（新加，带 token + 上下文头）。

### 10.3 契约测试重写 + `backend/tests` 进 CI

新的 `backend/tests/contract/test_auth_required.py` 守的是**今天**的边界：

| 断言 | 守什么 |
|---|---|
| `test_public_paths_resolve_to_real_routes` | 公开端点清单里的每条规则都指向真实路由（防拼错 / 路由改名后忘了改） |
| `test_public_paths_do_not_expose_mutating_routes` | 公开端点不能盖住会改数据的路由（防"顺手把前缀放宽了"） |
| `test_webhook_pattern_only_covers_the_webhook` | glob 规则不会连 CRUD 一起放开 |
| `test_anonymous_requests_are_rejected` | 匿名访问真的被拒（发 HTTP 请求，不是看代码） |
| `test_anonymous_write_is_rejected` | 匿名**写**也被拒 |
| `test_public_endpoints_stay_reachable` | 探针不能被误锁 |

`backend/pyproject.toml` 的 `testpaths` 加上了 `tests` —— 之前 `backend/tests/`
**从来没被 CI 收集过**。实测把中间件那行注释掉，这 8 条断言立刻红。

同时新增 `backend/tests/shared/route_table.py`：把 FastAPI 的路由摊平成
`(路径, 方法, 依赖图)`。**不能直接遍历 `app.routes`** —— 这个 FastAPI 版本
(0.141) 把 `include_router` 包成 `_IncludedRouter`，路由是延迟挂载的，
`route.path` 上只有局部路径（§8 末尾那条坑）。

### 10.4 前端 mock 真正退役

`packages/api/src/index.ts` 原来有 `export * from './mock'` —— 6198 行 mock
静态挂在主入口上。改成子路径导出：

```json
"exports": {
  ".": "./src/index.ts",
  "./mock": "./src/mock.ts",
  "./mock-adapter": "./src/mockAdapter.ts"
}
```

实测：dev server 的模块图里已经没有 `mock.ts`（只剩 index / pathMap /
responseAdapters / camelizeKeys 四个模块）。**生产产物大小没变** ——
Rollup 本来就把没人用的再导出 tree-shake 掉了；改的是**耦合**和**意图**：
主入口不再假装 mock 是 API 客户端的一部分。

### 10.5 `AgentsPage` 的 demo 分支

`AgentsPage.tsx` 里的「载入演示数据」原本只在 demo 模式可用（开发模式会弹
"不能载入演示数据"）。演示环境有了真种子之后，这个口子没必要了 ——
**整块删掉**（含 `ImportExportModals.tsx` 里的示例数据按钮），
两种模式的导入流程完全一致：上传真实文件。

前端现在只剩两处按模式分叉，都是**需求本身要求的**：

| 位置 | 为什么保留 |
|---|---|
| `quickLoginAccounts.ts` | 演示走演示账号、开发走开发账号 —— 两套凭据不共用，这是拆分的核心 |
| `LoginPage.tsx` | 演示环境的标题文案不同 |

### 10.6 `GET /api/artifacts/{id}/content` 不再读 mock 目录

这条路由本来就只服务于 `QZDAP_ENV=test` 下的 `MockLLMClient`。以前是
"目录不存在就 404"，看起来像坏了；现在**明确地**只在 test 环境提供，
其它环境直接 404 并说明原因。

---

## 11. 第十一轮：记忆的写路径 + 收藏按钮的真 bug

### 11.1 记忆管理页整块是只读的

`/admin/memory` 的**六个**写操作，前端调得挺欢，后端一个端点都没有：

| 前端调用 | 后端 | 后果 |
|---|---|---|
| `POST /api/admin/memory/l1/{id}/flush` | 无 | 单条 flush → 404 |
| `POST /api/admin/memory/l1/flush-all` | 无 | 全部 flush → 404 |
| `PATCH /api/admin/memory/l2/{id}` | 无 | 确认/退休 L2 → 404 |
| `POST /api/admin/memory/l2/promote` | 无 | L2→L3 晋升 → 404 |
| `PATCH /api/admin/memory/l3/{id}` | 无 | 发布/下线知识 → 404 |
| `POST /api/admin/memory/l3` | 无 | **「新建知识」按钮直接 `window.alert('尚未实现')`** |

后端只有 12 个 GET —— 记忆模块整个是**只读目录**。

这一轮补齐了全部六个端点（`modules/memory/.../adapter/http/router.py`），
配套：

* 领域模型补了 `L3Entry.create()` 工厂（`domain/entities.py`）——
  新建知识走**真实领域模型**，不是路由里手搓 dataclass。
* 仓储补了 `MemoryCatalogRepository.update_l3()`（端口 + SQL 实现）。
* 服务层补了 `flush_l1 / flush_all_l1 / update_l2 / promote_l2 /
  create_l3 / update_l3`，都带**工作区归属校验** —— 别的��作区的 id 一律
  404，不是 403（不泄露"存在但无权"）。
* 写路由挂 `_require_active_workspace`，跟 knowledge 模块同一套写法。

**晋升写的是草稿**：前端 `PromoteMemoryModal` 的文案本来就写着
"晋升后会写入 L3 · 草稿状态，管理员审核后发布" —— 后端之前没有端点，
没人对过这句话。现在后端跟文案一致了，`L3` 列表里能看到草稿，
点「发布」才生效。手工新建的知识默认**直接发布**（管理员明确的动作）。

### 11.2 演示环境补上三层记忆

真实记忆是**聊天时提炼**出来的。演示环境不接模型 → 没有聊天 → 记忆管理页
一片空白。新增 `seed_demo_memory()`：L1 会话 3 条 / L2 事实 5 条 /
L3 知识 3 条 / 晋升事件 6 条。

**幂等策略跟其它域不一样**：记忆是累积出来的，重复种会把真实记忆冲掉 ——
所以工作区里**已经有记忆行就整体跳过**，不是按名字去重。

### 11.3 收藏按钮：连点两个，丢一个

用户侧五个页面（智能体 / 技能 / 知识 / 工作流 / 团队）都有"收藏"，
写法一样：

```ts
favoriteMutation.mutate({ id, on }, { onSuccess: () => setFavorites(...) })
```

**React Query v5 的 observer 换人会把先发那次调用的回调丢掉** ——
`observer.mutate()` 里 `removeObserver(this)` 之后新 mutation 接管 observer，
前一个 mutation 完成时**不再通知**，于是它的 `onSuccess` 永远不跑。
表现是：快速收藏两个条目，第一个的星标不亮。

修法有两条，缺一不可：

1. **用 `mutateAsync` 不用 `mutate`** —— 每次调用拿到自己那个 promise，
   跟 observer 换人无关（`useApiMutation` 走的是 `useMutation`，`mutateAsync` 一直在）。
2. **本地状态用「设置」不用「切换」** —— 新的 `applyFavorite(current, id, on)`
   把列表写成服务端确认过的样子，幂等。就算两次回调都回来了，
   「切换」语义也会把同一个条目翻回去。

涉及文件：`features/user/{agents,skills,knowledge,automations,team}/` +
新增 `features/user/favoriteState.ts`。

### 11.4 前端测试：40 个文件 / 130 个用例 → 0

**根因只有一个**：query key 的形状过期了。测试里手拼的 key 少了
`runtimeStorageKey('query')` 那一段（按业务环境隔离缓存用的），
预置的数据页面读不到 → 缓存 miss → 页面空白。
**而且这种错不会报错**，只会让 40 个测试文件集体变红。

修法不是逐个改测试，而是把 key 的算法**收成一处**：

```ts
// services/query.ts
export function apiQueryKey(key, opts?): readonly unknown[] {
  return [...key, opts?.workspaceId ?? 'w1', runtimeStorageKey('query')];
}
```

`useApiQuery` 和测试预置缓存都调它。顺带发现 `pageQueryKey(X, 'seg')` 的
第二个位置参数是 `workspaceId` 不是路径段 —— 多段 key 会被悄悄改写。
现在签名收成**选项对象**，传错字符串直接是类型错误。

> **查询参数不进 key**：每个页面都是拿整份列表再在客户端过滤
> （后端那些目录端点本来也不支持过滤参数），按过滤条件切 key 只会让
> 缓存碎片化、白白多发请求。

### 11.5 `packages/api` 里剩下那 5 个失败：三处陈旧夹具

web 包全绿之后，`packages/api` 还剩 5 个失败。查下来是**同一个 mock 的三处夹具跟现实脱节**：

| 症状 | 真相 | 修法 |
|---|---|---|
| `mockSkills` 里找不到 `s3` | `skillAssetDefaults` **有** s3 的元数据（owner 张睿 / 可观测性组 / 只读+日志），测试也在用 —— 从迁移那个 commit（`04d0e2b`）起夹具就缺了，**这批测试从来没绿过** | 把 s3（`log-query`，只读）补回 `mockSkills`，让夹具跟自己的默认表一致 |
| `demoNotice` 里找不到「演示」 | 文案早就换了：现在是「平台内置条目用于冷启动；生产来源以 Registry 同步与工作区晋升为主」 | 断言改成 `Registry`（跟 `meta.channels` 对得上，而不是绑一句文案） |
| `POST /api/workflows/wf1/publish` 抛「高风险工作流缺少审批、审计或回滚路径」 | mock 的治理规则要求**外部写 + 审批 + 审计 + 回滚**四件齐，而 wf1（入职办理与权限开通）只有 approval / audit —— **没有回滚节点**。偏偏 v4 的描述就写着「新增分支：回滚路径」 | 给 wf1 补一个 `compensate` 节点（撤销已开通的账号权限），只进 v4（v1/v2/v3 按节点 id 白名单滤，不受影响） |

第三条值得单独说：**不是测试写错了，是演示用的旗舰工作流在 mock 里根本发布不了**。
夹具的描述和它自己的节点对不上 —— 修夹具比改断言对。

---

## 8. 复现本文的实测数字

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

# 演示数据覆盖率：4 / 309
#   逐条调 mockHandler(path, {method})，抛 E_MOCK_NOT_IMPLEMENTED 记为未实现
```

> ⚠️ **别用遍历 `app.routes` 的方式统计路由**。这个 FastAPI 版本把
> `include_router` 包成 `_IncludedRouter`，路由是**延迟**挂载的：
> `route.path` 上只有局部路径（`/login`），前缀要等匹配时才补上
> （`/v1/identity/login`）。遍历 `app.routes` 会拿到一张**错的**路径表 ——
> 本文的初稿就是这么错的（把 309 算成 314，还差点把一条正确的规则判成漂移）。
> **OpenAPI schema 才是运行时真正对外暴露的那份路径。**
