# model — 模型供应与额度

> 能力域之一。负责模型供应商接入、模型目录、路由策略、健康检查、**额度控制**与 LLM 审计。

⚠️ **额度实现在本模块，不在 governance**——`governance` 管策略 / 审批 / 审计 / 数据主体请求，额度是模型侧的算力与成本约束。

## 职责

- 模型供应商接入与**凭据加密落库**
- 模型目录管理与目录自动探测
- 路由策略（fallback / quality-first / cost-first / latency-first / round-robin / weighted）与 failover 链
- 健康检查与告警
- **额度（quota）与用量**
- LLM 调用审计

## 源码位置

```
backend/modules/model/src/qzdap/modules/model/
├── domain/          entities.py（Provider · Model · RouteRule · HealthEvent）
├── application/
│   ├── services.py       ModelService（模型 / 供应商 / 路由 / 健康 / 目录 / 连通性）
│   ├── quota_service.py  QuotaService（check_and_consume · upsert_quota）
│   ├── audit_service.py  LLMAuditService
│   ├── alert_service.py  AlertService
│   └── ports.py
└── adapter/
    ├── persistence/  models.py · quota_models.py · repositories.py
    ├── crypto/       credential_cipher.py（AES-GCM 凭据加密）
    ├── llm/          prober.py（目录探测）· connectivity_tester.py · client_factory.py
    └── http/         router.py
```

## HTTP 端点

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/admin/models` | 模型列表 |
| GET | `/api/admin/models/{model_id}` | 模型详情 |
| POST | `/api/admin/models` | 建模型 |
| PATCH | `/api/admin/models/{model_id}` | 更新模型 |
| DELETE | `/api/admin/models/{model_id}` | 删模型 |
| POST | `/api/admin/models/{model_id}/star` | 收藏 |
| POST | `/api/admin/models/catalog` | 目录自动探测 |
| POST | `/api/admin/models/import` | 批量导入 |
| POST | `/api/admin/models/connectivity-test` | 连通性测试 |
| POST | `/api/admin/models/batch-status` | 批量启停 |
| GET | `/api/admin/models/providers` | 供应商列表 |
| POST | `/api/admin/models/providers/{provider_id}/health-check` | 供应商健康检查 |
| GET | `/api/admin/models/health` | 健康快照 |
| GET | `/api/admin/models/routes` | 路由列表 |
| POST | `/api/admin/models/routes` | 建路由 |
| POST | `/api/admin/models/routes/{route_id}/toggle` | 启停路由 |
| DELETE | `/api/admin/models/routes/{route_id}` | 删路由 |
| GET | `/api/admin/models/routes/{route_id}/preview-chain` | 预览 failover 链 |
| GET | `/api/admin/models/quotas` | 额度列表 |
| POST | `/api/admin/models/quotas` | 设额度 |
| DELETE | `/api/admin/models/quotas/{quota_id}` | 删额度 |
| GET | `/api/admin/models/quotas/usage` | 用量统计 |
| GET | `/api/admin/llm/audit` | LLM 调用审计 |

## 数据表

| 表 | 职责 | 关键列 |
|---|---|---|
| `admin_model_providers` | 供应商 | id / name / protocol / base_url / **encrypted_payload**(LargeBinary) / api_key_masked / error_rate / avg_latency_ms / qps |
| `admin_models` | 模型 | id / provider_id / model_name / context_window / price_in / price_out / status |
| `admin_model_routes` | 路由策略 | id / strategy / model_ids / priority / enabled |
| `admin_model_health` | 健康事件 | id / model_id / status / latency_ms / error / at |
| `model_quotas` | 额度定义 | id / tenant_id / workspace_id / period / limit_value |
| `model_quota_usage` | 用量计数 | id / quota_id / used / period |

## 实现要点

- **凭据加密落库**：`adapter/crypto/credential_cipher.py` 用 AES-GCM，支持三种主密钥来源（32 原始字节 / hex / passphrase + Argon2id）；`key_version` 字段为将来轮换预留
- **AAD 绑定 `protocol|base_url`**：换个 base_url 密文就解不开——防止密文被搬到另一个地址
- **主密钥来自环境**：`QZDAP_MODEL_MASTER_KEY`（32 字节 hex）。生产环境若主密钥仍是 dev 前缀，容器启动直接 `RuntimeError`（`container.py:79-93`）
- **目录探测按协议分**：`HttpCatalogProber` 支持 openai / anthropic / google / qwen 四种协议；无标准 `/models` 的供应商抛 `CatalogDiscoveryUnsupported`（qwen 即如此）
- **连通性测试防内网**：`PublicNetworkTransport` 阻断内网地址 + 响应体限流 + key 脱敏
- **额度的硬闸门**：`QuotaService.check_and_consume` 在调用前检查并扣减，超额直接拒绝
- **成本可追溯到 turn**：`UsageChunk` 带 6 个归属维度（tenant / workspace / user / agent / agent_version / model_version），成本同时落 `session_turns.cost_usd`

## 已知边界

- ⚠️ **健康检查靠事件累积，没有主动探活调度器**——`admin_model_health` 只在真实调用后追加
- ⚠️ `LLMAuditService` 只落审计事件，**不做合规分析**
- ⚠️ `preview-chain` 是静态预览，**实际的 failover 决策在 kernel 侧**（`libs/llm/router.py`），不在本模块
- ⚠️ 未配置真实供应商时，装的是 `UnavailableLLMClient`——目录与数据库 API 照常启动，但任何 chat / embed 调用一律 503（不是返回 mock）
