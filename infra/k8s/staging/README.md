# Staging pre-deploy — Stage A.3-A.8

Sandbox copy of the prod `infra/k8s/` manifests, retargeted to namespace
`qzdap-staging` and the staging Vault KV tree.  All nine ``QZDAP_*_REF`` env
vars resolve through the HashiCorp Vault CSI driver (see
`secret.example.yaml`) — no secret literal ever lands in a k8s Secret.

The prod tree under `infra/k8s/` is untouched; this directory is the
single source of truth for staging runs.

## A.3 · namespace

```bash
kubectl apply -f infra/k8s/staging/namespace.yaml
kubectl get ns qzdap-staging
kubectl label ns qzdap-staging name=qzdap-staging --overwrite
```

## A.4 · SecretProviderClass (csi:)

```bash
cp infra/k8s/staging/secret.example.yaml infra/k8s/staging/secret.yaml
$EDITOR infra/k8s/staging/secret.yaml   # fill vaultAddress + roleName + secretPath
kubectl apply -f infra/k8s/staging/secret.yaml -n qzdap-staging
```

`secret.yaml` is gitignored (top-level `.gitignore` covers
`infra/k8s/*.yaml` after this copy); `secret.example.yaml` stays
committed as the template.

## A.5 · ConfigMap + NetworkPolicy + HPA

```bash
kubectl apply -f infra/k8s/staging/configmap.yaml     # non-sensitive config (vault_mode=csi)
kubectl apply -f infra/k8s/staging/networkpolicy.yaml # default-deny + ingress-nginx allow
kubectl apply -f infra/k8s/staging/hpa.yaml           # stable 3-10, canary 1-3
```

`configmap.yaml` no longer carries the bogus `QZDAP_VAULT_MODE: kms`
(prod had this typo — `kms` is not in the Settings Literal); staging
sets it to `csi` to match the CSI-mounted SecretProviderClass above.

## A.6 · image (local-only — no registry push)

The prod tree would push to `<registry>/qzdap-app:<sha>`; staging skips
the registry entirely and consumes the image straight off the node's
local docker daemon (`imagePullPolicy: IfNotPresent`).

```bash
# Build the prod image locally
cd backend
docker build -t qzdap-app:prod -f infra/docker/Dockerfile.app .

# Transfer to the staging cluster (choose one)
# (a) kind:  kind load docker-image qzdap-app:prod --name <cluster-name>
# (b) k3d:   k3d image import qzdap-app:prod --cluster <cluster-name>
# (c) ssh:   docker save qzdap-app:prod | ssh <node> 'docker load'
# (d) colima + same host: image is already visible to the cluster
```

Deployment.yaml's `image: qzdap-app:prod` + `imagePullPolicy: IfNotPresent`
relies on the image being present on every node.

## A.7 · alembic migration (staging DB)

```bash
kubectl run -n qzdap-staging migrator --rm -it --restart=Never \
  --image=qzdap-app:prod \
  --overrides='{"spec":{"serviceAccountName":"qzdap-app"}}' \
  --command -- alembic upgrade head
# Verify
kubectl run -n qzdap-staging pgcheck --rm -it --restart=Never \
  --image=postgres:16-alpine --env="PGPASSWORD=$STAGING_PG_PASS" \
  --command -- psql -h <staging-pg-host> -U qzdap -d qzdap -c "SELECT * FROM alembic_version;"
```

The staging DB is a copy of the latest prod snapshot (rotated weekly) —
migrations here validate the chain before the prod upgrade.

## A.8 · Prometheus / Grafana provisioning

The prod tree (`infra/prometheus/`, `infra/grafana/`) assumes a cluster
with `monitoring` namespace + Prometheus Operator + Grafana Operator
CRDs already installed.  Staging uses the same manifests; just set
`metadata.namespace: monitoring` and apply:

```bash
kubectl apply -f infra/prometheus/rules/         # 4 alert + 4 recording
kubectl apply -f infra/grafana/dashboards/       # qzdap-overview + qzdap-costs
kubectl apply -f infra/grafana/provisioning/     # datasource + provider
```

If the staging cluster does NOT have the operators, fall back to plain
ConfigMap mounts and wire scrape rules manually into the existing
Prometheus / Grafana instances.

## After A.8 · smoke check (pre-Stage B)

```bash
kubectl get pods -n qzdap-staging
kubectl logs -n qzdap-staging -l app=qzdap --tail=200 | grep -E '(boot|seeded|ready)'
# Expect: boot resolved 9 QZDAP_*_REF env vars
# Expect: /readyz returns 200 (deployment.yaml probes hit 8102)
```