# 生产部署指南 (LLM 模块 + 全栈)

本文档覆盖企智搭 (QiZhiDa) 平台生产环境部署, 重点是 P6 model 模块(LLM 管理)。

## 1. 前置要求

### 1.1 运行时

- Python 3.12+ (推荐 3.13)
- PostgreSQL 14+ (pgvector 扩展需启用)
- Redis 6+ (事件总线 / 限流)
- (可选) HashiCorp Vault 或 CSI 驱动管理 secrets
- (可选) Kubernetes 1.24+ (现成 manifests 在 `infra/k8s/`)

### 1.2 必需环境变量

```bash
# ── 核心 ──
QZDAP_ENV=production
QZDAP_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
QZDAP_JWT_SECRET=<32 字节 hex, 强随机, 不可提交>
QZDAP_SANDBOX_RUNTIME_URL=https://sandbox.internal/v1
QZDAP_SANDBOX_RUNTIME_SECRET=<32 字节 hex>

# ── LLM 模块 (Phase 1-8) ──
# 32 字节 hex, AES-GCM 加密 admin_model_providers.encrypted_payload 用
# 启动时无此变量 → model_service 加载失败, admin 无法配真实模型
QZDAP_MODEL_MASTER_KEY=<32 字节 hex>

# 速率限制 (composition/main.py RateLimitPolicy 读)
QZDAP_RATE_LIMIT_PER_TENANT_PER_MIN=1000
QZDAP_RATE_LIMIT_PER_API_KEY_PER_MIN=1000
QZDAP_RATE_LIMIT_WINDOW_SECONDS=60

# 默认 LLM (QZDAP_LLM_PROVIDER=mock 被禁用, dev 也按生产走)
QZDAP_LLM_PROVIDER=openai
QZDAP_LLM_BASE_URL=https://api.openai.com/v1
QZDAP_LLM_API_KEY=<通过 vault 注入, 不要用 QZDAP_LLM_API_KEY_REF>
QZDAP_LLM_DEFAULT_MODEL=gpt-4o-mini
```

### 1.3 强烈建议

```bash
# 通过 vault / k8s Secret 注入
QZDAP_JWT_SECRET_REF=vault:secret/data/qzdap#jwt
QZDAP_SANDBOX_RUNTIME_SECRET_REF=vault:secret/data/qzdap#sandbox
QZDAP_DEV_ADMIN_PASSWORD_REF=vault:secret/data/qzdap#admin
QZDAP_MODEL_MASTER_KEY_REF=vault:secret/data/qzdap#model_key
```

## 2. 数据库初始化

### 2.1 迁移

```bash
cd backend
export QZDAP_DATABASE_URL=postgresql+asyncpg://...
uv run alembic -c migrations/alembic.ini upgrade head
```

迁移链当前到 `0041_model_quotas` (Phase 4)。
如需新建 phase, 继续往后加 `0042_*.py`。

### 2.2 关键表 (生产必查)

| 表 | 用途 | 重要性 |
|---|---|---|
| `admin_model_providers` | LLM 供应商配置 (凭据 AES-GCM 加密) | **关键** — 没数据没真模型 |
| `admin_models` | catalog 模型 (deepseek-flash 等) | **关键** — agent 引用 |
| `admin_model_routes` | 路由策略 (Phase 7) | 启用策略路由 |
| `model_quotas` | 配额配置 (Phase 4) | 启用配额 |
| `model_quota_usage` | 滑动窗口计数 | 配额实际起作用 |
| `admin_model_health` | 健康事件 (Phase 5) | 监控 / 告警数据源 |
| `audit_log` | 审计 (Phase 8) | 治理合规 |
| `user_workspaces` | workspace 成员 | 租户隔离 (Phase 9) |

## 3. 启动

### 3.1 本地 / Docker

```bash
# Docker
docker compose -f deploy/docker-compose.prod.yml up -d
# 等 healthz 返回 200
curl http://localhost:9151/healthz
```

### 3.2 Kubernetes

```bash
# 应用 (现成 manifests 在 .claude/worktrees/.../infra/k8s/)
kubectl apply -f infra/k8s/namespace.yaml
kubectl apply -f infra/k8s/secret.example.yaml  # 替换占位
kubectl apply -f infra/k8s/configmap.yaml
kubectl apply -f infra/k8s/deployment.yaml
kubectl apply -f infra/k8s/service.yaml
kubectl apply -f infra/k8s/ingress.yaml
kubectl apply -f infra/k8s/hpa.yaml
kubectl apply -f infra/k8s/networkpolicy.yaml
```

### 3.3 启动后必做

1. **配置 LLM 供应商** (admin 侧 / 模型管理):
   ```bash
   POST /api/admin/models/providers
   Headers: X-Tenant-Id, X-Workspace-Id, X-User-Id
   Body: {name, base_url, protocol, api_key, region}
   ```
   api_key 在 server 端被 AES-GCM 加密 (用 QZDAP_MODEL_MASTER_KEY), 写 `encrypted_payload`。

2. **配置 catalog 模型** (admin 侧):
   ```bash
   POST /api/admin/models
   Body: {name, provider_id, upstream_model, status: 'active', tier, ...}
   ```

3. **创建 agent 选 model**:
   ```bash
   POST /v1/agents/{aid}/versions
   Body: {version_tag, system_prompt, model_id: '<model upstream name>'}
   ```
   (model_id 是 str — router 端解析成 UUID, 未命中 raise 422)

4. **可选: 配路由策略** (Phase 7):
   ```bash
   POST /api/admin/models/routes
   Body: {name, primary_model_id, strategy: 'quality-first', fallback_model_ids: [...]}
   ```
   5 策略: `fallback` / `quality-first` / `cost-first` / `latency-first` (Phase 7)
   注: 当前 agent 系统用的是 `model_id` (str), 路由需手动 wire (Phase 7+ 后续)

5. **可选: 配配额** (Phase 4):
   ```bash
   POST /api/admin/models/{model_id}/quotas (待补)  // 现有 model_quotas 表直接 INSERT
   Body: {period: 'minute', max_requests: 100, max_tokens_in: 1000000}
   ```

## 4. 监控 / 告警

### 4.1 关键端点

| 端点 | 用途 | 频率 |
|---|---|---|
| `/healthz` | 进程存活 | 10s |
| `/readyz` | DB + Redis 可达 | 10s |
| `/api/admin/models/health` | Provider 健康事件流 (Phase 5) | 30s 拉取 |
| `/api/admin/models` | 模型 catalog 状态 | 按需 |
| `/api/tasks` | 用户任务列表 (Round-8) | 按需 |

### 4.2 关键指标 (Prometheus 可抓)

- `admin_model_health.type='incident'` 计数 — provider 异常
- `model_quota_usage.requests` 增长率 — 超额告警
- `audit_log` 中 `event_type='llm.invoke.failed'` 比例 — 失败率
- 业务错误码:
  - `MODEL_NOT_FOUND` / `CREDENTIAL_NOT_FOUND` / `QUOTA_EXCEEDED` (429)
  - `MODEL_ROUTE_EXHAUSTED` (502) — 所有 fallback 都失败
  - `PROVIDER_UNAVAILABLE` (503) — env LLM 是 mock 时返回 (dev 也禁 mock)

### 4.3 健康事件告警建议

```sql
-- 5 分钟内 incident > 10 → 告警
SELECT count(*)
FROM admin_model_health
WHERE type = 'incident'
  AND occurred_at > now() - interval '5 minutes'
GROUP BY provider_id;
```

## 5. 故障排查

### 5.1 Chat 报 `PROVIDER_UNAVAILABLE`

dev 模式禁 mock, 报这个说明:
- 用了 QZDAP_LLM_PROVIDER=mock (拒绝) — 改成 openai / anthropic
- 或 env 没设 LLM config, 走默认 mock 拒绝 — 显式设 QZDAP_LLM_PROVIDER=openai

### 5.2 Chat 报 `CREDENTIAL_NOT_FOUND`

`admin_model_providers.encrypted_payload` 用了不同 master key 加密。
**修复**: 用新 master key 重新加密 (一次性脚本, 查 Phase 1.5 实施时的 re-encrypt 脚本模板)。

### 5.3 Chat 报 `QUOTA_EXCEEDED`

`model_quotas` 配了限额, 已达上限。
**修复**: 调高限额 (admin 侧) 或换 agent (用未限流的 model)。

### 5.4 Chat 报 `MODEL_ROUTE_EXHAUSTED`

路由里所有 model (primary + fallback) 都失败。
**诊断**:
1. 看 `admin_model_health` 最近 5min 的 incident 计数
2. 看 provider 的 API key / 网络可达性
3. 简化: 临时改单 model (去掉 fallback 链)

### 5.5 跨租户污染 (Phase 9 验证)

跑 `test_multi_tenant_isolation.py`:
```bash
cd backend
QZDAP_DATABASE_URL=... QZDAP_MODEL_MASTER_KEY=... \
  uv run pytest modules/model/tests/integration/test_multi_tenant_isolation.py -v
```

## 6. 关键架构决策 (Phase 1-9 总结)

1. **链路打通** (Phase 1+1.5):
   agent.model (str) → CatalogModelResolver → ModelId → LLMPortAdapter → ModelService → 真供应商
2. **失败转移** (Phase 3): ProviderTransportError 触发下一个
3. **故障链** (Phase 7): 4 策略 (fallback / quality-first / cost-first / latency-first)
4. **配额** (Phase 4): 显式 commit 防 rollback 抹掉
5. **健康 + 审计** (Phase 5+8): 显式 commit 同
6. **多租户隔离** (Phase 9): 集成测试覆盖

所有跨模块写 (QuotaService / Health / Audit) 都用 **self.commit** 在 inner, 避免
outer facade 的 rollback 抹掉。修复一个真实生产 bug: ProviderTransportError 时
quota 计数器必须 +1, 不能随业务事务回滚。

## 7. 后续 (Phase 10+)

- Strategy 路由接入 agent_versions (当前 agent 系统只支持单 model)
- 跨租户 audit 列表 API (`/api/admin/audit/llm?actor=&model_id=&range=`)
- 引导式 admin onboarding card (前端)
- 限流 per-api-key 真正的 token 计数 (目前是 req/min)
- admin UI 模型连通性测试按钮 / 批量导入 (已有端点, 前端 button 收尾)

## 8. 快速检查清单 (生产部署前)

- [ ] `QZDAP_ENV=production` (不是 development / demo)
- [ ] `QZDAP_MODEL_MASTER_KEY` 已设 (32 字节 hex)
- [ ] 生产环境**无** QZDAP_LLM_PROVIDER=mock (Phase 0 已禁, 但 verify 一下)
- [ ] `QZDAP_JWT_SECRET` 不是 `dev-` 前缀
- [ ] `QZDAP_SANDBOX_RUNTIME_SECRET` 不是 `dev-` 前缀
- [ ] 所有 secrets 通过 vault / k8s Secret 注入, 不在 env 中明文
- [ ] DB migration 到 `0041_model_quotas`
- [ ] admin 侧已配 至少 1 个 provider + 1 个 active model
- [ ] 跑 `pytest modules/model/tests/integration/test_multi_tenant_isolation.py` 通过
- [ ] `/healthz` 和 `/readyz` 都 200
- [ ] Prometheus 指标 / Grafana dashboard 配置
- [ ] audit log 长期保留策略 (建议 >= 1 年, 治理合规)
