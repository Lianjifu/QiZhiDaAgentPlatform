# Enterprise-Agent-OS — k8s manifests

Single-namespace (`qzdap-prod`) deployment of the FastAPI composition root.
Two pools share the same ConfigMap and Secret, differ only by the
`QZDAP_RING` env. A canary ingress splits traffic based on the
`X-QZDAP-Ring: canary` header.

## Files

| File | Purpose |
|---|---|
| `namespace.yaml` | `qzdap-prod` ns |
| `configmap.yaml` | non-secret env (QZDAP_ENV, ports, log level, pricing defaults) |
| `secret.example.yaml` | secret **template** — never commit real values |
| `deployment.yaml` | `qzdap-app-stable` (3 replicas) + `qzdap-app-canary` (1 replica) |
| `service.yaml` | ClusterIP for stable + canary + metrics |
| `ingress.yaml` | nginx ingress with header-based canary rule |
| `hpa.yaml` | HPA 3-10 (stable) + 1-3 (canary) |
| `networkpolicy.yaml` | default-deny + allow ingress-nginx + DB egress |

## Apply

```bash
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
# Render real secret from vault (out-of-band):
#   kubectl apply -f rendered-secret.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f ingress.yaml
kubectl apply -f hpa.yaml
kubectl apply -f networkpolicy.yaml
```

## Smoke

```bash
# Stable (no header)
curl -fsS https://qzdap.example.com/livez

# Canary (with header)
curl -fsS -H "X-QZDAP-Ring: canary" https://qzdap.example.com/livez

# Inspect which pod answered
kubectl logs -l ring=stable --tail=5
kubectl logs -l ring=canary --tail=5
```

## Secret handling

The committed `secret.example.yaml` is a template with placeholder
values. In production use one of two pipelines — both are wired in
`libs/vault` so the application code never sees the difference:

| Pipeline | Resolver | When to use |
|---|---|---|
| **External Secrets Operator (ESO)** → k8s `Secret` → env | `HashicorpVaultSecretsResolver` (refs like `vault:secret/data/<path>`) | standard; secret becomes an env var |
| **HashiCorp Vault CSI Provider** → file mount under `/vault/secrets/` | `CSIVaultSecretsResolver` (refs like `csi:<KEY>`) | compliance / FIPS; secret **never** appears as env |

`secret.example.yaml` ships both an ESO-friendly k8s `Secret` template
**and** a `SecretProviderClass` for the CSI path.  The matching
`deploy/env.prod.example` uses `vault:` refs for non-sensitive items
and `csi:` refs for material that must never hit the process env.

`gitleaks` (configured in `.gitleaks.toml`) catches accidental commits
of real secret values.

## Rollout

```bash
# Rolling restart stable
kubectl rollout restart deploy/qzdap-app-stable -n qzdap-prod
kubectl rollout status  deploy/qzdap-app-stable -n qzdap-prod

# Roll back
kubectl rollout undo deploy/qzdap-app-stable -n qzdap-prod
```
