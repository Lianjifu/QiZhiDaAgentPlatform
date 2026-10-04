# ADR 0016 — Enterprise-Agent-OS 上线策略

## Status

Accepted (2026-09-23).

## Context

P10 上线需 7 天 100% 稳定运行（doc 12 §P10）。本仓为 greenfield：无
"旧系统" 可迁移；EOS 自身即目标系统。但 "渐进切流量" 的运维价值仍然
存在 —— 在切到 100% 前需要 1% → 10% → 50% 的灰度验证期，以便观察
P95 / 错误率 / 多租户隔离是否仍然达标。

当前缺口：

- 缺双实例池 gray A/B 切流配置（k8s / ingress）。
- 缺响应差异记录 harness（用来日后真做 "旧 vs 新" 切换时验证 parity）。
- 缺 on-call runbook（应急回滚决策树见 doc 13 §13.5，但 on-call
  日常故障处置文档未沉淀）。
- 缺 SLI/SLO 文档（P9-6 已有 PromQL 告警，但缺 SLO 目标与错误预算）。
- 缺 pre-launch checklist（doc 13 §13.3 有验收清单，但缺 ops 视角
  上线前 gates）。

## Decision

1. **同代码双实例 gray A/B**：用 `QZDAP_RING` 环境变量（取值 `stable` /
   `canary`，默认 `stable`）标识实例角色；ingress 层按 HTTP header
   `X-QZDAP-Ring: canary` 把流量路由到 canary 副本池，未带 header 的默认
   走 stable。
   - k8s：nginx ingress + `canary-by-header` 注解
     （[infra/k8s/ingress.yaml](../../infra/k8s/ingress.yaml)）。
   - 备选：独立 Envoy header-route
     （[infra/envoy/envoy.yaml](../../infra/envoy/envoy.yaml)）。
2. **dual-run harness** = 内部请求镜像：保留 `/v1/_dual/echo` 路由前缀
   30 天观察期，供后续真 "旧 → 新" 切换时复用；本次 P10 不强制引入
   `dual_run_records` 表（greenfield 暂不需要）。
3. **交付物**：
   - `infra/k8s/` 完整 manifests（namespace / configmap / secret.example /
     deployment / service / ingress / hpa / networkpolicy）。
   - `deploy/docker-compose.prod.yml`（prod profile，含 stable + canary）。
   - `infra/docker/Dockerfile.app`（prod 镜像）。
   - `doc/prelaunch-checklist.md`（8 项 ops gate）。
   - `doc/runbook.md`（5 类故障处置）。
   - `doc/slo.md`（5 SLI + 4 SLO + 错误预算）。
   - `backend/tests/perf/bench_turn_latency.py` +
     `bench_observability_ingest.py`（asyncio + httpx 性能基线）。
   - `backend/Makefile` 增 `bench` target。
4. **不做**：旧系统迁移；blue-green DNS 切换；ISTIO service mesh；
   chaos engineering；auto-rollback；multi-region。

## Consequences

### Positive

- 同代码双实例灰度验证生产路径性能 / 错误率差异。
- 双实例池 + header 切流是 future-proof 设计：将来真 "旧 → 新" 切换时
  canary 端换成旧系统镜像即可，stable 端换成新系统镜像，分流机制不变。
- prelaunch + runbook + slo 三件套给 on-call 提供完整执行清单 + 目标 +
  预算视图。
- bench 脚本可在 CI nightly 跑性能回归（P95 阈值漂移告警）。

### Negative

- 双实例池需要双倍资源（默认 stable=3 pod + canary=1 pod）。
- 灰度期 canary 流量低，单独错误样本不足以做 SLO 评估；必须等
  canary 流量 > 1% 才有效。
- k8s 部署需要 SRE 上手（manifest 维护 / ingress-nginx 升级路径）。
- QZDAP_RING env 注入是手工流程；缺 helm chart 自动化。

## Alternatives considered

- **Big-bang 切换**：风险高。P9 末仍有少量 flaky metric 待观察，
  不接受一刀切。
- **Blue-green**：需要 DNS 切换 + 双倍常驻资源；无法在 HTTP 层做
  header 切流，不便 per-tenant 灰度。
- **Feature flag**：本仓无旧系统，flag 切换意义小；且 flag 状态散落
  仓库，不如 ring-based 实例池直观。

## References

- 实施计划：[doc/backend/12-实施计划.md §P10](../../doc/backend/12-实施计划.md)
- 验收清单：[doc/backend/13-风险与验收.md §13.10 P10 上线验收](../../doc/backend/13-风险与验收.md)
- 部署：[doc/backend/11-部署与运行.md](../../doc/backend/11-部署与运行.md)
- 告警基线：[infra/prometheus/rules/qzdap-alerts.yaml](../../infra/prometheus/rules/qzdap-alerts.yaml)
- 面板：[infra/grafana/dashboards/qzdap-overview.json](../../infra/grafana/dashboards/qzdap-overview.json)
