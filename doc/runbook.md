# P10 On-call Runbook

> 5 类高频故障 × 处置步骤 × 升级路径。
> 配合 [prelaunch-checklist.md](./prelaunch-checklist.md) 与
> [slo.md](./slo.md) 使用。

## 升级路径

```
on-call → lead SRE → 架构师 → CTO
         (15 min)   (30 min)  (60 min)
```

所有故障处置必须在 24 小时内写事故复盘（incident post-mortem）。

## 故障 1 · Turn P95 突增

**触发告警**：`EosHighTurnP95Latency`（[qzdap-alerts.yaml](../../infra/prometheus/rules/qzdap-alerts.yaml)）

**严重等级**：Warning（持续 5 分钟）；Critical（持续 30 分钟）。

### 1.1 定位

1. 打开 Grafana [`qzdap-overview`](../../infra/grafana/dashboards/qzdap-overview.json)
   panel #2（P95 Turn Latency by tenant），确认是哪个 / 哪些 tenant。
2. 按 `tenant_id` 过滤 structlog 日志，找慢点：LLM / Tool / Memory。
3. 拉 `/v1/observability/costs?group_by=model` 看是否有异常 model
   占比上升。

### 1.2 处置

| 慢点 | 处置 |
|---|---|
| LLM provider | 切 routing policy（`PUT /v1/routing-policies/{id}` 改 priority 指向次选 provider） |
| Tool 调用 | 看 tool 自身延迟；暂时 disable 该 tool（`PATCH /v1/tools/{name}` `enabled=false`） |
| Memory 向量检索 | 看 `pg_stat_statements`；临时切 baseline 检索（`pgvector.ef_search=10`） |
| Skill 沙箱 | 看 `QZDAP_SKILL_RUNTIME_URL` 可达性；沙箱预热池 |

### 1.3 灰度降级

如根因未知：

1. 拉 canary 流量回 stable：移除 `X-QZDAP-Ring: canary` header 30 分钟。
2. 仍异常：把 stable 副本数减半（`kubectl scale deploy/qzdap-app-stable --replicas=1`）。
3. 仍异常：触发 [doc/backend/13-风险与验收.md §13.5 应急回滚](../../doc/backend/13-风险与验收.md)。

## 故障 2 · Eval gate 错误率尖峰

**触发告警**：`EosEvalGateFailureSpike`

**严重等级**：Warning。

### 2.1 定位

1. 查 `eval_runs` 表最新 50 条失败记录（`status='failed'`）。
2. 关联 `decision_events` 表找 reason。

### 2.2 处置

1. 临时放宽 gate 阈值：
   ```bash
   export QZDAP_EVAL_SCORE_MIN=0.6   # 默认 0.7
   kubectl rollout restart deploy/qzdap-app-stable
   ```
2. 通知 agent_factory owner 复盘。
3. 24 小时内恢复默认阈值。

## 故障 3 · Cost spike（critical）

**触发告警**：`EosCostSpikePerTenant`（critical）

**严重等级**：Critical（30 分钟内 2× 24h baseline）。

### 3.1 立即处置（5 分钟内）

1. 拉 `/v1/observability/costs?group_by=model` 找 top model。
2. 临时 suspend 该 tenant subscription：
   ```bash
   curl -X PUT https://qzdap.example.com/v1/platform/subscriptions/me \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "X-Tenant-Id: $TID" \
     -d '{"plan_code":"free","status":"suspended"}'
   ```
3. 在 Grafana `qzdap-costs` 标 incident start。

### 3.2 通知

- tenant owner（通过 channel webhook → 飞书 / 钉钉）
- finance 团队（邮件）

### 3.3 解除

修复定价 / 模型路由后，恢复 subscription（`status=active`）。

## 故障 4 · Cross-tenant 数据泄漏

**触发告警**：`cross_tenant_query_blocked` > 0（[doc/backend/11-部署与运行.md §11.8](../../doc/backend/11-部署与运行.md)）

**严重等级**：**最高 — 安全事故**。

### 4.1 立即处置（1 分钟内）

1. 立刻 disable 整 ingress：
   ```bash
   kubectl scale deploy/qzdap-app-stable --replicas=0
   kubectl scale deploy/qzdap-app-canary --replicas=0
   ```
2. 把 `infra/k8s/ingress.yaml` 临时删除（`kubectl delete ingress qzdap-app`）。
3. 在 #security-incident 频道喊 incident。

### 4.2 定位

1. 跑 regression：`pytest -k cross_tenant -q` —— 必须全绿。
2. 查 `audit_log` 表最近 1h 所有 cross-tenant 违规尝试：
   ```sql
   SELECT tenant_id, principal_id, action, resource_type, resource_id, occurred_at
     FROM audit_log
    WHERE event_type = 'TENANT_DENIED'
      AND occurred_at > NOW() - INTERVAL '1 hour'
    ORDER BY occurred_at DESC;
   ```
3. 受影响租户列表通知。

### 4.3 恢复

修复 ORM guard / JWT 中间件后，跑 regression 全绿 → 重新 enable ingress →
发事故公告 → 24h 内写 post-mortem。

## 故障 5 · SSE 首字节超 1s

**触发信号**：[slo.md SLI-5 SSE first byte](./slo.md) 超过 1000ms。

**严重等级**：Warning。

### 5.1 定位

1. 看 `uvicorn` worker 数（`kubectl get pods -o jsonpath='{.items[*].spec.containers[*].resources}'`）。
2. 检查 LLM streaming 是否启用（`Settings.llm_streaming=True`）。
3. 看 ingress 缓冲设置：nginx 默认会缓冲，需 `proxy_buffering off`。

### 5.2 处置

1. 加 worker：`kubectl scale deploy/qzdap-app-stable --replicas=5`。
2. 确认 `--loop uvloop --http httptools`（[doc/backend/11-部署与运行.md §11.6.1](../../doc/backend/11-部署与运行.md)）。
3. 加 nginx annotation `proxy-buffering: "off"`。
4. 如 LLM 未流式：临时切到 mock provider 验证 SSE 路径。

## 故障 R-Dev · 校验失败

### 现象

`make verify` 失败（ruff / importlinter / mypy / pytest）。

### 处置

1. `make lint` 看具体哪个 rule 挂。
2. `make type-check` 看 mypy 错位置。
3. 修复后必须重跑 `make verify` 全绿再发版。
4. 旧测试零回归是 hard gate。

## 故障 R-Health · `/readyz` 返回 503

### 现象

`/readyz` 返回非 200。

### 处置

1. 看 `/healthz`：若 200 则 DB 可达但 Redis 失败；若 503 则 DB 失败。
2. PG：检查 `pg_isready`、`SELECT 1`、连接池（`pg_stat_activity`）。
3. Redis：`redis-cli ping`、连接池。
4. Vector：pgvector extension 是否安装；HNSW 索引是否就绪。

## 故障 R-Smoke · smoke 失败

### 现象

`tests/e2e/smoke.py` 报错。

### 处置

1. 看 smoke 输出的 traceback 定位 endpoint。
2. 检查 `QZDAP_DATABASE_URL` / `QZDAP_REDIS_URL` env 是否正确。
3. 检查 admin token 是否过期（`QZDAP_JWT_SECRET`）。
4. 单测覆盖修复后必须重跑 smoke。

## References

- [prelaunch-checklist.md](./prelaunch-checklist.md) — 上线前 gates
- [slo.md](./slo.md) — SLI/SLO 目标
- [adr/0016-gray-rollout.md](./adr/0016-gray-rollout.md) — 上线决策
- [doc/backend/11-部署与运行.md §11.11 故障排查速查](../../doc/backend/11-部署与运行.md)
- [doc/backend/13-风险与验收.md §13.5 应急回滚](../../doc/backend/13-风险与验收.md)
- [infra/prometheus/rules/qzdap-alerts.yaml](../../infra/prometheus/rules/qzdap-alerts.yaml) — 4 条 alert
