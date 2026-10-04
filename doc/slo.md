# SLO / SLI / Error Budget

> P10 上线目标。5 个 SLI + 4 个 SLO + 错误预算。
> 配合 [prelaunch-checklist.md](./prelaunch-checklist.md) 与 [runbook.md](./runbook.md)。

## SLI 定义

| # | SLI | 定义 | 数据源 |
|---|---|---|---|
| SLI-1 | Turn P95 latency | `histogram_quantile(0.95, sum by (le) (rate(qzdap_turn_latency_ms_bucket[5m])))` | `qzdap_turn_latency_ms_bucket` histogram |
| SLI-2 | HTTP error rate | `sum(rate(qzdap_http_requests_total{status=~"5.."}[5m])) / sum(rate(qzdap_http_requests_total[5m]))` | `qzdap_http_requests_total` counter |
| SLI-3 | Cost spike | `sum by (tenant) (rate(qzdap_cost_usd_total[1h])) / sum by (tenant) (rate(qzdap_cost_usd_total[24h] offset 24h))` | `qzdap_cost_usd_total`（来自 P9 cost_records） |
| SLI-4 | Cross-tenant isolation | `increase(qzdap_tenant_violation_total[5m]) == 0` | audit_log 触发 ORM guard 计数 |
| SLI-5 | SSE first byte | `histogram_quantile(0.95, sum by (le) (rate(qzdap_sse_first_byte_ms_bucket[5m])))` | SSE 连接首字节时间 histogram |

> P10 末 / P11 时由 P11 接入 prometheus_client instrumentation 落地
> SLI 1/2/4/5 的 metric（详见 [runbook.md 故障 1](./runbook.md)）。
> SLI-3 cost 由 P9 已有 `cost_records` 表直接查 SUM 提供。

## SLO 目标

| # | SLO | 阈值 | 错误预算 / 30d |
|---|---|---|---|
| SLO-1 | Turn P95 latency | ≤ 10s | 99.5% 可用 = 3.6h 预算 |
| SLO-2 | HTTP error rate | ≤ 1% | 99% 可用 = 7.2h 预算 |
| SLO-3 | Cross-tenant isolation | 100%（零容忍） | 0 容忍 |
| SLO-4 | SSE first byte P95 | ≤ 1000ms | 99% 可用 = 7.2h 预算 |

### 错误预算计算

| SLO | 可用率 | 月度预算 | 周度预算 | 日度预算 |
|---|---|---|---|---|
| SLO-1 | 99.5% | 3.6h | 50.4min | 7.2min |
| SLO-2 | 99.0% | 7.2h | 1h | 8.6min |
| SLO-4 | 99.0% | 7.2h | 1h | 8.6min |

### 错误预算耗尽策略

预算 > 80% 消耗：on-call 收到周报，lead 决定是否冻结非关键发版。
预算 = 100% 消耗：冻结所有非紧急发版；on-call 必须在 24h 内出 RCA。

## Cost spike（SLI-3）— alert only

Cost spike 不参与错误预算计算（成本是业务侧 metric，非可用性 metric）。
触发即响应（[runbook.md 故障 3](./runbook.md) critical）。

## 上线阶段 SLO 演进

| 阶段 | 流量 | SLO-1 P95 阈值 | SLO-2 错误率阈值 |
|---|---|---|---|
| Canary 1% | 1% | ≤ 30s（容差大） | ≤ 5% |
| Canary 10% | 10% | ≤ 20s | ≤ 3% |
| Canary 50% | 50% | ≤ 15s | ≤ 2% |
| Stable 100% | 100% | ≤ 10s（SLO-1） | ≤ 1%（SLO-2） |

每个阶段维持 ≥ 24 小时无告警才推进。

## References

- [prelaunch-checklist.md](./prelaunch-checklist.md) — G3 bench turn latency 阈值 = SLO-1
- [runbook.md](./runbook.md) — 5 类故障处置对应 5 SLI
- [adr/0016-gray-rollout.md](./adr/0016-gray-rollout.md) — 上线策略
- [infra/prometheus/rules/qzdap-alerts.yaml](../../infra/prometheus/rules/qzdap-alerts.yaml) — 4 alert rules
