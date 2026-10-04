# Grafana — 企智搭 · 智能体平台

Multi-tenant dashboards + provisioning for the QZDAP backend.

## Layout

```
infra/grafana/
├── dashboards/
│   ├── qzdap-overview.json      # 5 panel TOP dashboard (rate / latency / error / cost / eval)
│   └── qzdap-costs.json         # Cost observability dashboard (pie / 7d trend / top 10 tenants)
└── provisioning/
    ├── dashboards/
    │   └── qzdap-dashboards.yaml  # Auto-load dashboards/ directory
    └── datasources/
        └── prometheus.yaml      # Prometheus datasource (URL + scrape)
```

## Dashboards

### QZDAP — Overview (`qzdap-overview.json`)

5 panels, multi-tenant via `tenant_id` template variable:

| # | Panel | Source |
|---|---|---|
| 1 | Tenant Request Rate | `rate(qzdap_http_requests_total[5m])` |
| 2 | P95 Turn Latency | `histogram_quantile(0.95, ...)` |
| 3 | Error Rate (5xx) | 5xx / total ratio |
| 4 | LLM Cost (USD/5m) | `rate(qzdap_cost_usd_total[5m]) * 300` |
| 5 | Eval Gate Pass Rate | passed / total |

### QZDAP — Costs (`qzdap-costs.json`)

3 panels:

| # | Panel | Source |
|---|---|---|
| 1 | Cost by Type (24h) | `sum by (cost_type) (increase(...[24h]))` |
| 2 | Cost Trend (7d) | 1h rollup stacked area |
| 3 | Top 10 Tenants by LLM Cost | `topk(10, ...)` table |

## Deploy

### docker-compose

```yaml
services:
  grafana:
    image: grafana/grafana:11.1.0
    environment:
      GF_AUTH_ANONYMOUS_ENABLED: "true"
      GF_AUTH_ANONYMOUS_ORG_ROLE: Viewer
    volumes:
      - ./dashboards:/etc/grafana/dashboards:ro
      - ./provisioning:/etc/grafana/provisioning:ro
    ports:
      - "3000:3000"
```

After boot, dashboards appear under folder **QiZhiDa**.

### Bare-metal / VM

```bash
sudo cp dashboards/*.json /etc/grafana/dashboards/
sudo cp provisioning/dashboards/qzdap-dashboards.yaml /etc/grafana/provisioning/dashboards/
sudo cp provisioning/datasources/prometheus.yaml /etc/grafana/provisioning/datasources/
sudo systemctl reload grafana-server
```

## Verify

```bash
# JSON parses cleanly
python3 -c "import json; json.load(open('dashboards/qzdap-overview.json'))"
python3 -c "import json; json.load(open('dashboards/qzdap-costs.json'))"

# Provisioning YAML parses
python3 -c "import yaml; yaml.safe_load(open('provisioning/datasources/prometheus.yaml'))"
python3 -c "import yaml; yaml.safe_load(open('provisioning/dashboards/qzdap-dashboards.yaml'))"
```

## Multi-tenancy

Both dashboards use the `tenant` template variable sourced from
`label_values(qzdap_*_total, tenant)` so it auto-populates as the
backend emits metrics with the `tenant` label.  Until P10+
instrumentation middleware is wired, the dropdown will be empty —
that's expected for P9-6.

## Metric contract

Same set of `qzdap_*` metrics documented in
[`infra/prometheus/README.md`](../prometheus/README.md#metrics-contract).
