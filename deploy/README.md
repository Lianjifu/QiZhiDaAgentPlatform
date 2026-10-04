# Enterprise-Agent-OS — Deploy / Sandbox

Two deploy paths live here:

- **`deploy/docker-compose.prod.yml`** — production compose (full prod
  path: stable + canary pools, PG/Redis/MinIO, ingress profile).
- **`deploy/run-staging.sh`** — single-host sandbox for local dev /
  staging. Two modes:
  - `docker` (default) — postgres + qzdap-app:prod in two containers;
    entrypoint picks gunicorn vs uvicorn per `QZDAP_GUNICORN_WORKERS`.
  - `uvicorn` — postgres in docker, app runs on the host via
    `uv run uvicorn --reload` (no image build, hot reload, debugger
    attach, ~150 MB less memory than the gunicorn-4 path).

## Sandbox quick start

```bash
# 1. create env file (gitignored)
cp deploy/env.staging.example deploy/env.staging

# 2a. docker mode — both containers, single-worker uvicorn inside
./deploy/run-staging.sh up docker
curl http://localhost:8102/readyz

# 2b. uvicorn mode — PG in docker, app on host with hot reload
./deploy/run-staging.sh up uvicorn

# 3. teardown
./deploy/run-staging.sh stop
```

`run-staging.sh` subcommands: `up [docker|uvicorn]` / `stop` / `logs` /
`ps` / `migrate`. PG image is `pgvector/pgvector:pg16` (the `vector`
extension is required by migration `0009_knowledge.py`).

## Production compose

## Traffic split

A separate ingress (nginx ingress canary annotation or envoy) must split
client requests based on the `X-QZDAP-Ring` header:

- `X-QZDAP-Ring: canary` → port 8103
- (no header) → port 8102

See [`infra/k8s/ingress.yaml`](../infra/k8s/ingress.yaml) for the k8s
equivalent. For compose-only dev, route manually with two A records or
a local nginx sidecar.

## Secrets

All credentials live in `.env.prod` which is `.gitignore`d. Reference
`QZDAP_*_REF` env vars only — never inline raw secrets.  Two ref schemes
are accepted (both implemented in `libs/vault`):

| Scheme | Resolver | Source |
|---|---|---|
| `vault:secret/data/<path>` | `HashicorpVaultSecretsResolver` | HashiCorp Vault KV v2 (env `QZDAP_VAULT_URL` / `QZDAP_VAULT_TOKEN`) |
| `csi:<KEY_NAME>` | `CSIVaultSecretsResolver` | Vault CSI driver mount at `/vault/secrets/<KEY>` |

See `infra/k8s/secret.example.yaml` for the matching k8s SecretProviderClass
when running under k8s.

## Burn-in gate runner

`deploy/burn_in.py` orchestrates the prelaunch gates G2 / G3 / G5 / G6 /
G7 / G8 from `doc/prelaunch-checklist.md`. Locally it can already run
G5 (gitleaks), G6 (promtool check rules + config), and G7 (Grafana
dashboard JSON schema). Setting `QZDAP_STABLE_URL` + `QZDAP_CANARY_URL`
adds G2 (dual `/readyz` 200), G8 (smoke happy path against both rings).
G3 also needs `QZDAP_BENCH_TOKEN`, `QZDAP_BENCH_TENANT`,
`QZDAP_BENCH_WORKSPACE`, `QZDAP_BENCH_AGENT_ID` — without these the bench
script exits 2 and the gate skips with a clear message (skipped gates
don't fail the runner).

Note: G8 smoke (`backend/tests/e2e/smoke.py`) hits
`/v1/identity/tenants` without an `Authorization` header, so it expects
a dev-mode deployment (`QZDAP_AUTH_MODE=disabled` or similar). Against a
prod deployment with auth on, G8 will fail with 401 — gate it as ⊘ or
run smoke in a staging ring.

```bash
# local-only gates
uv run python deploy/burn_in.py

# full gates after deployment
QZDAP_STABLE_URL=https://qzdap-stable.example.com \
QZDAP_CANARY_URL=https://qzdap-canary.example.com \
  uv run python deploy/burn_in.py
```

Exit code = number of failed gates (skipped gates don't count).

## Scaling

```bash
docker compose -f deploy/docker-compose.prod.yml --profile prod up -d \
    --scale qzdap-app-stable=3 --scale qzdap-app-canary=1
```
