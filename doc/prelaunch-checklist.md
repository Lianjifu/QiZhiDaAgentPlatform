# P10 Pre-launch Checklist (ops gates)

> 上线前的 8 项 ops gate。每条 gate 必须为 ✅ 才能切流到 100%。
> 配合 [runbook.md](./runbook.md) 与 [slo.md](./slo.md) 使用。

## Gates

- [ ] **G1. `make verify` 全绿**
  - 命令：`cd backend && make verify`
  - 阈值：ruff ✓ / importlinter ✓ / mypy ✓ / pytest 全绿 / coverage ≥ 80%
  - 出错处置：参考 [runbook.md §R-Dev 校验失败](./runbook.md)

- [ ] **G2. 双实例 `/readyz` 200**
  - 命令：
    ```bash
    curl -fsS https://qzdap-stable.example.com/readyz   # → 200
    curl -fsS https://qzdap-canary.example.com/readyz   # → 200
    ```
  - 阈值：两实例 `status: ready`；DB / Redis 可达。
  - 出错处置：[runbook.md §R-Health 503](./runbook.md)

- [ ] **G3. bench turn latency P95 ≤ 10s**
  - 命令：`make bench-turn-latency`
  - 阈值：P95 ≤ 10s（[slo.md SLI-1](./slo.md)）；连续 3 次取中位。
  - 出错处置：[runbook.md §R-Perf P95 突增](./runbook.md)

- [ ] **G4. cross-tenant isolation 测试 100%**
  - 命令：`cd backend && uv run pytest -k cross_tenant -q`
  - 阈值：0 failure；matrix 覆盖所有 4 模块（agent_runtime / tool /
    memory / knowledge）。
  - 出错处置：**立即停上线**；参考 [runbook.md §R-CrossTenant 泄漏](./runbook.md)。

- [ ] **G5. secret 全部走 `*_REF`（无明文）**
  - 命令：`gitleaks detect --no-git --source .`
  - 阈值：0 finding；`infra/k8s/secret.example.yaml` 不含明文 secret。
  - 出错处置：把所有 secret 改为 `QZDAP_*_REF=<vault-path>`；
    真实值由 vault 注入。

- [ ] **G6. Prometheus rule 部署**
  - 命令：
    ```bash
    promtool check rules infra/prometheus/rules/*.yaml
    ```
  - 阈值：4 条 alert rule + 4 条 recording rule 全部合法；`QZDAP_RING` 维度
    label 已加。
  - 出错处置：参考 [infra/prometheus/README.md](../../infra/prometheus/README.md)。

- [ ] **G7. Grafana dashboard 加载**
  - 命令：
    ```bash
    curl -fsS https://grafana.example.com/api/dashboards/uid/qzdap-overview
    ```
  - 阈值：`qzdap-overview` + `qzdap-costs` 两个 dashboard 加载成功；
    `tenant_id` 模板变量有 ≥ 1 个候选值。
  - 出错处置：参考 [infra/grafana/README.md](../../infra/grafana/README.md)。

- [ ] **G8. smoke run 走一遍 happy path**
  - 命令：`make smoke` 或 `cd backend && uv run python tests/e2e/smoke.py`
  - 阈值：创建 session → SSE turn → tool call → memory write 全部 200；
    触发 1+ `RunRecord` + `CostRecord` 落库。
  - 出错处置：[runbook.md §R-Smoke 失败](./runbook.md)。

## Sign-off

| 角色 | 签字 | 日期 |
|---|---|---|
| SRE | | |
| 架构师 | | |
| 后端主程 | | |
| QA | | |

## References

- [runbook.md](./runbook.md) — on-call 故障处置
- [slo.md](./slo.md) — SLI/SLO 目标
- [burn-in-preflight.md](./burn-in-preflight.md) — 从代码到 100% 流量的执行剧本（Stage A/B/C + 灰度 + 回滚）
- [adr/0016-gray-rollout.md](./adr/0016-gray-rollout.md) — 上线决策
- [doc/backend/13-风险与验收.md §13.10](../../doc/backend/13-风险与验收.md) — P10 上线验收小节
