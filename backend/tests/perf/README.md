# Performance bench harness

asyncio + httpx scripts for measuring the two primary latency SLIs:

| Script | Target | SLO |
|---|---|---|
| `bench_turn_latency.py` | SSE turn end-to-end P95 | [SLO-1](../../doc/slo.md) ≤ 10s |
| `bench_observability_ingest.py` | event-bus → DB row P95 | micro-bench, target ≤ 5ms (in-memory) |

## bench_turn_latency

Drives a real `/v1/sessions/{sid}/turn/stream` call under configurable
concurrency, prints P50/P95/P99 + QPS + failure rate. Exits non-zero
if P95 > threshold or failure rate > 1%.

### Setup

```bash
# 1. start app
cd backend
make run-app   # port 8102

# 2. mint admin token + create a session/workspace
export QZDAP_BENCH_TOKEN=$(uv run python -c 'from libs.auth.scripts.mint_admin import main; main()' 2>/dev/null || \
    uv run python -c 'from libs.auth import mint_admin_token; print(mint_admin_token())')
export QZDAP_BENCH_TENANT=$(uuidgen)
export QZDAP_BENCH_WORKSPACE=$(uuidgen)
export QZDAP_BENCH_AGENT_ID=$(curl -fsS -X POST http://127.0.0.1:8102/v1/agents \
    -H "Authorization: Bearer $QZDAP_BENCH_TOKEN" \
    -H "X-Tenant-Id: $QZDAP_BENCH_TENANT" \
    -H "Content-Type: application/json" \
    -d '{"name":"bencher","template_id":"default"}' | jq -r .id)

# 3. run
uv run python -m tests.perf.bench_turn_latency --concurrency 10 --turns 5
```

### Canary variant

To measure canary pool:

```bash
QZDAP_BENCH_RING=canary \
    uv run python -m tests.perf.bench_turn_latency --concurrency 5 --turns 3
```

## bench_observability_ingest

Micro-bench of the event-bus → recorder path. Does NOT exercise SQL.
Uses `InMemoryRunRecordRepository` / `InMemoryCostRecordRepository`
from `tests/unit/_in_memory.py`.

```bash
cd backend
uv run python -m tests.perf.bench_observability_ingest --events 5000 --warmup 200
```

## CI integration

Both scripts return exit code 1 on threshold breach. A nightly CI job
can run them against staging and post P95 to the Grafana
`qzdap-overview` panel via the `/metrics` pushgateway.

## SLO mapping

See [`../../doc/slo.md`](../../doc/slo.md) for the SLI/SLO targets.
