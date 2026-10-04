# P10 Burn-in Preflight (从代码落地到切 100%)

> Tier A 6/6 ✅ 已合入 `main`。本文档是 `doc/prelaunch-checklist.md` (G1-G8)
> 与 [runbook.md](./runbook.md) 之间的 **执行剧本**——按顺序铺好才能
> 把流量从 0% 推到 100%。
>
> 总时长预估：**约 8-10 天**（部署 1 天 + 灰度 7 天 burn-in）。

## 0. 三阶段总览

```
┌─────────────┐    ┌──────────────────┐    ┌────────────────────┐
│ Stage A     │    │ Stage B          │    │ Stage C            │
│ Pre-deploy  │ →  │ Stable+Canary    │ →  │ Traffic Ramp       │
│ (~30 min)   │    │ deploy + G1-G8   │    │ 1% → 10% → 50%     │
│             │    │ 验证 (~1 day)    │    │ → 100% (~7 days)   │
└─────────────┘    └──────────────────┘    └────────────────────┘
```

| Stage | 触发条件 | 退出条件 |
|---|---|---|
| A. Pre-deploy | `main` 是绿的；Tier A 6/6 ✅ | 所有环境变量 + secrets 已注入；k8s 命名空间就绪 |
| B. Deploy + verify | Stage A 退出 | G1-G8 全部 ✅（或 ⊘ 显式跳过） |
| C. Traffic ramp | Stage B 退出 | 100% 流量；G1-G8 7 天无回归 |

---

## Stage A · Pre-deploy (~30 min)

### A.1 代码与制品

- [ ] `git log --oneline origin/main..HEAD` 为空（已在 main）。
- [ ] `cd backend && make verify` 本地全绿（ruff / importlinter / mypy / pytest）。
- [ ] 镜像：`docker build -t qzdap-app:<sha> -f infra/docker/Dockerfile.app .`
  （`<sha>` = `git rev-parse --short HEAD`）。

### A.2 配置文件 (`.env.prod`)

参照 `deploy/env.prod.example` 生成 `.env.prod`（**gitignored**）。

**所有 secret 必须用 `*_REF` 引用**：

```bash
# ✅ 推荐
QZDAP_DATABASE_PASSWORD_REF=vault:secret/data/qzdap/prod/db#password
QZDAP_REDIS_PASSWORD_REF=csi:REDIS_PASSWORD

# ❌ 严禁（gitleaks G5 会失败）
QZDAP_DATABASE_PASSWORD=hunter2
```

完整支持的 ref 方案见 [deploy/README.md §Secrets](../deploy/README.md)：

| Scheme | Resolver | 何时用 |
|---|---|---|
| `vault:secret/data/<path>` | `HashicorpVaultSecretsResolver` | 中心化 secret、TTL、自动 rotate |
| `csi:<KEY_NAME>` | `CSIVaultSecretsResolver` | k8s 集群内；CSI 驱动挂 `/vault/secrets/<KEY>` |

非敏感配置可走 `.env` 直填（如 `QZDAP_RING=stable`、`QZDAP_LOG_LEVEL=info`）。

### A.3 k8s 命名空间

```bash
kubectl apply -f infra/k8s/namespace.yaml
# 验证
kubectl get ns qzdap-prod
kubectl label ns qzdap-prod name=qzdap-prod --overwrite
```

### A.4 Secrets (k8s)

```bash
# SecretProviderClass 模板：infra/k8s/secret.example.yaml
cp infra/k8s/secret.example.yaml infra/k8s/secret.yaml
$EDITOR infra/k8s/secret.yaml      # 填 Vault address / role / path
kubectl apply -f infra/k8s/secret.yaml -n qzdap-prod
```

注：实际接入后 `infra/k8s/secret.yaml` 加进 `.gitignore`（gitleaks 兜底）。

### A.5 ConfigMap / NetworkPolicy / HPA

```bash
kubectl apply -f infra/k8s/configmap.yaml         # 非敏感配置
kubectl apply -f infra/k8s/networkpolicy.yaml      # default-deny + ingress-nginx 放行
kubectl apply -f infra/k8s/hpa.yaml                # HPA: stable 3-10, canary 1-3
```

### A.6 镜像推送

```bash
docker tag qzdap-app:<sha> <registry>/qzdap-app:<sha>
docker push <registry>/qzdap-app:<sha>
# 同时更新 :stable :canary 别名
docker tag qzdap-app:<sha> <registry>/qzdap-app:stable
docker tag qzdap-app:<sha> <registry>/qzdap-app:canary
docker push <registry>/qzdap-app:stable
docker push <registry>/qzdap-app:canary
```

### A.7 数据库迁移

```bash
# 在稳定的 PG 上跑 migration（业务 pod 还没起，安全）
kubectl run -n qzdap-prod migrator --rm -it --restart=Never \
  --image=<registry>/qzdap-app:<sha> \
  --overrides='{"spec":{"serviceAccountName":"qzdap-app"}}' \
  -- alembic upgrade head
# 验证：SELECT * FROM alembic_version; → 0017
```

### A.8 Prometheus / Grafana provisioning

```bash
# Prometheus: rules + scrape config（rule_files 已挂载 configmap volume）
kubectl apply -f infra/prometheus/prometheus.example.yml   # 适配后
kubectl apply -f infra/prometheus/rules/                  # 4 alert + 4 recording

# Grafana: dashboards + provisioning
kubectl apply -f infra/grafana/dashboards/                # qzdap-overview + qzdap-costs
kubectl apply -f infra/grafana/provisioning/              # datasource + provider yaml
```

---

## Stage B · Deploy + G1-G8 verify (~1 day)

### B.1 部署 stable（先 canary 之前）

```bash
kubectl apply -f infra/k8s/service.yaml
kubectl apply -f infra/k8s/deployment.yaml
# 默认 replicas=3 for stable, replicas=1 for canary
kubectl scale deploy/qzdap-app-canary --replicas=0 -n qzdap-prod
kubectl rollout status deploy/qzdap-app-stable -n qzdap-prod
```

### B.2 配置 URL

```bash
export QZDAP_STABLE_URL=https://qzdap-stable.example.com
export QZDAP_CANARY_URL=https://qzdap-canary.example.com

# G3 还需要 tenant 域 env vars（bootstrapped by smoke / staging seed）
export QZDAP_BENCH_TOKEN=<admin-bearer>
export QZDAP_BENCH_TENANT=<tenant-uuid>
export QZDAP_BENCH_WORKSPACE=<workspace-uuid>
export QZDAP_BENCH_AGENT_ID=<agent-uuid>
```

如果 `QZDAP_BENCH_*` 缺，runner 会以 ⊘ skip G3（而非 ✗ fail），exit code 仍
是 0 — 即 Stage B 仍可退出，但 G3 需要补 stage 或在凭据就绪后单跑。

G8 smoke (`backend/tests/e2e/smoke.py`) 以无 `Authorization` header
请求 `/v1/identity/tenants`，因此**仅在 dev-mode deployment
(`QZDAP_AUTH_MODE=disabled`) 下可跑**。生产环境下应把 smoke 放到 staging
ring（`QZDAP_RING=stable` 但 `auth=disabled` 的旁路），或在 prod gate 上
显式标记 ⊘。

### B.3 跑 burn-in runner（一条命令覆盖 G2/G3/G5/G6/G7/G8）

```bash
cd backend && make burn-in
# 等价于：
#   uv run python ../deploy/burn_in.py
```

预期输出（顺序）：

```
[✓] G5 secret-scan (gitleaks)              ← 0 leaks
[✓] G6 prometheus rules + config           ← 4 alert + 4 recording VALID
[✓] G7 grafana dashboards JSON + live load ← qzdap-overview 5 panels, qzdap-costs 3 panels
[✓] G2 /readyz 200 (stable + canary)       ← 200/200
[✓] G3 bench P95 ≤ 10s                     ← P95 < 10s（需要 QZDAP_BENCH_*）
[✓] G8 smoke happy path (stable + canary)  ← session/turn/tool/memory 全绿
=== 0 failed, 0 skipped ===
```

G3 / G8 在缺少前置 env 时会 ⊘ skip 而非 ✗ fail（exit code 仍 = 0），
便于 stage 期间分段补齐；但 Stage B 退出条件要求 **0 failed, 0 skipped**
才算完全 Stage B 出口。

### B.4 部署 canary

```bash
kubectl scale deploy/qzdap-app-canary --replicas=1 -n qzdap-prod
kubectl rollout status deploy/qzdap-app-canary -n qzdap-prod

# 重跑 burn-in
make burn-in
# 预期：两实例 /readyz 都 200；smoke 两份都过
```

### B.5 故障联动确认（dry-run）

- [ ] `kubectl logs deploy/qzdap-app-stable -n qzdap-prod | grep "seeded"`
      → 看到 `seeded N office skill packs (vetter=local, trust_keys=1)`（如果开启 seeder）
- [ ] `curl https://qzdap-stable.example.com/v1/skills -H "Authorization: Bearer $ADMIN"`
      → 4 条 `skp.office.*`（前提是 `QZDAP_PLATFORM_SEED_OFFICE_SKILL_PACKS=true`）

---

## Stage C · Traffic ramp (~7 days)

### C.1 灰度策略

按 `X-QZDAP-Ring` header 路由（[infra/k8s/ingress.yaml](../../infra/k8s/ingress.yaml)）：

| Header | 路由 |
|---|---|
| （无）| stable (3 pods) |
| `X-QZDAP-Ring: canary` | canary (1 pod) |

### C.2 四阶段进度

每阶段**至少 24 小时无 P0/P1 告警**才推进下一阶段。阈值参考 [slo.md §上线阶段 SLO 演进](./slo.md)：

| Phase | 流量 | 时长 | SLO-1 P95 | SLO-2 错误率 | 监控重点 |
|---|---|---|---|---|---|
| 1. Canary 1% | 1% | ≥ 24h | ≤ 30s | ≤ 5% | `/readyz` / SSE 首字节 |
| 2. Canary 10% | 10% | ≥ 24h | ≤ 20s | ≤ 3% | Turn P95 / cost |
| 3. Canary 50% | 50% | ≥ 24h | ≤ 15s | ≤ 2% | Cross-tenant / eval gate |
| 4. Stable 100% | 100% | ≥ 24h 后切 | ≤ 10s（SLO-1） | ≤ 1%（SLO-2） | 错误预算 |

### C.3 推动各 phase 的步骤

```bash
# 通用入口（替换 <PERCENT>）
# 用 envoy / nginx-ingress canary annotation 按比例切
# 例：nginx.ingress.kubernetes.io/canary-weight: "<PERCENT>"

# Phase 1 (1%)
kubectl patch ingress qzdap-app -n qzdap-prod \
  --type=json -p='[{"op":"add","path":"/spec/rules/0/http/paths/-","value":{...canary...}}]'
# 或在 helmfile/argocd 中调 canary-weight: "1"

# 1 小时后查 baseline
make burn-in   # G2/G3/G8 应持续 ✅

# 24h 后推进下一 phase（重复上面的步骤）
```

### C.4 每日运维（持续 7 天）

- [ ] 上午 09:00 / 下午 17:00 各看一次 Grafana [`qzdap-overview`](../../infra/grafana/dashboards/qzdap-overview.json)：
  - Panel #2 (P95 Turn Latency)
  - Panel #3 (HTTP error rate)
  - Panel #5 (Cross-tenant violations — 必须 0)
- [ ] 每天跑一次 `make burn-in`（即便没有发版也跑一次；防止规则漂移）
- [ ] 看 Prometheus `EOS*` alerts：
  ```bash
  curl -s 'http://prometheus:9090/api/v1/alerts' | jq '.data.alerts[] | {name: .labels.alertname, state: .state}'
  ```
- [ ] 任意 P0/P1 告警 → 立刻进 [runbook.md](./runbook.md) 对应章节；如根因未知 → 走 §1.3 灰度降级（拉 canary 回 stable）。

### C.5 切流 100% 的判定

7 天 burn-in 内同时满足：

- [ ] G1-G8 全程 ✅（无回归）
- [ ] SLO-1/2/4 错误预算消耗 < 50%
- [ ] SLO-3 (cross-tenant) 始终 0 violation
- [ ] 无未关闭的 P0/P1 事故
- [ ] on-call 签字 + 架构师签字（[prelaunch-checklist.md §Sign-off](./prelaunch-checklist.md)）

→ 移除 `X-QZDAP-Ring` header 路由（默认全走 stable），归档 7 天 burn-in 报告。

---

## Rollback（任意阶段触发）

按 [runbook.md §升级路径](./runbook.md) 通知链执行（on-call → lead SRE → 架构师 → CTO）。

### 5 分钟内

1. **回流量**（P95 突增 / 错误率尖峰 / SSE 超时 场景）：
   ```bash
   # 把 canary weight 改回 0%（即全走 stable）
   kubectl patch ingress qzdap-app -n qzdap-prod --type=json \
     -p='[{"op":"replace","path":"/spec/rules/0/http/paths/.../canary-weight","value":"0"}]'
   ```
2. **保留现场**：不要立刻重启 pod；保留 logs / traces。

### 30 分钟内

3. 拉 `kubectl logs` + Grafana 锁定根因（LLM / Tool / Memory / Skill 沙箱）。
4. 如果 stable 也异常：
   ```bash
   kubectl scale deploy/qzdap-app-stable --replicas=1 -n qzdap-prod
   ```
6. 仍异常 → 触发 [doc/backend/13-风险与验收.md §13.5 应急回滚](../../doc/backend/13-风险与验收.md)：
   - 回滚镜像到上一个 `<sha>` tag
   - `kubectl rollout undo deploy/qzdap-app-stable`

### 24 小时内

- [ ] 出事故复盘（post-mortem）；归档 Grafana 截图 + promtool alert 时间线。
- [ ] 如果是 secret 泄漏：立刻 rotate + 重跑 [G5 gitleaks](./prelaunch-checklist.md) 兜底。

---

## References

- [prelaunch-checklist.md](./prelaunch-checklist.md) — G1-G8 详细阈值与命令
- [runbook.md](./runbook.md) — 5 类故障处置 + on-call 升级路径
- [slo.md](./slo.md) — 5 个 SLI / 4 个 SLO / 错误预算 + 上线阶段阈值
- [deploy/README.md](../deploy/README.md) — compose 部署 + burn-in runner 用法
- [deploy/burn_in.py](../deploy/burn_in.py) — G2/G3/G5/G6/G7/G8 编排脚本
- [infra/k8s/](../../infra/k8s/) — k8s manifests（deployment / ingress / service / hpa / secret / configmap / networkpolicy）
- [infra/prometheus/rules/](../../infra/prometheus/rules/) — 4 alert + 4 recording rules
- [infra/grafana/dashboards/](../../infra/grafana/dashboards/) — qzdap-overview + qzdap-costs