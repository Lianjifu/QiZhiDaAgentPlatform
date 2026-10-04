"""Burn-in gate runner — orchestrates G2/G3/G5/G6/G7/G8.

Designed to run against a fully-deployed 企智搭 · 智能体平台 pair
(stable + canary). When QZDAP_STABLE_URL / QZDAP_CANARY_URL are unset,
only the locally-runnable gates fire (G5 secrets, G6 promtool,
G7 grafana JSON validation).

Usage::

    # local-only gates (no URLs needed)
    uv run python deploy/burn_in.py

    # full gates (requires deployed stable + canary; G3 also needs
    # QZDAP_BENCH_TOKEN/TENANT/WORKSPACE/AGENT_ID — see g3_bench)
    QZDAP_STABLE_URL=https://qzdap-stable.example.com \
    QZDAP_CANARY_URL=https://qzdap-canary.example.com \
    uv run python deploy/burn_in.py

Exit code is the number of gates that failed (0 = all green).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
GITLEAKS = shutil.which("gitleaks")
PROMTOOL = shutil.which("promtool")


def _run(
    cmd: Sequence[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    p = subprocess.run(
        list(cmd),
        cwd=cwd or REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return p.returncode, p.stdout, p.stderr


# ── G5 secrets ───────────────────────────────────────────────────────────
def g5_secret_scan() -> tuple[bool, str]:
    if GITLEAKS is None:
        return False, "gitleaks binary not installed (brew install gitleaks)"
    rc, out, err = _run(
        ["gitleaks", "detect", "--source", ".", "--no-banner", "--redact"],
        cwd=REPO_ROOT,
    )
    msg = out.strip().splitlines()[-3:] if out else err.strip().splitlines()[-3:]
    return rc == 0, "\n".join(msg)


# ── G6 Prometheus rules ───────────────────────────────────────────────────
def g6_prom_rules() -> tuple[bool, str]:
    if PROMTOOL is None:
        return False, "promtool binary not installed (brew install prometheus)"
    rules_dir = REPO_ROOT / "infra" / "prometheus" / "rules"
    if not rules_dir.is_dir():
        return False, f"rules dir missing: {rules_dir}"
    rule_files = sorted(str(p) for p in rules_dir.glob("*.yaml"))
    if not rule_files:
        return False, "no rule files found"
    rc, out, err = _run(["promtool", "check", "rules", *rule_files])
    msg = (out + err).strip().splitlines()[-6:]
    if rc != 0:
        return False, "\n".join(msg)
    # Also lint the prometheus config
    cfg = REPO_ROOT / "infra" / "prometheus" / "prometheus.example.yml"
    rc2, out2, err2 = _run(["promtool", "check", "config", str(cfg)])
    if rc2 != 0:
        return False, (out2 + err2).strip()
    msg2 = msg + [f"config: {cfg.name} VALID"]
    return True, "\n".join(msg2)


# ── G7 Grafana dashboards ────────────────────────────────────────────────
def g7_grafana_loads(stable_url: str | None) -> tuple[bool, str]:
    jsons = sorted((REPO_ROOT / "infra" / "grafana" / "dashboards").glob("*.json"))
    if not jsons:
        return False, "no dashboards found under infra/grafana/dashboards/"
    msgs: list[str] = []
    for j in jsons:
        try:
            payload = json.loads(j.read_text())
        except json.JSONDecodeError as e:
            return False, f"{j.name}: INVALID JSON ({e})"
        title = payload.get("title", "<untitled>")
        panels = len(payload.get("panels", []))
        msgs.append(f"  ✓ {j.name} title={title!r} panels={panels}")

    if not stable_url:
        return True, (
            "JSON schema OK (skipping live Grafana load — "
            "set QZDAP_STABLE_URL to curl /api/dashboards/uid/<id>):\n"
            + "\n".join(msgs)
        )
    # Live load: /api/dashboards/uid/qzdap-overview  + /qzdap-costs
    import httpx  # local import so the rest of the script can run without it

    all_ok = True
    msgs.append("---")
    for uid in ("qzdap-overview", "qzdap-costs"):
        url = f"{stable_url.rstrip('/')}/api/dashboards/uid/{uid}"
        try:
            r = httpx.get(url, timeout=10.0)
        except httpx.HTTPError as e:
            msgs.append(f"  ✗ {uid}: transport error {e}")
            all_ok = False
            continue
        if r.status_code == 200:
            msgs.append(f"  ✓ {uid}: 200")
        else:
            msgs.append(f"  ✗ {uid}: HTTP {r.status_code}")
            all_ok = False
    return all_ok, "\n".join(msgs)


# ── G2 /readyz on stable + canary ────────────────────────────────────────
def g2_readyz(stable_url: str | None, canary_url: str | None) -> tuple[bool, str]:
    if not stable_url or not canary_url:
        return False, (
            "skipping — set QZDAP_STABLE_URL + QZDAP_CANARY_URL to enable "
            "dual-instance /readyz check"
        )
    import httpx

    msgs: list[str] = []
    all_ok = True
    for label, base in (("stable", stable_url), ("canary", canary_url)):
        url = f"{base.rstrip('/')}/readyz"
        t0 = time.monotonic()
        try:
            r = httpx.get(url, timeout=10.0)
        except httpx.HTTPError as e:
            msgs.append(f"  ✗ {label}: transport error {e}")
            all_ok = False
            continue
        dt = (time.monotonic() - t0) * 1000
        body = r.text[:200]
        if r.status_code == 200:
            msgs.append(f"  ✓ {label}: 200 ({dt:.0f} ms) body={body}")
        else:
            msgs.append(f"  ✗ {label}: HTTP {r.status_code} body={body}")
            all_ok = False
    return all_ok, "\n".join(msgs)


# ── G8 smoke happy path ─────────────────────────────────────────────────
def g8_smoke(stable_url: str | None, canary_url: str | None) -> tuple[bool, str]:
    if not stable_url and not canary_url:
        return False, (
            "skipping — set QZDAP_STABLE_URL and/or QZDAP_CANARY_URL to run "
            "the happy-path smoke. Script: tests/e2e/smoke.py (uses "
            "QZDAP_SMOKE_BASE_URL; no auth required — smoke hits /healthz + "
            "/v1/identity/tenants, so it expects an open / dev-mode "
            "deployment, NOT prod with auth on)."
        )
    script = REPO_ROOT / "backend" / "tests" / "e2e" / "smoke.py"
    if not script.is_file():
        return False, f"smoke script missing: {script}"
    msgs: list[str] = []
    all_ok = True
    for label, base in (("stable", stable_url), ("canary", canary_url)):
        if not base:
            continue
        env = {**os.environ, "QZDAP_SMOKE_BASE_URL": base}
        rc, out, err = _run(
            ["uv", "run", "--frozen", "python", str(script)],
            cwd=REPO_ROOT / "backend",
            env=env,
        )
        msgs.append(f"--- {label} ({base}) rc={rc} ---")
        msgs.append((out or err).strip().splitlines()[-12:].__str__().strip("[]'"))
        if rc != 0:
            all_ok = False
    return all_ok, "\n".join(msgs)


# ── G3 bench P95 ────────────────────────────────────────────────────────
def g3_bench(stable_url: str | None) -> tuple[bool, str]:
    if not stable_url:
        return False, (
            "skipping — set QZDAP_STABLE_URL to run "
            "backend/tests/perf/bench_turn_latency.py. Threshold P95 ≤ 10s "
            "per doc/prelaunch-checklist.md G3."
        )
    # The bench script requires tenant-scoped IDs that an operator must
    # seed once; if any are missing we skip rather than fabricate.
    bench_env_required = ("QZDAP_BENCH_TOKEN", "QZDAP_BENCH_TENANT",
                          "QZDAP_BENCH_WORKSPACE", "QZDAP_BENCH_AGENT_ID")
    missing = [n for n in bench_env_required if not os.environ.get(n)]
    if missing:
        return False, (
            "skipping — bench needs tenant-scoped env vars to construct "
            "an authenticated turn; set " + ", ".join(missing) +
            " (or run `make smoke` first to bootstrap a tenant + workspace)."
        )
    script = REPO_ROOT / "backend" / "tests" / "perf" / "bench_turn_latency.py"
    if not script.is_file():
        return False, f"bench script missing: {script}"
    env = {**os.environ, "QZDAP_BENCH_URL": stable_url}
    rc, out, err = _run(
        ["uv", "run", "--frozen", "python", str(script)],
        cwd=REPO_ROOT / "backend",
        env=env,
    )
    msgs = (out or err).strip().splitlines()[-15:]
    return rc == 0, "\n".join(msgs)


# ── Runner ──────────────────────────────────────────────────────────────
def main() -> int:
    stable = os.environ.get("QZDAP_STABLE_URL")
    canary = os.environ.get("QZDAP_CANARY_URL")
    failures = 0
    skipped = 0

    print("=== Burn-in runner — gates G2/G3/G5/G6/G7/G8 ===\n")

    sections = [
        ("G5 secret-scan (gitleaks)", g5_secret_scan),
        ("G6 prometheus rules + config (promtool)", g6_prom_rules),
        ("G7 grafana dashboards JSON + live load", lambda: g7_grafana_loads(stable)),
        ("G2 /readyz 200 (stable + canary)", lambda: g2_readyz(stable, canary)),
        ("G3 bench P95 ≤ 10s", lambda: g3_bench(stable)),
        ("G8 smoke happy path (stable + canary)", lambda: g8_smoke(stable, canary)),
    ]
    for label, fn in sections:
        ok, msg = fn()
        msg_lc = msg.lower()
        if ok:
            mark = "✓"
        elif msg_lc.startswith("skipping"):
            mark = "⊘"
            skipped += 1
        else:
            mark = "✗"
            failures += 1
        print(f"[{mark}] {label}\n{msg}\n")
    print(
        f"=== {failures} failed, {skipped} skipped "
        f"(set QZDAP_STABLE_URL + QZDAP_CANARY_URL to run remote gates) ==="
    )
    return failures


if __name__ == "__main__":
    sys.exit(main())