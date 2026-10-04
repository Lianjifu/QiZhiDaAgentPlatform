# Office Packs: Authoring, Signing, Trust Store

P10 / Tier B ships with **office** packs across three kinds — Skill
(A6), Knowledge + Plan (Tier B) — under
[`backend/packs/office/`](../../packs/office/).  This document explains
how they are built, signed, and verified at runtime.

## Pack kinds and canonical fields

Each pack directory contains two files (plus optional
runtime-only files like `entrypoint.py` for skill packs):

```
<pack_id>/
    manifest.json     # K-specific canonical fields, json.dumps(sort_keys=True)
    signature.json    # {"signature": "<b64>", "signer_key_id": "<hex>"}
```

| Kind | Canonical fields | Count |
|---|---|---|
| Skill (A6) | `name, version, description, entrypoint, image, image_digest, parameters_schema, artifact_uri, network_policy, cpu_quota, memory_bytes, timeout_seconds` | 12 |
| Knowledge (Tier B) | `name, version, description, chunking_strategy, embedding_model, asset_ids, refresh_policy, network_policy` | 8 |
| Plan (Tier B) | `name, version, description, plan_dsl, allowed_tenants, schedule, default_timeout_seconds` | 7 |

Any change to a canonical field requires a fresh signature —
[`scripts/pack_sign.py`](../../scripts/pack_sign.py) is the only
supported way to (re)sign.  The CLI is subcommand-driven:

```bash
uv run --frozen python scripts/pack_sign.py skill     <pack_dir> -k <priv.pem>
uv run --frozen python scripts/pack_sign.py knowledge <pack_dir> -k <priv.pem>
uv run --frozen python scripts/pack_sign.py plan      <pack_dir> -k <priv.pem>
```

## Authoring flow

```bash
cd backend

# 1. (one-time) Generate a dev keypair
uv run --frozen python scripts/dev_signing_keygen.py \
    -o .qzdap/skill-trust -p qzdap-office-dev

# 2. (one-time) Seed the trust stores with the public half
uv run --frozen python scripts/pack_trust_seed.py \
    .qzdap/skill-trust/qzdap-office-dev.pub.pem .qzdap/skill-trust
mkdir -p .qzdap/knowledge-trust .qzdap/plan-trust
cp .qzdap/skill-trust/<key_id>.pub.pem .qzdap/knowledge-trust/
cp .qzdap/skill-trust/<key_id>.pub.pem .qzdap/plan-trust/

# 3. (per-pack change) Sign every pack of the relevant kind
for d in packs/office/skills/*/;     do uv run --frozen python scripts/pack_sign.py skill     "$d" -k .qzdap/skill-trust/qzdap-office-dev.priv.pem; done
for d in packs/office/knowledge/*/;  do uv run --frozen python scripts/pack_sign.py knowledge "$d" -k .qzdap/skill-trust/qzdap-office-dev.priv.pem; done
for d in packs/office/plans/*/;      do uv run --frozen python scripts/pack_sign.py plan      "$d" -k .qzdap/skill-trust/qzdap-office-dev.priv.pem; done

# 4. (one-time) Migration + boot
alembic upgrade head   # picks up 0016_skill_signing, 0018_knowledge_signing, 0019_plan_signing

QZDAP_SKILL_SIGNING_MODE=local     QZDAP_SKILL_TRUST_DIR=./.qzdap/skill-trust \
QZDAP_KNOWLEDGE_SIGNING_MODE=local QZDAP_KNOWLEDGE_TRUST_DIR=./.qzdap/knowledge-trust \
QZDAP_PLAN_SIGNING_MODE=local      QZDAP_PLAN_TRUST_DIR=./.qzdap/plan-trust \
QZDAP_PLATFORM_SEED_OFFICE_SKILL_PACKS=true     QZDAP_PLATFORM_OFFICE_SKILL_PACKS_ROOT=$(pwd)/packs/office/skills \
QZDAP_PLATFORM_SEED_OFFICE_KNOWLEDGE_PACKS=true QZDAP_PLATFORM_OFFICE_KNOWLEDGE_PACKS_ROOT=$(pwd)/packs/office/knowledge \
QZDAP_PLATFORM_SEED_OFFICE_PLAN_PACKS=true      QZDAP_PLATFORM_OFFICE_PLAN_PACKS_ROOT=$(pwd)/packs/office/plans \
    uv run --frozen python -m qzdap.composition.main
# Expected logs:
#   "seeded 4 office skill packs (vetter=local, ...)"
#   "seeded 2 office knowledge packs (vetter=local, ...)"
#   "seeded 2 office plan packs (vetter=local, ...)"
```

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `QZDAP_SKILL_SIGNING_MODE` | `disabled` | `disabled` / `local` / `vault`. `vault` = `VaultBackedSkillVetter` (Tier B). |
| `QZDAP_SKILL_TRUST_DIR` | `./.qzdap/skill-trust` | Local trust dir for `local` mode. |
| `QZDAP_VAULT_SKILL_TRUST_REF` | `vault:secret/data/qzdap/skill-trust/keys` | KV v2 ref pulled by `vault` mode (TTL = `QZDAP_VAULT_SKILL_TRUST_REFRESH_SECONDS`). |
| `QZDAP_VAULT_SKILL_TRUST_REFRESH_SECONDS` | `300` | TTL for vault-cached keys. |
| `QZDAP_VAULT_SKILL_TRUST_MIN_KEYS` | `1` | Boot fails if Vault returns fewer than this many keys. |
| `QZDAP_KNOWLEDGE_SIGNING_MODE` | `disabled` | `disabled` or `local`. (vault-mode for knowledge is out of scope.) |
| `QZDAP_KNOWLEDGE_TRUST_DIR` | `./.qzdap/knowledge-trust` | Local trust dir for `local` mode. |
| `QZDAP_PLAN_SIGNING_MODE` | `disabled` | `disabled` or `local`. |
| `QZDAP_PLAN_TRUST_DIR` | `./.qzdap/plan-trust` | Local trust dir for `local` mode. |
| `QZDAP_PLATFORM_SEED_OFFICE_SKILL_PACKS` | `true` | If `true`, lifespan walker registers every pack in `QZDAP_PLATFORM_OFFICE_SKILL_PACKS_ROOT`. |
| `QZDAP_PLATFORM_OFFICE_SKILL_PACKS_ROOT` | `packs/office/skills` | Pack root for the skill walker. |
| `QZDAP_PLATFORM_SEED_OFFICE_KNOWLEDGE_PACKS` | `true` | Enable / disable the knowledge walker. |
| `QZDAP_PLATFORM_OFFICE_KNOWLEDGE_PACKS_ROOT` | `packs/office/knowledge` | Pack root for the knowledge walker. |
| `QZDAP_PLATFORM_SEED_OFFICE_PLAN_PACKS` | `true` | Enable / disable the plan walker. |
| `QZDAP_PLATFORM_OFFICE_PLAN_PACKS_ROOT` | `packs/office/plans` | Pack root for the plan walker. |

## Trust store mechanics

Each `LocalTrustStore*Vetter` scans `<trust_dir>/*.pub.pem` **once at
construction** and builds an in-memory `{key_id: Ed25519PublicKey}`
cache.  Empty / missing directories fail boot — there is no silent
`NoOp*Vetter` fallback.  `key_id` is
`sha256(pem_bytes).hexdigest()`.

`VaultBackedSkillVetter` (Tier B, Skill only) re-reads the configured
KV v2 ref on first call and then refreshes every
`QZDAP_VAULT_SKILL_TRUST_REFRESH_SECONDS`.  Rotation latency is bounded
by that TTL.  First-call failure (Vault unreachable, ref denied,
returned key count below `QZDAP_VAULT_SKILL_TRUST_MIN_KEYS`) maps to
`SkillSignerUntrusted` so the platform boots closed.

## Runtime gate

The matching `Create*UseCase` runs the vetter **before** any
persistence write:

| Use case | Unsigned | Untrusted signer |
|---|---|---|
| `RegisterSkillUseCase` / `UpdateSkillUseCase` | `SkillSignatureInvalid` (HTTP 400) | `SkillSignerUntrusted` (HTTP 400) |
| `CreateKnowledgePackageUseCase` | `KnowledgeSignatureInvalid` (HTTP 400) | `KnowledgeSignerUntrusted` (HTTP 400) |
| `CreatePlanUseCase` | `PlanSignatureInvalid` (HTTP 400) | `PlanSignerUntrusted` (HTTP 400) |

`assert_image_digest_matches` is wired but not yet invoked on Skill
packs — the OCI registry integration is a follow-up.  Documented
inline with `# TODO A6` markers.

## Shared signing library

The `qzdap_pack_signing` workspace lib
([`backend/libs/pack_signing/`](../../libs/pack_signing/)) owns the
generic Ed25519 + canonical-JSON plumbing (`canonical_payload`,
`sign_payload`, `verify_signature`, `public_key_id`,
`scan_trust_dir`).  Per-module files
(`modules/skill/.../signing.py`,
`modules/knowledge/.../signing.py`,
`modules/orchestration/.../signing.py`) are thin adapters that pin
the kind-specific canonical fields.

## Testing

```bash
cd backend

# Signing + wire-up across all three pack kinds (Tier B: 133 cases)
uv run --frozen pytest \
    libs/pack_signing/tests/ \
    modules/skill/tests/unit/test_skill_signing_wireup.py \
    modules/skill/tests/unit/test_skill_signing_and_vetter.py \
    modules/skill/tests/unit/test_vault_vetter.py \
    modules/skill/tests/unit/test_pack_sign.py \
    modules/skill/tests/unit/test_pack_loader.py \
    modules/knowledge/tests/unit/test_knowledge_signing_and_vetter.py \
    modules/knowledge/tests/unit/test_knowledge_signing_wireup.py \
    modules/orchestration/tests/unit/test_plan_signing_and_vetter.py \
    modules/orchestration/tests/unit/test_plan_signing_wireup.py \
    --no-cov -p no:cacheprovider
```

## Out of scope (separate tickets)

- Workflow pack signing — Workflow = Plan runtime form (duplicate)
- Scenario primitive + packs — needs a fresh design
- Real OCI registry integration for `assert_image_digest_matches`
- Per-tenant pack overrides (workspace-level trust stores)
- `VaultBackedKnowledgeVetter` / `VaultBackedPlanVetter` (symmetric addition)