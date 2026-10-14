# 功能审查方案 · 方法论框架
>
> 适用范围:`QiZhiDaAgentPlatform`(Python 3.12 + FastAPI 模块化单体 / React 18 + Vite + pnpm workspace 管理侧与用户侧双 SPA / `POST /v1/sessions/{id}/turns` 8 类 SSE chunk)
> 本文件只描述"如何审",不输出"审到了什么"——具体 finding 由各专项子 agent 产出,主会话汇总。

---

## 0. 设计原则

1. **从契约出发**:先确认 spec / OpenAPI / 类型契约,再验证实现是否兑现。
2. **从外向内**:先黑盒(curl / playwright)再白盒(读源码),保证黑盒失败时回退到白盒定位时不带偏见。
3. **以角色驱动**:每个用例明确"谁在用、要达成什么",避免纯实现视角的"我跑通了"。
4. **证据可回放**:每条 finding 必须有可复现的命令、HTTP trace、SSE 切片或截图。
5. **维度正交**:八个维度之间相互独立、互不替代,防止"测了单元测试就以为测了鲁棒性"。

---

## 1. 审查维度清单

每条检查项的写法:`[维度] 子项 — 关注点`。

### 1.1 完整性(Completeness)
- [ ] **功能完成度** — spec 中的每个用户故事是否都有对应实现?是否仍存在 TODO / FIXME / mock-handler 兜底?
- [ ] **API 端点覆盖** — OpenAPI 列出的每个路径是否真存在于路由表?返回码是否覆盖 200/400/401/403/404/409/422/5xx?
- [ ] **流式契约完整** — 8 种 SSE chunk(message / tool_call / tool_result / skill_invocation / memory_write / knowledge_search / usage / done)是否能在一个真实 turn 中全部跑出?`done` 必现?
- [ ] **角色/权限矩阵** — admin / member / integrator 三种身份下,每个端点的可见性、可调用性是否符合预期?
- [ ] **迁移与种子** — alembic 迁移链与 seed 脚本能否在空库上重放?是否依赖未文档化的"演示模式"?

### 1.2 正确性(Correctness)
- [ ] **业务规则** — 关键不变量(会话状态机、token 计费、并发租户隔离、工具调用幂等)是否在源码中显式断言?
- [ ] **数据正确性** — 数据库读写、缓存一致性、向量检索召回是否经过断言测试?
- [ ] **时序正确性** — 流式 chunk 的发出顺序、最终一致性窗口、重放一致性是否被验证?
- [ ] **错误码语义** — 同一类失败(例:rate limit)在不同端点是否返回一致的错误结构?
- [ ] **i18n / 时区 / 货币** — 文案、货币、时间戳是否在边界条件下仍正确?

### 1.3 鲁棒性(Robustness)
- [ ] **异常路径** — provider 5xx、token 过期、SSE 断连、工具超时、向量库不可达是否都有降级?
- [ ] **边界输入** — 超长 prompt(>100K token)、空 session、并发同写、重复提交、重放?
- [ ] **资源耗尽** — 大消息体、并发连接数激增、内存队列背压、连接泄漏?
- [ ] **优雅降级** — provider 不可用时是否仍可"部分能力可用",而不是整页白屏?
- [ ] **重试与幂等** — 客户端断线重连后,SSE 是否会重复推送已完成 chunk?服务端是否有去重键?

### 1.4 安全性(Security)
- [ ] **认证授权** — JWT / session cookie 校验、过期刷新、跨租户越权(IDOR)、最小权限?
- [ ] **注入防护** — SQL 注入、prompt 注入、模板注入、路径穿越、SSRF(provider / tool)是否有清洗?
- [ ] **数据脱敏** — 日志 / trace / 错误响应中是否泄漏 PII、API key、prompt 原文?
- [ ] **密钥与配置** — `.env.example` 与实际加载路径是否一致?是否在仓库泄露过密钥?
- [ ] **CORS / CSRF / SameSite** — 管理侧与用户侧不同源的策略、跨站请求伪造防护?
- [ ] **审计日志** — 管理员动作、登录、密钥调用是否进入审计流?

### 1.5 可观测性(Observability)
- [ ] **链路追踪** — 一次 turn 是否能贯穿到 provider / tool / vector store 的 trace_id?
- [ ] **指标** — 是否有 turn 成功率、TTFT、chunk 间隔、tool 调用次数、token 用量的指标?
- [ ] **日志级别** — 生产默认 INFO,但错误路径是否包含 stack 与上下文?
- [ ] **SSE 调试体验** — 客户端是否能拿到 `x-request-id` / `x-trace-id` 并在 UI 展示?
- [ ] **告警可定义** — 是否暴露 `/metrics`(Prometheus)或等价端点?

### 1.6 一致性(Consistency)
- [ ] **架构一致性** — import-linter 边界是否被新增模块破坏?六边形分层(域/应用/接口/基础设施)是否被新代码绕过?
- [ ] **命名 / 风格一致性** — 命名约定、错误响应结构、pydantic 模型命名是否统一?
- [ ] **前后端契约一致性** — 前端 TS 类型与后端 Pydantic schema 是否同源生成 / 同步更新?
- [ ] **文档一致性** — README、OpenAPI、内联 docstring 三者描述同一行为?
- [ ] **跨模块一致性** — 类似功能(例:两次审计 list + filter + paginate)是否共用同一抽象?

### 1.7 可测试性(Testability)
- [ ] **可注入性** — provider / DB / vector store 是否能通过依赖注入被替换为 fake / mock?
- [ ] **可重入性** — 测试能否并发跑、不依赖全局状态、不依赖种子数据?
- [ ] **覆盖率** — 关键路径(会话、turn、tool 调用、权限校验)单测覆盖率是否 ≥ 80%?
- [ ] **可回放** — SSE 流是否能用录制的 fixture 在测试中重放?
- [ ] **契约测试** — 是否有针对 OpenAPI 的 schema 校验、对前端类型的双向校验?

### 1.8 用户体验(UX)
- [ ] **加载与骨架** — 异步前端,关键页是否有 skeleton / 渐进渲染 / 不会"白屏闪一下"?
- [ ] **错误友好度** — 401 / 403 / 5xx 是否落到 toast / inline / 重登录引导,而不是 raw stack?
- [ ] **流式体感** — TTFT、token 间隔、typing 指示是否顺滑?长回复是否自动滚动?
- [ ] **可访问性** — 键盘可达、对比度、ARIA、`prefers-reduced-motion`?
- [ ] **可恢复性** — 用户误操作(关 tab、网络断)是否能续聊?未发送的输入是否本地缓存?

---

## 2. 审查顺序(推荐执行流)

```
┌─ A. 文档与契约冻结(spec / OpenAPI / README / CHANGELOG)
│   └─ 产出:评审基线(版本号、scope、out-of-scope)
├─ B. 环境与依赖准备(venv / pnpm install / docker compose / 演示 vs 开发模式)
│   └─ 产出:可复现的 review 环境,记录 OS / Node / Python / 镜像版本
├─ C. 后端契约验证 — curl + pytest
│   ├─ C1. 路由可达性 / OpenAPI schema 校验
│   ├─ C2. 鉴权矩阵(无 token / 错 token / 跨租户)
│   ├─ C3. 错误码语义枚举(每个端点 1xx 失败用例)
│   └─ C4. 流式端到端(SSE 8 种 chunk 重放)
├─ D. 前端契约验证 — vitest + playwright
│   ├─ D1. TS 类型与后端 schema 漂移检测
│   ├─ D2. 关键页面快照 + 交互(登录、列表、详情、试运行)
│   ├─ D3. 流式 UI 行为(中断、续传、错误态)
│   └─ D4. 管理 / 用户侧权限边界
├─ E. 源码白盒 — grep + 阅读
│   ├─ E1. import-linter 边界、循环依赖
│   ├─ E2. 错误处理集中点(provider / tool / vector)
│   ├─ E3. 危险函数清单(eval / subprocess / 反序列化 / SSRF 出口)
│   └─ E4. 配置与密钥加载路径
├─ F. 边界场景与故障注入
│   ├─ F1. 超长 prompt / 超大并发
│   ├─ F2. provider / vector / DB 故障注入(toxiproxy / monkeypatch)
│   └─ F3. SSE 断连、重连、重放
├─ G. 性能、安全、可观测
│   ├─ G1. locust 关键 turn 路径压测,记录 P50 / P95 / P99
│   ├─ G2. bandit / semgrep / npm audit / pip-audit
│   └─ G3. trace / metric / log 三件套冒烟
└─ H. 汇总:维度自检表 + 风险矩阵 + 给主会话的报告
```

总耗时(单人):中等项目 2–3 工作日;每加一个模块 +0.5 日。多人并行时建议 **C / D / E 并行,F / G 串行**,H 由主会话回收。

---

## 3. 审查产出格式(每条 finding)

```markdown
### F-001 <一句话标题,动词开头>

- **严重度**:P0 / P1 / P2 / P3
- **类别**:完整性 | 正确性 | 鲁棒性 | 安全性 | 可观测性 | 一致性 | 可测试性 | UX
- **位置**:`backend/modules/foo/router.py:142` 或 `frontend/web/src/pages/AgentDetail.tsx:88`
- **证据**:
  - 命令:`curl -i ...`
  - 响应:`HTTP/1.1 500 ...` 或截图路径
  - 关键源码片段(≤10 行)
- **影响**:谁受影响(admin/member/integrator)、触发条件、爆炸半径。
- **复现**:3 步以内的最小复现。
- **建议修复**:方向性建议(不写完整 patch),给出首选方案 + 备选方案 + 取舍。
- **关联**:关联 finding ID、相关 spec 章节、相关 issue/PR。
- **状态**:Open | Accepted | In Progress | Fixed | WontFix
- **审计员**:agent 名 + 时间戳。
```

**表格汇总**(主会话一次性生成):

| ID | 严重度 | 类别 | 标题 | 位置 | 状态 |
|----|--------|------|------|------|------|
| F-001 | P0    |      |      |      |      |

---

## 4. 审查工具栈

### 4.1 后端

| 工具 | 用途 | 典型命令 |
|------|------|---------|
| `uvicorn` / `fastapi --reload` | 本地起服务 | `uvicorn app.main:app --port 8000 --reload` |
| `curl` / `httpie` | 手工验证端点 | `curl -N -H "Authorization: Bearer $T" .../turns -d @req.json` |
| `pytest` + `httpx.AsyncClient` | 集成 / 契约测试 | `pytest backend/tests -x -q -k "test_turn_stream"` |
| `pytest --cov` | 覆盖率 | `pytest --cov=backend.modules --cov-report=term-missing` |
| `schemathesis` | OpenAPI fuzz | `schemathesis run backend/openapi.json --checks=all` |
| `toxiproxy` | 故障注入(延迟、断连) | docker compose 起,前后端切换 BASE_URL |
| `locust` | 压测 | `locust -f locustfile.py --headless -u 50 -r 5 -t 2m` |
| `bandit` / `semgrep` / `pip-audit` | 安全 | `bandit -r backend/modules; pip-audit` |
| `import-linter` | 架构边界 | `lint-imports` |
| `ruff` / `mypy` | 风格 / 类型 | `ruff check backend; mypy backend/modules` |

### 4.2 前端

| 工具 | 用途 | 典型命令 |
|------|------|---------|
| `pnpm dev` | 双 SPA 起服务 | `pnpm --filter web-admin dev` |
| `vite preview` | 生产构建产物验证 | `pnpm build && vite preview --port 4173` |
| `vitest` | 单元 / 组件 | `pnpm vitest run --coverage` |
| `@testing-library/react` | 组件行为 | 同上 |
| `playwright` | E2E / 视觉 | `pnpm playwright test --trace on` |
| `msw`(Mock Service Worker) | 离线契约 | `pnpm vitest --mode=mock` |
| `axe-playwright` | 可访问性 | `pnpm playwright test --grep @a11y` |
| `npm audit` / `pnpm audit` | 依赖漏洞 | `pnpm audit --prod` |
| `eslint` / `tsc --noEmit` | 风格 / 类型 | `pnpm lint; pnpm tsc -p noEmit` |

### 4.3 流式 / 跨端

| 工具 | 用途 |
|------|------|
| `curl -N` / `httpie --stream` | SSE 原始流录制 |
| 自研 `sse-tap`(可选) | 把 SSE 切成 8 类 chunk 的 fixture,供回放测试 |
| `wscat`(如未来引入 ws) | WebSocket 调试 |
| `mitmproxy` | 中间人观察 TLS 内的真实请求 |

### 4.4 命令组织建议

- 一键脚本 `bin/audit.sh` 顺序执行 `lint / type / unit / contract / e2e / security / load`,CI 与本地同源。
- SSE fixture 落到 `tests/fixtures/sse/*.jsonl`,每行一个 chunk,可被前后端共用。
- 任何"复现命令"都要可独立复制粘贴运行,带环境变量前缀(`BASE_URL=... TOKEN=...`)。

---

## 5. 三类角色场景覆盖检查

### 5.1 管理员(Admin)

| 场景 | 检查重点 |
|------|---------|
| 登录 / 注销 / MFA | session 过期、踢下线、多端登录策略 |
| 用户与租户管理 | 创建 / 禁用 / 角色变更、跨租户越权 |
| 智能体(Agent)配置 | 模型 provider 选择、prompt 模板、工具授权、超时 |
| 知识库管理 | 上传、分片、向量化、检索回放 |
| 审计与监控 | 操作日志、token 用量、SSE 异常告警 |
| 试运行 / Dry Run | 试运行不应产生真实副作用 / 计费 |

### 5.2 成员(Member / 用户侧)

| 场景 | 检查重点 |
|------|---------|
| 登录 / 续期 | refresh token 轮换、过期体验 |
| 会话列表 / 新建 / 删除 | 列表性能、删除幂等、回收站 |
| 单轮对话与多轮上下文 | 流式体感、TTFT、长上下文截断策略 |
| 工具调用观察(可见/不可见) | 用户对 tool_call / tool_result 的可见性是否符合产品预期 |
| 中断 / 续传 | 中断后重发不应重复计费、不应重复触发副作用 |
| 引用与导出 | 引用是否可点击回溯到知识库原文?导出格式完整? |
| 错误与降级 | provider 不可用时,前端如何提示,有无兜底文案 |

### 5.3 系统集成方(Integrator / 外部 API)

| 场景 | 检查重点 |
|------|---------|
| API 鉴权 | API key 申请、轮换、撤销、scope 最小化 |
| OpenAPI 完整性 | 所有端点可发现,字段描述、非空约束、可空性一致 |
| 流式接入 | 客户端 SDK 是否处理 SSE 断连、心跳、超时重试? |
| Webhook / 回调 | 签名、重放保护、重试策略 |
| 配额 / 限流 | 限流阈值、429 响应、Retry-After、批量接口 |
| 数据契约稳定性 | 版本号 / `v1` 前缀、向后兼容策略、字段废弃流程 |
| 沙箱 / 隔离 | 集成方租户能否访问他人数据? |

---

## 6. 风险优先级矩阵

| 等级 | 判定准则(满足任一即可) | 例 |
|------|---------------------|----|
| **P0** | 直接导致**数据损坏、安全漏洞、不可恢复故障、计费错误、合规红线**;或核心路径上**任何合法角色无法完成核心动作)。** | 跨租户越权读取;prompt 注入导致越权执行;流式 done 缺失导致客户端永远 loading;扣费但未记账。 |
| **P1** | 影响**主流用户群的关键体验或关键业务能力**,但有 workaround 或仅影响部分角色 / 路径。 | 试运行产生真实扣费;SSE chunk 顺序错乱但能恢复;前端 TS 类型与后端漂移导致构建警告淹没。 |
| **P2** | 影响**次要功能、边缘场景、可观测性、可维护性**,但不影响主流程。 | 错误码语义不一致;日志缺 trace_id;P95 慢 2 倍但未超阈值;命名风格漂移。 |
| **P3** | **代码味道 / 风格 / 文档 / 测试覆盖缺口**,无即时业务影响。 | 长函数 / 重复代码 / 过时注释 / README 不准确 / 测试缺少断言。 |

### 6.1 矩阵的辅助判定

- **可恢复性**:不可逆 → 至少 P1;有审计 + 补偿可降一级。
- **触发概率**:核心路径 100% 触发 → 升级一档;边缘场景保持。
- **影响半径**:全租户 / 全用户 → 升级一档;仅特定配置 / 特定角色 → 保持。
- **可观测性**:静默失败 → 升级一档;有可见告警 → 可降一级。
- **修复成本**:修复 ≤ 1 天 → 不降级;修复 > 1 周但有标准方案 → 不升级;修复 > 1 周且无成熟方案 → 维持原级,标记需要架构讨论。

### 6.2 输出节奏

- P0 / P1:**阻塞**任何合并与上线,24h 内必须关闭或显式豁免(记录 owner + ETA)。
- P2:进入下一迭代 backlog,本轮评审给出修复方向。
- P3:沉淀到代码卫生债列表,按季度清理。

---

## 7. 子 agent 分工建议(与本方法论配套)

为避免一个 agent 把八个维度都做一遍产生"广而不深"的报告,推荐按下列边界拆分:

| 子 agent | 负责维度 | 边界 |
|---------|---------|------|
| backend-contract | 完整性 / 正确性 / 一致性(后端) | 仅 OpenAPI + curl + pytest,不改代码 |
| frontend-contract | 完整性 / 正确性 / 一致性(前端) | 仅 TS 类型 + vitest + playwright,不读后端源码 |
| streaming-e2e | 鲁棒性 / UX(流式体感) | SSE 8 chunk 重放、续传、断连 |
| security | 安全性 | bandit / semgrep / 注入 / 越权 / 密钥 |
| observability | 可观测性 | trace / metric / log 三件套冒烟 |
| performance | 性能 / 鲁棒性 | locust + toxiproxy |
| architecture | 一致性 / 可测试性 | import-linter / 模块边界 / 命名 |

每个子 agent 只产出 **finding 列表**(遵守第 3 节格式),不写修复 patch;主会话负责汇总去重、打风险矩阵、对照 spec 出最终报告。