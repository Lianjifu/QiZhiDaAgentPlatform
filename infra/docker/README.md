# Enterprise-Agent-OS — prod runtime image

Multi-stage Docker build for the FastAPI composition root. Produces a
production image with gunicorn (uvicorn workers) running on port 8102.

## Build

```bash
# from repo root
docker build -f infra/docker/Dockerfile.app -t qzdap-app:prod .
```

## Run (single instance)

```bash
docker run --rm -p 8102:8102 \
    -e QZDAP_RING=stable \
    -e QZDAP_DATABASE_URL_SECRET_REF=vault://prod/qzdap/database_url \
    -e QZDAP_REDIS_URL_SECRET_REF=vault://prod/qzdap/redis_url \
    qzdap-app:prod
```

## Configuration

All runtime config comes via environment variables. Critical ones:

| Env | Purpose | Default |
|---|---|---|
| `QZDAP_ENV` | `production` for prod | `production` |
| `QZDAP_RING` | `stable` or `canary` (P10 gray) | `stable` |
| `QZDAP_GUNICORN_WORKERS` | worker count | 4 |
| `QZDAP_GUNICORN_THREADS` | threads per worker | 2 |
| `QZDAP_GUNICORN_TIMEOUT` | request timeout (s) | 60 |
| `QZDAP_GUNICORN_BIND` | bind address | `0.0.0.0:8102` |

## Health checks

- `/livez` — liveness (process alive)
- `/readyz` — readiness (DB + Redis reachable)
- `/healthz` — full health (DB + Redis + vector store)

All three are wired to the existing `qzdap_http.health` module.

## Production tuning

The image uses `tini` as PID 1 for proper signal forwarding (SIGTERM
from `kubectl delete pod` triggers graceful shutdown). `proxy-protocol`
is enabled so ingress can forward client IP without losing
`X-Forwarded-For` semantics.
